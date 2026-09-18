from __future__ import annotations

import os
from typing import Any


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def _taxa_decimal(conta: dict[str, Any], chave_nova: str, chave_legada: str, fallback: float) -> float:
    commission_rates = conta.get("commissionRates") or {}
    if commission_rates.get(chave_nova) not in {None, ""}:
        return float(commission_rates[chave_nova])
    if conta.get(chave_legada) not in {None, ""}:
        return float(conta[chave_legada]) / 10000.0
    return fallback


def montar_perfil_taxas(
    conta: dict[str, Any] | None = None,
    saldos: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    conta = conta or {}
    saldos = saldos or {}
    taxa_padrao = float(os.getenv("SIGNAL_TRADE_FEE_PCT", "0.0012") or 0.0012)
    maker = _taxa_decimal(conta, "maker", "makerCommission", taxa_padrao)
    taker = _taxa_decimal(conta, "taker", "takerCommission", taxa_padrao)
    buyer = _taxa_decimal(conta, "buyer", "buyerCommission", taxa_padrao)
    seller = _taxa_decimal(conta, "seller", "sellerCommission", taxa_padrao)

    saldo_bnb = float(((saldos.get("BNB") or {}).get("total")) or 0.0)
    usar_bnb = os.getenv("BNB_FEE_DISCOUNT_ENABLED", "true").lower() == "true"
    saldo_minimo = max(0.0, float(os.getenv("BNB_SALDO_MINIMO", "5") or 5))
    desconto = _clamp(float(os.getenv("BNB_FEE_DISCOUNT_RATIO", "0.25") or 0.25), 0.0, 0.9)
    desconto_ativo = usar_bnb and saldo_bnb >= saldo_minimo
    fator = 1.0 - desconto if desconto_ativo else 1.0

    return {
        "maker_decimal": maker,
        "taker_decimal": taker,
        "buyer_decimal": buyer,
        "seller_decimal": seller,
        "maker_decimal_efetiva": maker * fator,
        "taker_decimal_efetiva": taker * fator,
        "buyer_decimal_efetiva": buyer * fator,
        "seller_decimal_efetiva": seller * fator,
        "maker_pct": round(maker * 100.0, 4),
        "taker_pct": round(taker * 100.0, 4),
        "maker_pct_efetiva": round(maker * fator * 100.0, 4),
        "taker_pct_efetiva": round(taker * fator * 100.0, 4),
        "desconto_bnb_ativo": desconto_ativo,
        "desconto_bnb_pct": round(desconto * 100.0, 2) if desconto_ativo else 0.0,
        "saldo_bnb_total": saldo_bnb,
        "saldo_bnb_minimo": saldo_minimo,
        "inferencia_por_saldo_bnb": desconto_ativo,
    }
