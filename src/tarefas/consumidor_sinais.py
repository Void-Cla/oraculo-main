from __future__ import annotations

import asyncio
import time
from typing import Any

from src.contratos.trading import ExecutionPlan, ExecutionResult
from src.core.segredos import resolver_credenciais_usuario
from src.core.settings import env_bool, env_int
from src.executor.gerenciador_ordens import GerenciadorOrdens
from src.observabilidade.audit import registrar_audit
from src.observabilidade.logger import get_logger
from src.persistencia.repositorio_auditoria import RepositorioAuditoria
from src.persistencia.repositorio_ordens import RepositorioOrdens
from src.persistencia.repositorio_snapshot import obter_snapshot, salvar_snapshot
from src.persistencia.repositorio_usuarios import RepositorioUsuarios
from src.sinais.fila_sinais import fila_sinais_global
from src.tarefas.retomada import operacoes_bloqueadas_por_retomada

LOG = get_logger("consumidor_sinais")


async def _salvar_snapshot_execucao(ordem: dict[str, Any], ordem_id: int, detalhe_exec: dict[str, Any]) -> None:
    simbolo = str(ordem["simbolo"]).upper()
    snapshot = dict(await obter_snapshot(simbolo) or {})
    detalhe_ordem = ordem.get("detalhe", {}) if isinstance(ordem.get("detalhe"), dict) else {}
    await salvar_snapshot(
        simbolo,
        {
            **snapshot,
            "modo_operacao": snapshot.get("modo_operacao", "normal"),
            "ultima_ordem": {
                "id": ordem_id,
                "lado": ordem.get("lado"),
                "preco_execucao": detalhe_exec.get("preco_execucao") or ordem.get("preco_referencia"),
                "quantidade": detalhe_exec.get("quantidade_executada") or ordem.get("quantidade"),
                "ts": detalhe_exec.get("ts_execucao") or int(time.time() * 1000),
                "status": "EXECUTADA",
            },
            "posicao_aberta": True,
            "lado_posicao": "LONG" if str(ordem.get("lado")).upper() == "BUY" else "SHORT",
            "p_conf_ultimo": float(detalhe_ordem.get("p_conf_ultimo", 0.0) or 0.0),
            "ev_liquido_ultimo": float(detalhe_ordem.get("ev_liquido_usdt", 0.0) or 0.0),
        },
    )


