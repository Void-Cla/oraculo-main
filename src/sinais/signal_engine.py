from __future__ import annotations

import os
import time
from typing import Any

from src.calculos.gerador_features import calcular_features_1m
from src.intelligence.market_analyst import VotoIA
from src.meta_strategy.meta_controller import gerar_sinal_meta
from src.meta_strategy.regime_detector import detectar_regime
from src.modelagem.preditor import preditor_end_to_end
from src.observabilidade.logger import get_logger
from src.probabilidade.probabilistic_engine import ProbabilisticTradeEngine
from src.sinais.consenso import consolidar_decisao

LOG = get_logger("signal_engine")


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def _ts_ms(valor: int | float) -> int:
    numero = int(valor)
    if numero <= 0:
        return int(time.time() * 1000)
    if numero < 10_000_000_000:
        numero *= 1000
    if numero < 946_684_800_000:
        return int(time.time() * 1000)
    return numero


def _sentimento_medio_noticias(noticias: list[Any] | None) -> float:
    if not noticias:
        return 0.0
    scores: list[float] = []
    for item in noticias:
        if isinstance(item, dict) and item.get("sentimento") is not None:
            try:
                scores.append(float(item["sentimento"]))
            except (TypeError, ValueError):
                continue
    if not scores:
        return 0.0
    return _clamp(sum(scores) / len(scores), -1.0, 1.0)


def _normalizar_klines(klines: list[Any], limite: int = 40) -> list[dict[str, float]]:
    norm = []
    for item in klines[-limite:]:
        if isinstance(item, dict):
            norm.append(
                {
                    "ts": float(item["ts"]),
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item["volume"]),
                }
            )
        else:
            norm.append(
                {
                    "ts": float(item[0]),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                }
            )
    return norm


def _contexto_mercado(klines: list[Any]) -> dict[str, Any]:
    norm = _normalizar_klines(klines, limite=20)
    highs = [float(item["high"]) for item in norm]
    lows = [float(item["low"]) for item in norm]
    closes = [float(item["close"]) for item in norm]
    return {
        "max_high_20": max(highs) if highs else 0.0,
        "min_low_20": min(lows) if lows else 0.0,
        "close_ultimo": closes[-1] if closes else 0.0,
    }


# Limiar de retorno p/ classificar janela como UP/DOWN em vez de FLAT: 15 bps (0.0015),
# ≈1.5 desvio-padrão do retorno típico de 1 minuto do BTC. Antes, 3 bps (0.0003) fazia
# ~85% das janelas serem classificadas UP ou DOWN (raramente FLAT), saturando o score
# direcional quase sempre e tornando a confirmação multi-timeframe pouco discriminativa.
LIMIAR_RETORNO_JANELA_PADRAO: float = 0.0015


def _direcao_janela(closes: list[float], passos: int, limiar: float = LIMIAR_RETORNO_JANELA_PADRAO) -> tuple[str, float]:
    if len(closes) <= passos:
        passos = max(1, len(closes) - 1)
    if passos <= 0:
        return ("FLAT", 0.0)
    atual = float(closes[-1])
    anterior = float(closes[-1 - passos])
    if anterior <= 0.0:
        return ("FLAT", 0.0)
    retorno = (atual / anterior) - 1.0
    if retorno >= limiar:
        return ("UP", retorno)
    if retorno <= -limiar:
        return ("DOWN", retorno)
    return ("FLAT", retorno)


def _confirmacao_multi_timeframe(
    klines: list[Any],
    limiar_confirmacao: int,
    limiar_retorno: float = LIMIAR_RETORNO_JANELA_PADRAO,
) -> dict[str, Any]:
    norm = _normalizar_klines(klines, limite=20)
    closes = [float(item["close"]) for item in norm]
    janelas = {1: "1m", 5: "5m", 10: "10m", 15: "15m"}
    tendencias: dict[str, dict[str, float | str]] = {}
    score_buy = 0
    score_sell = 0
    retornos: list[float] = []
    for passos, nome in janelas.items():
        direcao, retorno = _direcao_janela(closes, passos, limiar=limiar_retorno)
        tendencias[nome] = {"direcao": direcao, "retorno": retorno}
        retornos.append(retorno)
        if direcao == "UP":
            score_buy += 1
        elif direcao == "DOWN":
            score_sell += 1

    score_direcional = (score_buy - score_sell) / max(len(janelas), 1)
    permitir_buy = score_buy >= limiar_confirmacao
    permitir_sell = score_sell >= limiar_confirmacao
    acao_dominante = "HOLD"
    if score_buy > score_sell:
        acao_dominante = "BUY"
    elif score_sell > score_buy:
        acao_dominante = "SELL"

    return {
        "janelas": tendencias,
        "score_buy": score_buy,
        "score_sell": score_sell,
        "score_direcional": _clamp(score_direcional, -1.0, 1.0),
        "permitir_buy": permitir_buy,
        "permitir_sell": permitir_sell,
        "confirmado": bool(permitir_buy or permitir_sell),
        "acao_dominante": acao_dominante,
        "retorno_medio": (sum(retornos) / len(retornos)) if retornos else 0.0,
    }


