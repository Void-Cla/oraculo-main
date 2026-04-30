from __future__ import annotations

"""API principal do Oráculo (entrada da aplicação).

Este módulo expõe os endpoints HTTP, inicializa tarefas assíncronas
e faz a orquestração de alto nível entre coleta, modelos, sinais e execução.
Comentários e nomes públicos seguem português conciso para consistência.
"""

import asyncio
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from src.binance_api.cliente import ClienteBinance
from src.binance_api.coletor_velas_rest import coletar_e_persistir
from src.executor.gerenciador_ordens import GerenciadorOrdens
from src.modelagem.gerenciador_modelo import GerenciadorModelo
from src.multiativo.config import validar_par_monitorado
from src.multiativo.orquestrador import montar_monitoramento_multiativo
from src.observabilidade.audit import registrar_audit
from src.observabilidade.logger import get_logger
from src.observabilidade.metricas import (
    CONTENT_TYPE_LATEST,
    confianca_previsao,
    decisoes_total,
    exportar_metricas,
    latencia_previsao_segundos,
    previsoes_erro_total,
    previsoes_total,
)
from src.persistencia.conexao import inicializar_db, obter_db_path
from src.persistencia.repositorio_auditoria import RepositorioAuditoria
from src.persistencia.repositorio_config import RepositorioConfig
from src.persistencia.repositorio_features import RepositorioFeatures
from src.persistencia.repositorio_livro_topo import RepositorioLivroTopo
from src.persistencia.repositorio_ohlcv import RepositorioOhlcv
from src.persistencia.repositorio_ordens import RepositorioOrdens
from src.persistencia.repositorio_snapshot import obter_snapshot, salvar_snapshot
from src.persistencia.repositorio_outcomes import RepositorioOutcomes
from src.persistencia.repositorio_predicoes import RepositorioPredicoes
from src.persistencia.repositorio_usuarios import RepositorioUsuarios
from src.servicos.ajustes import (
    garantir_ajustes_padrao,
    obter_ajustes_risco,
    obter_ajustes_retomada,
    obter_ajustes_sinal,
    obter_ajustes_testnet,
    salvar_ajustes_risco,
    salvar_ajustes_retomada,
    salvar_ajustes_sinal,
    salvar_ajustes_testnet,
)
from src.servicos.dashboard import montar_dashboard
from src.servicos.fluxo_usuario_sinais import executar_fluxo_usuario_sinal
from src.servicos.noticias import obter_noticias_para_peso, renderizar_fonte_noticias_html
from src.servicos.painel_conta import montar_painel_conta
from src.servicos.sessoes import criar_sessao_binance, encerrar_sessao, obter_sessao
from src.servicos.testnet_auto_trader import TestnetAutoTrader
from src.sinais.fila_sinais import fila_sinais_global
from src.tarefas.tarefas_previsao import gerar_previsao_dados_persistidos, gerar_previsao_por_klines, loop_previsao
from src.tarefas.consumidor_sinais import loop_consumidor_sinais
from src.tarefas.carga_teste_rapida import executar_carga_testes
from src.tarefas.observacao import aguardar_observacao
from src.tarefas.recalibracao_startup import recalibrar_ao_religar
from src.tarefas.retomada import avaliar_retomada

LOG = get_logger("main")
TESTNET_TRADER = TestnetAutoTrader()
AUTO_TRADER = TESTNET_TRADER


class LivroTopoEntrada(BaseModel):
    bid_price: float | None = None
    bid_qty: float | None = None
    ask_price: float | None = None
    ask_qty: float | None = None


