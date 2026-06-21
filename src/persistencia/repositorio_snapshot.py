from __future__ import annotations

"""Repositório do snapshot único de estado por símbolo."""

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from src.persistencia.conexao import get_conexao, inicializar_db

# Upsert único — fonte de verdade do SQL de gravação do snapshot (evita duplicação).
_SQL_UPSERT = """
INSERT INTO snapshot_estado (simbolo, estado_json, atualizado_em)
VALUES (?, ?, ?)
ON CONFLICT(simbolo) DO UPDATE SET
  estado_json = excluded.estado_json,
  atualizado_em = excluded.atualizado_em
"""


def _serializar(estado: dict[str, Any]) -> tuple[str, str]:
    payload = json.dumps(estado, ensure_ascii=False, sort_keys=True, default=str)
    return payload, datetime.now(timezone.utc).isoformat()


class RepositorioSnapshot:
    @staticmethod
    async def criar_tabela() -> None:
        inicializar_db()

    @staticmethod
    async def salvar(simbolo: str, estado: dict[str, Any]) -> None:
        if not isinstance(estado, dict):
            raise TypeError("estado_deve_ser_dict")
        payload, atualizado_em = _serializar(estado)
        async with get_conexao() as conn:
            await conn.execute(_SQL_UPSERT, (simbolo.upper(), payload, atualizado_em))
            await conn.commit()

    @staticmethod
    async def atualizar(
        simbolo: str, mutador: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> dict[str, Any]:
        """Read-modify-write ATÔMICO (INC-05): lê, aplica `mutador` e grava na MESMA
        transação `BEGIN IMMEDIATE`, serializando escritas concorrentes no mesmo símbolo
        e eliminando o lost update silencioso. Incrementa `versao` para rastreio.
        """
        chave = simbolo.upper()
        async with get_conexao() as conn:
            await conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = await conn.execute(
                    "SELECT estado_json FROM snapshot_estado WHERE simbolo = ?", (chave,)
                )
                linha = await cursor.fetchone()
                estado_atual = json.loads(linha["estado_json"] or "{}") if linha else {}
                novo = dict(mutador(dict(estado_atual)))
                novo["versao"] = int(estado_atual.get("versao", 0) or 0) + 1
                payload, atualizado_em = _serializar(novo)
                await conn.execute(_SQL_UPSERT, (chave, payload, atualizado_em))
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        novo.setdefault("atualizado_em", atualizado_em)
        return novo

    @staticmethod
    async def obter(simbolo: str) -> dict[str, Any] | None:
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                SELECT estado_json, atualizado_em
                FROM snapshot_estado
                WHERE simbolo = ?
                """,
                (simbolo.upper(),),
            )
            linha = await cursor.fetchone()
        if linha is None:
            return None
        estado = json.loads(linha["estado_json"] or "{}")
        estado.setdefault("atualizado_em", linha["atualizado_em"])
        return estado


async def salvar_snapshot(simbolo: str, estado: dict[str, Any]) -> None:
    await RepositorioSnapshot.salvar(simbolo, estado)


async def obter_snapshot(simbolo: str) -> dict[str, Any] | None:
    return await RepositorioSnapshot.obter(simbolo)


async def atualizar_snapshot(
    simbolo: str, mutador: Callable[[dict[str, Any]], dict[str, Any]]
) -> dict[str, Any]:
    """Atualização atômica do snapshot (preferir a obter+salvar em caminhos concorrentes)."""
    return await RepositorioSnapshot.atualizar(simbolo, mutador)
