from __future__ import annotations

from typing import Any

from .base import clamp, montar_sinal


def gerar_sinal_volatility_scalping(simbolo: str, features: dict[str, Any], contexto: dict[str, Any] | None = None) -> dict[str, Any]:
    vol5 = float(features.get("vol5", 0.0) or 0.0)
    spread = float(features.get("spread_rel", 0.0) or 0.0)
    pressao = float(features.get("pressao_rel", 0.0) or 0.0)
    diff_micro = float(features.get("diff_close_micro_rel", 0.0) or 0.0)

    score = clamp((pressao * 0.45) + (diff_micro * 12.0) - (spread * 10.0), -0.8, 0.8)
    vol_minimo = 0.00015
    spread_maximo = 0.0012 if vol5 < 0.0015 else 0.0015
    gatilho_score = 0.08 if vol5 < 0.0015 else 0.16
    acao = "HOLD"
    if vol5 >= vol_minimo and spread <= spread_maximo:
        if score >= gatilho_score:
            acao = "BUY"
        elif score <= -gatilho_score:
            acao = "SELL"

    return montar_sinal(
        estrategia="volatility_scalping",
        simbolo=simbolo,
        acao=acao,
        confianca=0.42 + min(abs(score), 0.45),
        stop_loss_pct=max(vol5 * 1.5, 0.003),
        take_profit_pct=max(vol5 * 2.2, 0.006),
        motivo=f"vol5={vol5:.5f}; spread={spread:.5f}; pressao={pressao:.4f}; diff_micro={diff_micro:.5f}",
        contexto=contexto,
    )
