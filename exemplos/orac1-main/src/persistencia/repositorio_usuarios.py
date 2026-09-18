from __future__ import annotations

import json
import time
from typing import Any

from src.core.segredos import normalizar_secret_id
from src.risco.risk_engine import config_risco_padrao

from .conexao import get_conexao, inicializar_db


def _normalizar_risk_config(risk_config: dict[str, Any] | None) -> dict[str, Any]:
    base = config_risco_padrao()
    if risk_config:
        base.update(risk_config)
    return base


def _normalizar_secret_ids(
    api_key_secret_id: str | None,
    api_secret_secret_id: str | None,
    *,
    api_key_ref: str | None = None,
    api_secret_ref: str | None = None,
) -> tuple[str | None, str | None]:
    chave = api_key_secret_id or api_key_ref
    segredo = api_secret_secret_id or api_secret_ref
    return normalizar_secret_id(chave), normalizar_secret_id(segredo)


class RepositorioUsuarios:
    @staticmethod
    async def criar_tabela() -> None:
        inicializar_db()

    @staticmethod
    async def criar(
        nome: str,
        api_key_secret_id: str | None = None,
        api_secret_secret_id: str | None = None,
        api_key_ref: str | None = None,
        api_secret_ref: str | None = None,
        testnet: bool = True,
        ativo: bool = True,
        risk_config: dict[str, Any] | None = None,
    ) -> int:
        timestamp = int(time.time() * 1000)
        payload_risco = json.dumps(_normalizar_risk_config(risk_config), ensure_ascii=False, sort_keys=True)
        api_key_secret_id, api_secret_secret_id = _normalizar_secret_ids(
            api_key_secret_id,
            api_secret_secret_id,
            api_key_ref=api_key_ref,
            api_secret_ref=api_secret_ref,
        )
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO usuarios (
                  nome, api_key_ref, api_secret_ref, api_key_secret_id, api_secret_secret_id,
                  ativo, testnet, risk_config_json, criado_em, atualizado_em
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    nome,
                    None,
                    None,
                    api_key_secret_id,
                    api_secret_secret_id,
                    int(ativo),
                    int(testnet),
                    payload_risco,
                    timestamp,
                    timestamp,
                ),
            )
            await conn.commit()
            return int(cursor.lastrowid)

    @staticmethod
    async def atualizar(
        usuario_id: int,
        *,
        nome: str | None = None,
        api_key_secret_id: str | None = None,
        api_secret_secret_id: str | None = None,
        api_key_ref: str | None = None,
        api_secret_ref: str | None = None,
        ativo: bool | None = None,
        testnet: bool | None = None,
        risk_config: dict[str, Any] | None = None,
    ) -> None:
        atual = await RepositorioUsuarios.obter(usuario_id)
        if atual is None:
            raise ValueError(f"usuario {usuario_id} nao encontrado")

        novo_payload = _normalizar_risk_config(risk_config or atual["risk_config"])
        api_key_secret_id, api_secret_secret_id = _normalizar_secret_ids(
            api_key_secret_id,
            api_secret_secret_id,
            api_key_ref=api_key_ref if api_key_secret_id is None else None,
            api_secret_ref=api_secret_ref if api_secret_secret_id is None else None,
        )
        async with get_conexao() as conn:
            await conn.execute(
                """
                UPDATE usuarios
                SET nome = ?, api_key_ref = ?, api_secret_ref = ?, api_key_secret_id = ?, api_secret_secret_id = ?,
                    ativo = ?, testnet = ?, risk_config_json = ?, atualizado_em = ?
                WHERE id = ?
                """,
                (
                    nome or atual["nome"],
                    atual["api_key_ref"],
                    atual["api_secret_ref"],
                    api_key_secret_id if api_key_secret_id is not None else atual.get("api_key_secret_id"),
                    api_secret_secret_id if api_secret_secret_id is not None else atual.get("api_secret_secret_id"),
                    int(atual["ativo"] if ativo is None else ativo),
                    int(atual["testnet"] if testnet is None else testnet),
                    json.dumps(novo_payload, ensure_ascii=False, sort_keys=True),
                    int(time.time() * 1000),
                    usuario_id,
                ),
            )
            await conn.commit()

    @staticmethod
    async def obter(usuario_id: int) -> dict[str, Any] | None:
        async with get_conexao() as conn:
            cursor = await conn.execute(
                """
                SELECT id, nome, api_key_ref, api_secret_ref, api_key_secret_id, api_secret_secret_id,
                       ativo, testnet, risk_config_json, criado_em, atualizado_em
                FROM usuarios
                WHERE id = ?
                """,
                (usuario_id,),
            )
            linha = await cursor.fetchone()
        if linha is None:
            return None
        dados = dict(linha)
        dados["ativo"] = bool(dados["ativo"])
        dados["testnet"] = bool(dados["testnet"])
        dados["risk_config"] = json.loads(dados.pop("risk_config_json"))
        return dados

    @staticmethod
    async def listar(apenas_ativos: bool = False) -> list[dict[str, Any]]:
        where = "WHERE ativo = 1" if apenas_ativos else ""
        async with get_conexao() as conn:
            cursor = await conn.execute(
                f"""
                SELECT id, nome, api_key_ref, api_secret_ref, api_key_secret_id, api_secret_secret_id,
                       ativo, testnet, risk_config_json, criado_em, atualizado_em
                FROM usuarios
                {where}
                ORDER BY nome ASC
                """
            )
            linhas = await cursor.fetchall()
        saida = []
        for linha in linhas:
            dados = dict(linha)
            dados["ativo"] = bool(dados["ativo"])
            dados["testnet"] = bool(dados["testnet"])
            dados["risk_config"] = json.loads(dados.pop("risk_config_json"))
            saida.append(dados)
        return saida
