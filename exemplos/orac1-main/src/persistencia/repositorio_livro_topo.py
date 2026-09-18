from __future__ import annotations

from typing import Any

from .conexao import get_conexao, inicializar_db


class RepositorioLivroTopo:
    @staticmethod
    async def criar_tabela() -> None:
        inicializar_db()

    @staticmethod
    async def salvar(
        ts: int,
        simbolo: str,
        bid_price: float | None,
        bid_qty: float | None,
        ask_price: float | None,
        ask_qty: float | None,
    ) -> None:
        async with get_conexao() as conn:
            await conn.execute(
                """
                INSERT INTO livro_topo (ts, simbolo, bid_price, bid_qty, ask_price, ask_qty)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(ts, simbolo) DO UPDATE SET
                  bid_price = excluded.bid_price,
                  bid_qty = excluded.bid_qty,
                  ask_price = excluded.ask_price,
                  ask_qty = excluded.ask_qty
                """,
                (ts, simbolo.upper(), bid_price, bid_qty, ask_price, ask_qty),
            )
            await conn.commit()

    @staticmethod
    async def obter_ultimo(simbolo: str) -> dict[str, Any] | None:
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                SELECT ts, simbolo, bid_price, bid_qty, ask_price, ask_qty
                FROM livro_topo
                WHERE simbolo = ?
                ORDER BY ts DESC
                LIMIT 1
                """,
                (simbolo.upper(),),
            )
            linha = await cursor.fetchone()
        return dict(linha) if linha is not None else None

    @staticmethod
    async def listar_ultimos(simbolo: str, limite: int = 100) -> list[dict[str, Any]]:
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                SELECT ts, simbolo, bid_price, bid_qty, ask_price, ask_qty
                FROM livro_topo
                WHERE simbolo = ?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (simbolo.upper(), limite),
            )
            linhas = await cursor.fetchall()
        return list(reversed([dict(linha) for linha in linhas]))
