from __future__ import annotations

from typing import Any

# Hardcoded — sem os.getenv
_TAXA_PADRAO_DECIMAL: float = 0.001      # 0.1% padrão Binance
_BNB_SALDO_MINIMO: float = 0.01          # mínimo de BNB para ativar desconto
_BNB_DESCONTO_RATIO: float = 0.25        # 25% de desconto com BNB


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
    maker  = _taxa_decimal(conta, "maker",  "makerCommission",  _TAXA_PADRAO_DECIMAL)
    taker  = _taxa_decimal(conta, "taker",  "takerCommission",  _TAXA_PADRAO_DECIMAL)
    buyer  = _taxa_decimal(conta, "buyer",  "buyerCommission",  _TAXA_PADRAO_DECIMAL)
    seller = _taxa_decimal(conta, "seller", "sellerCommission", _TAXA_PADRAO_DECIMAL)

    saldo_bnb = float(((saldos.get("BNB") or {}).get("total")) or 0.0)
    desconto_ativo = saldo_bnb >= _BNB_SALDO_MINIMO
    fator = (1.0 - _BNB_DESCONTO_RATIO) if desconto_ativo else 1.0

    return {
        "maker_decimal":           maker,
        "taker_decimal":           taker,
        "buyer_decimal":           buyer,
        "seller_decimal":          seller,
        "maker_decimal_efetiva":   maker  * fator,
        "taker_decimal_efetiva":   taker  * fator,
        "buyer_decimal_efetiva":   buyer  * fator,
        "seller_decimal_efetiva":  seller * fator,
        "maker_pct":               round(maker  * 100.0, 4),
        "taker_pct":               round(taker  * 100.0, 4),
        "maker_pct_efetiva":       round(maker  * fator * 100.0, 4),
        "taker_pct_efetiva":       round(taker  * fator * 100.0, 4),
        "desconto_bnb_ativo":      desconto_ativo,
        "desconto_bnb_pct":        round(_BNB_DESCONTO_RATIO * 100.0, 2) if desconto_ativo else 0.0,
        "saldo_bnb_total":         saldo_bnb,
        "saldo_bnb_minimo":        _BNB_SALDO_MINIMO,
        "inferencia_por_saldo_bnb": desconto_ativo,
    }


def aplicar_taxa_efetiva(ajustes_sinal: dict[str, Any], perfil_taxas: dict[str, Any]) -> dict[str, Any]:
    """FONTE ÚNICA (INC-03): injeta a taxa taker efetiva (com desconto BNB) em `ajustes_sinal`.

    Usada tanto pelo autotrader quanto pelo fluxo manual, para que o MESMO trade receba a
    MESMA avaliação de EV independentemente do caminho que o acionou.
    """
    ajustes_exec = dict(ajustes_sinal)
    taxa_taker_efetiva = float((perfil_taxas or {}).get("taker_decimal_efetiva", 0.0) or 0.0)
    if taxa_taker_efetiva > 0.0:
        ajustes_exec["signal_trade_fee_pct"] = taxa_taker_efetiva
    return ajustes_exec
