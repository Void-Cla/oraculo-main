from __future__ import annotations

"""Repositório OHLCV.

Fornece funções para inserir e ler candles (1m e 15s) no banco SQLite.
Usado por coletores e pipelines de features.
"""

from typing import Any

from .conexao import get_conexao, inicializar_db


def _linha_para_dict(linha: Any) -> dict[str, Any]:
    return dict(linha) if linha is not None else {}


class RepositorioOhlcv:
    @staticmethod
    async def criar_tabela() -> None:
        inicializar_db()

    @staticmethod
    async def inserir_ohlcv(
        ts: int,
        simbolo: str,
        open_p: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> None:
        async with get_conexao() as conn:
            await conn.execute(
                """
                INSERT INTO ohlcv_1m (ts, simbolo, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ts, simbolo) DO UPDATE SET
                  open = excluded.open,
                  high = excluded.high,
                  low = excluded.low,
                  close = excluded.close,
                  volume = excluded.volume
                """,
                (ts, simbolo.upper(), open_p, high, low, close, volume),
            )
            await conn.commit()

    @staticmethod
    async def inserir_ohlcv_15s(
        ts: int,
        simbolo: str,
        open_p: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> None:
        async with get_conexao() as conn:
            await conn.execute(
                """
                INSERT INTO ohlcv_15s (ts, simbolo, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ts, simbolo) DO UPDATE SET
                  open = excluded.open,
                  high = excluded.high,
                  low = excluded.low,
                  close = excluded.close,
                  volume = excluded.volume
                """,
                (ts, simbolo.upper(), open_p, high, low, close, volume),
            )
            await conn.commit()

    @staticmethod
    async def inserir_varias(registros: list[dict[str, Any]]) -> None:
        if not registros:
            return
        async with get_conexao() as conn:
            await conn.executemany(
                """
                INSERT INTO ohlcv_1m (ts, simbolo, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ts, simbolo) DO UPDATE SET
                  open = excluded.open,
                  high = excluded.high,
                  low = excluded.low,
                  close = excluded.close,
                  volume = excluded.volume
                """,
                [
                    (
                        int(item["ts"]),
                        str(item["simbolo"]).upper(),
                        float(item["open"]),
                        float(item["high"]),
                        float(item["low"]),
                        float(item["close"]),
                        float(item["volume"]),
                    )
                    for item in registros
                ],
            )
            await conn.commit()

    @staticmethod
    async def inserir_varias_15s(registros: list[dict[str, Any]]) -> None:
        if not registros:
            return
        async with get_conexao() as conn:
            await conn.executemany(
                """
                INSERT INTO ohlcv_15s (ts, simbolo, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ts, simbolo) DO UPDATE SET
                  open = excluded.open,
                  high = excluded.high,
                  low = excluded.low,
                  close = excluded.close,
                  volume = excluded.volume
                """,
                [
                    (
                        int(item["ts"]),
                        str(item["simbolo"]).upper(),
                        float(item["open"]),
                        float(item["high"]),
                        float(item["low"]),
                        float(item["close"]),
                        float(item["volume"]),
                    )
                    for item in registros
                ],
            )
            await conn.commit()

    @staticmethod
    async def obter_ultimas(simbolo: str, limite: int = 100) -> list[dict[str, Any]]:
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                SELECT ts, simbolo, open, high, low, close, volume
                FROM ohlcv_1m
                WHERE simbolo = ?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (simbolo.upper(), limite),
            )
            linhas = await cursor.fetchall()
        return list(reversed([_linha_para_dict(linha) for linha in linhas]))

    @staticmethod
    async def obter_intervalo(
        simbolo: str,
        ts_inicial: int | None = None,
        ts_final: int | None = None,
        limite: int = 1000,
    ) -> list[dict[str, Any]]:
        clausulas = ["simbolo = ?"]
        parametros: list[Any] = [simbolo.upper()]
        if ts_inicial is not None:
            clausulas.append("ts >= ?")
            parametros.append(ts_inicial)
        if ts_final is not None:
            clausulas.append("ts <= ?")
            parametros.append(ts_final)
        parametros.append(limite)

        sql = f"""
        SELECT ts, simbolo, open, high, low, close, volume
        FROM ohlcv_1m
        WHERE {' AND '.join(clausulas)}
        ORDER BY ts DESC
        LIMIT ?
        """

        async with get_conexao() as conn:
            cursor = await conn.execute(sql, tuple(parametros))
            linhas = await cursor.fetchall()
        return list(reversed([_linha_para_dict(linha) for linha in linhas]))
