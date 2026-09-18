from __future__ import annotations

from src.observabilidade import metricas as m


def test_metricas_exportadas_contain_previsoes():
    # incrementa uma metrica e verifica export
    m.previsoes_total.labels(simbolo="BTCUSDT", origem="test").inc()
    payload = m.exportar_metricas()
    assert b"oraculo_previsoes_total" in payload


def test_metricas_orders_counters_and_gauges():
    m.orders_success_total.labels(simbolo="BTCUSDT").inc()
    m.orders_failed_total.labels(simbolo="BTCUSDT").inc()
    m.auto_trader_consecutive_errors.labels(token="tok1", simbolo="BTCUSDT").set(2)
    m.auto_trader_circuit_tripped.labels(token="tok1", simbolo="BTCUSDT").set(0)
    payload = m.exportar_metricas()
    assert b"oraculo_orders_success_total" in payload
    assert b"oraculo_auto_trader_consecutive_errors" in payload
