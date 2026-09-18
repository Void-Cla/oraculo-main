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
    # Freios conservadores aplicados ao usuário virtual: respeita o valor do caller dentro
    # da faixa [1, 5] — não força mais sempre 1 (bug de posição-fantasma corrigido).
    # Um valor acima do teto defensivo (9) é limitado a 5, não colapsado para 1.
    risco = _usuario_virtual({"max_trades_abertos": 9}, modo_testnet=True)["risk_config"]
    assert risco["max_trades_abertos"] == 5
    # Valores dentro da faixa são respeitados como estão (ex.: o autotrader real usa 5).
    risco_3 = _usuario_virtual({"max_trades_abertos": 3}, modo_testnet=True)["risk_config"]
    assert risco_3["max_trades_abertos"] == 3
    # Piso continua em 1 (nunca 0 ou negativo).
    risco_0 = _usuario_virtual({"max_trades_abertos": 0}, modo_testnet=True)["risk_config"]
    assert risco_0["max_trades_abertos"] == 1
