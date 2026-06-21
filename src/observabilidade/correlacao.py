"""Correlação de logs — rastreabilidade fim-a-fim de uma decisão financeira (FASE 7).

Um `correlation_id` acompanha o fluxo do sinal até a ordem e o outcome, tornando possível
auditar, anos depois, por que uma ordem específica foi executada ou bloqueada.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def novo_correlation_id() -> str:
    """Gera um identificador de correlação único (hex de 32 chars)."""
    return uuid.uuid4().hex


def contexto_operacao(
    simbolo: str, usuario_id: str | int = "auto", correlation_id: str | None = None
) -> dict[str, Any]:
    """Cria o contexto de correlação inicial de uma operação (sinal → ordem → outcome)."""
    return {
        "correlation_id": correlation_id or novo_correlation_id(),
        "simbolo": str(simbolo).upper(),
        "usuario_id": str(usuario_id),
        "ts_inicio": datetime.now(timezone.utc).isoformat(),
    }
