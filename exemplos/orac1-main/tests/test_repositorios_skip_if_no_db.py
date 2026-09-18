import os

import pytest

from src.persistencia.conexao import inicializar_db
from src.persistencia.repositorio_auditoria import RepositorioAuditoria
from src.persistencia.repositorio_config import RepositorioConfig
from src.persistencia.repositorio_features import RepositorioFeatures
from src.persistencia.repositorio_livro_topo import RepositorioLivroTopo
from src.persistencia.repositorio_ohlcv import RepositorioOhlcv
from src.persistencia.repositorio_outcomes import RepositorioOutcomes
from src.persistencia.repositorio_predicoes import RepositorioPredicoes


@pytest.mark.asyncio
async def test_fluxo_integrado_repositorios_sqlite(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "integrado.sqlite")
    inicializar_db()

    await RepositorioOhlcv.inserir_ohlcv(1, "BTCUSDT", 100, 110, 90, 105, 1.2)
    await RepositorioLivroTopo.salvar(1, "BTCUSDT", 104.9, 3.0, 105.1, 2.0)
    await RepositorioFeatures.salvar(1, "BTCUSDT", {"r_1m": 0.05, "vol5": 0.01})
    await RepositorioPredicoes.salvar(1, "BTCUSDT", 106.0, 106.2, 105.8, 106.6, 0.8, meta={"origem": "teste"})
    await RepositorioOutcomes.salvar(1, 2, "BTCUSDT", 107.0, 106.2)
    await RepositorioConfig.definir("risco.max_posicao", 0.03)
    await RepositorioAuditoria.registrar("BTCUSDT", "teste", {"ok": True}, created_ts=1)

    ult = await RepositorioOhlcv.obter_ultimas("BTCUSDT", limite=1)
    livro = await RepositorioLivroTopo.obter_ultimo("BTCUSDT")
    feat = await RepositorioFeatures.obter(1, "BTCUSDT")
    preds = await RepositorioPredicoes.listar_recentes("BTCUSDT", limite=1)
    outs = await RepositorioOutcomes.listar_por_previsao(1, "BTCUSDT")
    cfg = await RepositorioConfig.obter("risco.max_posicao")
    audit = await RepositorioAuditoria.listar_recentes(simbolo="BTCUSDT", limite=5)

    assert ult[0]["close"] == 105
    assert livro["ask_price"] == 105.1
    assert feat["r_1m"] == 0.05
    assert preds[0]["meta"]["origem"] == "teste"
    assert outs[0]["y_true"] == 107.0
    assert cfg == 0.03
    assert audit[0]["payload"]["ok"] is True
