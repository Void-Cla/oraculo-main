from __future__ import annotations

import json
from typing import Any

from .conexao import get_conexao, inicializar_db


class RepositorioPredicoes:
    @staticmethod
    async def criar_tabela() -> None:
        inicializar_db()

    @staticmethod
    async def salvar(
        created_ts: int,
        simbolo: str,
        y_hat: float,
        y_cal: float | None = None,
        ic68_low: float | None = None,
        ic68_high: float | None = None,
        p_conf: float | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        payload = json.dumps(meta or {}, ensure_ascii=False, sort_keys=True)
        async with get_conexao() as conn:
            await conn.execute(
                """
                INSERT INTO predictions (
                  created_ts, simbolo, y_hat, y_cal, ic68_low, ic68_high, p_conf, meta_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(created_ts, simbolo) DO UPDATE SET
                  y_hat = excluded.y_hat,
                  y_cal = excluded.y_cal,
                  ic68_low = excluded.ic68_low,
                  ic68_high = excluded.ic68_high,
                  p_conf = excluded.p_conf,
                  meta_json = excluded.meta_json
                """,
                (created_ts, simbolo.upper(), y_hat, y_cal, ic68_low, ic68_high, p_conf, payload),
            )
            await conn.commit()

    @staticmethod
    async def obter(created_ts: int, simbolo: str) -> dict[str, Any] | None:
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                SELECT created_ts, simbolo, y_hat, y_cal, ic68_low, ic68_high, p_conf, meta_json
                FROM predictions
                WHERE created_ts = ? AND simbolo = ?
                """,
                (created_ts, simbolo.upper()),
            )
            linha = await cursor.fetchone()
        if linha is None:
            return None
        dados = dict(linha)
        dados["meta"] = json.loads(dados.pop("meta_json") or "{}")
        return dados

    @staticmethod
    async def listar_recentes(simbolo: str, limite: int = 100) -> list[dict[str, Any]]:
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                SELECT created_ts, simbolo, y_hat, y_cal, ic68_low, ic68_high, p_conf, meta_json
                FROM predictions
                WHERE simbolo = ?
                ORDER BY created_ts DESC
                LIMIT ?
                """,
                (simbolo.upper(), limite),
            )
            linhas = await cursor.fetchall()

        saida: list[dict[str, Any]] = []
        for linha in reversed(linhas):
            dados = dict(linha)
            dados["meta"] = json.loads(dados.pop("meta_json") or "{}")
            saida.append(dados)
        return saida
