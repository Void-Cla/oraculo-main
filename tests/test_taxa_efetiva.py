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


# ── taker_pct_operacional (DA-32 — veracidade do front) ──────────────────────
def test_taxa_operacional_com_comissao_zero_do_testnet_usa_piso():
    """Testnet da Binance devolve commissionRates=0 — o front exibia 0.000%, mas o motor
    precifica com piso. `taker_pct_operacional` espelha a taxa REALMENTE usada nas contas."""
    perfil = montar_perfil_taxas(conta={"commissionRates": {"taker": "0"}})
    assert perfil["taker_pct_efetiva"] == 0.0          # verdade da fonte (testnet cobra 0)
    assert perfil["taker_pct_operacional"] == 0.1      # verdade do CÁLCULO (piso 0.1%/perna)


def test_taxa_operacional_com_comissao_real_segue_a_efetiva():
    """Com comissão real (>0), a operacional é idêntica à efetiva (com desconto BNB)."""
    perfil = montar_perfil_taxas(
        conta={"commissionRates": {"taker": "0.00100000"}},
        saldos={"BNB": {"total": 10.0}},
    )
    assert perfil["taker_pct_operacional"] == perfil["taker_pct_efetiva"] == 0.075
