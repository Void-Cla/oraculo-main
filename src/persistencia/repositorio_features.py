from __future__ import annotations

import json
from typing import Any

from .conexao import get_conexao, inicializar_db


class RepositorioFeatures:
    @staticmethod
    async def criar_tabela() -> None:
        inicializar_db()

    @staticmethod
    async def salvar(ts: int, simbolo: str, features: dict[str, Any]) -> None:
        payload = json.dumps(features, ensure_ascii=False, sort_keys=True)
        # Extrair regime e vol_regime para colunas indexadas (facilita queries ML)
        regime = str(features.get("regime") or "")
        vol_ref = max(float(features.get("vol5") or 0.0), float(features.get("vol10") or 0.0))
        vol_regime = "HIGH" if vol_ref >= 0.012 else ("LOW" if vol_ref <= 0.003 else "MED")
        async with get_conexao() as conn:
            await conn.execute(
                """
                INSERT INTO features_1m (ts, simbolo, features_json, regime, vol_regime)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(ts, simbolo) DO UPDATE SET
                  features_json = excluded.features_json,
                  regime = excluded.regime,
                  vol_regime = excluded.vol_regime
                """,
                (ts, simbolo.upper(), payload, regime, vol_regime),
            )
            await conn.commit()

    @staticmethod
    async def obter(ts: int, simbolo: str) -> dict[str, Any] | None:
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                SELECT features_json
                FROM features_1m
                WHERE ts = ? AND simbolo = ?
                """,
                (ts, simbolo.upper()),
            )
            linha = await cursor.fetchone()
        if linha is None:
            return None
        return json.loads(linha["features_json"])

    @staticmethod
    async def listar_ultimas(simbolo: str, limite: int = 100) -> list[dict[str, Any]]:
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                SELECT ts, features_json
                FROM features_1m
                WHERE simbolo = ?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (simbolo.upper(), limite),
            )
            linhas = await cursor.fetchall()

        saida: list[dict[str, Any]] = []
        for linha in reversed(linhas):
            dados = json.loads(linha["features_json"])
            saida.append({"ts": int(linha["ts"]), **dados})
        return saida
