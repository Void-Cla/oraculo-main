from __future__ import annotations

import json
import time
import uuid
from typing import Any

from src.core.settings import env_int

from .conexao import get_conexao, inicializar_db

_STATUS_PENDENTE = "PENDENTE"
_STATUS_PROCESSANDO = "PROCESSANDO"
_STATUS_CONCLUIDO = "CONCLUIDO"
_STATUS_FALHA = "FALHA"


class RepositorioFilaSinais:
    @staticmethod
    async def criar_tabela() -> None:
        inicializar_db()

    @staticmethod
    async def publicar(item: dict[str, Any]) -> dict[str, Any]:
        inicializar_db()
        timestamp = int(time.time() * 1000)
        correlation_id = str(item.get("correlation_id") or uuid.uuid4())
        payload = dict(item)
        payload["correlation_id"] = correlation_id
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO fila_sinais (
                  created_ts, updated_ts, status, tentativas, disponivel_em,
                  ordem_id, usuario_id, simbolo, correlation_id, payload_json, erro_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    timestamp,
                    _STATUS_PENDENTE,
                    0,
                    timestamp,
                    payload.get("ordem_id"),
                    payload.get("usuario_id"),
                    str(payload.get("simbolo", "")),
                    correlation_id,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    None,
                ),
            )
            await conn.commit()
            fila_id = int(cursor.lastrowid)
        return {"fila_id": fila_id, "correlation_id": correlation_id, "payload": payload}

    @staticmethod
    async def consumir() -> dict[str, Any]:
        inicializar_db()
        intervalo_ms = env_int("FILA_POLL_INTERVAL_MS", 250, minimo=50)
        while True:
            item = await RepositorioFilaSinais._claim_proximo()
            if item is not None:
                return item
            await _sleep_ms(intervalo_ms)

    @staticmethod
    async def _claim_proximo() -> dict[str, Any] | None:
        agora = int(time.time() * 1000)
        async with get_conexao() as conn:
            await conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = await conn.execute(
                    """
                    SELECT id, tentativas
                    FROM fila_sinais
                    WHERE status = ? AND disponivel_em <= ?
                    ORDER BY created_ts ASC, id ASC
                    LIMIT 1
                    """,
                    (_STATUS_PENDENTE, agora),
                )
                linha = await cursor.fetchone()
                if linha is None:
                    await conn.commit()
                    return None
                fila_id = int(linha["id"])
                tentativas = int(linha["tentativas"] or 0) + 1
                await conn.execute(
                    """
                    UPDATE fila_sinais
                    SET status = ?, tentativas = ?, updated_ts = ?
                    WHERE id = ?
                    """,
                    (_STATUS_PROCESSANDO, tentativas, agora, fila_id),
                )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

            cursor = await conn.execute(
                """
                SELECT id, created_ts, updated_ts, status, tentativas, disponivel_em,
                       ordem_id, usuario_id, simbolo, correlation_id, payload_json, erro_json
                FROM fila_sinais
                WHERE id = ?
                """,
                (fila_id,),
            )
            item = await cursor.fetchone()
        if item is None:
            return None
        payload = json.loads(item["payload_json"] or "{}")
        payload["fila_id"] = item["id"]
        payload["correlation_id"] = item["correlation_id"]
        payload["_fila_meta"] = {
            "status": item["status"],
            "tentativas": item["tentativas"],
            "created_ts": item["created_ts"],
            "updated_ts": item["updated_ts"],
        }
        return payload

    @staticmethod
    async def concluir(fila_id: int, resultado: dict[str, Any] | None = None) -> None:
        inicializar_db()
        await RepositorioFilaSinais._atualizar_status(
            fila_id=fila_id,
            status=_STATUS_CONCLUIDO,
            erro=None,
            merge_payload={"resultado_execucao": resultado or {}},
        )

    @staticmethod
    async def falhar(fila_id: int, erro: dict[str, Any], *, refileirar: bool) -> None:
        inicializar_db()
        agora = int(time.time() * 1000)
        if refileirar:
            atraso_ms = env_int("FILA_RETRY_DELAY_MS", 2000, minimo=200)
            async with get_conexao() as conn:
                await conn.execute(
                    """
                    UPDATE fila_sinais
                    SET status = ?, updated_ts = ?, disponivel_em = ?, erro_json = ?
                    WHERE id = ?
                    """,
                    (
                        _STATUS_PENDENTE,
                        agora,
                        agora + atraso_ms,
                        json.dumps(erro, ensure_ascii=False, sort_keys=True),
                        fila_id,
                    ),
                )
                await conn.commit()
            return

        await RepositorioFilaSinais._atualizar_status(
            fila_id=fila_id,
            status=_STATUS_FALHA,
            erro=erro,
            merge_payload=None,
        )

    @staticmethod
    async def snapshot(limite: int = 100) -> list[dict[str, Any]]:
        inicializar_db()
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                SELECT id, created_ts, updated_ts, status, tentativas, correlation_id, payload_json, erro_json
                FROM fila_sinais
                ORDER BY created_ts DESC, id DESC
                LIMIT ?
                """,
                (max(1, limite),),
            )
            linhas = await cursor.fetchall()
        saida: list[dict[str, Any]] = []
        for linha in reversed(linhas):
            payload = json.loads(linha["payload_json"] or "{}")
            payload["fila_id"] = linha["id"]
            payload["status_fila"] = linha["status"]
            payload["tentativas_fila"] = int(linha["tentativas"] or 0)
            payload["correlation_id"] = linha["correlation_id"]
            payload["erro_fila"] = json.loads(linha["erro_json"]) if linha["erro_json"] else None
            payload["created_ts_fila"] = linha["created_ts"]
            payload["updated_ts_fila"] = linha["updated_ts"]
            saida.append(payload)
        return saida

    @staticmethod
    async def resetar_teste() -> None:
        inicializar_db()
        async with get_conexao() as conn:
            await conn.execute("DELETE FROM fila_sinais")
            await conn.commit()

    @staticmethod
    async def _atualizar_status(
        *,
        fila_id: int,
        status: str,
        erro: dict[str, Any] | None,
        merge_payload: dict[str, Any] | None,
    ) -> None:
        agora = int(time.time() * 1000)
        async with get_conexao() as conn:
            cursor = await conn.execute("SELECT payload_json FROM fila_sinais WHERE id = ?", (fila_id,))
            linha = await cursor.fetchone()
            payload = json.loads(linha["payload_json"] or "{}") if linha else {}
            if merge_payload:
                payload.update(merge_payload)
            await conn.execute(
                """
                UPDATE fila_sinais
                SET status = ?, updated_ts = ?, payload_json = ?, erro_json = ?
                WHERE id = ?
                """,
                (
                    status,
                    agora,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    json.dumps(erro, ensure_ascii=False, sort_keys=True) if erro else None,
                    fila_id,
                ),
            )
            await conn.commit()


async def _sleep_ms(intervalo_ms: int) -> None:
    import asyncio

    await asyncio.sleep(intervalo_ms / 1000)
