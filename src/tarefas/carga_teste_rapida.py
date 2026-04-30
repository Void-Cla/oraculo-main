from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from src.binance_api.cliente import ClienteBinance
from src.core.segredos import resolver_credenciais_usuario
from src.executor.executor_usuario import ExecutorIsoladoUsuario
from src.observabilidade.logger import get_logger
from src.persistencia.repositorio_auditoria import RepositorioAuditoria
from src.persistencia.repositorio_ohlcv import RepositorioOhlcv
from src.persistencia.repositorio_ordens import RepositorioOrdens
from src.persistencia.repositorio_usuarios import RepositorioUsuarios
from src.risco.risk_engine import avaliar_sinal_para_usuario
from src.sinais.fila_sinais import fila_sinais_global
from src.sinais.signal_engine import gerar_sinal_orquestrado
from src.tarefas.retomada import operacoes_bloqueadas_por_retomada

LOG = get_logger("carga_teste_rapida")


async def executar_carga_testes() -> None:
    """Publica sinais rápidos para testar execução (destinado a Testnet)."""
    usuario_id_env = os.getenv("CARGA_TESTE_USUARIO_ID")
    if not usuario_id_env:
        LOG.error("carga_teste_sem_usuario_id")
        return

    try:
        usuario_id = int(usuario_id_env)
    except Exception:
        LOG.error("carga_teste_usuario_id_invalido", extra={"valor": usuario_id_env})
        return

    intervalo = max(1, int(os.getenv("CARGA_TESTE_INTERVAL_SECONDS", "30")))
    total = max(1, int(os.getenv("CARGA_TESTE_TOTAL", "10")))
    simbolos = [s.strip().upper() for s in os.getenv("CARGA_TESTE_SIMPLOS", "BTCUSDT,ETHUSDT,BNBUSDT,BTCUSDT,ETHUSDT,BNBUSDT,ETHBTC,BNBBTC,BNBUSDT,ETHUSDT").split(",") if s.strip()]

    usuario = await RepositorioUsuarios.obter(usuario_id)
    if usuario is None:
        LOG.error("carga_teste_usuario_nao_encontrado", extra={"usuario_id": usuario_id})
        return

    contador = 0
    LOG.info("carga_teste_iniciada", extra={"usuario_id": usuario_id, "total": total, "intervalo": intervalo})
    try:
        force_always = str(os.getenv("CARGA_TESTE_FORCE_ALWAYS_TRADE", "false")).lower() == "true"
        force_simulated = str(os.getenv("FORCE_SIMULATED_TESTNET", "false")).lower() == "true"
        while contador < total:
            simbolo = simbolos[contador % len(simbolos)]
            # Gerar sinal orquestrado simples
            try:
                klines = await RepositorioOhlcv.obter_ultimas(simbolo, limite=60)
                if not klines:
                    LOG.warning("carga_teste_sem_klines", extra={"simbolo": simbolo})
                    await asyncio.sleep(intervalo)
                    contador += 1
                    continue
                credenciais = resolver_credenciais_usuario(usuario)
                api_key = credenciais.get("api_key")
                api_secret = credenciais.get("api_secret")
                cliente = ClienteBinance(api_key=api_key, api_secret=api_secret, testnet=bool(usuario.get("testnet", False)))
                try:
                    resumo = await cliente.obter_resumo_conta(simbolo_referencia=simbolo)
                finally:
                    await cliente.fechar()

                saldo_fornecido = {
                    "saldo_total": float(resumo.get("saldo_total_estimado_usdt", 0.0) or 0.0),
                    "saldo_livre": float(resumo.get("saldo_total_estimado_usdt", 0.0) or 0.0),
                }

                # If force mode is enabled and the target user is a Testnet user,
                # create a deterministic BUY/SELL signal. Do NOT force trades for
                # real accounts.
                if force_always and bool(usuario.get("testnet", False)):
                    lado = "BUY" if (contador % 2) == 0 else "SELL"
                    close_price = float(klines[-1][4] if isinstance(klines[-1], (list, tuple)) and len(klines[-1]) > 4 else klines[-1].get("close", 0.0))
                    sinal = {
                        "simbolo": simbolo,
                        "acao": lado,
                        "features": {"close": close_price},
                        "motivo": "forcado_carga_teste",
                    }
                else:
                    # For real accounts or when force_always is not set, use normal signal generation
                    sinal = gerar_sinal_orquestrado(
                        simbolo=simbolo,
                        klines=klines,
                        livro_topo=None,
                        noticias=[],
                        saldo=saldo_fornecido,
                        force_allow_for_testnet=(bool(usuario.get("testnet", False)) and os.getenv("FORCE_ALLOW_RISKY_TRADES", "false").lower() == "true"),
                    )
            except Exception as exc:
                LOG.warning("falha_gerar_sinal", extra={"erro": str(exc), "simbolo": simbolo})
                await asyncio.sleep(intervalo)
                contador += 1
                continue

            if await operacoes_bloqueadas_por_retomada():
                aprovacao = {
                    "aprovado": False,
                    "motivos": ["retomada_operacoes_bloqueadas"],
                    "confirmacao_multi_timeframe": {},
                    "probabilidade_trade": {},
                    "janela_decisao": {},
                }
            # When forcing trades, only bypass the usual risk engine for Testnet users
            elif force_always and bool(usuario.get("testnet", False)):
                saldo_total = float(saldo_fornecido.get("saldo_total", 0.0) or 0.0)
                saldo_livre = float(saldo_fornecido.get("saldo_livre", saldo_total) or 0.0)
                stop_loss_pct = float(os.getenv("CARGA_TESTE_DEFAULT_SL_PCT", "0.01"))
                take_profit_pct = float(os.getenv("CARGA_TESTE_DEFAULT_TP_PCT", "0.01"))
                # determine a conservative notional: at least 1 USDT, at most saldo_livre
                notional_sugerido = min(max(1.0, saldo_total * 0.01), saldo_livre if saldo_livre > 0 else 1.0)
                fracao_capital = (notional_sugerido / saldo_total) if saldo_total > 0 else 0.0
                lucro_liq_pct = float(os.getenv("CARGA_TESTE_DEFAULT_LUCRO_PCT", "0.01"))
                aprovacao = {
                    "usuario_id": usuario["id"],
                    "usuario_nome": usuario["nome"],
                    "simbolo": simbolo,
                    "acao": sinal.get("acao"),
                    "aprovado": True,
                    "motivos": ["forcado_carga_teste"],
                    "fracao_capital": fracao_capital,
                    "notional_sugerido": float(notional_sugerido),
                    "stop_loss_pct": stop_loss_pct,
                    "take_profit_pct": take_profit_pct,
                    "lucro_liquido_esperado_pct": lucro_liq_pct,
                    "lucro_liquido_esperado_usdt": max(0.0, notional_sugerido * lucro_liq_pct),
                    "confirmacao_multi_timeframe": {},
                    "probabilidade_trade": {},
                    "janela_decisao": {},
                    "paper_trading": True if (force_simulated or usuario.get("testnet")) else False,
                    "risk_config_aplicado": usuario.get("risk_config", {}),
                }
            else:
                aprovacao = avaliar_sinal_para_usuario(usuario=usuario, sinal=sinal, saldo=saldo_fornecido, estado_execucao={})
            if aprovacao.get("aprovado"):
                executor = ExecutorIsoladoUsuario(usuario)
                plano = await executor.preparar_execucao(aprovacao, preco_referencia=float(sinal["features"].get("close", 0.0) or 0.0))
                ordem_id = await RepositorioOrdens.criar(
                    usuario_id=usuario_id,
                    simbolo=simbolo,
                    lado=aprovacao["acao"],
                    status="SIMULADA" if aprovacao["paper_trading"] else "PENDENTE",
                    modo=str(plano["modo"]),
                    preco_referencia=float(plano["simulacao_ordem"]["preco_referencia"]),
                    quantidade=float(plano["simulacao_ordem"]["quantidade"]),
                    notional=float(plano["simulacao_ordem"]["notional_estimado"]),
                    stop_loss_pct=float(aprovacao["stop_loss_pct"]),
                    take_profit_pct=float(aprovacao["take_profit_pct"]),
                    detalhe={
                        "usuario_nome": usuario["nome"],
                        "simulacao_ordem": plano["simulacao_ordem"],
                        "motivos_risco": aprovacao["motivos"],
                    },
                )
                await RepositorioAuditoria.registrar(simbolo=simbolo, tipo="carga_teste_ordem_criada", payload={"ordem_id": ordem_id, "usuario_id": usuario_id})
                await fila_sinais_global.publicar({
                        "usuario_id": usuario_id,
                        "usuario_nome": usuario["nome"],
                        "simbolo": simbolo,
                        "sinal": sinal,
                        "aprovacao_risco": aprovacao,
                        "plano_execucao": plano,
                        "ordem_id": ordem_id,
                    })
                LOG.info("carga_teste_ordem_publicada", extra={"ordem_id": ordem_id, "simbolo": simbolo})
            else:
                # criar registro de ordem rejeitada para visibilidade
                ordem_id = await RepositorioOrdens.criar(
                    usuario_id=usuario_id,
                    simbolo=simbolo,
                    lado=sinal["acao"],
                    status="REJEITADA",
                    modo="paper" if usuario.get("testnet") else "real",
                    preco_referencia=float(sinal["features"].get("close", 0.0) or 0.0),
                    quantidade=0.0,
                    notional=0.0,
                    stop_loss_pct=0.0,
                    take_profit_pct=0.0,
                    detalhe={"motivos_risco": aprovacao.get("motivos", [])},
                )
                await RepositorioAuditoria.registrar(simbolo=simbolo, tipo="carga_teste_ordem_rejeitada", payload={"ordem_id": ordem_id, "motivos": aprovacao.get("motivos", [])})

            contador += 1
            await asyncio.sleep(intervalo)
    except asyncio.CancelledError:
        LOG.info("carga_teste_cancelada")
        raise
    except Exception as exc:
        LOG.error("carga_teste_falha_geral", extra={"erro": str(exc)})
