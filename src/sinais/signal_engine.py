from __future__ import annotations

import os
import time
from typing import Any

from src.calculos.gerador_features import calcular_features_1m
from src.meta_strategy.meta_controller import gerar_sinal_meta
from src.meta_strategy.regime_detector import detectar_regime
from src.modelagem.preditor import preditor_end_to_end
from src.probabilidade.probabilistic_engine import ProbabilisticTradeEngine
from src.sinais.consenso import consolidar_decisao


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


def _direcao_janela(closes: list[float], passos: int, limiar: float = 0.0003) -> tuple[str, float]:
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


def _confirmacao_multi_timeframe(klines: list[Any], limiar_confirmacao: int) -> dict[str, Any]:
    norm = _normalizar_klines(klines, limite=20)
    closes = [float(item["close"]) for item in norm]
    janelas = {1: "1m", 5: "5m", 10: "10m", 15: "15m"}
    tendencias: dict[str, dict[str, float | str]] = {}
    score_buy = 0
    score_sell = 0
    retornos: list[float] = []
    for passos, nome in janelas.items():
        direcao, retorno = _direcao_janela(closes, passos)
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


def gerar_sinal_orquestrado(
    simbolo: str,
    klines: list[Any],
    livro_topo: dict[str, Any] | None = None,
    noticias: list[Any] | None = None,
    saldo: dict[str, Any] | None = None,
    *,
    force_allow_for_testnet: bool | None = None,
    ajustes_sinal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ajustes_sinal = ajustes_sinal or {}
    sent_score = _sentimento_medio_noticias(noticias)
    features = calcular_features_1m(klines, livro_topo=livro_topo, sent_score=sent_score)
    regime_info = detectar_regime(features)
    contexto = _contexto_mercado(klines)
    limiar_confirmacao = int(ajustes_sinal.get("signal_confirm_threshold", os.getenv("SIGNAL_CONFIRMATION_THRESHOLD", "3")))
    confirmacao = _confirmacao_multi_timeframe(klines, limiar_confirmacao)
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
    taxa_trade = float(ajustes_sinal.get("signal_trade_fee_pct", os.getenv("SIGNAL_TRADE_FEE_PCT", "0.0012")))
    slippage = float(ajustes_sinal.get("signal_slippage_pct", os.getenv("SIGNAL_SLIPPAGE_PCT", "0.0005")))
    lucro_liquido_min = float(ajustes_sinal.get("signal_min_net_profit_pct", os.getenv("SIGNAL_MIN_NET_PROFIT_PCT", "0.002")))
    signal_min_ev = float(ajustes_sinal.get("signal_min_ev", os.getenv("SIGNAL_MIN_EV", "0.0008")))
    signal_min_prob = float(ajustes_sinal.get("signal_min_prob", os.getenv("SIGNAL_MIN_PROB", "0.58")))
    signal_prob_temperature = float(ajustes_sinal.get("signal_prob_temperature", os.getenv("SIGNAL_PROB_TEMPERATURE", "1.0")))
    signal_prob_scale = float(ajustes_sinal.get("signal_prob_scale", os.getenv("SIGNAL_PROB_SCALE", "10.0")))

    pte = ProbabilisticTradeEngine(
        fee=taxa_trade,
        slippage=slippage,
        min_ev=signal_min_ev,
        min_prob=signal_min_prob,
        temperature=signal_prob_temperature,
        scale=signal_prob_scale,
    )
    force_allow_env = os.getenv("FORCE_ALLOW_RISKY_TRADES", "false").lower() == "true"
    force_allow = bool(force_allow_env and force_allow_for_testnet is True)
    if force_allow:
        lucro_liquido_min = float(os.getenv("SIGNAL_MIN_NET_PROFIT_PCT_TESTNET", "-1.0"))

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
        lucro_liquido_esperado = max(ev_buy, ev_sell)

    consenso = consolidar_decisao(
        sinal_base=sinal,
        score_modelo=score_ml,
        score_llm=score_llm,
        confirmacao=confirmacao,
        probabilidade_trade=pte_resultado,
        lucro_liquido_esperado=lucro_liquido_esperado,
        lucro_liquido_minimo=lucro_liquido_min,
        force_allow=force_allow,
    )
    sinal["acao"] = consenso["acao"]
    sinal["confianca"] = consenso["confianca"]
    sinal["motivo"] = f"{sinal.get('motivo', 'sinal_orquestrado')}; {consenso['motivo']}"

    sinal["ts"] = int(time.time() * 1000)
    sinal["confirmacao_multi_timeframe"] = confirmacao
    sinal["probabilidade_trade"] = pte_resultado
    sinal["movimento_previsto_pct"] = movimento_previsto
    sinal["custos_estimados_pct"] = custos_totais
    sinal["lucro_liquido_esperado_pct"] = lucro_liquido_esperado
    janela_minutos = int(ajustes_sinal.get("signal_decision_window_minutes", os.getenv("SIGNAL_DECISION_WINDOW_MINUTES", "20")))
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
