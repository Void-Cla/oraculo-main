"""Parse e sanitização do JSON retornado pela IA — defensivo (nunca confia no LLM)."""
from __future__ import annotations

import json
from typing import Any


def _remover_cerca_markdown(texto: str) -> str:
    """Remove cercas ```json ... ``` (LLM frequentemente embrulha o JSON). Usa removeprefix/
    removesuffix (NÃO lstrip, que removeria um CONJUNTO de chars — armadilha já vista no projeto)."""
    t = texto.strip()
    for prefixo in ("```json", "```JSON", "```"):
        if t.startswith(prefixo):
            t = t[len(prefixo):]
            break
    if t.endswith("```"):
        t = t[: -len("```")]
    return t.strip()


def extrair_json(texto: str | None) -> dict[str, Any] | None:
    """Extrai um objeto JSON da resposta do LLM. Retorna None se inválido (fail-safe)."""
    if not texto:
        return None
    bruto = _remover_cerca_markdown(str(texto))
    try:
        valor = json.loads(bruto)
    except (json.JSONDecodeError, ValueError):
        # Fallback: tenta recortar do primeiro '{' ao último '}'.
        inicio, fim = bruto.find("{"), bruto.rfind("}")
        if inicio == -1 or fim <= inicio:
            return None
        try:
            valor = json.loads(bruto[inicio : fim + 1])
        except (json.JSONDecodeError, ValueError):
            return None
    return valor if isinstance(valor, dict) else None
