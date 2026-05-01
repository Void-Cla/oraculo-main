from __future__ import annotations

"""Janela de observação que bloqueia operações após retomada insegura."""

import asyncio

from src.core.settings import env_int
from src.observabilidade.audit import registrar_audit
from src.observabilidade.logger import get_logger
from src.persistencia.repositorio_config import RepositorioConfig
from src.persistencia.repositorio_snapshot import obter_snapshot, salvar_snapshot

LOG = get_logger("observacao")


async def aguardar_observacao(
    simbolo: str,
    *,
    candles: int | None = None,
    intervalo_segundos: int = 60,
) -> None:
    """Mantém `retomada_operacoes_bloqueadas` ativo até N candles passarem."""
    total = int(candles if candles is not None else env_int("RETOMADA_CANDLES_OBSERVACAO", 5, minimo=1))
    simbolo = simbolo.upper()
    await RepositorioConfig.definir("retomada_modo", "observacao")
    await RepositorioConfig.definir("retomada_operacoes_bloqueadas", True)
    snapshot = dict(await obter_snapshot(simbolo) or {})
    await salvar_snapshot(simbolo, {**snapshot, "modo_operacao": "observacao"})
    await registrar_audit(
        "observacao_iniciada",
        "observacao",
        f"observacao_por_{total}_candles",
        simbolo=simbolo,
        meta={"candles": total, "intervalo_segundos": intervalo_segundos},
    )
    LOG.info("observacao_iniciada", extra={"simbolo": simbolo, "candles": total})

    for indice in range(1, total + 1):
        await asyncio.sleep(max(0, int(intervalo_segundos)))
        LOG.info("observacao_progresso", extra={"simbolo": simbolo, "candle": indice, "total": total})

    motivo_bloqueio = str(await RepositorioConfig.obter("bloqueio_operacional_motivo") or "")
    if motivo_bloqueio:
        await RepositorioConfig.definir("retomada_modo", "pausado")
        await RepositorioConfig.definir("retomada_operacoes_bloqueadas", True)
        await registrar_audit(
            "observacao_bloqueio_preservado",
            "observacao",
            motivo_bloqueio,
            simbolo=simbolo,
            meta={"candles": total},
        )
        LOG.error("observacao_bloqueio_preservado", extra={"simbolo": simbolo, "motivo": motivo_bloqueio})
        return

    await RepositorioConfig.definir("retomada_modo", "normal")
    await RepositorioConfig.definir("retomada_operacoes_bloqueadas", False)
    snapshot = dict(await obter_snapshot(simbolo) or {})
    await salvar_snapshot(simbolo, {**snapshot, "modo_operacao": "normal"})
    await registrar_audit(
        "observacao_concluida",
        "observacao",
        "retomada_liberada_para_operacao",
        simbolo=simbolo,
        meta={"candles": total},
    )
    LOG.info("observacao_concluida", extra={"simbolo": simbolo})
