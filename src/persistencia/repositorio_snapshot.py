from __future__ import annotations

"""Repositório do snapshot único de estado por símbolo."""

import json
from datetime import datetime, timezone
from typing import Any

from src.persistencia.conexao import get_conexao, inicializar_db


class RepositorioSnapshot:
    @staticmethod
    async def criar_tabela() -> None:
        inicializar_db()

    @staticmethod
    async def salvar(simbolo: str, estado: dict[str, Any]) -> None:
        if not isinstance(estado, dict):
            raise TypeError("estado_deve_ser_dict")
        payload = json.dumps(estado, ensure_ascii=False, sort_keys=True, default=str)
        atualizado_em = datetime.now(timezone.utc).isoformat()
        async with get_conexao() as conn:
            await conn.execute(
                """
                INSERT INTO snapshot_estado (simbolo, estado_json, atualizado_em)
                VALUES (?, ?, ?)
                ON CONFLICT(simbolo) DO UPDATE SET
                  estado_json = excluded.estado_json,
                  atualizado_em = excluded.atualizado_em
                """,
                (simbolo.upper(), payload, atualizado_em),
            )
            await conn.commit()

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
