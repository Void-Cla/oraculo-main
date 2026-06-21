"""FASE 7 — métricas de qualidade de sinal (IC, Brier, drawdown) e correlation_id."""
from __future__ import annotations

import pytest

from src.observabilidade.correlacao import contexto_operacao, novo_correlation_id
from src.observabilidade.qualidade_sinal import (
    calcular_brier,
    calcular_drawdown_maximo,
    calcular_ic,
)


def test_ic_perfeito_e_invertido():
    assert calcular_ic([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert calcular_ic([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)


def test_ic_entrada_insuficiente_ou_degenerada():
    assert calcular_ic([1.0], [1.0]) == 0.0
    assert calcular_ic([5, 5, 5], [1, 2, 3]) == 0.0  # variância zero nas predições


def test_brier_perfeito_e_nulo():
    assert calcular_brier([1.0, 0.0, 1.0], [1, 0, 1]) == pytest.approx(0.0)
    assert calcular_brier([0.5, 0.5], [1, 0]) == pytest.approx(0.25)


def test_drawdown_maximo():
    # Pico 100 → vale 70 = 30% de drawdown máximo.
    assert calcular_drawdown_maximo([100, 90, 70, 120]) == pytest.approx(0.30)
    assert calcular_drawdown_maximo([100]) == 0.0


def test_correlation_id_unico_e_contexto():
    assert novo_correlation_id() != novo_correlation_id()
    ctx = contexto_operacao("btcusdt", usuario_id=7)
    assert ctx["simbolo"] == "BTCUSDT"
    assert ctx["usuario_id"] == "7"
    assert len(ctx["correlation_id"]) == 32
