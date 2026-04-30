from __future__ import annotations

"""Fachada de auditoria enriquecida sem duplicar persistência."""

from typing import Any

from src.observabilidade.logger import get_logger
from src.persistencia.repositorio_auditoria import RepositorioAuditoria

LOG = get_logger("audit")


async def registrar_audit(
    evento: str,
    componente: str,
    motivo: str,
    *,
    usuario_id: int | str | None = None,
    simbolo: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Registra auditoria enriquecida e nunca propaga falha ao chamador."""
    try:
        await RepositorioAuditoria.registrar_enriquecido(
            evento=evento,
            componente=componente,
            motivo=motivo,
            usuario_id=usuario_id,
            simbolo=(simbolo or "SISTEMA").upper(),
            meta=meta or {},
        )
    except Exception as exc:
        LOG.error("audit_falhou", extra={"evento": evento, "componente": componente, "erro": str(exc)})
