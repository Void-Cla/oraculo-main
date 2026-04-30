import os

import pytest

from src.persistencia.conexao import inicializar_db
from src.tarefas.recalibracao_startup import _carregar_amostras_recentes


@pytest.mark.asyncio
async def test_carregar_amostras_recentes_usa_schema_real(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "recalibracao.sqlite")
    inicializar_db()

    from src.persistencia.repositorio_features import RepositorioFeatures
    from src.persistencia.repositorio_outcomes import RepositorioOutcomes
    from src.persistencia.repositorio_predicoes import RepositorioPredicoes

    await RepositorioFeatures.salvar(1, "BTCUSDT", {"r_1m": 0.01, "close": 100.0})
    await RepositorioPredicoes.salvar(1, "BTCUSDT", 101.0, 101.0, p_conf=0.7)
    await RepositorioOutcomes.salvar(1, 2, "BTCUSDT", 102.0, 101.0)

    amostras = await _carregar_amostras_recentes("BTCUSDT", 10)

    assert len(amostras) == 1
    assert amostras[0][0]["r_1m"] == 0.01
    assert amostras[0][1] == 102.0
