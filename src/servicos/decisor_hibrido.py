from __future__ import annotations

import os
from typing import Any

from src.observabilidade.logger import get_logger
from src.servicos.llm_analista import analisar_contexto

LOG = get_logger("decisor_hibrido")


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def decidir(
    simbolo: str,
    features: dict[str, Any],
    y_hat: float,
    y_cal: float | None = None,
    conf_num: float = 0.5,
    noticias: list[Any] | None = None,
    saldo: dict[str, Any] | None = None,
    resultado_llm: dict[str, Any] | None = None,
    ajustes_sinal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    close = float(features.get("close", 0.0) or 0.0)
    preco_previsto = float(y_cal if y_cal is not None else y_hat)
    variacao_prevista = ((preco_previsto - close) / close) if close else 0.0

    llm = resultado_llm or analisar_contexto([], features, noticias=noticias, saldo=saldo)
    conf_llm = float(llm.get("score_conf", 0.5) or 0.5)
    score_llm = float(llm.get("score_direcional", 0.0) or 0.0)

    ajustes_sinal = ajustes_sinal or {}
    limiar_variacao = float(ajustes_sinal.get("limiar_variacao_numerica", 0.0015))
    limiar_operacao = float(ajustes_sinal.get("limiar_score_operacao", 0.18))
    max_spread = float(ajustes_sinal.get("max_spread_rel", 0.003))
    max_vol = float(ajustes_sinal.get("max_vol5", 0.02))
    max_posicao = float(ajustes_sinal.get("max_posicao_fracao", 0.05))
    peso_num_cfg = float(ajustes_sinal.get("peso_modelo_numerico", 0.65))
    peso_llm_cfg = float(ajustes_sinal.get("peso_modelo_llm", 0.35))

    score_numerico = _clamp(variacao_prevista / limiar_variacao, -1.0, 1.0)
    peso_num_real = max(conf_num, 0.0) * peso_num_cfg
    peso_llm_real = max(conf_llm, 0.0) * peso_llm_cfg
    soma_pesos = peso_num_real + peso_llm_real or 1.0
    peso_num_aplicado = peso_num_real / soma_pesos
    peso_llm_aplicado = peso_llm_real / soma_pesos

    score_final = (score_numerico * peso_num_aplicado) + (score_llm * peso_llm_aplicado)
    spread_rel = abs(float(features.get("spread_rel", 0.0) or 0.0))
    vol5 = abs(float(features.get("vol5", 0.0) or 0.0))

    travas_risco: list[str] = []
    if spread_rel > max_spread:
        travas_risco.append("spread_alto")
    if vol5 > max_vol:
        travas_risco.append("volatilidade_alta")
    if saldo:
        saldo_livre = float(saldo.get("saldo_livre", saldo.get("saldo_total", 0.0)) or 0.0)
        if saldo_livre <= 0.0:
            travas_risco.append("saldo_indisponivel")

    acao = "HOLD"
    motivo = "sinal insuficiente"
    tamanho = 0.0
    conflito = score_numerico * score_llm < 0.0
    if travas_risco:
        motivo = f"bloqueado_por_risco:{','.join(travas_risco)}"
    elif score_final >= limiar_operacao:
        acao = "BUY"
        motivo = "compra_hibrida"
    elif score_final <= -limiar_operacao:
        acao = "SELL"
        motivo = "venda_hibrida"

    if acao != "HOLD":
        tamanho = max_posicao * min(1.0, abs(score_final)) * min(1.0, max(conf_num, conf_llm))
        if conflito and conf_num >= 0.55 and conf_llm >= 0.55:
            tamanho *= 0.5
            motivo += "_com_reducao_por_conflito"
        tamanho = _clamp(tamanho, 0.0, max_posicao)

    justificativa = (
        f"score_final={score_final:.3f}; score_num={score_numerico:.3f}; score_llm={score_llm:.3f}; "
        f"peso_num={peso_num_aplicado:.3f}; peso_llm={peso_llm_aplicado:.3f}; variacao_prevista={variacao_prevista:.5f}"
    )
    resultado = {
        "simbolo": simbolo.upper(),
        "acao": acao,
        "tamanho": float(tamanho),
        "motivo": motivo,
        "justificativa": justificativa,
        "score_final": float(score_final),
        "score_numerico": float(score_numerico),
        "score_llm": float(score_llm),
        "conf_num": float(conf_num),
        "conf_llm": float(conf_llm),
        "peso_modelo_numerico": float(peso_num_aplicado),
        "peso_modelo_llm": float(peso_llm_aplicado),
        "peso_modelo_numerico_config": float(peso_num_cfg),
        "peso_modelo_llm_config": float(peso_llm_cfg),
        "variacao_prevista": float(variacao_prevista),
        "travas_risco": travas_risco,
        "llm": llm,
    }
    LOG.info("decisao_emitida", extra=resultado)
    return resultado
