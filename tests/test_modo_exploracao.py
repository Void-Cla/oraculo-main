"""Modo exploração (micro-trading 1-15m operacional) — relaxa pisos SÓ em testnet.

Trava de segurança central: dinheiro real NUNCA opera EV negativo, independente do flag.
"""
import pytest

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


def test_exploracao_relaxa_confirmacao_multi_timeframe(monkeypatch):
    """Decisão do dono (2026-07-12): em exploração, a confirmação multi-TF exige só 1 janela
    ≥0.08% (produção segue 3 janelas ≥0.15%). Sem exploração, as chaves nem são escritas."""
    monkeypatch.setenv("AUTO_MODO_EXPLORACAO", "true")
    monkeypatch.setenv("PERMITIR_CONTA_REAL", "false")
    risco, sinal = {}, {"signal_confirm_threshold": 3}
    assert _aplicar_modo_exploracao(risco, sinal, modo_testnet=True) is True
    assert sinal["signal_confirm_threshold"] == 1
    assert sinal["signal_janela_limiar_pct"] == pytest.approx(0.0008)

    monkeypatch.delenv("AUTO_MODO_EXPLORACAO", raising=False)
    sinal_sem_exploracao = {"signal_confirm_threshold": 3}
    assert _aplicar_modo_exploracao({}, sinal_sem_exploracao, modo_testnet=True) is False
    assert sinal_sem_exploracao["signal_confirm_threshold"] == 3
    assert "signal_janela_limiar_pct" not in sinal_sem_exploracao


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


# ── TAMANHO DIRIGIDO PELO FRONTEND (DA-31) ───────────────────────────────────
def test_usuario_virtual_testnet_notional_dirige_tetos_de_risco():
    """Em testnet, o notional escolhido no front (slider %) solta os tetos de risco para que a
    posição reflita a % — em vez de ser esmagada pelo teto hardcoded de perda $0.20."""
    # notional de $10.000 (ex.: 60% de uma carteira) — o teto de perda deve escalar com ele.
    u = _usuario_virtual({}, modo_testnet=True, notional_usdt=10_000.0)
    rc = u["risk_config"]
    # max_loss = notional * stop_referencia(2%) = $200 (não os $0.20 hardcoded).
    assert rc["max_loss_trade_usdt"] == pytest.approx(200.0)
    assert rc["risk_per_trade"] >= 1.0            # não é mais o gargalo
    assert rc["max_exposicao_ativo"] >= 0.95      # exposição solta em testnet


def test_usuario_virtual_testnet_sem_notional_mantem_tetos_conservadores():
    """Sem notional informado, mesmo em testnet, os tetos conservadores absolutos permanecem
    (não é regressão do comportamento antigo para quem não passa notional)."""
    u = _usuario_virtual({}, modo_testnet=True)  # notional_usdt=0 (default)
    rc = u["risk_config"]
    assert rc["max_loss_trade_usdt"] == pytest.approx(0.20)
    assert rc["risk_per_trade"] == pytest.approx(0.005)
    assert rc["max_exposicao_ativo"] == pytest.approx(0.20)


def test_usuario_virtual_conta_real_ignora_notional_e_mantem_tetos_seguros():
    """SEGURANÇA (não-negociável): em CONTA REAL, o notional do front NÃO solta os tetos —
    perda máx $0.20, 0.5% do saldo, 20% de exposição por ativo permanecem absolutos."""
    u = _usuario_virtual({}, modo_testnet=False, notional_usdt=1_000_000.0)
    rc = u["risk_config"]
    assert rc["max_loss_trade_usdt"] == pytest.approx(0.20)
    assert rc["risk_per_trade"] == pytest.approx(0.005)
    assert rc["max_exposicao_ativo"] == pytest.approx(0.20)


# ── FREQUÊNCIA (DA-32): cadência solta em testnet, freios originais em conta real ─
def test_usuario_virtual_testnet_permite_ate_12_trades_hora_cooldown_3min():
    """Testnet valida com VOLUME — cadência até 12/h e cooldown ≥3min (anti-spam mantido).
    Só CADÊNCIA muda: os gates de qualidade (EV/lucro mínimo/consenso) não são tocados aqui."""
    rc = _usuario_virtual({"max_trades_por_hora": 40, "cooldown_minutos": 1}, modo_testnet=True)["risk_config"]
    assert rc["max_trades_por_hora"] == 12   # caller pediu 40 → teto 12
    assert rc["cooldown_segundos"] == 45       # caller pediu 1min → piso 45s em testnet


def test_usuario_virtual_conta_real_mantem_3_trades_hora_cooldown_10min():
    rc = _usuario_virtual({"max_trades_por_hora": 40, "cooldown_minutos": 1}, modo_testnet=False)["risk_config"]
    assert rc["max_trades_por_hora"] == 3    # freio original de conta real intocado
    assert rc["cooldown_minutos"] == 10


def test_limites_lucro_exploracao_preserva_um_centavo_liquido():
    base = _limites_lucro_ciclo(notional_entrada=12.0, ajustes_sinal={}, perfil={})
    assert base["minimo_usdt"] >= 0.01  # piso normal mantém hard floor
    expl = _limites_lucro_ciclo(
        notional_entrada=12.0,
        ajustes_sinal={"modo_exploracao": True, "auto_lucro_liquido_minimo_usdt": 0.0, "signal_min_net_profit_pct": -1.0},
        perfil={},
    )
    assert expl["minimo_usdt"] >= 0.01  # exploração não aceita lucro bruto sem lucro líquido
