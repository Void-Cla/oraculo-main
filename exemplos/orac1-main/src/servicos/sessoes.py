from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

from src.binance_api.cliente import ClienteBinance
from src.core.settings import env_bool, env_float

_SESSOES: dict[str, dict[str, Any]] = {}
_CREDENCIAIS: dict[str, dict[str, str]] = {}
_LOCK = asyncio.Lock()


def _agora_ms() -> int:
    return int(time.time() * 1000)


def _ttl_ms() -> int:
    horas = env_float("SESSION_TTL_HOURS", 12.0, minimo=1.0)
    return max(1, int(horas * 60 * 60 * 1000))


def _resolver_testnet(testnet: bool | None) -> bool:
    if testnet is not None:
        return bool(testnet)
    return env_bool("BINANCE_TESTNET", False)


def _mascarar_chave(api_key: str) -> str:
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}***{api_key[-4:]}"


def _identidade_conta(conta: dict[str, Any]) -> dict[str, str]:
    account_type = str(conta.get("accountType") or "SPOT").upper()
    uid = conta.get("uid")
    return {
        "nome_exibicao": f"Conta {account_type} Binance",
        "id_conta": str(uid) if uid not in {None, ""} else "nao_informado_pela_binance",
    }


def _publica_sessao(sessao: dict[str, Any]) -> dict[str, Any]:
    return {
        "autenticado": True,
        "token": sessao["token"],
        "criado_em": sessao["criado_em"],
        "expira_em": sessao["expira_em"],
        "api_key_mascarada": sessao["api_key_mascarada"],
        "modo_testnet": sessao["modo_testnet"],
        "nome_exibicao": sessao["nome_exibicao"],
        "id_conta": sessao["id_conta"],
    }


def _limpar_expiradas_sem_lock() -> None:
    agora = _agora_ms()
    expiradas = [token for token, sessao in _SESSOES.items() if int(sessao["expira_em"]) <= agora]
    for token in expiradas:
        _SESSOES.pop(token, None)
        _CREDENCIAIS.pop(token, None)


async def criar_sessao_binance(api_key: str, api_secret: str, testnet: bool | None = None) -> dict[str, Any]:
    api_key = (api_key or "").strip()
    api_secret = (api_secret or "").strip()
    if not api_key or not api_secret:
        raise ValueError("api_key_e_api_secret_sao_obrigatorias")

    cliente = ClienteBinance(api_key=api_key, api_secret=api_secret, testnet=_resolver_testnet(testnet))
    try:
        conta = await cliente.obter_conta_raw()
    finally:
        await cliente.fechar()

    agora = _agora_ms()
    ttl = _ttl_ms()
    token = secrets.token_urlsafe(32)
    sessao = {
        "token": token,
        "api_key_mascarada": _mascarar_chave(api_key),
        "modo_testnet": _resolver_testnet(testnet),
        "criado_em": agora,
        "expira_em": agora + ttl,
        **_identidade_conta(conta),
    }

    async with _LOCK:
        _limpar_expiradas_sem_lock()
        _SESSOES[token] = sessao
        if env_bool("SESSION_STORE_CREDENTIALS", True):
            _CREDENCIAIS[token] = {"api_key": api_key, "api_secret": api_secret}
    return _publica_sessao(sessao)


async def obter_sessao(token: str | None, renovar_ttl: bool = True, incluir_credenciais: bool = True) -> dict[str, Any] | None:
    if not token:
        return None
    async with _LOCK:
        _limpar_expiradas_sem_lock()
        sessao = _SESSOES.get(token)
        if sessao is None:
            return None
        if renovar_ttl:
            sessao["expira_em"] = _agora_ms() + _ttl_ms()
        payload = dict(sessao)
        if incluir_credenciais:
            payload.update(_CREDENCIAIS.get(token, {}))
        return payload


async def obter_sessao_publica(token: str | None, renovar_ttl: bool = True) -> dict[str, Any] | None:
    sessao = await obter_sessao(token, renovar_ttl=renovar_ttl)
    if sessao is None:
        return None
    return _publica_sessao(sessao)


async def encerrar_sessao(token: str | None) -> bool:
    if not token:
        return False
    async with _LOCK:
        _CREDENCIAIS.pop(token, None)
        return _SESSOES.pop(token, None) is not None


def resetar_sessoes_teste() -> None:
    _SESSOES.clear()
    _CREDENCIAIS.clear()
