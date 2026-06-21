"""INC-03 — fonte única da taxa efetiva: mesmo trade, mesma avaliação de fee."""
from __future__ import annotations

from src.multiativo.fee_optimizer import aplicar_taxa_efetiva, montar_perfil_taxas


def test_aplicar_taxa_efetiva_injeta_taker_com_desconto_bnb():
    # Conta com taker 0.1% e saldo BNB suficiente → taxa efetiva com desconto.
    perfil = montar_perfil_taxas(
        conta={"commissionRates": {"taker": "0.00100000"}},
        saldos={"BNB": {"total": 10.0}},
    )
    ajustes = aplicar_taxa_efetiva({"signal_trade_fee_pct": 0.001}, perfil)
    assert ajustes["signal_trade_fee_pct"] == perfil["taker_decimal_efetiva"]
    assert ajustes["signal_trade_fee_pct"] < 0.001  # desconto BNB aplicado


def test_aplicar_taxa_efetiva_sem_perfil_nao_altera():
    base = {"signal_trade_fee_pct": 0.001}
    assert aplicar_taxa_efetiva(base, {}) == base
    assert aplicar_taxa_efetiva(base, {"taker_decimal_efetiva": 0.0}) == base
