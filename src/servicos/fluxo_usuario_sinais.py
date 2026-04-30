from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from src.executor.executor_usuario import ExecutorIsoladoUsuario
from src.observabilidade.audit import registrar_audit
from src.persistencia.repositorio_auditoria import RepositorioAuditoria
from src.persistencia.repositorio_livro_topo import RepositorioLivroTopo
from src.persistencia.repositorio_ohlcv import RepositorioOhlcv
from src.persistencia.repositorio_ordens import RepositorioOrdens
from src.persistencia.repositorio_snapshot import obter_snapshot, salvar_snapshot
from src.persistencia.repositorio_usuarios import RepositorioUsuarios
from src.risco.risk_engine import avaliar_sinal_para_usuario
from src.servicos.ajustes import obter_ajustes_risco, obter_ajustes_sinal
from src.servicos.noticias import obter_noticias_para_peso
from src.sinais.fila_sinais import fila_sinais_global
from src.sinais.signal_engine import gerar_sinal_orquestrado
from src.tarefas.retomada import operacoes_bloqueadas_por_retomada


def _item_para_dict(item: Any) -> dict[str, Any]:
    if item is None:
        return {}
    if hasattr(item, "model_dump"):
        return item.model_dump(exclude_none=True)
    if hasattr(item, "dict"):
        return item.dict(exclude_none=True)
    if isinstance(item, dict):
        return dict(item)
    raise TypeError(f"item nao suportado: {type(item)!r}")


def _lista_para_dicts(itens: list[Any] | None) -> list[dict[str, Any]]:
    return [_item_para_dict(item) for item in list(itens or [])]