async def _processar_item(item: dict[str, Any]) -> None:
    fila_id = int(item.get("fila_id", 0) or 0)
    ordem_id = int(item.get("ordem_id", 0) or 0)
    usuario_id = item.get("usuario_id")
    tentativas = int((item.get("_fila_meta") or {}).get("tentativas", 0) or 0)
    plano = ExecutionPlan.from_mapping(item.get("plano_execucao") or {})

    try:
        ordem = await RepositorioOrdens.obter(ordem_id)
        if ordem is None:
            if fila_id:
                await fila_sinais_global.concluir(
                    fila_id,
                    ExecutionResult(ordem_id=ordem_id, status="IGNORADA", modo="desconhecido", detalhe={"motivo": "ordem_nao_encontrada"}).to_dict(),
                )
            LOG.warning("ordem_nao_encontrada", extra={"ordem_id": ordem_id})
            return

        if ordem["status"] in {"EXECUTADA", "CANCELADA", "REJEITADA"}:
            if fila_id:
                await fila_sinais_global.concluir(
                    fila_id,
                    ExecutionResult(ordem_id=ordem_id, status="IGNORADA", modo=str(ordem.get("modo", "")), detalhe={"motivo": "status_final"}).to_dict(),
                )
            LOG.info("ordem_ignorada_status", extra={"ordem_id": ordem_id, "status": ordem["status"]})
            return

        if await operacoes_bloqueadas_por_retomada():
            detalhe_bloqueio = {"motivo": "retomada_operacoes_bloqueadas", "ordem_id": ordem_id}
            if fila_id:
                await fila_sinais_global.falhar(fila_id, detalhe_bloqueio, refileirar=True)
            await registrar_audit(
                "execucao_bloqueada",
                "consumidor_sinais",
                "retomada_operacoes_bloqueadas",
                usuario_id=usuario_id,
                simbolo=ordem["simbolo"],
                meta=detalhe_bloqueio,
            )
            LOG.warning("execucao_bloqueada_por_retomada", extra=detalhe_bloqueio)
            return

        modo = (ordem.get("modo") or "").lower()
        simulacao = plano.simulacao_ordem or ordem.get("detalhe", {}).get("simulacao_ordem") or {}
        preco_exec = float(simulacao.get("preco_estimado_execucao") or ordem.get("preco_referencia") or 0.0)
        quantidade = float(simulacao.get("quantidade") or ordem.get("quantidade") or 0.0)

        if modo == "paper":
            detalhe_exec = {
                "simulada": True,
                "preco_execucao": preco_exec,
                "quantidade_executada": quantidade,
                "notional_execucao": preco_exec * quantidade,
                "ts_execucao": int(time.time() * 1000),
            }
            await RepositorioOrdens.atualizar_status(ordem_id, "EXECUTADA", {"execucao": detalhe_exec})
            await _salvar_snapshot_execucao(ordem, ordem_id, detalhe_exec)
            await RepositorioAuditoria.registrar(
                simbolo=ordem["simbolo"],
                tipo="execucao_simulada",
                payload={"ordem_id": ordem_id, "detalhe": detalhe_exec},
                componente="consumidor_sinais",
                motivo="ordem_simulada_executada",
                meta={"ordem_id": ordem_id, "modo": "paper"},
            )
            await registrar_audit(
                "ordem_executada",
                "executor",
                f"ordem {ordem_id} executada em paper",
                usuario_id=usuario_id,
                simbolo=ordem["simbolo"],
                meta={"ordem_id": ordem_id, "modo": "paper", "detalhe": detalhe_exec},
            )
            if fila_id:
                await fila_sinais_global.concluir(
                    fila_id,
                    ExecutionResult(ordem_id=ordem_id, status="EXECUTADA", modo="paper", detalhe=detalhe_exec).to_dict(),
                )
            LOG.info("ordem_simulada_executada", extra={"ordem_id": ordem_id})
            return

        usuario = await RepositorioUsuarios.obter(usuario_id) if usuario_id is not None else None
        credenciais = resolver_credenciais_usuario(usuario or {})
        api_key = credenciais.get("api_key")
        api_secret = credenciais.get("api_secret")
        force_sim = env_bool("FORCE_SIMULATED_TESTNET", False)

        if modo == "testnet" and (force_sim or not (api_key and api_secret)):
            detalhe_exec = {
                "simulada": True,
                "preco_execucao": preco_exec,
                "quantidade_executada": quantidade,
                "notional_execucao": preco_exec * quantidade,
                "ts_execucao": int(time.time() * 1000),
                "origem_credencial": credenciais.get("origem"),
            }
            await RepositorioOrdens.atualizar_status(ordem_id, "EXECUTADA", {"execucao": detalhe_exec})
            await _salvar_snapshot_execucao(ordem, ordem_id, detalhe_exec)
            await RepositorioAuditoria.registrar(
                simbolo=ordem["simbolo"],
                tipo="execucao_simulada",
                payload={"ordem_id": ordem_id, "detalhe": detalhe_exec},
                componente="consumidor_sinais",
                motivo="ordem_testnet_simulada_executada",
                meta={"ordem_id": ordem_id, "modo": "testnet_simulada"},
            )
            await registrar_audit(
                "ordem_executada",
                "executor",
                f"ordem {ordem_id} executada em testnet_simulada",
                usuario_id=usuario_id,
                simbolo=ordem["simbolo"],
                meta={"ordem_id": ordem_id, "modo": "testnet_simulada", "detalhe": detalhe_exec},
            )
            if fila_id:
                await fila_sinais_global.concluir(
                    fila_id,
                    ExecutionResult(ordem_id=ordem_id, status="EXECUTADA", modo="testnet_simulada", detalhe=detalhe_exec).to_dict(),
                )
            LOG.info("ordem_simulada_executada_testnet_override", extra={"ordem_id": ordem_id, "force_sim": force_sim})
            return

        ger = GerenciadorOrdens(api_key=api_key, api_secret=api_secret, testnet=bool((usuario or {}).get("testnet", False)))
        try:
            resposta = await ger.criar_ordem_limit(ordem["simbolo"], ordem["lado"], float(ordem.get("quantidade") or 0.0), preco_exec)
        finally:
            await ger.fechar()

        await RepositorioOrdens.atualizar_status(ordem_id, "EXECUTADA", {"execucao": resposta})
        await _salvar_snapshot_execucao(ordem, ordem_id, resposta)
        await RepositorioAuditoria.registrar(
            simbolo=ordem["simbolo"],
            tipo="execucao_real",
            payload={"ordem_id": ordem_id, "resposta": resposta},
            componente="consumidor_sinais",
            motivo="ordem_real_executada",
            meta={"ordem_id": ordem_id, "modo": modo},
        )
        await registrar_audit(
            "ordem_executada",
            "executor",
            f"ordem {ordem_id} executada em {modo}",
            usuario_id=usuario_id,
            simbolo=ordem["simbolo"],
            meta={"ordem_id": ordem_id, "modo": modo},
        )
        if fila_id:
            await fila_sinais_global.concluir(
                fila_id,
                ExecutionResult(ordem_id=ordem_id, status="EXECUTADA", modo=modo, detalhe=resposta).to_dict(),
            )
        LOG.info("ordem_executada_real", extra={"ordem_id": ordem_id})
    except Exception as exc:
        try:
            if ordem_id:
                await RepositorioOrdens.atualizar_status(ordem_id, "REJEITADA", {"erro_execucao": str(exc)})
        except Exception:
            LOG.warning("falha_atualizar_status_rejeitado", extra={"ordem_id": ordem_id})
        if ordem_id:
            await RepositorioAuditoria.registrar(
                simbolo=str(item.get("simbolo") or "DESCONHECIDO"),
                tipo="execucao_falha",
                payload={"ordem_id": ordem_id, "erro": str(exc)},
                componente="consumidor_sinais",
                motivo="falha_execucao_ordem",
                meta={"ordem_id": ordem_id, "erro": str(exc)},
            )
            await registrar_audit(
                "ordem_rejeitada_execucao",
                "executor",
                str(exc),
                usuario_id=usuario_id,
                simbolo=str(item.get("simbolo") or "DESCONHECIDO"),
                meta={"ordem_id": ordem_id},
            )
        if fila_id:
            max_tentativas = env_int("FILA_MAX_TENTATIVAS", 3, minimo=1)
            await fila_sinais_global.falhar(
                fila_id,
                {"erro": str(exc), "ordem_id": ordem_id, "usuario_id": usuario_id},
                refileirar=tentativas < max_tentativas,
            )
        LOG.error("erro_processar_item_fila", extra={"erro": str(exc), "item": item})


async def loop_consumidor_sinais() -> None:
    LOG.info("consumidor_sinais_iniciado")
    tarefas_em_andamento: set[asyncio.Task[Any]] = set()
    try:
        while True:
            item = await fila_sinais_global.consumir()
            tarefa = asyncio.create_task(_processar_item(item))
            tarefas_em_andamento.add(tarefa)
            tarefa.add_done_callback(tarefas_em_andamento.discard)
    except asyncio.CancelledError:
        for tarefa in list(tarefas_em_andamento):
            tarefa.cancel()
        if tarefas_em_andamento:
            await asyncio.gather(*tarefas_em_andamento, return_exceptions=True)
        LOG.info("consumidor_sinais_cancelado")
        raise
    except Exception as exc:
        for tarefa in list(tarefas_em_andamento):
            tarefa.cancel()
        if tarefas_em_andamento:
            await asyncio.gather(*tarefas_em_andamento, return_exceptions=True)
        LOG.error("consumidor_sinais_falha_geral", extra={"erro": str(exc)})
