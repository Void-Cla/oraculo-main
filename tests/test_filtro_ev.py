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
