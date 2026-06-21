"""FASE 6 — valida a decomposição: módulos de autotrader e re-export do god-file."""
from __future__ import annotations


def test_calculos_extraido_e_reexportado():
    from src.autotrader.calculos import _custos_ciclo_pct, _normalizar_notional_operacional
    from src.servicos import testnet_auto_trader as god

    # Re-export: o god-file expõe os mesmos objetos importados do pacote autotrader.
    assert god._normalizar_notional_operacional is _normalizar_notional_operacional
    assert god._custos_ciclo_pct is _custos_ciclo_pct
    # Custo round-trip: fee*2 + slippage*2 + spread.
    custo = _custos_ciclo_pct({"signal_trade_fee_pct": 0.001, "signal_slippage_pct": 0.0005}, 0.0002)
    assert custo == 0.001 * 2 + 0.0005 * 2 + 0.0002


def test_configurador_extraido_e_reexportado():
    from src.autotrader.configurador import _ajustes_microtrading_auto, _usuario_virtual
    from src.servicos import testnet_auto_trader as god

    assert god._usuario_virtual is _usuario_virtual
    assert god._ajustes_microtrading_auto is _ajustes_microtrading_auto
    # Freios conservadores aplicados ao usuário virtual.
    risco = _usuario_virtual({"max_trades_abertos": 9}, modo_testnet=True)["risk_config"]
    assert risco["max_trades_abertos"] == 1
