"""P2 — o auto-trader persiste cada execução na tabela `ordens` (visibilidade UI + ML)."""
import os

import pytest


def _setup_db(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "p2.sqlite")
    from src.persistencia.conexao import inicializar_db
    inicializar_db()


class _AprovacaoFalsa:
    stop_loss_pct = 0.01
    take_profit_pct = 0.02


@pytest.mark.asyncio
async def test_persistir_ordem_executada_grava_na_tabela(tmp_path):
    _setup_db(tmp_path)
    from src.servicos.testnet_auto_trader import TestnetAutoTrader
    from src.persistencia.repositorio_ordens import RepositorioOrdens

    trader = TestnetAutoTrader()
    oid = await trader._persistir_ordem_executada(
        simbolo="BTCUSDT", lado="BUY", modo_testnet=True,
        preco=60000.0, quantidade=0.001, notional=60.0,
        aprovacao=_AprovacaoFalsa(),
        ordem={"orderId": 1, "status": "FILLED", "executedQty": "0.001", "clientOrderId": "x"},
    )
    assert oid is not None
    ordens = await RepositorioOrdens.listar_recentes(simbolo="BTCUSDT", limite=10)
    assert len(ordens) == 1
    assert ordens[0]["lado"] == "BUY"
    assert ordens[0]["status"] == "EXECUTADA"
    assert ordens[0]["modo"] == "testnet"
    assert ordens[0]["quantidade"] == pytest.approx(0.001)
    assert ordens[0]["detalhe"]["origem"] == "auto_trader"


@pytest.mark.asyncio
async def test_ordem_persistida_recebe_resultado_no_fechamento(tmp_path):
    # Fluxo P2 completo: persiste a venda → grava ciclo_ordem_id_venda → registrar_resultado anexa lucro.
    _setup_db(tmp_path)
    from src.servicos.testnet_auto_trader import TestnetAutoTrader
    from src.persistencia.repositorio_ordens import RepositorioOrdens

    trader = TestnetAutoTrader()
    oid = await trader._persistir_ordem_executada(
        simbolo="ETHUSDT", lado="SELL", modo_testnet=True,
        preco=3000.0, quantidade=0.02, notional=60.0,
        aprovacao=_AprovacaoFalsa(),
        ordem={"orderId": 9, "status": "FILLED", "executedQty": "0.02"},
    )
    assert oid is not None
    await RepositorioOrdens.registrar_resultado(
        oid, lucro_usdt=0.42, lucro_pct=0.007, duracao_ms=120000, regime="TREND_UP", estrategia="micro",
    )
    ordem = await RepositorioOrdens.obter(oid)
    assert ordem["lucro_usdt"] == pytest.approx(0.42)
    assert ordem["regime"] == "TREND_UP"
    assert ordem["estrategia"] == "micro"


@pytest.mark.asyncio
async def test_persistir_best_effort_nao_propaga_erro(tmp_path, monkeypatch):
    # Falha ao persistir NÃO derruba o ciclo — retorna None e loga.
    _setup_db(tmp_path)
    from src.servicos.testnet_auto_trader import TestnetAutoTrader
    from src.persistencia import repositorio_ordens

    async def _boom(*a, **k):
        raise RuntimeError("db_indisponivel")

    monkeypatch.setattr(repositorio_ordens.RepositorioOrdens, "criar", _boom)
    trader = TestnetAutoTrader()
    oid = await trader._persistir_ordem_executada(
        simbolo="BTCUSDT", lado="BUY", modo_testnet=True,
        preco=60000.0, quantidade=0.001, notional=60.0,
        aprovacao=_AprovacaoFalsa(), ordem={"status": "FILLED"},
    )
    assert oid is None
