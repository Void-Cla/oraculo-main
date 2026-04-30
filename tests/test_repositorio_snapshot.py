import os

import pytest

from src.persistencia.conexao import inicializar_db
from src.persistencia.repositorio_snapshot import obter_snapshot, salvar_snapshot


@pytest.mark.asyncio
async def test_salvar_e_recuperar_snapshot(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "snapshot.sqlite")
    inicializar_db()

    await salvar_snapshot("BTCUSDT", {"modo_operacao": "normal", "posicao_aberta": False})
    recuperado = await obter_snapshot("BTCUSDT")

    assert recuperado is not None
    assert recuperado["modo_operacao"] == "normal"
    assert recuperado["posicao_aberta"] is False


@pytest.mark.asyncio
async def test_snapshot_inexistente_retorna_none(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "snapshot_vazio.sqlite")
    inicializar_db()

    assert await obter_snapshot("XYZUSDT") is None
