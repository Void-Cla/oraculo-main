from __future__ import annotations

import os
from typing import Any


def avaliar_profit_guard(
    *,
    lucro_liquido_pct: float,
    notional_usdt: float,
    spread_rel: float,
    taxas_totais_pct: float,
    slippage_pct: float,
    minimo_pct: float | None = None,
    minimo_usdt: float | None = None,
) -> dict[str, Any]:
    lucro_pct = float(lucro_liquido_pct or 0.0)
    notional = max(0.0, float(notional_usdt or 0.0))
    lucro_usdt = notional * lucro_pct
    minimo_pct_cfg = minimo_pct if minimo_pct is not None else float(os.getenv("SIGNAL_MIN_NET_PROFIT_PCT", "0.002") or 0.002)
    # Prefer explicit param; fallback to env or conservative default 0.01 (micro-trading)
    minimo_usdt_cfg = minimo_usdt if minimo_usdt is not None else float(os.getenv("LUCRO_LIQUIDO_MINIMO_USDT", "0.01") or 0.01)
    minimo_pct = max(0.0, float(minimo_pct_cfg or 0.0))
    minimo_usdt = max(0.0, float(minimo_usdt_cfg or 0.0))
    spread_maximo = max(0.0, float(os.getenv("MAX_SPREAD_REL", "0.003") or 0.003))

    motivos: list[str] = []
    if lucro_pct < minimo_pct:
        motivos.append("lucro_liquido_pct_abaixo_do_minimo")
    if lucro_usdt < minimo_usdt:
        motivos.append("lucro_liquido_usdt_abaixo_do_minimo")
    if float(spread_rel or 0.0) > spread_maximo:
        motivos.append("spread_alto")
    if notional <= 0.0:
        motivos.append("notional_invalido")

    return {
        "aprovado": not motivos,
        "motivos": motivos,
        "lucro_liquido_pct": lucro_pct,
        "lucro_liquido_usdt": round(lucro_usdt, 8),
        "minimo_pct": minimo_pct,
        "minimo_usdt": minimo_usdt,
        "spread_rel": float(spread_rel or 0.0),
        "spread_maximo": spread_maximo,
        "taxas_totais_pct": float(taxas_totais_pct or 0.0),
        "slippage_pct": float(slippage_pct or 0.0),
    }
