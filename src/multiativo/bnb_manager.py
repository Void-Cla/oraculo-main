from __future__ import annotations

from typing import Any

# Hardcoded — sem os.getenv
_BNB_SALDO_MINIMO: float = 0.01          # qualquer BNB ativa o desconto
_BNB_COMPRA_REPOSICAO_USDT: float = 5.0  # compra pequena para pagar taxa


def avaliar_saldo_bnb(
    *,
    saldos: dict[str, dict[str, float]] | None = None,
    preco_bnb_usdt: float = 0.0,
) -> dict[str, Any]:
    saldos = saldos or {}
    saldo_bnb  = max(0.0, float(((saldos.get("BNB") or {}).get("total")) or 0.0))
    saldo_usdt = max(0.0, float(((saldos.get("USDT") or {}).get("livre")) or 0.0))
    saldo_usdt_apos_compra = max(0.0, saldo_usdt - _BNB_COMPRA_REPOSICAO_USDT)

    falta_bnb = max(0.0, _BNB_SALDO_MINIMO - saldo_bnb)
    compra_sugerida_usdt = 0.0
    if saldo_bnb < _BNB_SALDO_MINIMO and saldo_usdt >= _BNB_COMPRA_REPOSICAO_USDT:
        compra_sugerida_usdt = _BNB_COMPRA_REPOSICAO_USDT
    elif saldo_bnb < _BNB_SALDO_MINIMO and preco_bnb_usdt > 0.0:
        compra_sugerida_usdt = min(_BNB_COMPRA_REPOSICAO_USDT, falta_bnb * preco_bnb_usdt)

    quantidade_sugerida_bnb = (compra_sugerida_usdt / preco_bnb_usdt) if preco_bnb_usdt > 0.0 else 0.0

    return {
        "saldo_bnb_total":                 round(saldo_bnb, 8),
        "saldo_bnb_minimo":                round(_BNB_SALDO_MINIMO, 8),
        "preco_bnb_usdt":                  round(float(preco_bnb_usdt or 0.0), 8),
        "saldo_usdt_livre":                round(saldo_usdt, 8),
        "repor_bnb_agora":                 saldo_bnb < _BNB_SALDO_MINIMO and compra_sugerida_usdt > 0.0,
        "falta_bnb":                       round(falta_bnb, 8),
        "compra_sugerida_usdt":            round(compra_sugerida_usdt, 8),
        "quantidade_sugerida_bnb":         round(max(0.0, quantidade_sugerida_bnb), 8),
        "saldo_usdt_estimado_apos_compra": round(saldo_usdt_apos_compra, 8),
    }