async def _carregar_mercado_para_sinal(simbolo: str, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    klines = _lista_para_dicts(payload.get("klines"))
    if klines:
        livro_topo = _item_para_dict(payload.get("livro_topo")) if payload.get("livro_topo") else None
        return (klines, livro_topo)

    registros = await RepositorioOhlcv.obter_ultimas(simbolo, limite=60)
    if not registros:
        raise HTTPException(status_code=404, detail=f"nao ha dados suficientes para gerar sinal em {simbolo}")
    return (registros, await RepositorioLivroTopo.obter_ultimo(simbolo))


async def executar_fluxo_usuario_sinal(usuario_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    usuario = await RepositorioUsuarios.obter(usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail=f"usuario {usuario_id} nao encontrado")
    if not usuario["ativo"]:
        raise HTTPException(status_code=409, detail=f"usuario {usuario_id} inativo")

    simbolo = str(payload.get("simbolo", "BTCUSDT") or "BTCUSDT").upper()
    ajustes_sinal = (await obter_ajustes_sinal())["aplicado"]
    ajustes_risco = (await obter_ajustes_risco())["aplicado"]
    klines, livro_topo = await _carregar_mercado_para_sinal(simbolo, payload)
    saldo = _item_para_dict(payload.get("saldo")) if payload.get("saldo") else None
    noticias = _lista_para_dicts(payload.get("noticias"))
    if not noticias:
        noticias_cache = await obter_noticias_para_peso(simbolo=simbolo)
        noticias = list(noticias_cache.get("itens", []))

    sinal = gerar_sinal_orquestrado(
        simbolo=simbolo,
        klines=klines,
        livro_topo=livro_topo,
        noticias=noticias,
        saldo=saldo,
        ajustes_sinal=ajustes_sinal,
    )
    usuario_exec = dict(usuario)
    if ajustes_risco:
        usuario_exec["risk_config"] = {**usuario_exec.get("risk_config", {}), **ajustes_risco}

    if await operacoes_bloqueadas_por_retomada():
        aprovacao = {
            "usuario_id": usuario["id"],
            "usuario_nome": usuario["nome"],
            "simbolo": simbolo,
            "acao": sinal.get("acao", "HOLD"),
            "aprovado": False,
            "motivos": ["retomada_operacoes_bloqueadas"],
            "fracao_capital": 0.0,
            "notional_sugerido": 0.0,
            "stop_loss_pct": float(sinal.get("stop_loss_pct", 0.0) or 0.0),
            "take_profit_pct": float(sinal.get("take_profit_pct", 0.0) or 0.0),
            "lucro_liquido_esperado_pct": float(sinal.get("lucro_liquido_esperado_pct", 0.0) or 0.0),
            "lucro_liquido_esperado_usdt": 0.0,
            "ev_liquido_usdt": 0.0,
            "confirmacao_multi_timeframe": sinal.get("confirmacao_multi_timeframe", {}),
            "probabilidade_trade": sinal.get("probabilidade_trade", {}),
            "janela_decisao": sinal.get("janela_decisao", {}),
            "paper_trading": True,
            "risk_config_aplicado": usuario_exec.get("risk_config", {}),
        }
    else:
        aprovacao = avaliar_sinal_para_usuario(
            usuario=usuario_exec,
            sinal=sinal,
            saldo=saldo,
            estado_execucao=dict(payload.get("estado_execucao") or {}),
        )

    plano_execucao = None
    ordem_id = None
    publicar_fila = bool(payload.get("publicar_fila", True))
    acao_registravel = str(sinal.get("acao", "HOLD") or "HOLD").upper()
    if acao_registravel == "HOLD":
        acao_registravel = str(((sinal.get("consenso") or {}).get("acao_consenso")) or "HOLD").upper()

    if aprovacao["aprovado"]:
        executor = ExecutorIsoladoUsuario(usuario)
        plano_execucao = await executor.preparar_execucao(
            aprovacao,
            preco_referencia=float(sinal["features"].get("close", 0.0) or 0.0),
        )
        ordem_id = await RepositorioOrdens.criar(
            usuario_id=usuario_id,
            simbolo=simbolo,
            lado=aprovacao["acao"],
            status="SIMULADA" if aprovacao["paper_trading"] else "PENDENTE",
            modo=str(plano_execucao["modo"]),
            preco_referencia=float(plano_execucao["simulacao_ordem"]["preco_referencia"]),
            quantidade=float(plano_execucao["simulacao_ordem"]["quantidade"]),
            notional=float(plano_execucao["simulacao_ordem"]["notional_estimado"]),
            stop_loss_pct=float(aprovacao["stop_loss_pct"]),
            take_profit_pct=float(aprovacao["take_profit_pct"]),
            detalhe={
                "usuario_nome": usuario["nome"],
                "fracao_capital": aprovacao["fracao_capital"],
                "simulacao_ordem": plano_execucao["simulacao_ordem"],
                "motivos_risco": aprovacao["motivos"],
                "confirmacao_multi_timeframe": aprovacao.get("confirmacao_multi_timeframe", {}),
                "probabilidade_trade": aprovacao.get("probabilidade_trade", {}),
                "lucro_liquido_esperado_pct": aprovacao.get("lucro_liquido_esperado_pct", 0.0),
                "ev_liquido_usdt": aprovacao.get("ev_liquido_usdt", 0.0),
                "p_conf_ultimo": float((sinal.get("previsao_modelo") or {}).get("p_conf", 0.0) or 0.0),
                "janela_decisao": aprovacao.get("janela_decisao", {}),
            },
        )
        snapshot = dict(await obter_snapshot(simbolo) or {})
        await salvar_snapshot(
            simbolo,
            {
                **snapshot,
                "modo_operacao": snapshot.get("modo_operacao", "normal"),
                "ultima_ordem": {
                    "id": ordem_id,
                    "lado": aprovacao["acao"],
                    "preco_execucao": float(plano_execucao["simulacao_ordem"]["preco_estimado_execucao"]),
                    "quantidade": float(plano_execucao["simulacao_ordem"]["quantidade"]),
                    "ts": int(plano_execucao["simulacao_ordem"]["executar_apos_ts"]),
                    "status": "SIMULADA" if aprovacao["paper_trading"] else "PENDENTE",
                },
                "posicao_aberta": False,
                "lado_posicao": None,
                "p_conf_ultimo": float((sinal.get("previsao_modelo") or {}).get("p_conf", 0.0) or 0.0),
                "ev_liquido_ultimo": float(aprovacao.get("ev_liquido_usdt", 0.0) or 0.0),
            },
        )
        await registrar_audit(
            "sinal_aprovado",
            "risk_engine",
            "sinal_aprovado_para_execucao",
            usuario_id=usuario_id,
            simbolo=simbolo,
            meta={"ordem_id": ordem_id, "ev_liquido_usdt": aprovacao.get("ev_liquido_usdt", 0.0), "acao": aprovacao["acao"]},
        )
        if publicar_fila:
            await fila_sinais_global.publicar(
                {
                    "usuario_id": usuario_id,
                    "usuario_nome": usuario["nome"],
                    "simbolo": simbolo,
                    "sinal": sinal,
                    "aprovacao_risco": aprovacao,
                    "plano_execucao": plano_execucao,
                    "ordem_id": ordem_id,
                }
            )
    elif acao_registravel != "HOLD":
        ordem_id = await RepositorioOrdens.criar(
            usuario_id=usuario_id,
            simbolo=simbolo,
            lado=acao_registravel,
            status="REJEITADA",
            modo="paper" if usuario["testnet"] else "real",
            preco_referencia=float(sinal["features"].get("close", 0.0) or 0.0),
            quantidade=0.0,
            notional=0.0,
            stop_loss_pct=float(sinal.get("stop_loss_pct", 0.0) or 0.0),
            take_profit_pct=float(sinal.get("take_profit_pct", 0.0) or 0.0),
            detalhe={
                "motivos_risco": aprovacao["motivos"],
                "usuario_nome": usuario["nome"],
                "confirmacao_multi_timeframe": aprovacao.get("confirmacao_multi_timeframe", {}),
                "probabilidade_trade": aprovacao.get("probabilidade_trade", {}),
                "lucro_liquido_esperado_pct": aprovacao.get("lucro_liquido_esperado_pct", 0.0),
                "ev_liquido_usdt": aprovacao.get("ev_liquido_usdt", 0.0),
                "p_conf_ultimo": float((sinal.get("previsao_modelo") or {}).get("p_conf", 0.0) or 0.0),
                "janela_decisao": aprovacao.get("janela_decisao", {}),
                "acao_consenso": acao_registravel,
                "motivo_sinal": sinal.get("motivo"),
            },
        )
        snapshot = dict(await obter_snapshot(simbolo) or {})
        await salvar_snapshot(
            simbolo,
            {
                **snapshot,
                "ultima_rejeicao": {
                    "ordem_id": ordem_id,
                    "motivos": aprovacao["motivos"],
                    "acao": acao_registravel,
                },
                "p_conf_ultimo": float((sinal.get("previsao_modelo") or {}).get("p_conf", 0.0) or 0.0),
                "ev_liquido_ultimo": float(aprovacao.get("ev_liquido_usdt", 0.0) or 0.0),
            },
        )
        await registrar_audit(
            "sinal_rejeitado",
            "risk_engine",
            ",".join(aprovacao["motivos"]) or "sinal_rejeitado",
            usuario_id=usuario_id,
            simbolo=simbolo,
            meta={"ordem_id": ordem_id, "ev_liquido_usdt": aprovacao.get("ev_liquido_usdt", 0.0), "acao": acao_registravel},
        )
        if publicar_fila:
            await fila_sinais_global.publicar(
                {
                    "usuario_id": usuario_id,
                    "usuario_nome": usuario["nome"],
                    "simbolo": simbolo,
                    "sinal": sinal,
                    "aprovacao_risco": aprovacao,
                    "plano_execucao": plano_execucao,
                    "ordem_id": ordem_id,
                }
            )

    await RepositorioAuditoria.registrar(
        simbolo=simbolo,
        tipo="signal_engine",
        payload={
            "usuario_id": usuario_id,
            "usuario_nome": usuario["nome"],
            "sinal": sinal,
            "aprovacao_risco": aprovacao,
            "plano_execucao": plano_execucao,
            "ordem_id": ordem_id,
            "publicado_fila": bool(publicar_fila and ordem_id is not None),
        },
        componente="fluxo_usuario_sinais",
        motivo=str(sinal.get("motivo") or "sinal_processado"),
        meta={"ordem_id": ordem_id, "aprovado": aprovacao.get("aprovado"), "ev_liquido_usdt": aprovacao.get("ev_liquido_usdt", 0.0)},
    )

    return {
        "usuario": usuario,
        "sinal": sinal,
        "aprovacao_risco": aprovacao,
        "plano_execucao": plano_execucao,
        "ordem_id": ordem_id,
        "fila_publicada": bool(publicar_fila and ordem_id is not None),
    }
