import os

import pytest

from src.persistencia.repositorio_ordens import RepositorioOrdens
from src.sinais.fila_sinais import fila_sinais_global


def _payload_klines() -> list[dict[str, float]]:
    # 30 velas sintéticas com tendência de alta suave — material suficiente para o pipeline.
    klines = []
    for idx in range(1, 31):
        close = 100.0 + (idx * 0.5)
        klines.append(
            {
                "ts": idx,
                "open": close - 0.2,
                "high": close + 0.4,
                "low": close - 0.5,
                "close": close,
                "volume": 15 + idx,
            }
        )
    return klines


@pytest.mark.asyncio
async def test_pipeline(tmp_path):
    # Banco isolado por teste (PT-02): nada de depender de usuário pré-existente no banco real.
    os.environ["DB_PATH"] = str(tmp_path / "pipeline.sqlite")

    from src.persistencia.conexao import inicializar_db
    from src.persistencia.repositorio_usuarios import RepositorioUsuarios

    inicializar_db()
    # Onboarding real do usuário — o fluxo exige usuário existente e ativo.
    usuario_id = await RepositorioUsuarios.criar(
        nome="trader_pipeline",
        testnet=True,
        ativo=True,
        risk_config={"risk_per_trade": 0.01, "max_drawdown": 0.05, "max_exposicao_ativo": 0.2},
    )

    from src.servicos.fluxo_usuario_sinais import executar_fluxo_usuario_sinal

    payload = {
        "simbolo": "BTCUSDT",
        "publicar_fila": True,
        "klines": _payload_klines(),
        "livro_topo": {"bid_price": 115.04, "bid_qty": 5.0, "ask_price": 115.06, "ask_qty": 4.0},
        "saldo": {"saldo_total": 1000.0, "saldo_livre": 950.0},
        "estado_execucao": {"drawdown_atual": 0.01, "exposicao_ativo": 0.0, "trades_abertos": 0},
        "noticias": [],
    }

    resultado = await executar_fluxo_usuario_sinal(usuario_id, payload)

    # O fluxo executou ponta a ponta sem NameError (regressão do BUG-01).
    assert "sinal" in resultado
    assert "aprovacao_risco" in resultado

    ordem_id = resultado.get("ordem_id")
    assert ordem_id is not None, "Ordem não foi criada"

    ordem = await RepositorioOrdens.obter(ordem_id)
    assert ordem is not None, "Ordem não encontrada no banco de dados"

    fila_snapshot = await fila_sinais_global.snapshot()
    assert any(item["ordem_id"] == ordem_id for item in fila_snapshot), "Sinal não foi publicado na fila"
