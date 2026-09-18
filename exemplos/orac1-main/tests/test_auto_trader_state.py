from __future__ import annotations

from src.servicos.testnet_auto_trader import (
    TestnetAutoTrader as TraderAutoTestnet,
    _aplicar_config_estado,
    _novo_estado,
    _obter_estado_par,
)


def test_novo_estado_contem_circuit_breaker_campos():
    estado = _novo_estado({})
    assert "consecutive_errors" in estado
    assert "circuit_tripped" in estado
    assert "daily_loss_usdt" in estado
    assert "consecutive_errors_limit" in estado


def test_status_auto_trader_expoe_seguranca_para_ui():
    trader = TraderAutoTestnet()
    trader._state["tok"] = _novo_estado({"simbolo": "BTCUSDT"})

    status = trader.status("tok")

    assert status["pronto"] is False
    assert status["sincronizado"] is False
    assert "aguardando_primeira_leitura" in status["bloqueios"]
    assert status["idade_dados_ms"]["saldo"] is None
    assert status["seguranca"]["pronto"] is False
    assert status["historico_ciclos"] == []
    assert isinstance(status["config"]["perfis_capital"], dict)


def test_estado_auto_trader_suporta_capital_por_perfil():
    estado = _novo_estado(
        {
            "simbolo": "BTCUSDT",
            "notional_usdt": 5.0,
            "perfis_capital": {
                "mini": {"ativo": True, "capital_usdt": 12.0},
                "ganancioso": {"ativo": False, "capital_usdt": 3.0},
            },
        }
    )
    assert estado["notional_usdt"] == 12.0
    assert estado["config_perfis_capital"]["ganancioso"]["ativo"] is False

    _aplicar_config_estado(
        estado,
        {
            "perfis_capital": {
                "mini": {"ativo": True, "capital_usdt": 7.0},
                "diario": {"ativo": True, "capital_usdt": 3.0},
            }
        },
    )
    assert estado["notional_usdt"] == 10.0


def test_estado_por_par_sincroniza_config_perfis_do_global():
    estado = _novo_estado(
        {
            "simbolo": "BTCUSDT",
            "perfis_capital": {
                "mini": {"ativo": True, "capital_usdt": 12.0},
            },
        }
    )
    estado["pares_estado"]["ETHUSDT"] = {
        "simbolo": "ETHUSDT",
        "config_perfis_capital": {},
    }

    estado_par = _obter_estado_par(estado, "ETHUSDT")

    assert estado_par["config_perfis_capital"]["mini"]["capital_usdt"] == 12.0

    _aplicar_config_estado(
        estado,
        {
            "perfis_capital": {
                "mini": {"ativo": True, "capital_usdt": 7.0},
                "diario": {"ativo": True, "capital_usdt": 3.0},
            }
        },
    )

    estado_par = _obter_estado_par(estado, "ETHUSDT")

    assert estado_par["config_perfis_capital"]["mini"]["capital_usdt"] == 7.0
    assert estado_par["config_perfis_capital"]["diario"]["capital_usdt"] == 3.0
