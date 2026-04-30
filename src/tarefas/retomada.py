from __future__ import annotations

"""Avaliação de retomada autônoma após pausa operacional."""

import json
from datetime import datetime, timezone
from typing import Any, Literal

from src.core.settings import env_float
from src.observabilidade.logger import get_logger
from src.persistencia.conexao import get_conexao
from src.persistencia.repositorio_config import RepositorioConfig
from src.persistencia.repositorio_snapshot import obter_snapshot
from src.sinais.detector_drift import detectar_drift

LOG = get_logger("retomada")

ModoRetomada = Literal["normal", "observacao", "recalibracao_forcada"]


def _determinar_modo(
    horas: float,
    variacao_pct: float | None,
    *,
    pausa_media_horas: float | None = None,
    pausa_longa_horas: float | None = None,
    variacao_relevante_pct: float | None = None,
) -> ModoRetomada:
    """Regra pura de decisão do modo de retomada."""
    pausa_media = float(pausa_media_horas if pausa_media_horas is not None else env_float("RETOMADA_PAUSA_MEDIA_H", 4.0, minimo=0.0))
    pausa_longa = float(pausa_longa_horas if pausa_longa_horas is not None else env_float("RETOMADA_PAUSA_LONGA_H", 24.0, minimo=0.0))
    variacao_limite = float(variacao_relevante_pct if variacao_relevante_pct is not None else env_float("RETOMADA_VARIACAO_PCT", 3.0, minimo=0.0))
    if horas >= pausa_longa:
        return "recalibracao_forcada"
    if horas >= pausa_media:
        return "observacao"
    if variacao_pct is not None and variacao_pct >= variacao_limite:
        return "observacao"
    return "normal"


def _resultado(
    modo: ModoRetomada,
    horas_parado: float,
    variacao_pct: float | None,
    preco_ultima_ordem: float | None,
    preco_atual: float | None,
    mensagem: str,
    *,
    snapshot: dict[str, Any] | None = None,
    drift: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "modo": modo,
        "horas_parado": horas_parado,
        "variacao_pct": variacao_pct,
        "preco_ultima_ordem": preco_ultima_ordem,
        "preco_atual": preco_atual,
        "mensagem": mensagem,
        "snapshot": snapshot,
        "drift": drift,
    }


def _ts_ordem_para_datetime(created_ts: int | float) -> datetime:
    numero = int(created_ts)
    segundos = numero / 1000.0 if numero >= 10_000_000_000 else numero
    return datetime.fromtimestamp(segundos, tz=timezone.utc)


def _preco_execucao_do_detalhe(detalhe: dict[str, Any], preco_referencia: float | None) -> float | None:
    execucao = detalhe.get("execucao") if isinstance(detalhe.get("execucao"), dict) else {}
    simulacao = detalhe.get("simulacao_ordem") if isinstance(detalhe.get("simulacao_ordem"), dict) else {}
    valor = (
        execucao.get("preco_execucao")
        or simulacao.get("preco_estimado_execucao")
        or simulacao.get("preco_referencia")
        or preco_referencia
    )
    try:
        preco = float(valor)
    except (TypeError, ValueError):
        return None
    return preco if preco > 0.0 else None


async def _obter_ultima_ordem(simbolo: str) -> dict[str, Any] | None:
    async with get_conexao() as conn:
        cursor = await conn.execute(
            """
            SELECT created_ts, preco_referencia, detalhe_json
            FROM ordens
            WHERE simbolo = ? AND status = 'EXECUTADA'
            ORDER BY created_ts DESC, id DESC
            LIMIT 1
            """,
            (simbolo.upper(),),
        )
        linha = await cursor.fetchone()
    if linha is None:
        return None
    detalhe = json.loads(linha["detalhe_json"] or "{}")
    return {
        "ts": _ts_ordem_para_datetime(linha["created_ts"]),
        "preco_execucao": _preco_execucao_do_detalhe(detalhe, linha["preco_referencia"]),
        "detalhe": detalhe,
    }


async def _obter_preco_atual(simbolo: str) -> float | None:
    from src.binance_api.cliente import ClienteBinance

    cliente = ClienteBinance()
    try:
        return await cliente.obter_preco_atual(simbolo)
    except Exception as exc:
        LOG.warning("preco_atual_indisponivel", extra={"simbolo": simbolo.upper(), "erro": str(exc)})
        return None
    finally:
        await cliente.fechar()


async def avaliar_retomada(
    simbolo: str,
    *,
    ajustes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Avalia pausa, variação de preço, drift e snapshot para definir retomada."""
    simbolo = simbolo.upper()
    ajustes = ajustes or {}
    snapshot = await obter_snapshot(simbolo)
    ultima = await _obter_ultima_ordem(simbolo)
    if ultima is None:
        return _resultado("normal", 0.0, None, None, None, "inicializacao_sem_historico", snapshot=snapshot)

    agora = datetime.now(timezone.utc)
    horas_parado = max(0.0, (agora - ultima["ts"]).total_seconds() / 3600.0)
    preco_anterior = ultima.get("preco_execucao")
    preco_atual = await _obter_preco_atual(simbolo)
    variacao_pct = None
    if preco_anterior and preco_atual:
        variacao_pct = abs((float(preco_atual) - float(preco_anterior)) / float(preco_anterior)) * 100.0

    modo = _determinar_modo(
        horas_parado,
        variacao_pct,
        pausa_media_horas=ajustes.get("pausa_media_h"),
        pausa_longa_horas=ajustes.get("pausa_longa_h"),
        variacao_relevante_pct=ajustes.get("variacao_pct"),
    )
    drift = await detectar_drift(
        simbolo,
        ultima["ts"].isoformat(),
        threshold=ajustes.get("drift_volatilidade_threshold"),
        janela_candles=ajustes.get("drift_janela_candles"),
    )
    if drift.get("drift_detectado") and modo == "normal":
        modo = "observacao"
        LOG.info("modo_elevado_por_drift", extra={"simbolo": simbolo, **drift})

    mensagem = (
        f"parado={horas_parado:.2f}h variacao={variacao_pct:.3f}% modo={modo}"
        if variacao_pct is not None
        else f"parado={horas_parado:.2f}h modo={modo}"
    )
    LOG.info(
        "retomada_avaliada",
        extra={"simbolo": simbolo, "modo": modo, "horas_parado": horas_parado, "variacao_pct": variacao_pct},
    )
    return _resultado(modo, horas_parado, variacao_pct, preco_anterior, preco_atual, mensagem, snapshot=snapshot, drift=drift)


async def operacoes_bloqueadas_por_retomada() -> bool:
    """Consulta fonte persistente única para bloquear execução durante retomada."""
    return bool(await RepositorioConfig.obter("retomada_operacoes_bloqueadas"))
