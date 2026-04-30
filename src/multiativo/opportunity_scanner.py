from __future__ import annotations

import os
from typing import Any

from .config import ativo_cotacao, metadados_par
from .profit_guard import avaliar_profit_guard


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def _score_volatilidade(features: dict[str, Any]) -> float:
    vol = max(float(features.get("vol5", 0.0) or 0.0), float(features.get("vol10", 0.0) or 0.0))
    amplitude = float(features.get("amplitude_rel", 0.0) or 0.0)
    return _clamp((vol * 55.0) + (amplitude * 18.0), 0.0, 1.0)


def _score_volume(features: dict[str, Any]) -> float:
    volume_ratio = float(features.get("volume_ratio", 0.0) or 0.0)
    return _clamp((volume_ratio - 0.6) / 1.4, 0.0, 1.0)


def _score_momentum(features: dict[str, Any]) -> tuple[float, float]:
    bruto = (
        (float(features.get("r_1m", 0.0) or 0.0) * 0.40)
        + (float(features.get("r_3m", 0.0) or 0.0) * 0.30)
        + (float(features.get("r_5m", 0.0) or 0.0) * 0.20)
        + (float(features.get("book_imb", 0.0) or 0.0) * 0.10)
    )
    return _clamp(abs(bruto) / 0.01, 0.0, 1.0), bruto


def _score_spread(features: dict[str, Any]) -> float:
    spread = float(features.get("spread_rel", 0.0) or 0.0)
    max_spread = max(1e-9, float(os.getenv("MAX_SPREAD_REL", "0.003") or 0.003))
    return _clamp(1.0 - (spread / max_spread), 0.0, 1.0)


def _score_risco(features: dict[str, Any]) -> float:
    spread = float(features.get("spread_rel", 0.0) or 0.0)
    volume_ratio = float(features.get("volume_ratio", 0.0) or 0.0)
    vol = max(float(features.get("vol5", 0.0) or 0.0), float(features.get("vol10", 0.0) or 0.0))
    max_spread = max(1e-9, float(os.getenv("MAX_SPREAD_REL", "0.003") or 0.003))
    spread_risk = _clamp(spread / max_spread, 0.0, 2.0) * 0.45
    liquidez_risk = _clamp((1.0 - volume_ratio) / 1.2, 0.0, 1.0) * 0.30
    vol_risk = _clamp(max(0.0, vol - 0.012) / 0.02, 0.0, 1.0) * 0.25
    return _clamp(spread_risk + liquidez_risk + vol_risk, 0.0, 1.0)


def _capital_disponivel_par(
    *,
    simbolo: str,
    saldos: dict[str, dict[str, float]] | None,
    precos_usdt: dict[str, float],
    capital_info: dict[str, Any],
) -> tuple[float, float]:
    referencia = max(0.0, float(capital_info.get("trade_referencia_usdt", 0.0) or 0.0))
    if not saldos:
        return referencia, referencia

    quote = ativo_cotacao(simbolo)
    saldo_quote = saldos.get(quote) or {}
    disponivel_quote = float(saldo_quote.get("livre", saldo_quote.get("total", 0.0)) or 0.0)
    preco_quote_usdt = 1.0 if quote == "USDT" else max(0.0, float(precos_usdt.get(quote, 0.0) or 0.0))
    disponivel_usdt = disponivel_quote * preco_quote_usdt if preco_quote_usdt > 0.0 else 0.0
    if quote == "USDT":
        disponivel_usdt = disponivel_quote
    return min(referencia, disponivel_usdt) if disponivel_usdt > 0.0 else 0.0, disponivel_usdt


