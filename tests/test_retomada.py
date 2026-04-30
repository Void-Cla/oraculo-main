from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.tarefas.retomada import _determinar_modo, avaliar_retomada


def test_determinar_modo_normal():
    assert _determinar_modo(1.0, 1.0, pausa_media_horas=4.0, pausa_longa_horas=24.0, variacao_relevante_pct=3.0) == "normal"


def test_determinar_modo_observacao_tempo():
    assert _determinar_modo(5.0, 1.0, pausa_media_horas=4.0, pausa_longa_horas=24.0, variacao_relevante_pct=3.0) == "observacao"


def test_determinar_modo_observacao_variacao():
    assert _determinar_modo(1.0, 5.0, pausa_media_horas=4.0, pausa_longa_horas=24.0, variacao_relevante_pct=3.0) == "observacao"


def test_determinar_modo_recalibracao():
    assert _determinar_modo(25.0, 1.0, pausa_media_horas=4.0, pausa_longa_horas=24.0, variacao_relevante_pct=3.0) == "recalibracao_forcada"


@pytest.mark.asyncio
async def test_avaliar_retomada_sem_historico():
    with (
        patch("src.tarefas.retomada.obter_snapshot", new_callable=AsyncMock) as snapshot,
        patch("src.tarefas.retomada._obter_ultima_ordem", new_callable=AsyncMock) as ultima,
    ):
        snapshot.return_value = None
        ultima.return_value = None
        resultado = await avaliar_retomada("BTCUSDT")

    assert resultado["modo"] == "normal"
    assert resultado["horas_parado"] == 0.0


@pytest.mark.asyncio
async def test_avaliar_retomada_drift_forca_observacao():
    with (
        patch("src.tarefas.retomada.obter_snapshot", new_callable=AsyncMock) as snapshot,
        patch("src.tarefas.retomada._obter_ultima_ordem", new_callable=AsyncMock) as ultima,
        patch("src.tarefas.retomada._obter_preco_atual", new_callable=AsyncMock) as preco,
        patch("src.tarefas.retomada.detectar_drift", new_callable=AsyncMock) as drift,
    ):
        snapshot.return_value = None
        ultima.return_value = {
            "ts": datetime.now(timezone.utc) - timedelta(minutes=20),
            "preco_execucao": 100.0,
        }
        preco.return_value = 101.0
        drift.return_value = {"drift_detectado": True, "razao_volatilidade": 3.0, "mensagem": "drift"}
        resultado = await avaliar_retomada(
            "BTCUSDT",
            ajustes={"pausa_media_h": 4.0, "pausa_longa_h": 24.0, "variacao_pct": 3.0},
        )

    assert resultado["modo"] == "observacao"
