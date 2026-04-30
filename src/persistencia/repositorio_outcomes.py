from __future__ import annotations

from typing import Any

from .conexao import get_conexao, inicializar_db


class RepositorioOutcomes:
    @staticmethod
    async def criar_tabela() -> None:
        inicializar_db()

    @staticmethod
    async def salvar(ts_previsao: int, ts_target: int, simbolo: str, y_true: float, y_hat: float) -> None:
        err_rel = ((y_true - y_hat) / y_hat) if y_hat else None
        async with get_conexao() as conn:
            await conn.execute(
                """
                INSERT INTO outcomes (ts_previsao, ts_target, simbolo, y_true, y_hat, err_rel)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(ts_previsao, simbolo) DO UPDATE SET
                  ts_target = excluded.ts_target,
                  y_true = excluded.y_true,
                  y_hat = excluded.y_hat,
                  err_rel = excluded.err_rel
                """,
                (ts_previsao, ts_target, simbolo.upper(), y_true, y_hat, err_rel),
            )
            await conn.commit()

    @staticmethod
    async def listar_por_previsao(ts_previsao: int, simbolo: str) -> list[dict[str, Any]]:
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                SELECT ts_previsao, ts_target, simbolo, y_true, y_hat, err_rel
                FROM outcomes
                WHERE ts_previsao = ? AND simbolo = ?
                ORDER BY ts_target ASC
                """,
                (ts_previsao, simbolo.upper()),
            )
            linhas = await cursor.fetchall()
        return [dict(linha) for linha in linhas]

    @staticmethod
    async def listar_recentes(simbolo: str, limite: int = 100) -> list[dict[str, Any]]:
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                SELECT ts_previsao, ts_target, simbolo, y_true, y_hat, err_rel
                FROM outcomes
                WHERE simbolo = ?
                ORDER BY ts_previsao DESC
                LIMIT ?
                """,
                (simbolo.upper(), limite),
            )
            linhas = await cursor.fetchall()
        return list(reversed([dict(linha) for linha in linhas]))
