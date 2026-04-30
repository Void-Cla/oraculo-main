from __future__ import annotations

import os
import re
from typing import Any

from src.core.settings import env_bool

_SECRET_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")


def normalizar_secret_id(valor: str | None) -> str | None:
    if valor is None:
        return None
    secret_id = str(valor).strip().upper()
    if not secret_id:
        return None
    if not _SECRET_ID_RE.fullmatch(secret_id):
        raise ValueError("secret_id_invalido_use_nome_de_variavel_de_ambiente")
    return secret_id


def resolver_secret_id(secret_id: str | None) -> str | None:
    normalizado = normalizar_secret_id(secret_id)
    if normalizado is None:
        return None
    valor = os.getenv(normalizado)
    if valor is None:
        return None
    valor = str(valor).strip()
    return valor or None


def permitir_credencial_bruta_legada() -> bool:
    return env_bool("ALLOW_LEGACY_RAW_USER_SECRETS", False)


def resolver_credenciais_usuario(usuario: dict[str, Any]) -> dict[str, Any]:
    api_key_secret_id = usuario.get("api_key_secret_id")
    api_secret_secret_id = usuario.get("api_secret_secret_id")
    if api_key_secret_id or api_secret_secret_id:
        api_key = resolver_secret_id(api_key_secret_id)
        api_secret = resolver_secret_id(api_secret_secret_id)
        return {
            "api_key": api_key,
            "api_secret": api_secret,
            "origem": "secret_id",
            "resolvido": bool(api_key and api_secret),
        }

    api_key_legado = usuario.get("api_key_ref")
    api_secret_legado = usuario.get("api_secret_ref")
    if api_key_legado and api_secret_legado and permitir_credencial_bruta_legada():
        return {
            "api_key": str(api_key_legado),
            "api_secret": str(api_secret_legado),
            "origem": "legado_bruto",
            "resolvido": True,
        }

    return {
        "api_key": None,
        "api_secret": None,
        "origem": "ausente",
        "resolvido": False,
    }
