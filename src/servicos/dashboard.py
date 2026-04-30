from __future__ import annotations

import time
from typing import Any

from src.binance_api.cliente import ClienteBinance
from src.persistencia.repositorio_auditoria import RepositorioAuditoria
from src.persistencia.repositorio_features import RepositorioFeatures
from src.persistencia.repositorio_livro_topo import RepositorioLivroTopo
from src.persistencia.repositorio_ohlcv import RepositorioOhlcv
from src.persistencia.repositorio_ordens import RepositorioOrdens
from src.persistencia.repositorio_outcomes import RepositorioOutcomes
from src.persistencia.repositorio_predicoes import RepositorioPredicoes
from src.persistencia.repositorio_usuarios import RepositorioUsuarios


def _ts_ms(valor: int | float | None) -> int:
    if valor is None:
        return 0
    numero = int(valor)
    if numero < 10_000_000_000:
        return numero * 1000
    return numero


def _sentido_delta(delta: float) -> str:
    if delta > 0:
        return "alta"
    if delta < 0:
        return "queda"
    return "neutro"


def _bool_status(valor: bool, ok: str = "operacional", ruim: str = "travado") -> str:
    return ok if valor else ruim


def _safe_percentual(valor: float | None) -> float:
    if valor is None:
        return 0.0
    return round(float(valor) * 100.0, 2)


