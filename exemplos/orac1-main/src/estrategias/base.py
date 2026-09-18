from __future__ import annotations

from typing import Any


def clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def montar_sinal(
    *,
    estrategia: str,
    simbolo: str,
    acao: str,
    confianca: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    motivo: str,
    contexto: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "estrategia": estrategia,
        "simbolo": simbolo.upper(),
        "acao": acao,
        "confianca": clamp(float(confianca), 0.0, 0.99),
        "stop_loss_pct": max(float(stop_loss_pct), 0.001),
        "take_profit_pct": max(float(take_profit_pct), 0.001),
        "motivo": motivo,
        "contexto_estrategia": contexto or {},
    }
