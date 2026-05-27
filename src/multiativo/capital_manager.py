from __future__ import annotations

from typing import Any

# Hardcoded — sem os.getenv
_FRACAO_MINIMA: float = 0.40            # mínimo 40% do capital por trade
_FRACAO_MAXIMA: float = 0.70            # máximo 70% (agressivo para capital pequeno)
_TAKE_PROFIT_ALVO: float = 0.001        # 0.1% alvo de TP por trade
_NOTIONAL_MINIMO_BINANCE: float = 5.0   # $5 mínimo da Binance
_LUCRO_MINIMO_USDT: float = 0.01        # $0.01 — hard floor


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
        saldo_total = 10.0   # fallback seguro se sem saldo

    lucro_minimo_usdt = max(
        _LUCRO_MINIMO_USDT,
        float(lucro_liquido_minimo_usdt or _LUCRO_MINIMO_USDT),
    )

    # Fração agressiva para capital pequeno (maximiza trades possíveis)
    if saldo_usdt_livre <= 20.0:
        fracao_alvo = _FRACAO_MAXIMA         # 70% — capital pequeno, joga tudo
    elif saldo_usdt_livre <= 100.0:
        fracao_alvo = 0.55                   # 55%
    elif saldo_usdt_livre <= 500.0:
        fracao_alvo = 0.40                   # 40%
    else:
        fracao_alvo = _FRACAO_MINIMA         # 40% mínimo

    capital_para_meta = lucro_minimo_usdt / max(_TAKE_PROFIT_ALVO, 0.0001)
    base_disponivel = saldo_usdt_livre if saldo_usdt_livre > 0.0 else saldo_total
    if capital_planejado_usdt and capital_planejado_usdt > 0.0:
        base_disponivel = min(base_disponivel, float(capital_planejado_usdt))

    trade_referencia = min(
        base_disponivel,
        max(_NOTIONAL_MINIMO_BINANCE, base_disponivel * fracao_alvo, capital_para_meta),
    )
    trade_referencia = min(trade_referencia, base_disponivel)
    lucro_minimo_pct = (lucro_minimo_usdt / trade_referencia) if trade_referencia > 0.0 else 0.0

    return {
        "saldo_total_estimado_usdt":    round(saldo_total, 8),
        "saldo_usdt_livre":             round(saldo_usdt_livre, 8),
        "capital_planejado_usdt":       round(float(capital_planejado_usdt or 0.0), 8),
        "fracao_minima":                _FRACAO_MINIMA,
        "fracao_maxima":                _FRACAO_MAXIMA,
        "fracao_alvo":                  round(fracao_alvo, 4),
        "trade_referencia_usdt":        round(max(0.0, trade_referencia), 8),
        "capital_minimo_para_meta_usdt": round(capital_para_meta, 8),
        "notional_minimo_usdt":         round(_NOTIONAL_MINIMO_BINANCE, 8),
        "lucro_liquido_minimo_usdt":    round(lucro_minimo_usdt, 8),
        "lucro_liquido_minimo_pct":     round(max(0.0, lucro_minimo_pct), 8),
        "take_profit_alvo_pct":         round(_TAKE_PROFIT_ALVO * 100.0, 4),
    }
