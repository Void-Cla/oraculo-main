"""INC-05 — atualizar_snapshot faz read-modify-write atômico e versiona o estado."""
from __future__ import annotations

import os

import pytest


@pytest.mark.asyncio
async def test_atualizar_snapshot_preserva_estado_e_versiona(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "snap.sqlite")
    from src.persistencia.conexao import inicializar_db
    from src.persistencia.repositorio_snapshot import (
        atualizar_snapshot,
        obter_snapshot,
        salvar_snapshot,
    )

    inicializar_db()
    await salvar_snapshot("BTCUSDT", {"x": 1})
    # Cada atualização lê o estado fresco — a chave anterior nunca é perdida.
    await atualizar_snapshot("BTCUSDT", lambda s: {**s, "y": 2})
    await atualizar_snapshot("BTCUSDT", lambda s: {**s, "z": 3})

    final = await obter_snapshot("BTCUSDT")
    assert final is not None
    assert final["x"] == 1 and final["y"] == 2 and final["z"] == 3
    assert final["versao"] >= 2  # incrementa a cada RMW
