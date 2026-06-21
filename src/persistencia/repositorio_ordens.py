from __future__ import annotations

import json
import logging
import time
from typing import Any

from .conexao import get_conexao, inicializar_db

_STATUS_VALIDOS = {
    "PENDENTE",
    "EM_ABERTO",
    "EXECUTADA",
    "CANCELADA",
    "REJEITADA",
    "SIMULADA",
}

logger = logging.getLogger("RepositorioOrdens")


class RepositorioOrdens:
    @staticmethod
    async def criar_tabela() -> None:
        inicializar_db()

    @staticmethod
    async def criar(
        *,
        usuario_id: int | None,
        simbolo: str,
        lado: str,
        status: str,
        modo: str,
        preco_referencia: float | None,
        quantidade: float | None,
        notional: float | None,
        stop_loss_pct: float | None,
        take_profit_pct: float | None,
        detalhe: dict[str, Any] | None = None,
    ) -> int:
        status = status.upper()
        if status not in _STATUS_VALIDOS:
            raise ValueError(f"status de ordem invalido: {status}")

        timestamp = int(time.time() * 1000)
        payload = json.dumps(detalhe or {}, ensure_ascii=False, sort_keys=True)
        try:
            async with get_conexao() as conn:
                cursor = await conn.execute(
                    """
                    INSERT INTO ordens (
                      created_ts, updated_ts, usuario_id, simbolo, lado, status, modo,
                      preco_referencia, quantidade, notional, stop_loss_pct, take_profit_pct, detalhe_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp,
                        timestamp,
                        usuario_id,
                        simbolo.upper(),
                        lado.upper(),
                        status,
                        modo.lower(),
                        preco_referencia,
                        quantidade,
                        notional,
                        stop_loss_pct,
                        take_profit_pct,
                        payload,
                    ),
                )
                await conn.commit()
                ordem_id = int(cursor.lastrowid)
                logger.info(f"Ordem criada com sucesso: {ordem_id}")
                return ordem_id
        except Exception as e:
            logger.error(f"Erro ao criar ordem: {e}", exc_info=True)
            raise

    @staticmethod
    async def obter(ordem_id: int) -> dict[str, Any] | None:
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                SELECT id, created_ts, updated_ts, usuario_id, simbolo, lado, status, modo,
                       preco_referencia, quantidade, notional, stop_loss_pct, take_profit_pct,
                       lucro_usdt, lucro_pct, duracao_ms, capital_pct_usado, regime, estrategia, detalhe_json
                FROM ordens
                WHERE id = ?
                """,
                (ordem_id,),
            )
            linha = await cursor.fetchone()
        if linha is None:
            return None
        dados = dict(linha)
        dados["detalhe"] = json.loads(dados.pop("detalhe_json") or "{}")
        return dados

    @staticmethod
    async def atualizar_status(ordem_id: int, status: str, detalhe_extra: dict[str, Any] | None = None) -> dict[str, Any]:
        status = status.upper()
        if status not in _STATUS_VALIDOS:
            raise ValueError(f"status de ordem invalido: {status}")

        atual = await RepositorioOrdens.obter(ordem_id)
        if atual is None:
            raise ValueError(f"ordem {ordem_id} nao encontrada")

        detalhe = dict(atual["detalhe"])
        if detalhe_extra:
            detalhe.update(detalhe_extra)

        async with get_conexao() as conn:
            await conn.execute(
                """
                UPDATE ordens
                SET status = ?, updated_ts = ?, detalhe_json = ?
                WHERE id = ?
                """,
                (
                    status,
                    int(time.time() * 1000),
                    json.dumps(detalhe, ensure_ascii=False, sort_keys=True),
                    ordem_id,
                ),
            )
            await conn.commit()
        return await RepositorioOrdens.obter(ordem_id)

    @staticmethod
    async def listar_recentes(
        *,
        usuario_id: int | None = None,
        simbolo: str | None = None,
        limite: int = 50,
    ) -> list[dict[str, Any]]:
        clausulas: list[str] = []
        parametros: list[Any] = []
        if usuario_id is not None:
            clausulas.append("usuario_id = ?")
            parametros.append(usuario_id)
        if simbolo:
            clausulas.append("simbolo = ?")
            parametros.append(simbolo.upper())
        where = f"WHERE {' AND '.join(clausulas)}" if clausulas else ""
        parametros.append(limite)

        async with get_conexao() as conn:
            cursor = await conn.execute(
                f"""
                SELECT id, created_ts, updated_ts, usuario_id, simbolo, lado, status, modo,
                       preco_referencia, quantidade, notional, stop_loss_pct, take_profit_pct,
                       lucro_usdt, lucro_pct, duracao_ms, capital_pct_usado, regime, estrategia, detalhe_json
                FROM ordens
                {where}
                ORDER BY created_ts DESC, id DESC
                LIMIT ?
                """,
                tuple(parametros),
            )
            linhas = await cursor.fetchall()

        saida = []
        for linha in reversed(linhas):
            dados = dict(linha)
            dados["detalhe"] = json.loads(dados.pop("detalhe_json") or "{}")
            saida.append(dados)
        return saida

    @staticmethod
    async def resumo_status(usuario_id: int | None = None, simbolo: str | None = None) -> dict[str, int]:
        resumo = {status.lower(): 0 for status in _STATUS_VALIDOS}
        ordens = await RepositorioOrdens.listar_recentes(usuario_id=usuario_id, simbolo=simbolo, limite=500)
        for ordem in ordens:
            resumo[ordem["status"].lower()] = resumo.get(ordem["status"].lower(), 0) + 1
        return resumo

    @staticmethod
    async def registrar_resultado(
        ordem_id: int,
        *,
        lucro_usdt: float,
        lucro_pct: float,
        duracao_ms: int,
        capital_pct_usado: float | None = None,
        regime: str | None = None,
        estrategia: str | None = None,
    ) -> None:
        """Persiste resultado financeiro de uma ordem encerrada."""
        async with get_conexao() as conn:
            await conn.execute(
                """
                UPDATE ordens
                SET lucro_usdt = ?,
                    lucro_pct = ?,
                    duracao_ms = ?,
                    capital_pct_usado = ?,
                    regime = ?,
                    estrategia = ?,
                    updated_ts = ?
                WHERE id = ?
                """,
                (
                    float(lucro_usdt),
                    float(lucro_pct),
                    int(duracao_ms),
                    float(capital_pct_usado) if capital_pct_usado is not None else None,
                    str(regime) if regime else None,
                    str(estrategia) if estrategia else None,
                    int(time.time() * 1000),
                    ordem_id,
                ),
            )
            await conn.commit()