def _calcular_metricas_modelo(predicoes: list[dict[str, Any]], outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    mapa_outcomes = {item["ts_previsao"]: item for item in outcomes}
    amostras_modelo = 0
    acertos_modelo = 0
    erros_rel: list[float] = []
    amostras_llm = 0
    acertos_llm = 0
    conf_modelo: list[float] = []
    conf_llm: list[float] = []

    for pred in predicoes:
        outcome = mapa_outcomes.get(pred["created_ts"])
        if outcome is None:
            continue
        meta = pred.get("meta", {})
        preco_ref = float(meta.get("preco_atual", 0.0) or 0.0)
        if preco_ref <= 0.0:
            continue

        y_pred = float(pred.get("y_cal") if pred.get("y_cal") is not None else pred.get("y_hat", preco_ref))
        y_true = float(outcome.get("y_true", preco_ref))
        direcao_pred = 1 if y_pred > preco_ref else -1 if y_pred < preco_ref else 0
        direcao_real = 1 if y_true > preco_ref else -1 if y_true < preco_ref else 0
        if direcao_pred != 0 and direcao_real != 0:
            amostras_modelo += 1
            if direcao_pred == direcao_real:
                acertos_modelo += 1
        if pred.get("p_conf") is not None:
            conf_modelo.append(float(pred["p_conf"]))
        if outcome.get("err_rel") is not None:
            erros_rel.append(abs(float(outcome["err_rel"])))

        llm_info = (((meta.get("decisao") or {}).get("llm")) or {})
        direcao_llm = str(llm_info.get("direcao", "neutro")).lower()
        if direcao_llm in {"compra", "venda"} and direcao_real != 0:
            amostras_llm += 1
            if (direcao_llm == "compra" and direcao_real > 0) or (direcao_llm == "venda" and direcao_real < 0):
                acertos_llm += 1
        if (meta.get("decisao") or {}).get("conf_llm") is not None:
            conf_llm.append(float((meta.get("decisao") or {}).get("conf_llm", 0.0)))

    hit_rate_modelo = (acertos_modelo / amostras_modelo) if amostras_modelo else 0.0
    hit_rate_llm = (acertos_llm / amostras_llm) if amostras_llm else 0.0
    confianca_media_modelo = (sum(conf_modelo) / len(conf_modelo)) if conf_modelo else 0.0
    confianca_media_llm = (sum(conf_llm) / len(conf_llm)) if conf_llm else 0.0
    erro_medio = (sum(erros_rel) / len(erros_rel)) if erros_rel else 0.0

    temperatura_modelo = int(round(((hit_rate_modelo * 0.6) + (confianca_media_modelo * 0.4)) * 100))
    temperatura_llm = int(round(((hit_rate_llm * 0.55) + (confianca_media_llm * 0.45)) * 100))

    return {
        "hit_rate_modelo": _safe_percentual(hit_rate_modelo),
        "hit_rate_llm": _safe_percentual(hit_rate_llm),
        "confianca_media_modelo": _safe_percentual(confianca_media_modelo),
        "confianca_media_llm": _safe_percentual(confianca_media_llm),
        "erro_rel_medio": round(erro_medio * 100.0, 2),
        "temperatura_modelo": max(0, min(100, temperatura_modelo)),
        "temperatura_llm": max(0, min(100, temperatura_llm)),
        "amostras_modelo": amostras_modelo,
        "amostras_llm": amostras_llm,
    }


def _sinal_auditavel_recente(auditoria: list[dict[str, Any]]) -> tuple[dict[str, Any], str] | tuple[None, None]:
    for item in reversed(auditoria):
        payload = dict(item.get("payload") or {})
        tipo = str(item.get("tipo") or "")
        if tipo == "auto_trade":
            sinal = dict(payload.get("sinal") or {})
            if sinal:
                return sinal, "auto_trade"
        if tipo == "signal_engine":
            sinal = dict(payload.get("sinal") or {})
            if sinal:
                return sinal, "signal_engine"
    return None, None


async def montar_dashboard(
    *,
    simbolo: str,
    usuario_id: int | None,
    loop_previsao_ativo: bool,
    db_path: str,
) -> dict[str, Any]:
    simbolo = simbolo.upper()
    usuario = await RepositorioUsuarios.obter(usuario_id) if usuario_id else None

    ohlcv = await RepositorioOhlcv.obter_ultimas(simbolo, limite=120)
    livro_topo = await RepositorioLivroTopo.obter_ultimo(simbolo)
    features = await RepositorioFeatures.listar_ultimas(simbolo, limite=1)
    predicoes = await RepositorioPredicoes.listar_recentes(simbolo, limite=40)
    outcomes = await RepositorioOutcomes.listar_recentes(simbolo, limite=40)
    auditoria = await RepositorioAuditoria.listar_recentes(simbolo=simbolo, limite=20)
    ordens = await RepositorioOrdens.listar_recentes(usuario_id=usuario_id, simbolo=simbolo, limite=30)
    resumo_ordens = await RepositorioOrdens.resumo_status(usuario_id=usuario_id, simbolo=simbolo)

    ultimo_ohlcv = ohlcv[-1] if ohlcv else None
    penultimo_ohlcv = ohlcv[-2] if len(ohlcv) >= 2 else None
    preco_atual = float(ultimo_ohlcv["close"]) if ultimo_ohlcv else 0.0
    variacao_1m = 0.0
    if ultimo_ohlcv and penultimo_ohlcv and float(penultimo_ohlcv["close"]):
        variacao_1m = (float(ultimo_ohlcv["close"]) - float(penultimo_ohlcv["close"])) / float(penultimo_ohlcv["close"])

    predicao_atual = predicoes[-1] if predicoes else None
    meta_predicao = (predicao_atual or {}).get("meta", {}) if predicao_atual else {}
    decisao_hibrida = meta_predicao.get("decisao", {}) if predicao_atual else {}
    llm_atual = decisao_hibrida.get("llm", {}) if decisao_hibrida else {}
    sinal_atual, origem_sinal_atual = _sinal_auditavel_recente(auditoria)
    decisao_atual = (
        {
            "acao": sinal_atual.get("acao", "HOLD"),
            "confianca": sinal_atual.get("confianca", 0.0),
            "motivo": sinal_atual.get("motivo") or "sinal_final_sem_motivo",
            "origem": origem_sinal_atual,
            "estrategia": sinal_atual.get("estrategia"),
            "regime": sinal_atual.get("regime"),
            "lucro_liquido_esperado_pct": sinal_atual.get("lucro_liquido_esperado_pct", 0.0),
        }
        if sinal_atual
        else decisao_hibrida
    )

    metricas_modelo = _calcular_metricas_modelo(predicoes, outcomes)
    historico_precos = [{"ts": item["ts"], "close": float(item["close"])} for item in ohlcv[-40:]]

    agora_ms = int(time.time() * 1000)
    ultimo_ts = _ts_ms(ultimo_ohlcv["ts"]) if ultimo_ohlcv else 0
    atraso_mercado_segundos = int(max(0, (agora_ms - ultimo_ts) / 1000)) if ultimo_ts else None
    status_mercado = "sem_dados"
    if atraso_mercado_segundos is not None:
        if atraso_mercado_segundos <= 90:
            status_mercado = "sincronizado"
        elif atraso_mercado_segundos <= 300:
            status_mercado = "atrasado"
        else:
            status_mercado = "travado"

    ganho_aberto_estimado = 0.0
    ordens_ativas: list[dict[str, Any]] = []
    for ordem in ordens:
        if ordem["status"] not in {"EM_ABERTO", "PENDENTE", "SIMULADA"}:
            continue
        quantidade = float(ordem.get("quantidade") or 0.0)
        entrada = float(ordem.get("preco_referencia") or 0.0)
        if quantidade > 0.0 and entrada > 0.0 and preco_atual > 0.0:
            pnl = (preco_atual - entrada) * quantidade
            if ordem["lado"] == "SELL":
                pnl *= -1.0
            ganho_aberto_estimado += pnl
        ordens_ativas.append(ordem)

    perfil_binance = {"disponivel": False, "motivo": "credenciais_binance_ausentes"}
    if usuario is not None:
        cliente = ClienteBinance()
        try:
            perfil_binance = await cliente.obter_resumo_conta(simbolo_referencia=simbolo, preco_referencia=preco_atual or None)
        except Exception as exc:
            perfil_binance = {"disponivel": False, "motivo": str(exc)}
        finally:
            await cliente.fechar()

    status_operacional = {
        "api": "operacional",
        "loop_previsao": _bool_status(loop_previsao_ativo),
        "mercado": status_mercado,
        "db_path": db_path,
        "atraso_mercado_segundos": atraso_mercado_segundos,
        "trava_risco": "travado" if any((ordem["status"] == "REJEITADA") for ordem in ordens[-5:]) else "operacional",
    }

    return {
        "simbolo": simbolo,
        "ts_atualizacao": agora_ms,
        "usuario": usuario,
        "operacional": status_operacional,
        "mercado": {
            "preco_atual": preco_atual,
            "variacao_1m_pct": round(variacao_1m * 100.0, 3),
            "sentido_1m": _sentido_delta(variacao_1m),
            "livro_topo": livro_topo,
            "historico_precos": historico_precos,
            "feature_recente": features[-1] if features else None,
        },
        "modelos": {
            **metricas_modelo,
            "predicao_atual": predicao_atual,
            "decisao_atual": decisao_atual,
            "decisao_hibrida_atual": decisao_hibrida,
            "sinal_atual": sinal_atual,
            "llm_atual": llm_atual,
        },
        "ordens": {
            "resumo": resumo_ordens,
            "ganho_aberto_estimado": round(ganho_aberto_estimado, 4),
            "ativas": ordens_ativas[-10:],
            "recentes": ordens[-20:],
        },
        "perfil_binance": perfil_binance,
        "historico": {
            "predicoes": predicoes[-12:],
            "outcomes": outcomes[-12:],
            "auditoria": auditoria[-12:],
            "sinais": [item for item in auditoria if item["tipo"] == "signal_engine"][-12:],
            "status_ordens": [item for item in auditoria if item["tipo"] == "ordem_status"][-12:],
            "previsoes_hibridas": [item for item in auditoria if item["tipo"] == "previsao_hibrida"][-12:],
        },
    }