def _janela_decisao(ts_referencia: int, janela_minutos: int) -> dict[str, Any]:
    janela_min = max(1, int(janela_minutos or 1))
    ts_base = _ts_ms(ts_referencia)
    janela_ms = janela_min * 60 * 1000
    indice = ts_base // janela_ms
    inicio_atual = indice * janela_ms
    proxima_execucao = inicio_atual if ts_base == inicio_atual else (inicio_atual + janela_ms)
    return {
        "janela_minutos": janela_min,
        "ts_referencia": ts_base,
        "executar_apos_ts": int(proxima_execucao),
        "atraso_execucao_ms": int(max(0, proxima_execucao - ts_base)),
        "janela_aberta_agora": ts_base == inicio_atual,
    }


async def gerar_sinal_orquestrado(
    simbolo: str,
    klines: list[Any],
    livro_topo: dict[str, Any] | None = None,
    noticias: list[Any] | None = None,
    saldo: dict[str, Any] | None = None,
    *,
    force_allow_for_testnet: bool | None = None,
    ajustes_sinal: dict[str, Any] | None = None,
    analista_ia: Any | None = None,
) -> dict[str, Any]:
    """Orquestra o pipeline completo de geração de sinal (features → regime → estratégias →
    previsão ML → consenso ponderado → EV).

    ASSÍNCRONA desde 2026-07-01: o voto direcional de peso igual da IA (`AnalistaMercadoIA`,
    ver `src/intelligence/market_analyst.py`) exige uma chamada de rede. `analista_ia` é
    OPT-IN — se `None` (padrão, comportamento idêntico ao anterior), a fonte "ia_gemini" do
    consenso usa `VotoIA()` default (acao=HOLD, confianca=0.0), que já colapsa a ~zero na
    média ponderada (ver `consenso.py`). Isso preserva o comportamento pré-existente quando o
    caller não passa um analista (ex.: sem GEMINI_API_KEY configurada).
    """
    ajustes_sinal = ajustes_sinal or {}
    is_performance_mode = bool(ajustes_sinal.get("performance_mode", False))
    sent_score = _sentimento_medio_noticias(noticias)
    features = calcular_features_1m(klines, livro_topo=livro_topo, sent_score=sent_score)
    regime_info = detectar_regime(features)
    contexto = _contexto_mercado(klines)
    # Default 3 de 4 janelas temporais (1m/5m/10m/15m) alinhadas p/ confirmar.
    # Em modo performance, reduzimos para 1 de 4 para execução imediata.
    LIMIAR_CONFIRMACAO_PADRAO = 1 if is_performance_mode else 3
    limiar_confirmacao = int(ajustes_sinal.get("signal_confirm_threshold", LIMIAR_CONFIRMACAO_PADRAO))
    # Limiar de retorno por janela parametrizável via ajustes (`signal_janela_limiar_pct`):
    # o modo exploração (testnet-only) relaxa p/ 0.08% — em LOW_VOL, o padrão de 0.15%
    # mantinha o bot em HOLD por horas mesmo em exploração. Clamp inferior evita 0/negativo
    # (que classificaria toda janela como UP e anularia a confirmação).
    limiar_janela = max(
        0.0001,
        float(ajustes_sinal.get("signal_janela_limiar_pct", LIMIAR_RETORNO_JANELA_PADRAO) or LIMIAR_RETORNO_JANELA_PADRAO),
    )
    confirmacao = _confirmacao_multi_timeframe(klines, limiar_confirmacao, limiar_retorno=limiar_janela)
    previsao = preditor_end_to_end(
        simbolo=simbolo,
        features=features,
        noticias=noticias,
        saldo=saldo,
        ajustes_sinal=ajustes_sinal,
    )

    llm_info = dict(previsao["decisao"].get("llm") or {})
    score_ml = float(previsao["decisao"].get("score_numerico", 0.0) or 0.0)
    score_llm = float(llm_info.get("score_direcional", llm_info.get("sentimento_noticias", 0.0)) or 0.0)

    contexto["ml_score"] = score_ml
    contexto["sentimento_noticias"] = float(llm_info.get("sentimento_noticias", sent_score) or sent_score)
    contexto["predicao_preco"] = float(previsao["y_cal"])
    contexto["score_confirmacao"] = float(confirmacao["score_direcional"])

    sinal = gerar_sinal_meta(simbolo, regime_info, features, contexto)
    close = max(float(features.get("close", 0.0) or 0.0), 1e-9)
    variacao_prevista = float(previsao["decisao"].get("variacao_prevista", 0.0) or 0.0)
    movimento_previsto = abs(variacao_prevista)
    spread_rel = abs(float(features.get("spread_rel", 0.0) or 0.0))
    taxa_trade = float(ajustes_sinal.get("signal_trade_fee_pct", 0.001))
    slippage = float(ajustes_sinal.get("signal_slippage_pct", 0.0005))
    lucro_liquido_min = float(ajustes_sinal.get("signal_min_net_profit_pct", 0.0005))
    signal_min_ev = float(ajustes_sinal.get("signal_min_ev", 0.0001))
    signal_min_prob = float(ajustes_sinal.get("signal_min_prob", 0.55))
    signal_prob_temperature = float(ajustes_sinal.get("signal_prob_temperature", 1.0))
    # Escala do logit no calibrador de probabilidade. Com scale=10, uma predição típica
    # de 0.5% de movimento (raw=0.005) gera logit=0.05, sigmoid≈0.512 — o modelo ML quase
    # não move a probabilidade calibrada para longe de 0.5, sendo dominado pelo ajuste
    # externo (confirmação/sentimento). Com scale=200, a mesma predição gera logit=1.0,
    # sigmoid≈0.73 — o modelo passa a ter peso real na decisão em vez de saturar/ficar mudo.
    SIGNAL_PROB_SCALE_PADRAO = 200.0
    signal_prob_scale = float(ajustes_sinal.get("signal_prob_scale", SIGNAL_PROB_SCALE_PADRAO))

    pte = ProbabilisticTradeEngine(
        fee=taxa_trade,
        slippage=slippage,
        min_ev=signal_min_ev,
        min_prob=signal_min_prob,
        temperature=signal_prob_temperature,
        scale=signal_prob_scale,
    )
    force_allow = bool(force_allow_for_testnet is True)
    if force_allow:
        lucro_liquido_min = -1.0

    pte_resultado = pte.evaluate_trade(
        raw_prediction=((float(previsao["y_cal"]) - close) / close),
        take_profit=float(sinal.get("take_profit_pct", 0.0) or 0.0),
        stop_loss=float(sinal.get("stop_loss_pct", 0.0) or 0.0),
        spread=spread_rel,
        score_confirmacao=float(confirmacao["score_direcional"]),
        sentimento_noticias=score_llm,
    )
    pte_resultado["llm"] = float(llm_info.get("score_conf", 0.0) or 0.0)
    pte_resultado["llm_score_direcional"] = score_llm
    ev_buy = float(pte_resultado.get("ev_buy", 0.0) or 0.0)
    ev_sell = float(pte_resultado.get("ev_sell", 0.0) or 0.0)
    custos_totais = float(pte_resultado.get("custos_totais_pct", 0.0) or 0.0)
    if sinal["acao"] == "BUY":
        lucro_liquido_esperado = ev_buy
    elif sinal["acao"] == "SELL":
        lucro_liquido_esperado = ev_sell
    else:
        # HOLD não tem EV acionável — nenhuma posição será aberta. Reportar o melhor EV
        # teórico (max(ev_buy, ev_sell)) infla métricas de diagnóstico e distorce backtest,
        # já que o valor nunca corresponde a um trade real executado.
        lucro_liquido_esperado = 0.0

    # Voto direcional de peso igual da IA (opt-in) — resolvido ANTES de `consolidar_decisao`
    # (que é síncrona e pura de propósito, ver docstring de `consolidar_decisao`). Sem
    # `analista_ia` injetado (padrão quando não há GEMINI_API_KEY), usa o `VotoIA()` default
    # — HOLD/confianca=0.0 — que colapsa a ~zero na média ponderada da fonte "ia_gemini".
    #
    # GATE DE MOMENTO CRÍTICO (DA-30, 2026-07-01): a IA só é consultada quando o motor mecânico
    # JÁ calculou EV líquido positivo (ev_buy ou ev_sell acima do mesmo piso `signal_min_ev`
    # usado pelo gate de EV mecânico) para este símbolo. Em ciclo HOLD sem candidato — a
    # maioria dos ciclos, por desenho, já que a maior parte do tempo não há edge — a IA NEM É
    # CHAMADA. Isto ataca a causa raiz do 429/cooldown observado em produção: antes, TODO ciclo
    # de TODO símbolo gastava 1 chamada de IA independente de haver oportunidade real; agora só
    # os ciclos onde o "trabalho bruto" mecânico já encontrou algo acionável gastam cota. O voto
    # da IA nunca decide sozinho (gate de EV segue intacto em `consolidar_decisao`/EV gate
    # abaixo) — este filtro só evita PERGUNTAR quando a resposta não teria efeito prático.
    ev_mecanico_acionavel = max(ev_buy, ev_sell) > signal_min_ev
    voto_ia: VotoIA = VotoIA()
    if analista_ia is not None and ev_mecanico_acionavel:
        saldo_num = float((saldo or {}).get("saldo_total", 0.0) or 0.0)
        try:
            voto_ia = await analista_ia.avaliar_direcional(
                simbolo=simbolo,
                sinal_mecanico=sinal,
                saldo=saldo_num,
                noticias=noticias,
            )
        except Exception as exc:  # fail-safe: a IA jamais derruba a geração do sinal mecânico
            LOG.error("falha_analista_ia_fail_safe", extra={"simbolo": simbolo, "erro": str(exc)})
            voto_ia = VotoIA()

    consenso = consolidar_decisao(
        sinal_base=sinal,
        score_modelo=score_ml,
        score_llm=score_llm,
        confirmacao=confirmacao,
        probabilidade_trade=pte_resultado,
        lucro_liquido_esperado=lucro_liquido_esperado,
        lucro_liquido_minimo=lucro_liquido_min,
        force_allow=force_allow,
        score_direcional_ia=voto_ia.score_direcional,
        confianca_ia=voto_ia.confianca,
    )
    sinal["acao"] = consenso["acao"]
    sinal["confianca"] = consenso["confianca"]
    sinal["motivo"] = f"{sinal.get('motivo', 'sinal_orquestrado')}; {consenso['motivo']}"
    sinal["voto_ia"] = voto_ia.to_dict()

    sinal["ts"] = int(time.time() * 1000)
    sinal["confirmacao_multi_timeframe"] = confirmacao
    sinal["probabilidade_trade"] = pte_resultado
    sinal["movimento_previsto_pct"] = movimento_previsto
    sinal["custos_estimados_pct"] = custos_totais
    sinal["lucro_liquido_esperado_pct"] = lucro_liquido_esperado
    janela_minutos = int(ajustes_sinal.get("signal_decision_window_minutes", 5))
    sinal["janela_decisao"] = _janela_decisao(int(features.get("ts", sinal["ts"]) or sinal["ts"]), janela_minutos)
    sinal["features"] = features
    sinal["previsao_modelo"] = {
        "y_hat": previsao["y_hat"],
        "y_cal": previsao["y_cal"],
        "p_conf": previsao["p_conf"],
        "direcao_modelo": previsao["direcao"],
        "score_numerico": score_ml,
        "score_llm": score_llm,
        "sentimento_noticias": float(llm_info.get("sentimento_noticias", sent_score) or sent_score),
    }
    sinal["consenso"] = {
        "acao_consenso": consenso["acao_consenso"],
        "score_total": consenso["score_total"],
        "fontes_alinhadas": consenso["fontes_alinhadas"],
        "fontes_contrarias": consenso["fontes_contrarias"],
        "fontes": consenso["fontes"],
    }
    return sinal
