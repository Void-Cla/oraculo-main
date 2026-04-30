import os

import pytest

from src.persistencia.conexao import inicializar_db
from src.persistencia.repositorio_ohlcv import RepositorioOhlcv


@pytest.mark.asyncio
async def test_inserir_e_obter_ohlcv(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "test_oraculo.sqlite")
    inicializar_db()

    await RepositorioOhlcv.criar_tabela()
    await RepositorioOhlcv.inserir_ohlcv(1, "TEST", 10.0, 11.0, 9.5, 10.5, 100.0)
    rows = await RepositorioOhlcv.obter_ultimas("TEST", limite=10)

    assert len(rows) == 1
    assert rows[0]["ts"] == 1
    assert rows[0]["open"] == 10.0
    assert rows[0]["close"] == 10.5
