from __future__ import annotations

import json
import time
from typing import Any

from .conexao import get_conexao, inicializar_db


def _serializar_valor(valor: Any) -> tuple[str, str]:
    if isinstance(valor, bool):
        return ("BOOL", "1" if valor else "0")
    if isinstance(valor, int) and not isinstance(valor, bool):
        return ("INT", str(valor))
    if isinstance(valor, float):
        return ("FLOAT", repr(valor))
    if isinstance(valor, (dict, list)):
        return ("JSON", json.dumps(valor, ensure_ascii=False, sort_keys=True))
    return ("STRING", str(valor))


def _desserializar_valor(valor: str | None, tipo: str) -> Any:
    if valor is None:
        return None
    if tipo == "BOOL":
        return valor == "1"
    if tipo == "INT":
        return int(valor)
    if tipo == "FLOAT":
        return float(valor)
    if tipo == "JSON":
        return json.loads(valor)
    return valor


class RepositorioConfig:
    @staticmethod
    async def criar_tabela() -> None:
        inicializar_db()

    @staticmethod
    async def definir(chave: str, valor: Any) -> None:
        tipo, payload = _serializar_valor(valor)
        async with get_conexao() as conn:
            await conn.execute(
                """
                INSERT INTO config (chave, valor, tipo, atualizado_em)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chave) DO UPDATE SET
                  valor = excluded.valor,
                  tipo = excluded.tipo,
                  atualizado_em = excluded.atualizado_em
                """,
                (chave, payload, tipo, int(time.time() * 1000)),
            )
            await conn.commit()

    @staticmethod
    async def obter(chave: str) -> Any:
        async with get_conexao() as conn:
            cursor = await conn.execute(
                "SELECT valor, tipo, atualizado_em FROM config WHERE chave = ?",
                (chave,),
            )
            linha = await cursor.fetchone()
        if linha is None:
            return None
        return _desserializar_valor(linha["valor"], linha["tipo"])

    @staticmethod
    async def listar_todas() -> list[dict[str, Any]]:
        async with get_conexao() as conn:
            cursor = await conn.execute(
                "SELECT chave, valor, tipo, atualizado_em FROM config ORDER BY chave ASC"
            )
            linhas = await cursor.fetchall()
        return [
            {
                "chave": linha["chave"],
                "valor": _desserializar_valor(linha["valor"], linha["tipo"]),
                "tipo": linha["tipo"],
                "atualizado_em": linha["atualizado_em"],
            }
            for linha in linhas
        ]

    @staticmethod
    async def set(chave: str, valor: Any) -> None:
        await RepositorioConfig.definir(chave, valor)

    @staticmethod
    async def get(chave: str) -> Any:
        return await RepositorioConfig.obter(chave)
