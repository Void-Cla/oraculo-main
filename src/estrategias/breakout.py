from __future__ import annotations

from typing import Any

from .base import clamp, montar_sinal


def gerar_sinal_breakout(simbolo: str, features: dict[str, Any], contexto: dict[str, Any] | None = None) -> dict[str, Any]:
    contexto = contexto or {}
    close = float(features.get("close", 0.0) or 0.0)
    max_high_20 = float(contexto.get("max_high_20", close) or close)
    min_low_20 = float(contexto.get("min_low_20", close) or close)
    volume_ratio = float(features.get("volume_ratio", 1.0) or 1.0)
    pressao_rel = float(features.get("pressao_rel", 0.0) or 0.0)
    vol5 = max(float(features.get("vol5", 0.0) or 0.0), 0.001)

    score = 0.0
    if close >= max_high_20:
        score += 0.50
    if close <= min_low_20:
        score -= 0.50
    score += clamp((volume_ratio - 1.0) * 0.25, -0.2, 0.2)
    score += clamp(pressao_rel * 0.2, -0.15, 0.15)

    acao = "HOLD"
    if score >= 0.22:
        acao = "BUY"
    elif score <= -0.22:
        acao = "SELL"

    return montar_sinal(
        estrategia="breakout",
        simbolo=simbolo,
        acao=acao,
        confianca=0.48 + min(abs(score), 0.42),
        stop_loss_pct=max(vol5 * 2.5, 0.005),
        take_profit_pct=max(vol5 * 4.0, 0.012),
        motivo=f"close={close:.4f}; high20={max_high_20:.4f}; low20={min_low_20:.4f}; vol_ratio={volume_ratio:.3f}",
        contexto=contexto,
    )