def ranquear_oportunidades(
    *,
    snapshots: dict[str, dict[str, Any]],
    sinais: dict[str, dict[str, Any]],
    saldos: dict[str, dict[str, float]] | None,
    precos_usdt: dict[str, float],
    capital_info: dict[str, Any],
    perfil_taxas: dict[str, Any],
) -> dict[str, Any]:
    min_prob = max(0.0, float(os.getenv("SIGNAL_MIN_PROB", "0.58") or 0.58))
    min_score = max(0.0, float(os.getenv("MULTI_MIN_OPPORTUNITY_SCORE", "0.45") or 0.45))
    slippage_pct = max(0.0, float(os.getenv("SIGNAL_SLIPPAGE_PCT", "0.0005") or 0.0005))
    taxa_total = float(perfil_taxas.get("taker_decimal_efetiva", 0.0) or 0.0) * 2.0
    lucro_minimo_pct = float(capital_info.get("lucro_liquido_minimo_pct", 0.0) or 0.0)
    lucro_minimo_usdt = float(capital_info.get("lucro_liquido_minimo_usdt", 0.0) or 0.0)
    resultados: list[dict[str, Any]] = []

    for simbolo, snapshot in snapshots.items():
        features = snapshot.get("features") or {}
        sinal = sinais.get(simbolo) or {}
        prob = sinal.get("probabilidade_trade") or {}
        profit_pct = float(sinal.get("lucro_liquido_esperado_pct", 0.0) or 0.0)
        movimento_pct = float(sinal.get("movimento_previsto_pct", 0.0) or 0.0)
        acao = str(sinal.get("acao") or "HOLD").upper()
        prob_lado = 0.0
        ev_lado = 0.0
        if acao == "BUY":
            prob_lado = float(prob.get("prob_up", 0.0) or 0.0)
            ev_lado = float(prob.get("ev_buy", 0.0) or 0.0)
        elif acao == "SELL":
            prob_lado = float(prob.get("prob_down", 0.0) or 0.0)
            ev_lado = float(prob.get("ev_sell", 0.0) or 0.0)

        score_vol = _score_volatilidade(features)
        score_volume = _score_volume(features)
        score_momentum, momentum_bruto = _score_momentum(features)
        score_spread = _score_spread(features)
        score_risco = _score_risco(features)
        score_oportunidade = _clamp(
            (score_vol * 0.23)
            + (score_volume * 0.24)
            + (score_momentum * 0.28)
            + (score_spread * 0.25)
            - (score_risco * 0.20),
            0.0,
            1.0,
        )

        notional_usdt, disponibilidade_usdt = _capital_disponivel_par(
            simbolo=simbolo,
            saldos=saldos,
            precos_usdt=precos_usdt,
            capital_info=capital_info,
        )
        guard = avaliar_profit_guard(
            lucro_liquido_pct=profit_pct,
            notional_usdt=notional_usdt,
            spread_rel=float(features.get("spread_rel", 0.0) or 0.0),
            taxas_totais_pct=taxa_total,
            slippage_pct=slippage_pct,
            minimo_pct=lucro_minimo_pct,
            minimo_usdt=lucro_minimo_usdt,
        )
        motivos = list(guard["motivos"])
        if acao == "HOLD":
            motivos.append("sem_direcao_operavel")
        if prob_lado < max(min_prob, 0.60):
            motivos.append("probabilidade_abaixo_do_minimo")
        if ev_lado <= 0.0:
            motivos.append("ev_nao_positivo")
        if score_oportunidade < min_score:
            motivos.append("score_oportunidade_baixo")
        if notional_usdt <= 0.0:
            motivos.append("capital_indisponivel_para_o_par")

        meta = metadados_par(simbolo)
        resultados.append(
            {
                "simbolo": simbolo,
                "base": meta["base"],
                "quote": meta["quote"],
                "acao_sugerida": acao,
                "score_oportunidade": round(score_oportunidade, 6),
                "score_componentes": {
                    "volatilidade": round(score_vol, 6),
                    "volume": round(score_volume, 6),
                    "momentum": round(score_momentum, 6),
                    "spread": round(score_spread, 6),
                    "risco": round(score_risco, 6),
                },
                "momentum_bruto": round(momentum_bruto, 8),
                "probabilidade_lado": round(prob_lado, 6),
                "expected_value": round(ev_lado, 8),
                "movimento_previsto_pct": round(movimento_pct * 100.0, 6),
                "lucro_liquido_esperado_pct": round(profit_pct * 100.0, 6),
                "lucro_liquido_esperado_usdt": round(float(guard["lucro_liquido_usdt"]), 8),
                "capital_disponivel_quote_usdt": round(disponibilidade_usdt, 8),
                "notional_sugerido_usdt": round(notional_usdt, 8),
                "spread_rel_pct": round(float(features.get("spread_rel", 0.0) or 0.0) * 100.0, 6),
                "valida": not motivos,
                "motivos_bloqueio": sorted(set(motivos)),
                "regime": sinal.get("regime"),
                "estrategia": sinal.get("estrategia"),
                "confirmacao_multi_timeframe": sinal.get("confirmacao_multi_timeframe", {}),
                "probabilidade_trade": prob,
            }
        )

    ordenadas = sorted(
        resultados,
        key=lambda item: (
            bool(item["valida"]),
            float(item["score_oportunidade"]),
            float(item["lucro_liquido_esperado_usdt"]),
        ),
        reverse=True,
    )
    melhor = ordenadas[0] if ordenadas else None
    return {
        "pares": ordenadas,
        "melhor_oportunidade": melhor,
        "total_validas": sum(1 for item in ordenadas if item["valida"]),
        "sem_vantagem_real": not any(item["valida"] for item in ordenadas),
    }
