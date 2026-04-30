from __future__ import annotations

from src.servicos.testnet_auto_trader import _novo_estado


def test_novo_estado_contem_circuit_breaker_campos():
    estado = _novo_estado({})
    assert "consecutive_errors" in estado
    assert "circuit_tripped" in estado
    assert "daily_loss_usdt" in estado
    assert "consecutive_errors_limit" in estado
