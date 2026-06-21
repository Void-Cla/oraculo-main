import pytest

from src.risco.filtro_ev import calcular_ev_liquido, sinal_passa_filtro_ev


def test_ev_positivo_aprovado():
    passou, ev = sinal_passa_filtro_ev(
        prob_up=0.7,
        prob_down=0.3,
        ganho_bruto_usdt=10.0,
        perda_bruta_usdt=5.0,
        valor_ordem_usdt=100.0,
        ev_minimo_usdt=1.0,
    )
    assert passou is True
    assert ev > 1.0


def test_ev_negativo_rejeitado():
    passou, ev = sinal_passa_filtro_ev(
        prob_up=0.4,
        prob_down=0.6,
        ganho_bruto_usdt=2.0,
        perda_bruta_usdt=8.0,
        valor_ordem_usdt=100.0,
        ev_minimo_usdt=1.0,
    )
    assert passou is False
    assert ev < 1.0


def test_custos_embutidos_tornam_ev_neutro_negativo():
    ev = calcular_ev_liquido(
        prob_up=0.5,
        prob_down=0.5,
        ganho_bruto_usdt=1.0,
        perda_bruta_usdt=1.0,
        valor_ordem_usdt=100.0,
    )
    assert ev < 0.0


def test_custo_taxa_e_slippage_sao_round_trip():
    # EV bruto neutro (0): o EV líquido deve ser exatamente -(taxa×2 + slippage×2).
    # Trava o invariante round-trip (DA-02) e impede regredir slippage para perna única.
    # taxa 0.1% → 0.001; round-trip taxa = 100*0.001*2 = 0.20
    # slippage 0.0005 → round-trip slippage = 100*0.0005*2 = 0.10  → custo total 0.30
    ev = calcular_ev_liquido(
        prob_up=0.5,
        prob_down=0.5,
        ganho_bruto_usdt=1.0,
        perda_bruta_usdt=1.0,
        valor_ordem_usdt=100.0,
        taxa_taker_pct=0.1,
        slippage_pct=0.0005,
    )
    assert ev == pytest.approx(-0.30)
