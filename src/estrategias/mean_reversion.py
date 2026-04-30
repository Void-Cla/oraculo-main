from __future__ import annotations

from typing import Any

from .base import clamp, montar_sinal


def gerar_sinal_mean_reversion(simbolo: str, features: dict[str, Any], contexto: dict[str, Any] | None = None) -> dict[str, Any]:
    close = float(features.get("close", 0.0) or 0.0)
    ma10 = float(features.get("ma10", 0.0) or 0.0)
    vol5 = max(float(features.get("vol5", 0.0) or 0.0), 0.001)
    if close <= 0.0 or ma10 <= 0.0:
        return montar_sinal(
            estrategia="mean_reversion",
            simbolo=simbolo,
            acao="HOLD",
            confianca=0.1,
            stop_loss_pct=0.005,
            take_profit_pct=0.01,
            motivo="dados insuficientes",
            contexto=contexto,
        )

    desvio = (close - ma10) / ma10
    score = clamp((-desvio) * 25.0, -0.8, 0.8)
    acao = "HOLD"
    if score >= 0.20:
        acao = "BUY"
    elif score <= -0.20:
        acao = "SELL"

    return montar_sinal(
        estrategia="mean_reversion",
        simbolo=simbolo,
        acao=acao,
        confianca=0.45 + min(abs(score), 0.45),
        stop_loss_pct=max(vol5 * 1.8, 0.004),
        take_profit_pct=max(abs(desvio) * 1.5, 0.007),
        motivo=f"close={close:.4f}; ma10={ma10:.4f}; desvio={desvio:.5f}",
        contexto=contexto,
    )