class NoticiaEntrada(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    sentimento: float | None = None
    fonte: str | None = None


class SaldoEntrada(BaseModel):
    saldo_total: float | None = None
    saldo_livre: float | None = None


class KlineEntrada(BaseModel):
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class PrevisaoManualEntrada(BaseModel):
    simbolo: str = "BTCUSDT"
    klines: list[KlineEntrada] = Field(default_factory=list)
    livro_topo: LivroTopoEntrada | None = None
    noticias: list[NoticiaEntrada] = Field(default_factory=list)
    saldo: SaldoEntrada | None = None
    salvar: bool = True


class ConfigEntrada(BaseModel):
    valor: Any


class UsuarioEntrada(BaseModel):
    nome: str
    api_key_secret_id: str | None = None
    api_secret_secret_id: str | None = None
    api_key_ref: str | None = None
    api_secret_ref: str | None = None
    ativo: bool = True
    testnet: bool = True
    risk_config: dict[str, Any] = Field(default_factory=dict)


class SinalUsuarioEntrada(BaseModel):
    simbolo: str = "BTCUSDT"
    klines: list[KlineEntrada] = Field(default_factory=list)
    livro_topo: LivroTopoEntrada | None = None
    noticias: list[NoticiaEntrada] = Field(default_factory=list)
    saldo: SaldoEntrada | None = None
    estado_execucao: dict[str, Any] = Field(default_factory=dict)
    publicar_fila: bool = True


class OrdemStatusEntrada(BaseModel):
    status: str
    detalhe_extra: dict[str, Any] = Field(default_factory=dict)


class SessaoEntrada(BaseModel):
    api_key: str
    api_secret: str
    testnet: bool = False


class AutoTradeEntrada(BaseModel):
    simbolo: str = "BTCUSDT"
    intervalo_segundos: int = 30
    notional_usdt: float = 5.0
    lado_inicial: str = "BUY"


class AutoTradeCapitalEntrada(BaseModel):
    notional_usdt: float = 5.0


class ManualTradeEntrada(BaseModel):
    simbolo: str = "BTCUSDT"
    lado: str
    quantidade: float | None = None
    notional_usdt: float | None = None


async def _definir_estado_retomada(app: FastAPI, simbolo: str, modo: str, bloqueado: bool, contexto: dict[str, Any]) -> None:
    app.state.retomada_modo = modo
    app.state.retomada_operacoes_bloqueadas = bool(bloqueado)
    await RepositorioConfig.definir("retomada_modo", modo)
    await RepositorioConfig.definir("retomada_operacoes_bloqueadas", bool(bloqueado))
    await RepositorioConfig.definir("retomada_contexto", contexto)
    snapshot = dict(await obter_snapshot(simbolo) or {})
    await salvar_snapshot(simbolo, {**snapshot, "modo_operacao": modo})


async def _inicializar_retomada(app: FastAPI) -> asyncio.Task | None:
    ajustes = (await obter_ajustes_retomada())["aplicado"]
    simbolo = str(ajustes.get("simbolo_principal") or os.getenv("SIMBOLO_PRINCIPAL") or "BTCUSDT").upper()
    try:
        contexto = await avaliar_retomada(simbolo, ajustes=ajustes)
    except Exception as exc:
        contexto = {"modo": "observacao", "mensagem": f"falha_avaliar_retomada:{exc}", "erro": str(exc)}
        await _definir_estado_retomada(app, simbolo, "observacao", True, contexto)
        await registrar_audit("retomada_falha", "retomada", str(exc), simbolo=simbolo, meta=contexto)
        LOG.error("retomada_falha", extra={"simbolo": simbolo, "erro": str(exc)})
        return None

    modo = str(contexto["modo"])
    await _definir_estado_retomada(app, simbolo, modo, modo != "normal", contexto)
    await registrar_audit("retomada_iniciada", "retomada", str(contexto.get("mensagem") or modo), simbolo=simbolo, meta=contexto)
    LOG.info("contexto_retomada", extra={"simbolo": simbolo, **contexto})

    if modo == "recalibracao_forcada":
        resultado = await recalibrar_ao_religar(simbolo, candles=int(ajustes.get("recalibracao_candles", 60) or 60))
        await registrar_audit("recalibracao_startup", "recalibracao_startup", str(resultado["status"]), simbolo=simbolo, meta=resultado)
        if resultado.get("status") == "ok":
            await _definir_estado_retomada(app, simbolo, "normal", False, {**contexto, "recalibracao": resultado})
            return None
        modo = "observacao"
        await _definir_estado_retomada(app, simbolo, modo, True, {**contexto, "recalibracao": resultado})

    if modo == "observacao":
        return asyncio.create_task(
            aguardar_observacao(
                simbolo,
                candles=int(ajustes.get("candles_observacao", 5) or 5),
                intervalo_segundos=60,
            )
        )
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    caminho = inicializar_db()
    tarefa_loop: asyncio.Task | None = None
    tarefa_consumidor: asyncio.Task | None = None
    tarefa_carga_teste: asyncio.Task | None = None
    tarefa_observacao: asyncio.Task | None = None
    await garantir_ajustes_padrao()
    tarefa_observacao = await _inicializar_retomada(app)
    if os.getenv("ATIVAR_LOOP_PREVISAO", "false").lower() == "true":
        tarefa_loop = asyncio.create_task(loop_previsao())
    if os.getenv("ATIVAR_CONSUMIDOR_SINAIS", "false").lower() == "true":
        tarefa_consumidor = asyncio.create_task(loop_consumidor_sinais())
    if os.getenv("ATIVAR_CARGA_TESTE", "false").lower() == "true":
        tarefa_carga_teste = asyncio.create_task(executar_carga_testes())
    app.state.tarefa_loop = tarefa_loop
    app.state.tarefa_consumidor = tarefa_consumidor
    app.state.tarefa_carga_teste = tarefa_carga_teste
    app.state.tarefa_observacao = tarefa_observacao
    LOG.info("app_iniciada", extra={"db_path": str(caminho), "loop_previsao_ativo": tarefa_loop is not None})
    try:
        yield
    finally:
        if tarefa_loop is not None:
            tarefa_loop.cancel()
            await asyncio.gather(tarefa_loop, return_exceptions=True)
        if tarefa_consumidor is not None:
            tarefa_consumidor.cancel()
            await asyncio.gather(tarefa_consumidor, return_exceptions=True)
        if tarefa_carga_teste is not None:
            tarefa_carga_teste.cancel()
            await asyncio.gather(tarefa_carga_teste, return_exceptions=True)
        if tarefa_observacao is not None:
            tarefa_observacao.cancel()
            await asyncio.gather(tarefa_observacao, return_exceptions=True)
        await TESTNET_TRADER.encerrar_todos()
        LOG.info("app_finalizada")


app = FastAPI(title="Oraculo API", version="0.2.0", lifespan=lifespan)


def _modelo_status(simbolo: str) -> dict[str, Any]:
    return GerenciadorModelo(simbolo=simbolo).status()


def _dump_model(modelo: Any) -> dict[str, Any]:
    if hasattr(modelo, "model_dump"):
        return modelo.model_dump(exclude_none=True)
    return modelo.dict(exclude_none=True)


def _noticias_para_lista(noticias: list[NoticiaEntrada]) -> list[dict[str, Any]]:
    return [_dump_model(item) for item in noticias]


def _max_age_sessao_segundos() -> int:
    horas = float(os.getenv("SESSION_TTL_HOURS", "12") or 12)
    return max(3600, int(horas * 3600))


def _simbolo_monitorado(simbolo: str) -> str:
    try:
        return validar_par_monitorado(simbolo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _normalizar_lado(lado: str) -> str:
    lado = str(lado or "").upper()
    if lado not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="lado_invalido")
    return lado


async def _sessao_autenticada(request: Request) -> dict[str, Any]:
    token = request.cookies.get("oraculo_sessao")
    sessao = await obter_sessao(token)
    if sessao is None:
        raise HTTPException(status_code=401, detail="sessao_binance_ausente_ou_expirada")
    return sessao


async def _status_auto_trade(token: str | None, sessao: dict[str, Any]) -> dict[str, Any]:
    if not token:
        return {"ativo": False, "estado_ciclo": "INDISPONIVEL", "ultimo_motivo": "sessao_ausente"}
    ajustes = await obter_ajustes_testnet()
    status = AUTO_TRADER.status(token)
    config_status = dict(status.get("config") or {})
    config_ajustes = dict(ajustes.get("aplicado") or {})
    status["config"] = {
        "simbolo": config_status.get("simbolo") or config_ajustes.get("simbolo", "BTCUSDT"),
        "intervalo_segundos": int(config_status.get("intervalo_segundos") or config_ajustes.get("intervalo_segundos", 30)),
        "notional_usdt": float(config_status.get("notional_usdt") or config_ajustes.get("notional_usdt", 5.0)),
    }
    status["modo_testnet"] = bool(sessao.get("modo_testnet", False))
    status["modo"] = "testnet" if status["modo_testnet"] else "real"
    if not status.get("ativo"):
        status["estado_ciclo"] = "PAUSADO"
        status["ultimo_motivo"] = "bot_pausado"
    return status


async def _status_auto_trade_testnet(token: str | None, sessao: dict[str, Any]) -> dict[str, Any]:
    if not sessao.get("modo_testnet"):
        return {
            "ativo": False,
            "estado_ciclo": "INDISPONIVEL",
            "ultimo_motivo": "disponivel_apenas_na_testnet",
        }
    return await _status_auto_trade(token, sessao)


@app.get("/")
async def raiz() -> dict[str, Any]:
    return {
        "nome": "Oraculo",
        "versao": app.version,
        "health": "/v1/health",
        "metrics": "/v1/metrics",
        "previsao": "/v1/previsao",
    }


@app.get("/v1/health")
async def health() -> dict[str, Any]:
    tarefa_loop = getattr(app.state, "tarefa_loop", None)
    tarefa_observacao = getattr(app.state, "tarefa_observacao", None)
    return {
        "status": "ok",
        "db_path": str(obter_db_path()),
        "loop_previsao_ativo": bool(tarefa_loop and not tarefa_loop.done()),
        "retomada_modo": getattr(app.state, "retomada_modo", await RepositorioConfig.obter("retomada_modo")),
        "retomada_operacoes_bloqueadas": bool(
            getattr(app.state, "retomada_operacoes_bloqueadas", await RepositorioConfig.obter("retomada_operacoes_bloqueadas"))
        ),
        "observacao_ativa": bool(tarefa_observacao and not tarefa_observacao.done()),
        "ts": int(time.time() * 1000),
    }


@app.get("/v1/metrics")
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(exportar_metricas(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/modelos/status")
async def status_modelo(simbolo: str = "BTCUSDT") -> dict[str, Any]:
    return _modelo_status(simbolo)


@app.post("/v1/sessao/entrar")
async def entrar_sessao(entrada: SessaoEntrada, response: Response) -> dict[str, Any]:
    modo = "testnet" if entrada.testnet else "real"
    try:
        sessao = await criar_sessao_binance(entrada.api_key, entrada.api_secret, testnet=entrada.testnet)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"falha_ao_validar_credenciais_binance_{modo}: {exc}") from exc

    response.set_cookie(
        key="oraculo_sessao",
        value=sessao["token"],
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        max_age=_max_age_sessao_segundos(),
        path="/",
    )
    payload = {k: v for k, v in sessao.items() if k != "token"}
    sessao_completa = await obter_sessao(sessao["token"])
    if sessao_completa is not None:
        payload["auto_trade"] = await _status_auto_trade(sessao["token"], sessao_completa)
    return payload


@app.get("/v1/sessao/status")
async def status_sessao(request: Request) -> dict[str, Any]:
    token = request.cookies.get("oraculo_sessao")
    sessao = await obter_sessao(token)
    if sessao is None:
        return {"autenticado": False}
    payload = {"autenticado": True, **{k: v for k, v in sessao.items() if k not in {"api_key", "api_secret"}}}
    payload["auto_trade"] = await _status_auto_trade(token, sessao)
    return payload


@app.post("/v1/sessao/sair")
async def sair_sessao(request: Request, response: Response) -> dict[str, Any]:
    token = request.cookies.get("oraculo_sessao")
    await encerrar_sessao(token)
    if token:
        await TESTNET_TRADER.parar(token)
    response.delete_cookie("oraculo_sessao", path="/")
    return {"autenticado": False}


@app.get("/v1/testnet/auto/status")
async def status_auto_testnet(request: Request) -> dict[str, Any]:
    sessao = await _sessao_autenticada(request)
    token = request.cookies.get("oraculo_sessao")
    return await _status_auto_trade_testnet(token, sessao)


@app.get("/v1/auto/status")
async def status_auto(request: Request) -> dict[str, Any]:
    sessao = await _sessao_autenticada(request)
    token = request.cookies.get("oraculo_sessao")
    return await _status_auto_trade(token, sessao)


@app.post("/v1/testnet/auto/start")
async def iniciar_auto_testnet(request: Request, entrada: AutoTradeEntrada) -> dict[str, Any]:
    sessao = await _sessao_autenticada(request)
    if not sessao.get("modo_testnet"):
        raise HTTPException(status_code=403, detail="modo_testnet_obrigatorio")
    ajustes = await salvar_ajustes_testnet(entrada.model_dump())
    token = request.cookies.get("oraculo_sessao")
    status = await AUTO_TRADER.iniciar(token or "", sessao, ajustes["aplicado"])
    return {"status": status, "ajustes": ajustes}


@app.post("/v1/auto/start")
async def iniciar_auto(request: Request, entrada: AutoTradeEntrada) -> dict[str, Any]:
    sessao = await _sessao_autenticada(request)
    if not sessao.get("modo_testnet") and os.getenv("PERMITIR_CONTA_REAL", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="conta_real_bloqueada")
    ajustes = await salvar_ajustes_testnet(entrada.model_dump())
    token = request.cookies.get("oraculo_sessao")
    status = await AUTO_TRADER.iniciar(token or "", sessao, ajustes["aplicado"])
    return {"status": status, "ajustes": ajustes}


@app.put("/v1/testnet/auto/config")
async def atualizar_config_auto_testnet(request: Request, entrada: AutoTradeCapitalEntrada) -> dict[str, Any]:
    sessao = await _sessao_autenticada(request)
    if not sessao.get("modo_testnet"):
        raise HTTPException(status_code=403, detail="modo_testnet_obrigatorio")
    atuais = await obter_ajustes_testnet()
    ajustes = await salvar_ajustes_testnet(
        {
            **atuais["aplicado"],
            "notional_usdt": float(entrada.notional_usdt),
        }
    )
    token = request.cookies.get("oraculo_sessao")
    status = await AUTO_TRADER.atualizar_config(
        token or "",
        {**ajustes["aplicado"], "modo_testnet": bool(sessao.get("modo_testnet", False))},
    )
    return {"status": status, "ajustes": ajustes}


@app.put("/v1/auto/config")
async def atualizar_config_auto(request: Request, entrada: AutoTradeCapitalEntrada) -> dict[str, Any]:
    sessao = await _sessao_autenticada(request)
    atuais = await obter_ajustes_testnet()
    ajustes = await salvar_ajustes_testnet(
        {
            **atuais["aplicado"],
            "notional_usdt": float(entrada.notional_usdt),
        }
    )
    token = request.cookies.get("oraculo_sessao")
    status = await AUTO_TRADER.atualizar_config(
        token or "",
        {**ajustes["aplicado"], "modo_testnet": bool(sessao.get("modo_testnet", False))},
    )
    return {"status": status, "ajustes": ajustes}


@app.post("/v1/testnet/auto/stop")
async def parar_auto_testnet(request: Request) -> dict[str, Any]:
    sessao = await _sessao_autenticada(request)
    token = request.cookies.get("oraculo_sessao")
    await AUTO_TRADER.parar(token or "")
    return await _status_auto_trade_testnet(token, sessao)


@app.post("/v1/auto/stop")
async def parar_auto(request: Request) -> dict[str, Any]:
    sessao = await _sessao_autenticada(request)
    token = request.cookies.get("oraculo_sessao")
    await AUTO_TRADER.parar(token or "")
    return await _status_auto_trade(token, sessao)


@app.post("/v1/trading/manual")
async def trading_manual(request: Request, entrada: ManualTradeEntrada) -> dict[str, Any]:
    sessao = await _sessao_autenticada(request)
    modo_testnet = bool(sessao.get("modo_testnet"))
    if not modo_testnet and os.getenv("PERMITIR_CONTA_REAL", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="conta_real_bloqueada")

    simbolo = _simbolo_monitorado(entrada.simbolo)
    lado = _normalizar_lado(entrada.lado)
    quantidade = float(entrada.quantidade) if entrada.quantidade is not None else None
    notional_usdt = float(entrada.notional_usdt) if entrada.notional_usdt is not None else None
    ger = GerenciadorOrdens(
        api_key=str(sessao["api_key"]),
        api_secret=str(sessao["api_secret"]),
        testnet=modo_testnet,
    )
    cliente = ClienteBinance(
        api_key=str(sessao["api_key"]),
        api_secret=str(sessao["api_secret"]),
        testnet=modo_testnet,
    )
    try:
        filtros = await ger.obter_filtros_simbolo(simbolo)
        min_notional = float(filtros.get("min_notional", 0.0) or 0.0)
        min_qty = float(filtros.get("min_qty", 0.0) or 0.0)
        step_size = float(filtros.get("step_size", 0.0) or 0.0)
        payload_ordem: dict[str, Any] = {}

        if lado == "BUY":
            if quantidade is not None:
                quantidade = ger.ajustar_quantidade(quantidade, step_size, min_qty)
                if quantidade <= 0:
                    raise HTTPException(status_code=400, detail="quantidade_invalida")
                preco = await cliente.obter_preco_atual(simbolo)
                notional_calculado = quantidade * preco if preco > 0 else 0.0
                if notional_calculado < max(min_notional, 1e-9):
                    raise HTTPException(status_code=400, detail="notional_abaixo_do_minimo")
                payload_ordem["quantidade"] = quantidade
            elif notional_usdt is not None:
                if notional_usdt < max(min_notional, 1e-9):
                    raise HTTPException(status_code=400, detail="notional_abaixo_do_minimo")
                payload_ordem["quote_order_qty"] = notional_usdt
            else:
                raise HTTPException(status_code=400, detail="quantidade_ou_notional_obrigatorio")
        else:
            if quantidade is None:
                if notional_usdt is None:
                    raise HTTPException(status_code=400, detail="quantidade_ou_notional_obrigatorio")
                preco = await cliente.obter_preco_atual(simbolo)
                quantidade = (notional_usdt / preco) if preco > 0 else 0.0
                notional_usdt = quantidade * preco if preco > 0 else notional_usdt
            else:
                preco = await cliente.obter_preco_atual(simbolo)
                notional_usdt = quantidade * preco if preco > 0 else notional_usdt
            quantidade = ger.ajustar_quantidade(float(quantidade), step_size, min_qty)
            if quantidade <= 0:
                raise HTTPException(status_code=400, detail="quantidade_invalida")
            if notional_usdt is not None and notional_usdt < max(min_notional, 1e-9):
                raise HTTPException(status_code=400, detail="notional_abaixo_do_minimo")
            payload_ordem["quantidade"] = quantidade

        if "quote_order_qty" in payload_ordem:
            ordem = await ger.criar_ordem_market(simbolo, lado, quote_order_qty=payload_ordem["quote_order_qty"])
        else:
            ordem = await ger.criar_ordem_market(simbolo, lado, quantidade=payload_ordem["quantidade"])

        await RepositorioAuditoria.registrar(
            simbolo=simbolo,
            tipo="ordem_manual",
            payload={
                "lado": lado,
                "modo": "testnet" if modo_testnet else "real",
                "quantidade": payload_ordem.get("quantidade"),
                "notional_usdt": payload_ordem.get("quote_order_qty") or notional_usdt,
                "ordem_id": ordem.get("orderId"),
                "status": ordem.get("status"),
            },
        )
        return {"ok": True, "ordem": ordem, "modo": "testnet" if modo_testnet else "real"}
    finally:
        await ger.fechar()
        await cliente.fechar()


@app.get("/v1/previsao")
async def obter_previsao(
    simbolo: str = "BTCUSDT",
    coletar_mercado: bool = False,
    limite_klines: int = 60,
    persistir: bool = True,
) -> JSONResponse:
    simbolo = simbolo.upper()
    origem = "api_rest"
    inicio = time.perf_counter()
    ajustes_sinal = (await obter_ajustes_sinal())["aplicado"]
    try:
        resultado = await gerar_previsao_dados_persistidos(
            simbolo=simbolo,
            coletar_mercado=coletar_mercado,
            limite_klines=max(20, limite_klines),
            persistir=persistir,
            origem=origem,
            ajustes_sinal=ajustes_sinal,
        )
        latencia_previsao_segundos.labels(simbolo=simbolo, origem=origem).observe(time.perf_counter() - inicio)
        previsoes_total.labels(simbolo=simbolo, origem=origem).inc()
        confianca_previsao.labels(simbolo=simbolo).set(resultado["p_conf"])
        decisoes_total.labels(simbolo=simbolo, acao=resultado["decisao"]["acao"]).inc()
        return JSONResponse(resultado)
    except ValueError as exc:
        if not coletar_mercado:
            origem_fallback = f"{origem}_fallback"
            try:
                resultado = await gerar_previsao_dados_persistidos(
                    simbolo=simbolo,
                    coletar_mercado=True,
                    limite_klines=max(20, limite_klines),
                    persistir=persistir,
                    origem=origem_fallback,
                    ajustes_sinal=ajustes_sinal,
                )
                latencia_previsao_segundos.labels(simbolo=simbolo, origem=origem_fallback).observe(time.perf_counter() - inicio)
                previsoes_total.labels(simbolo=simbolo, origem=origem_fallback).inc()
                confianca_previsao.labels(simbolo=simbolo).set(resultado["p_conf"])
                decisoes_total.labels(simbolo=simbolo, acao=resultado["decisao"]["acao"]).inc()
                return JSONResponse(resultado)
            except Exception as fallback_exc:
                previsoes_erro_total.labels(simbolo=simbolo, origem=origem_fallback).inc()
                LOG.warning(
                    "falha_fallback_previsao",
                    extra={"simbolo": simbolo, "erro_inicial": str(exc), "erro_fallback": str(fallback_exc)},
                )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        previsoes_erro_total.labels(simbolo=simbolo, origem=origem).inc()
        LOG.error("falha_endpoint_previsao", extra={"simbolo": simbolo, "erro": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/v1/previsao/manual")
async def prever_manual(payload: PrevisaoManualEntrada) -> JSONResponse:
    simbolo = payload.simbolo.upper()
    origem = "api_manual"
    inicio = time.perf_counter()
    ajustes_sinal = (await obter_ajustes_sinal())["aplicado"]
    try:
        resultado = await gerar_previsao_por_klines(
            simbolo=simbolo,
            klines=[_dump_model(item) for item in payload.klines],
            livro_topo=_dump_model(payload.livro_topo) if payload.livro_topo else None,
            noticias=_noticias_para_lista(payload.noticias),
            saldo=_dump_model(payload.saldo) if payload.saldo else None,
            persistir=payload.salvar,
            origem=origem,
            ajustes_sinal=ajustes_sinal,
        )
        latencia_previsao_segundos.labels(simbolo=simbolo, origem=origem).observe(time.perf_counter() - inicio)
        previsoes_total.labels(simbolo=simbolo, origem=origem).inc()
        confianca_previsao.labels(simbolo=simbolo).set(resultado["p_conf"])
        decisoes_total.labels(simbolo=simbolo, acao=resultado["decisao"]["acao"]).inc()
        return JSONResponse(resultado)
    except Exception as exc:
        previsoes_erro_total.labels(simbolo=simbolo, origem=origem).inc()
        LOG.error("falha_endpoint_previsao_manual", extra={"simbolo": simbolo, "erro": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/v1/export/ohlcv")
async def exportar_ohlcv(simbolo: str = "BTCUSDT", limite: int = 200) -> dict[str, Any]:
    return {"simbolo": simbolo.upper(), "itens": await RepositorioOhlcv.obter_ultimas(simbolo.upper(), limite=max(1, limite))}


@app.get("/v1/export/livro-topo")
async def exportar_livro_topo(simbolo: str = "BTCUSDT", limite: int = 50) -> dict[str, Any]:
    return {"simbolo": simbolo.upper(), "itens": await RepositorioLivroTopo.listar_ultimos(simbolo.upper(), limite=max(1, limite))}


@app.get("/v1/export/features")
async def exportar_features(simbolo: str = "BTCUSDT", limite: int = 200) -> dict[str, Any]:
    return {"simbolo": simbolo.upper(), "itens": await RepositorioFeatures.listar_ultimas(simbolo.upper(), limite=max(1, limite))}


@app.get("/v1/export/predicoes")
async def exportar_predicoes(simbolo: str = "BTCUSDT", limite: int = 200) -> dict[str, Any]:
    return {"simbolo": simbolo.upper(), "itens": await RepositorioPredicoes.listar_recentes(simbolo.upper(), limite=max(1, limite))}


@app.get("/v1/export/outcomes")
async def exportar_outcomes(simbolo: str = "BTCUSDT", limite: int = 200) -> dict[str, Any]:
    return {"simbolo": simbolo.upper(), "itens": await RepositorioOutcomes.listar_recentes(simbolo.upper(), limite=max(1, limite))}


@app.get("/v1/export/auditoria")
async def exportar_auditoria(simbolo: str | None = None, tipo: str | None = None, limite: int = 200) -> dict[str, Any]:
    return {"itens": await RepositorioAuditoria.listar_recentes(simbolo=simbolo, tipo=tipo, limite=max(1, limite))}


@app.get("/v1/noticias")
async def listar_noticias(simbolo: str = "BTCUSDT", atualizar: bool = False) -> JSONResponse:
    simbolo = _simbolo_monitorado(simbolo)
    noticias = await obter_noticias_para_peso(simbolo=simbolo, forcar_atualizacao=atualizar)
    return JSONResponse(noticias)


@app.get("/v1/noticias/multi")
async def listar_noticias_multi(simbolos: str = "BTCUSDT,ETHUSDT,BNBUSDT,ETHBTC,BNBBTC,BNBETH", atualizar: bool = False) -> JSONResponse:
    lista_simbolos = []
    vistos: set[str] = set()
    for bruto in str(simbolos or "").split(","):
        simbolo = _simbolo_monitorado(bruto.strip() or "BTCUSDT")
        if simbolo in vistos:
            continue
        vistos.add(simbolo)
        lista_simbolos.append(simbolo)
    resultados_brutos = await asyncio.gather(
        *(obter_noticias_para_peso(simbolo=item, forcar_atualizacao=atualizar) for item in lista_simbolos),
        return_exceptions=True,
    )
    resultados: list[dict[str, Any]] = []
    for simbolo, resultado in zip(lista_simbolos, resultados_brutos):
        if isinstance(resultado, Exception):
            LOG.warning("falha_noticias_multi", extra={"simbolo": simbolo, "erro": str(resultado)})
            resultados.append(
                {
                    "simbolo": simbolo,
                    "meta": {
                        "erro": str(resultado),
                        "fontes_detalhadas": [],
                        "fontes_monitoradas": 0,
                        "fontes_com_retorno": 0,
                        "fontes_minimas_exigidas": 10,
                        "status_classificacao": "falha_coleta",
                        "cache_usado": False,
                    },
                    "itens": [],
                }
            )
            continue
        resultados.append(resultado)
    return JSONResponse({"simbolos": lista_simbolos, "itens": resultados})


@app.get("/v1/noticias/frame", response_class=HTMLResponse)
async def frame_noticias_fonte(simbolo: str = "BTCUSDT", fonte: str = "Reuters") -> HTMLResponse:
    simbolo = _simbolo_monitorado(simbolo)
    return HTMLResponse(await renderizar_fonte_noticias_html(simbolo=simbolo, fonte_nome=fonte))


@app.get("/v1/multiativo/oportunidades")
async def listar_oportunidades_multiativo(request: Request, persistir_mercado: bool = False) -> JSONResponse:
    sessao = await obter_sessao(request.cookies.get("oraculo_sessao"))
    ajustes_sinal = (await obter_ajustes_sinal())["aplicado"]
    monitoramento = await montar_monitoramento_multiativo(
        sessao=sessao,
        persistir_mercado=persistir_mercado,
        ajustes_sinal=ajustes_sinal,
    )
    return JSONResponse(monitoramento)


@app.get("/v1/config")
async def listar_config() -> dict[str, Any]:
    return {"itens": await RepositorioConfig.listar_todas()}


@app.get("/v1/config/{chave}")
async def obter_config(chave: str) -> dict[str, Any]:
    valor = await RepositorioConfig.obter(chave)
    if valor is None:
        raise HTTPException(status_code=404, detail=f"configuracao '{chave}' nao encontrada")
    return {"chave": chave, "valor": valor}


@app.put("/v1/config/{chave}")
async def definir_config(chave: str, entrada: ConfigEntrada) -> dict[str, Any]:
    await RepositorioConfig.definir(chave, entrada.valor)
    return {"chave": chave, "valor": await RepositorioConfig.obter(chave)}


@app.get("/v1/ajustes")
async def listar_ajustes() -> dict[str, Any]:
    return {
        "sinal": await obter_ajustes_sinal(),
        "risco": await obter_ajustes_risco(),
        "testnet": await obter_ajustes_testnet(),
        "retomada": await obter_ajustes_retomada(),
    }


@app.put("/v1/ajustes/sinal")
async def definir_ajustes_sinal(entrada: ConfigEntrada) -> dict[str, Any]:
    return await salvar_ajustes_sinal(entrada.valor)


@app.put("/v1/ajustes/risco")
async def definir_ajustes_risco(entrada: ConfigEntrada) -> dict[str, Any]:
    return await salvar_ajustes_risco(entrada.valor)


@app.put("/v1/ajustes/testnet")
async def definir_ajustes_testnet(entrada: ConfigEntrada) -> dict[str, Any]:
    return await salvar_ajustes_testnet(entrada.valor)


@app.put("/v1/ajustes/retomada")
async def definir_ajustes_retomada(entrada: ConfigEntrada) -> dict[str, Any]:
    return await salvar_ajustes_retomada(entrada.valor)


@app.get("/v1/dashboard/resumo")
async def dashboard_resumo(simbolo: str = "BTCUSDT", usuario_id: int | None = None, coletar_mercado: bool = True) -> JSONResponse:
    simbolo = simbolo.upper()
    if coletar_mercado:
        ajustes_sinal = (await obter_ajustes_sinal())["aplicado"]
        try:
            await coletar_e_persistir(simbolo=simbolo, limit=80)
            await gerar_previsao_dados_persistidos(
                simbolo=simbolo,
                coletar_mercado=False,
                limite_klines=80,
                persistir=True,
                origem="dashboard",
                ajustes_sinal=ajustes_sinal,
            )
        except Exception as exc:
            LOG.warning("falha_refresh_dashboard", extra={"simbolo": simbolo, "erro": str(exc)})

    if usuario_id is None:
        usuarios_ativos = await RepositorioUsuarios.listar(apenas_ativos=True)
        usuario_id = usuarios_ativos[0]["id"] if usuarios_ativos else None

    tarefa_loop = getattr(app.state, "tarefa_loop", None)
    dashboard = await montar_dashboard(
        simbolo=simbolo,
        usuario_id=usuario_id,
        loop_previsao_ativo=bool(tarefa_loop and not tarefa_loop.done()),
        db_path=str(obter_db_path()),
    )
    return JSONResponse(dashboard)


@app.get("/v1/painel/conta")
async def painel_conta(request: Request, simbolo: str = "BTCUSDT") -> JSONResponse:
    simbolo = _simbolo_monitorado(simbolo)
    sessao = await _sessao_autenticada(request)
    tarefa_loop = getattr(app.state, "tarefa_loop", None)
    ajustes_sinal = (await obter_ajustes_sinal())["aplicado"]
    painel = await montar_painel_conta(
        simbolo=simbolo,
        sessao=sessao,
        loop_previsao_ativo=bool(tarefa_loop and not tarefa_loop.done()),
        db_path=str(obter_db_path()),
        ajustes_sinal=ajustes_sinal,
    )
    return JSONResponse(painel)


@app.get("/v1/usuarios")
async def listar_usuarios(apenas_ativos: bool = False) -> dict[str, Any]:
    return {"itens": await RepositorioUsuarios.listar(apenas_ativos=apenas_ativos)}


@app.get("/v1/usuarios/{usuario_id}")
async def obter_usuario(usuario_id: int) -> dict[str, Any]:
    usuario = await RepositorioUsuarios.obter(usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail=f"usuario {usuario_id} nao encontrado")
    return usuario


@app.post("/v1/usuarios")
async def criar_usuario(entrada: UsuarioEntrada) -> dict[str, Any]:
    try:
        usuario_id = await RepositorioUsuarios.criar(
            nome=entrada.nome,
            api_key_secret_id=entrada.api_key_secret_id,
            api_secret_secret_id=entrada.api_secret_secret_id,
            api_key_ref=entrada.api_key_ref,
            api_secret_ref=entrada.api_secret_ref,
            testnet=entrada.testnet,
            ativo=entrada.ativo,
            risk_config=entrada.risk_config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await obter_usuario(usuario_id)


@app.get("/v1/sinais/fila")
async def listar_fila_sinais(limite: int = 100) -> dict[str, Any]:
    return {"itens": await fila_sinais_global.snapshot(limite=max(1, limite))}


@app.get("/v1/ordens")
async def listar_ordens(usuario_id: int | None = None, simbolo: str | None = None, limite: int = 50) -> dict[str, Any]:
    return {
        "itens": await RepositorioOrdens.listar_recentes(
            usuario_id=usuario_id,
            simbolo=simbolo,
            limite=max(1, limite),
        )
    }


@app.put("/v1/ordens/{ordem_id}/status")
async def atualizar_status_ordem(ordem_id: int, entrada: OrdemStatusEntrada) -> dict[str, Any]:
    try:
        ordem = await RepositorioOrdens.atualizar_status(ordem_id, entrada.status, entrada.detalhe_extra)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await RepositorioAuditoria.registrar(
        simbolo=ordem["simbolo"],
        tipo="ordem_status",
        payload={"ordem_id": ordem_id, "status": ordem["status"], "detalhe": ordem["detalhe"]},
    )
    return ordem


@app.post("/v1/usuarios/{usuario_id}/sinais/gerar")
async def gerar_sinal_usuario(usuario_id: int, entrada: SinalUsuarioEntrada) -> JSONResponse:
    resultado = await executar_fluxo_usuario_sinal(usuario_id, entrada.model_dump())
    return JSONResponse(resultado)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
