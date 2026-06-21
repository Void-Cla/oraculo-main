"""Modo exploração (micro-trading 1-15m operacional) — relaxa pisos SÓ em testnet.

Trava de segurança central: dinheiro real NUNCA opera EV negativo, independente do flag.
"""
from src.autotrader.configurador import _usuario_virtual
from src.risco.risk_engine import ev_minimo_liquido_usdt
from src.servicos.testnet_auto_trader import _aplicar_modo_exploracao, _limites_lucro_ciclo


def test_exploracao_off_por_padrao_nao_mexe_nos_pisos(monkeypatch):
    monkeypatch.delenv("AUTO_MODO_EXPLORACAO", raising=False)
    risco = {"filtro_ev_minimo_usdt": 0.01}
    sinal = {"signal_min_prob": 0.6}
    engatou = _aplicar_modo_exploracao(risco, sinal, modo_testnet=True)
    assert engatou is False
    assert "permitir_ev_negativo" not in risco
    assert risco["filtro_ev_minimo_usdt"] == 0.01


def test_exploracao_engata_em_testnet(monkeypatch):
    monkeypatch.setenv("AUTO_MODO_EXPLORACAO", "true")
    monkeypatch.setenv("PERMITIR_CONTA_REAL", "false")
    risco, sinal = {}, {}
    engatou = _aplicar_modo_exploracao(risco, sinal, modo_testnet=True)
    assert engatou is True
    assert risco["permitir_ev_negativo"] is True
    assert risco["lucro_liquido_minimo"] < 0.0
    assert sinal["signal_min_prob"] == 0.0


def test_exploracao_recusa_fora_de_testnet(monkeypatch):
    monkeypatch.setenv("AUTO_MODO_EXPLORACAO", "true")
    monkeypatch.setenv("PERMITIR_CONTA_REAL", "false")
    risco, sinal = {}, {}
    engatou = _aplicar_modo_exploracao(risco, sinal, modo_testnet=False)
    assert engatou is False
    assert "permitir_ev_negativo" not in risco


def test_exploracao_recusa_com_conta_real_ligada(monkeypatch):
    monkeypatch.setenv("AUTO_MODO_EXPLORACAO", "true")
    monkeypatch.setenv("PERMITIR_CONTA_REAL", "true")
    risco, sinal = {}, {}
    engatou = _aplicar_modo_exploracao(risco, sinal, modo_testnet=True)
    assert engatou is False
    assert "permitir_ev_negativo" not in risco


def test_usuario_virtual_testnet_exploracao_zera_pisos():
    risco = {"permitir_ev_negativo": True, "filtro_ev_minimo_usdt": -1e9}
    u = _usuario_virtual(risco, modo_testnet=True)
    rc = u["risk_config"]
    assert rc["permitir_ev_negativo"] is True
    assert rc["lucro_liquido_minimo"] < 0.0          # aceita EV negativo (exploração)
    assert rc["lucro_liquido_minimo_usdt"] < 0.0
    assert ev_minimo_liquido_usdt(rc) < 0.0          # permite EV negativo


def test_usuario_virtual_real_proibe_ev_negativo_mesmo_com_flag():
    # SEGURANÇA: mesmo recebendo o flag, conta real força hard floor e proíbe EV negativo.
    risco = {"permitir_ev_negativo": True, "filtro_ev_minimo_usdt": -1e9}
    u = _usuario_virtual(risco, modo_testnet=False)
    rc = u["risk_config"]
    assert rc["permitir_ev_negativo"] is False
    assert rc["filtro_ev_minimo_usdt"] >= 0.01
    assert ev_minimo_liquido_usdt(rc) >= 0.01


def test_ev_minimo_padrao_mantem_hard_floor():
    assert ev_minimo_liquido_usdt({"filtro_ev_minimo_usdt": 0.0}) == 0.01
    assert ev_minimo_liquido_usdt({"filtro_ev_minimo_usdt": 0.05}) == 0.05


def test_limites_lucro_exploracao_zera_piso_de_saida():
    base = _limites_lucro_ciclo(notional_entrada=12.0, ajustes_sinal={}, perfil={})
    assert base["minimo_usdt"] >= 0.01  # piso normal mantém hard floor
    expl = _limites_lucro_ciclo(
        notional_entrada=12.0,
        ajustes_sinal={"modo_exploracao": True, "auto_lucro_liquido_minimo_usdt": 0.0, "signal_min_net_profit_pct": -1.0},
        perfil={},
    )
    assert expl["minimo_usdt"] == 0.0  # exploração permite ciclar sem piso de saída
