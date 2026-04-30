from __future__ import annotations

"""Recalibração do modelo online na retomada após pausa longa."""

import json
from typing import Any

from src.core.settings import env_int
from src.modelagem.gerenciador_modelo import GerenciadorModelo
from src.observabilidade.logger import get_logger
from src.persistencia.conexao import get_conexao

LOG = get_logger("recalibracao_startup")


async def _carregar_amostras_recentes(simbolo: str, limite: int) -> list[tuple[dict[str, Any], float]]:
    async with get_conexao() as conn:
        cursor = await conn.execute(
            """
            SELECT f.features_json, o.y_true
            FROM features_1m f
            JOIN predictions p
              ON p.created_ts = f.ts AND p.simbolo = f.simbolo
            JOIN outcomes o
              ON o.ts_previsao = p.created_ts AND o.simbolo = p.simbolo
            WHERE f.simbolo = ?
            ORDER BY f.ts DESC
            LIMIT ?
            """,
            (simbolo.upper(), limite),
        )
        linhas = await cursor.fetchall()

    amostras: list[tuple[dict[str, Any], float]] = []
    for linha in reversed(linhas):
        if linha["features_json"] is None or linha["y_true"] is None:
            continue
        amostras.append((json.loads(linha["features_json"]), float(linha["y_true"])))
    return amostras


async def recalibrar_ao_religar(simbolo: str, *, candles: int | None = None) -> dict[str, Any]:
    """Executa partial_fit com amostras persistidas e retorna status sem lançar em lote vazio."""
    limite = int(candles if candles is not None else env_int("RECALIBRACAO_CANDLES", 60, minimo=1))
    amostras = await _carregar_amostras_recentes(simbolo, limite)
    if not amostras:
        LOG.warning("recalibracao_sem_amostras", extra={"simbolo": simbolo.upper(), "limite": limite})
        return {"status": "sem_dados", "amostras": 0}

    gerenciador = GerenciadorModelo(simbolo=simbolo)
    atualizados = 0
    erros = 0
    for features, y_real in amostras:
        try:
            gerenciador.partial_fit(features, y_real)
            atualizados += 1
        except Exception as exc:
            erros += 1
            LOG.warning("partial_fit_erro", extra={"simbolo": simbolo.upper(), "erro": str(exc)})

    if atualizados <= 0:
        return {"status": "sem_amostras_validas", "amostras": 0, "erros": erros}

    gerenciador.salvar()
    LOG.info("recalibracao_concluida", extra={"simbolo": simbolo.upper(), "amostras": atualizados, "erros": erros})
    return {"status": "ok", "amostras": atualizados, "erros": erros}
