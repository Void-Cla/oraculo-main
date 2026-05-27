from __future__ import annotations

from typing import Any

# Hardcoded — sem os.getenv
_MINIMO_PCT_PADRAO: float = 0.0005      # 0.05% mínimo de lucro pct (micro-trading)
_MINIMO_USDT_PADRAO: float = 0.01       # $0.01 USDT — hard floor
_SPREAD_MAXIMO_PADRAO: float = 0.003    # 0.3% spread máximo


def avaliar_profit_guard(
    *,
    lucro_liquido_pct: float,
    notional_usdt: float,
    spread_rel: float,
    taxas_totais_pct: float,
    slippage_pct: float,
    minimo_pct: float | None = None,
    minimo_usdt: float | None = None,
    spread_maximo: float | None = None,
) -> dict[str, Any]:
    lucro_pct    = float(lucro_liquido_pct or 0.0)
    notional     = max(0.0, float(notional_usdt or 0.0))
    lucro_usdt   = notional * lucro_pct
    min_pct      = max(0.0, float(minimo_pct  if minimo_pct  is not None else _MINIMO_PCT_PADRAO))
    min_usdt     = max(0.0, float(minimo_usdt if minimo_usdt is not None else _MINIMO_USDT_PADRAO))
    spread_max   = max(0.0, float(spread_maximo if spread_maximo is not None else _SPREAD_MAXIMO_PADRAO))

    motivos: list[str] = []
    if lucro_pct < min_pct:
        motivos.append("lucro_liquido_pct_abaixo_do_minimo")
    if lucro_usdt < min_usdt:
        motivos.append("lucro_liquido_usdt_abaixo_do_minimo")
    if float(spread_rel or 0.0) > spread_max:
        motivos.append("spread_alto")
    if notional <= 0.0:
        motivos.append("notional_invalido")

    return {
        "aprovado":         not motivos,
        "motivos":          motivos,
        "lucro_liquido_pct":  lucro_pct,
        "lucro_liquido_usdt": round(lucro_usdt, 8),
        "minimo_pct":       min_pct,
        "minimo_usdt":      min_usdt,
        "spread_rel":       float(spread_rel or 0.0),
        "spread_maximo":    spread_max,
        "taxas_totais_pct": float(taxas_totais_pct or 0.0),
        "slippage_pct":     float(slippage_pct or 0.0),
    }
