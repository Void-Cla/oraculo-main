from __future__ import annotations

import os
from typing import Any


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def calcular_plano_capital(
    *,
    saldos: dict[str, dict[str, float]] | None = None,
    saldo_total_estimado_usdt: float | None = None,
    capital_planejado_usdt: float | None = None,
    lucro_liquido_minimo_usdt: float | None = None,
) -> dict[str, Any]:
    saldos = saldos or {}
    usdt = saldos.get("USDT") or {}
    saldo_usdt_livre = max(0.0, float(usdt.get("livre", 0.0) or 0.0))
    saldo_total = max(saldo_total_estimado_usdt or 0.0, saldo_usdt_livre)
    if saldo_total <= 0.0:
        saldo_total = max(0.0, float(os.getenv("ORACULO_CAPITAL_REFERENCIA_USDT", "10") or 10))

    fracao_minima = _clamp(float(os.getenv("CAPITAL_MIN_FRACTION", "0.30") or 0.30), 0.05, 0.95)
    fracao_maxima = _clamp(float(os.getenv("CAPITAL_MAX_FRACTION", "0.50") or 0.50), fracao_minima, 0.98)
    lucro_minimo_cfg = (
        lucro_liquido_minimo_usdt
        if lucro_liquido_minimo_usdt is not None
        else float(os.getenv("LUCRO_LIQUIDO_MINIMO_USDT", "0.01") or 0.01)
    )
    lucro_minimo_usdt = max(0.0, float(lucro_minimo_cfg or 0.0))
    take_profit_alvo = max(0.0005, float(os.getenv("SCALPING_TAKE_PROFIT_PCT", "0.003") or 0.003))
    notional_minimo_binance = max(1.0, float(os.getenv("NOTIONAL_MINIMO_USDT", "5") or 5))
    capital_planejado = max(0.0, float(capital_planejado_usdt or 0.0))

    if saldo_usdt_livre <= 25.0:
        fracao_alvo = fracao_maxima
    elif saldo_usdt_livre <= 100.0:
        fracao_alvo = min(fracao_maxima, max(fracao_minima, 0.35))
    else:
        fracao_alvo = min(fracao_maxima, max(fracao_minima, 0.20))

    capital_para_meta = lucro_minimo_usdt / take_profit_alvo
    base_disponivel = saldo_usdt_livre if saldo_usdt_livre > 0.0 else saldo_total
    if capital_planejado > 0.0:
        base_disponivel = min(base_disponivel, capital_planejado)
    trade_referencia = min(base_disponivel, max(notional_minimo_binance, base_disponivel * fracao_alvo, capital_para_meta))
    trade_referencia = min(trade_referencia, base_disponivel)
    lucro_minimo_pct = (lucro_minimo_usdt / trade_referencia) if trade_referencia > 0.0 else 0.0

    return {
        "saldo_total_estimado_usdt": round(saldo_total, 8),
        "saldo_usdt_livre": round(saldo_usdt_livre, 8),
        "capital_planejado_usdt": round(capital_planejado, 8),
        "fracao_minima": fracao_minima,
        "fracao_maxima": fracao_maxima,
        "fracao_alvo": round(fracao_alvo, 4),
        "trade_referencia_usdt": round(max(0.0, trade_referencia), 8),
        "capital_minimo_para_meta_usdt": round(capital_para_meta, 8),
        "notional_minimo_usdt": round(notional_minimo_binance, 8),
        "lucro_liquido_minimo_usdt": round(lucro_minimo_usdt, 8),
        "lucro_liquido_minimo_pct": round(max(0.0, lucro_minimo_pct), 8),
        "take_profit_alvo_pct": round(take_profit_alvo * 100.0, 4),
    }
