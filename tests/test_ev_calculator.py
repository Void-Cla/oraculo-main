"""Testes do EVCalculator — foco na corretude do custo round-trip (BUG-02)."""
from __future__ import annotations

import pytest

from src.probabilidade.ev_calculator import NUMERO_DE_PERNAS, EVCalculator


def test_custos_totais_conta_round_trip():
    # Entrada: fee=0.001, slippage=0.0005 (por perna), spread=0.0002 (custo único).
    # Esperado: (0.001 + 0.0005) * 2 + 0.0002 = 0.0032
    calc = EVCalculator(fee=0.001, slippage=0.0005)
    assert calc.custos_totais(spread=0.0002) == pytest.approx(0.0032)


def test_numero_de_pernas_e_dois():
    # Invariante explícito: toda operação completa tem 2 pernas (entrada + saída).
    assert NUMERO_DE_PERNAS == 2


def test_custo_round_trip_e_o_dobro_do_single_leg_sem_spread():
    calc = EVCalculator(fee=0.001, slippage=0.0005)
    single_leg = calc.fee + calc.slippage
    assert calc.custos_totais(spread=0.0) == pytest.approx(single_leg * 2)


def test_ev_diminui_quando_fee_aumenta():
    # Propriedade: aumentar a taxa nunca aumenta o EV.
    barato = EVCalculator(fee=0.001, slippage=0.0005)
    caro = EVCalculator(fee=0.005, slippage=0.0005)
    ev_barato = barato.calculate(p_win=0.6, avg_win=0.01, avg_loss=0.008)
    ev_caro = caro.calculate(p_win=0.6, avg_win=0.01, avg_loss=0.008)
    assert ev_caro <= ev_barato


def test_ev_com_custo_nunca_maior_que_ev_sem_custo():
    # Propriedade matemática: subtrair custo só pode reduzir o EV.
    calc = EVCalculator(fee=0.001, slippage=0.0005)
    sem_custo = EVCalculator(fee=0.0, slippage=0.0)
    args = dict(p_win=0.55, avg_win=0.012, avg_loss=0.009, spread=0.0001)
    assert calc.calculate(**args) <= sem_custo.calculate(**args)
