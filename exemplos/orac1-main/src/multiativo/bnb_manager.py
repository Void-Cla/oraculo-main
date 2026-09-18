from __future__ import annotations

import os
from typing import Any


def avaliar_saldo_bnb(
    *,
    saldos: dict[str, dict[str, float]] | None = None,
    preco_bnb_usdt: float = 0.0,
) -> dict[str, Any]:
    saldos = saldos or {}
    saldo_bnb = max(0.0, float(((saldos.get("BNB") or {}).get("total")) or 0.0))
    saldo_usdt = max(0.0, float(((saldos.get("USDT") or {}).get("livre")) or 0.0))
    saldo_minimo = max(0.0, float(os.getenv("BNB_SALDO_MINIMO", "5") or 5))
    compra_referencia = max(0.0, float(os.getenv("BNB_COMPRA_REPOSICAO_USDT", "10") or 10))
    saldo_usdt_apos_compra = max(0.0, saldo_usdt - compra_referencia)

    falta_bnb = max(0.0, saldo_minimo - saldo_bnb)
    compra_sugerida_usdt = 0.0
    if saldo_bnb < saldo_minimo and saldo_usdt >= compra_referencia:
        compra_sugerida_usdt = compra_referencia
    elif saldo_bnb < saldo_minimo and preco_bnb_usdt > 0.0:
        compra_sugerida_usdt = min(compra_referencia, falta_bnb * preco_bnb_usdt)

    quantidade_sugerida_bnb = (compra_sugerida_usdt / preco_bnb_usdt) if preco_bnb_usdt > 0.0 else 0.0
    return {
        "saldo_bnb_total": round(saldo_bnb, 8),
        "saldo_bnb_minimo": round(saldo_minimo, 8),
        "preco_bnb_usdt": round(float(preco_bnb_usdt or 0.0), 8),
        "saldo_usdt_livre": round(saldo_usdt, 8),
        "repor_bnb_agora": saldo_bnb < saldo_minimo and compra_sugerida_usdt > 0.0,
        "falta_bnb": round(falta_bnb, 8),
        "compra_sugerida_usdt": round(compra_sugerida_usdt, 8),
        "quantidade_sugerida_bnb": round(max(0.0, quantidade_sugerida_bnb), 8),
        "saldo_usdt_estimado_apos_compra": round(saldo_usdt_apos_compra, 8),
    }
