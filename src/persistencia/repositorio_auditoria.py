from __future__ import annotations

import json
import time
from typing import Any

from .conexao import get_conexao, inicializar_db


class RepositorioAuditoria:
    @staticmethod
    async def criar_tabela() -> None:
        inicializar_db()

    @staticmethod
    async def registrar(
        simbolo: str,
        tipo: str,
        payload: dict[str, Any],
        created_ts: int | None = None,
        componente: str | None = None,
        motivo: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> int:
        timestamp = created_ts if created_ts is not None else int(time.time() * 1000)
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        meta_json = json.dumps(meta or {}, ensure_ascii=False, sort_keys=True)
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO audit (created_ts, simbolo, tipo, payload_json, componente, motivo, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (timestamp, simbolo.upper(), tipo, payload_json, componente, motivo, meta_json),
            )
            await conn.commit()
            return int(cursor.lastrowid)

    @staticmethod
    async def registrar_enriquecido(
        *,
        evento: str,
        componente: str,
        motivo: str,
        simbolo: str = "SISTEMA",
        usuario_id: int | str | None = None,
        meta: dict[str, Any] | None = None,
        created_ts: int | None = None,
    ) -> int:
        payload = {
            "usuario_id": usuario_id,
            "motivo": motivo,
            "meta": meta or {},
        }
        return await RepositorioAuditoria.registrar(
            simbolo=simbolo,
            tipo=evento,
            payload=payload,
            created_ts=created_ts,
            componente=componente,
            motivo=motivo,
            meta=meta,
        )

    @staticmethod
    async def listar_recentes(
        simbolo: str | None = None,
        tipo: str | None = None,
        limite: int = 100,
    ) -> list[dict[str, Any]]:
        clausulas: list[str] = []
        parametros: list[Any] = []
        if simbolo:
            clausulas.append("simbolo = ?")
            parametros.append(simbolo.upper())
        if tipo:
            clausulas.append("tipo = ?")
            parametros.append(tipo)
        where = f"WHERE {' AND '.join(clausulas)}" if clausulas else ""
        parametros.append(limite)

        async with get_conexao() as conn:
            cursor = await conn.execute(
                f"""
                SELECT id, created_ts, simbolo, tipo, payload_json, componente, motivo, meta_json
                FROM audit
                {where}
                ORDER BY created_ts DESC, id DESC
                LIMIT ?
                """,
                tuple(parametros),
            )
            linhas = await cursor.fetchall()

        saida: list[dict[str, Any]] = []
        for linha in reversed(linhas):
            dados = dict(linha)
            dados["payload"] = json.loads(dados.pop("payload_json"))
            dados["meta_json"] = dados.get("meta_json") or "{}"
            dados["meta"] = json.loads(dados["meta_json"])
            saida.append(dados)
        return saida
