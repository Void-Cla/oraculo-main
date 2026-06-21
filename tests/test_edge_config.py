"""Governança de EDGE — gate de conta real (default-closed, frescor, fail-closed).

Estes testes travam as PROPRIEDADES DE SEGURANÇA do gate: sem edge validado e fresco,
nenhuma entrada real é liberada. Capital perdido não volta.
"""
import os

import pytest

_MS_DIA = 86_400_000


def _setup_db(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "edge.sqlite")
    from src.persistencia.conexao import inicializar_db

    inicializar_db()


def _resultado(simbolo, *, tem_edge, n_trades=50, ic=0.10, net=0.001):
    """Constrói um ResultadoBacktest real do walk_forward (sem rodar sklearn)."""
    from src.backtester.walk_forward import ResultadoBacktest

    return ResultadoBacktest(
        simbolo=simbolo, horizonte=60, n_amostras_teste=1000, n_trades=n_trades,
        ic_walk_forward=ic, retorno_liquido_medio_trade=net, retorno_liquido_total=net * n_trades,
        win_rate_liquido=0.6, max_drawdown=0.1, custo_pct_round_trip=0.003,
        alvo_liquido_pct=0.0, bruto_necessario_pct=0.003, tem_edge_liquido=tem_edge,
    )


# ── Núcleo puro do gate ──────────────────────────────────────────────────────
def test_gate_default_closed_simbolo_desconhecido():
    from src.risco.edge_config import avaliar_edge

    r = avaliar_edge(None, agora_ms=1_000_000)
    assert r.aprovado is False
    assert r.motivo == "edge_inexistente"


def test_gate_inativo_negado():
    from src.risco.edge_config import EdgeConfig, avaliar_edge

    cfg = EdgeConfig(simbolo="BTCUSDT", ativo=False, validado_em_ms=1_000_000)
    r = avaliar_edge(cfg, agora_ms=1_000_000)
    assert r.aprovado is False
    assert r.motivo == "edge_inativo"


def test_gate_expirado_negado():
    from src.risco.edge_config import EdgeConfig, avaliar_edge

    validado = 1_000_000
    cfg = EdgeConfig(simbolo="BTCUSDT", ativo=True, validado_em_ms=validado)
    r = avaliar_edge(cfg, agora_ms=validado + 8 * _MS_DIA, validade_dias=7)
    assert r.aprovado is False
    assert r.motivo == "edge_expirado"


def test_gate_valido_fresco_aprovado():
    from src.risco.edge_config import EdgeConfig, avaliar_edge

    validado = 1_000_000
    cfg = EdgeConfig(simbolo="BTCUSDT", ativo=True, validado_em_ms=validado)
    r = avaliar_edge(cfg, agora_ms=validado + 2 * _MS_DIA, validade_dias=7)
    assert r.aprovado is True
    assert r.motivo == "edge_validado_fresco"


# ── Tradução do veredito do walk-forward → ativo ────────────────────────────
def test_registrar_edge_liga_quando_ha_edge():
    from src.risco.edge_config import RegistroEdge, registrar_resultado_edge

    reg = RegistroEdge()
    cfg = registrar_resultado_edge(reg, _resultado("BNBUSDT", tem_edge=True, n_trades=50, ic=0.10, net=0.001))
    assert cfg.ativo is True


def test_registrar_edge_desliga_quando_sem_edge():
    from src.risco.edge_config import RegistroEdge, registrar_resultado_edge

    reg = RegistroEdge()
    cfg = registrar_resultado_edge(reg, _resultado("BTCUSDT", tem_edge=False, net=-0.001, ic=-0.02))
    assert cfg.ativo is False


def test_registrar_edge_exige_amostra_minima():
    # tem_edge_liquido=True porém amostra abaixo do mínimo (30) → NÃO liga conta real (mais estrito).
    from src.risco.edge_config import RegistroEdge, registrar_resultado_edge

    reg = RegistroEdge()
    cfg = registrar_resultado_edge(reg, _resultado("ETHUSDT", tem_edge=True, n_trades=10, ic=0.10, net=0.001))
    assert cfg.ativo is False


def test_registrar_edge_exige_ic_minimo():
    # net>0 e amostra ok, mas IC abaixo do mínimo (0.02) → sem sinal preditivo confiável → desliga.
    from src.risco.edge_config import RegistroEdge, registrar_resultado_edge

    reg = RegistroEdge()
    cfg = registrar_resultado_edge(reg, _resultado("ETHUSDT", tem_edge=True, n_trades=50, ic=0.005, net=0.001))
    assert cfg.ativo is False


# ── Persistência durável (sobrevive restart) ────────────────────────────────
@pytest.mark.asyncio
async def test_registro_persiste_e_recarrega(tmp_path):
    _setup_db(tmp_path)
    from src.risco.edge_config import RegistroEdge, registrar_resultado_edge

    reg = RegistroEdge()
    registrar_resultado_edge(reg, _resultado("BNBUSDT", tem_edge=True, n_trades=50, ic=0.10, net=0.001))
    await reg.salvar()

    recarregado = await RegistroEdge().carregar()
    cfg = recarregado.obter("BNBUSDT")
    assert cfg is not None
    assert cfg.ativo is True
    assert cfg.simbolo == "BNBUSDT"


@pytest.mark.asyncio
async def test_edge_aprovado_conta_real_default_closed(tmp_path):
    _setup_db(tmp_path)
    from src.risco.edge_config import edge_aprovado_conta_real

    r = await edge_aprovado_conta_real("BTCUSDT")  # registro vazio
    assert r.aprovado is False


@pytest.mark.asyncio
async def test_persistir_resultados_edge_resumo(tmp_path):
    _setup_db(tmp_path)
    from src.risco.edge_config import persistir_resultados_edge

    resumo = await persistir_resultados_edge([
        _resultado("BNBUSDT", tem_edge=True, n_trades=50, ic=0.10, net=0.001),
        _resultado("BTCUSDT", tem_edge=False, net=-0.001, ic=-0.02),
    ])
    assert "BNBUSDT" in resumo["simbolos_aprovados_para_real"]
    assert "BTCUSDT" not in resumo["simbolos_aprovados_para_real"]
    assert resumo["ha_edge_para_real"] is True


# ── Integração com o autotrader (gate na entrada real) ──────────────────────
@pytest.mark.asyncio
async def test_autotrader_gate_nega_sem_edge(tmp_path):
    _setup_db(tmp_path)
    from src.servicos.testnet_auto_trader import TestnetAutoTrader

    trader = TestnetAutoTrader()
    r = await trader._gate_edge_conta_real("BTCUSDT")
    assert r.aprovado is False


@pytest.mark.asyncio
async def test_autotrader_gate_fail_closed_em_erro(tmp_path, monkeypatch):
    _setup_db(tmp_path)
    import src.risco.edge_config as ec
    from src.servicos.testnet_auto_trader import TestnetAutoTrader

    async def _boom(*a, **k):
        raise RuntimeError("indisponivel")

    monkeypatch.setattr(ec, "edge_aprovado_conta_real", _boom)
    trader = TestnetAutoTrader()
    r = await trader._gate_edge_conta_real("BTCUSDT")
    assert r.aprovado is False
    assert r.motivo == "erro_no_gate_fail_closed"
