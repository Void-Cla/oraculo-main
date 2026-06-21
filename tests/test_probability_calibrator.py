"""Testes do ProbabilityCalibrator — estabilidade numérica do sigmoid (BUG-06)."""
from __future__ import annotations

import pytest

from src.probabilidade.probability_calibrator import ProbabilityCalibrator


def test_sigmoid_nao_estoura_com_temperatura_minima_e_predicao_extrema():
    # Antes do guard, temperature ~1e-6 + predição grande causava OverflowError em math.exp.
    calc = ProbabilityCalibrator(temperature=1e-6, scale=10.0)
    resultado = calc.calibrate(raw_prediction=1000.0)
    assert 0.0 <= resultado["prob_up"] <= 1.0
    assert resultado["prob_up"] == pytest.approx(1.0)
    assert resultado["prob_down"] == pytest.approx(0.0)


def test_sigmoid_satura_em_zero_para_predicao_muito_negativa():
    calc = ProbabilityCalibrator(temperature=1e-6, scale=10.0)
    resultado = calc.calibrate(raw_prediction=-1000.0)
    assert resultado["prob_up"] == pytest.approx(0.0)
    assert resultado["prob_down"] == pytest.approx(1.0)


def test_sigmoid_neutro_em_zero():
    calc = ProbabilityCalibrator(temperature=1.0, scale=10.0)
    assert calc.sigmoid(0.0) == pytest.approx(0.5)


def test_probabilidades_somam_um():
    calc = ProbabilityCalibrator()
    r = calc.calibrate(raw_prediction=0.3, ajuste_externo=0.1)
    assert r["prob_up"] + r["prob_down"] == pytest.approx(1.0)
