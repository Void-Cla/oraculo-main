from __future__ import annotations

from typing import Any

from .base import clamp, montar_sinal


def gerar_sinal_momentum(simbolo: str, features: dict[str, Any], contexto: dict[str, Any] | None = None) -> dict[str, Any]:
    ema5 = float(features.get("ema5", 0.0) or 0.0)
    ema10 = float(features.get("ema10", 0.0) or 0.0)
    r_3m = float(features.get("r_3m", 0.0) or 0.0)
    slope_ma = float(features.get("slope_ma", 0.0) or 0.0)
    vol = max(float(features.get("vol5", 0.0) or 0.0), 0.001)

    score = 0.0
    if ema5 > ema10:
        score += 0.45
    elif ema5 < ema10:
        score -= 0.45
    score += clamp(r_3m * 12.0, -0.35, 0.35)
    score += clamp((slope_ma / max(abs(float(features.get("close", 1.0) or 1.0)), 1.0)) * 20.0, -0.2, 0.2)

    acao = "HOLD"
    if score >= 0.20:
        acao = "BUY"
    elif score <= -0.20:
        acao = "SELL"

    confianca = 0.5 + min(abs(score), 0.45)
    stop = max(vol * 2.2, 0.004)
    take = max(stop * 1.8, 0.008)
    return montar_sinal(
        estrategia="momentum",
        simbolo=simbolo,
        acao=acao,
        confianca=confianca,
        stop_loss_pct=stop,
        take_profit_pct=take,
        motivo=f"ema5={ema5:.4f}; ema10={ema10:.4f}; r_3m={r_3m:.5f}; slope={slope_ma:.5f}",
        contexto=contexto,
    )
