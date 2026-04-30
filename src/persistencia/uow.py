from __future__ import annotations

from typing import Any, Iterable

import aiosqlite

from .conexao import criar_conexao


class UnidadeDeTrabalho:
    def __init__(self) -> None:
        self._conn: aiosqlite.Connection | None = None

    @property
    def conexao(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("unidade de trabalho nao iniciada")
        return self._conn

    async def __aenter__(self) -> "UnidadeDeTrabalho":
        self._conn = await criar_conexao()
        await self._conn.execute("BEGIN")
        return self

    async def executar(self, sql: str, parametros: Iterable[Any] = ()) -> aiosqlite.Cursor:
        return await self.conexao.execute(sql, tuple(parametros))

    async def consultar_um(self, sql: str, parametros: Iterable[Any] = ()) -> aiosqlite.Row | None:
        cursor = await self.executar(sql, parametros)
        return await cursor.fetchone()

    async def consultar_todos(self, sql: str, parametros: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        cursor = await self.executar(sql, parametros)
        return await cursor.fetchall()

    async def commit(self) -> None:
        await self.conexao.commit()

    async def rollback(self) -> None:
        await self.conexao.rollback()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                await self.commit()
            else:
                await self.rollback()
        finally:
            if self._conn is not None:
                await self._conn.close()
                self._conn = None
