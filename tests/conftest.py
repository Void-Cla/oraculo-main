from __future__ import annotations

import asyncio
import os
import shutil
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

(ROOT.parent / "pytest_work").mkdir(parents=True, exist_ok=True)


@pytest.fixture(autouse=True)
def _resetar_estado_global():
    from src.servicos.sessoes import resetar_sessoes_teste
    from src.sinais.fila_sinais import fila_sinais_global
    from src.persistencia.conexao import inicializar_db
    from src.persistencia.repositorio_config import RepositorioConfig

    resetar_sessoes_teste()
    asyncio.run(fila_sinais_global.resetar_teste())
    def _resetar_bloqueio_operacional_teste() -> None:
        db_path = os.environ.get("DB_PATH", "")
        if "pytest_work" not in db_path.replace("\\", "/"):
            return
        inicializar_db()
        asyncio.run(RepositorioConfig.definir("retomada_operacoes_bloqueadas", False))
        asyncio.run(RepositorioConfig.definir("retomada_modo", "normal"))
        asyncio.run(RepositorioConfig.definir("bloqueio_operacional_motivo", ""))

    try:
        _resetar_bloqueio_operacional_teste()
    except Exception:
        pass
    yield
    resetar_sessoes_teste()
    asyncio.run(fila_sinais_global.resetar_teste())
    try:
        _resetar_bloqueio_operacional_teste()
    except Exception:
        pass


@pytest.fixture
def tmp_path() -> Path:
    base = ROOT.parent / "pytest_work" / uuid.uuid4().hex
    base.mkdir(parents=True, exist_ok=True)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)
