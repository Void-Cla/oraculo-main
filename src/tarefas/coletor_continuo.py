"""Coletor CONTÍNUO de dados de mercado — pré-requisito honesto para a pesquisa de edge.

Roda independente do trading: baixa OHLCV + livro + features via REST público (sem
credenciais) e persiste com upsert idempotente. Acumular dado real contínuo é justamente
o que falta para validar edge com walk-forward (hoje o dado é fragmentado: só veio quando
o bot estava ligado). Ligado por env `ATIVAR_COLETA_CONTINUA`; símbolos/intervalo configuráveis.
"""
from __future__ import annotations

import asyncio
from typing import Any

from src.binance_api.cliente import ClienteBinance
from src.binance_api.coletor_velas_rest import coletar_e_persistir
from src.core.settings import env_bool, env_int, env_str
from src.multiativo.config import pares_primarios_usdt
from src.observabilidade.logger import get_logger

LOG = get_logger("coletor_continuo")

_BACKOFF_MAX_SEGUNDOS = 300  # teto de espera após falhas seguidas (resiliência em run longo)


def _simbolos_coleta() -> list[str]:
    """Símbolos a coletar: env `COLETA_SIMBOLOS` (csv) ou os pares USDT primários por padrão."""
    bruto = env_str("COLETA_SIMBOLOS", "")
    if bruto.strip():
        return [s.strip().upper() for s in bruto.split(",") if s.strip()]
    return list(pares_primarios_usdt())


async def coletar_uma_rodada(
    simbolos: list[str], limit: int, cliente: ClienteBinance
) -> dict[str, Any]:
    """Coleta uma passada por todos os símbolos. Falha de um símbolo não derruba a rodada."""
    ok = 0
    falhas: list[str] = []
    for simbolo in simbolos:
        try:
            resultado = await coletar_e_persistir(simbolo=simbolo, limit=limit, cliente=cliente)
            if resultado:
                ok += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # falha de um símbolo é isolada e logada (run longo)
            falhas.append(simbolo)
            LOG.warning("falha_coleta_simbolo", extra={"simbolo": simbolo, "erro": str(exc)})
    return {"coletados": ok, "total": len(simbolos), "falhas": falhas}


async def loop_coleta_continua() -> None:
    """Loop infinito de coleta. No-op se `ATIVAR_COLETA_CONTINUA` != true."""
    if not env_bool("ATIVAR_COLETA_CONTINUA", False):
        return
    simbolos = _simbolos_coleta()
    intervalo = env_int("COLETA_INTERVALO_SEGUNDOS", 60, minimo=10)
    limit = env_int("COLETA_LIMIT_KLINES", 60, minimo=2)
    cliente = ClienteBinance(testnet=False)  # dados públicos reais (sem credenciais)
    LOG.info("coleta_continua_iniciada", extra={"simbolos": simbolos, "intervalo_s": intervalo})
    erros_seguidos = 0
    try:
        while True:
            try:
                resumo = await coletar_uma_rodada(simbolos, limit, cliente)
                erros_seguidos = 0
                LOG.info("coleta_rodada_ok", extra=resumo)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                erros_seguidos += 1
                LOG.warning("falha_rodada_coleta", extra={"erro": str(exc), "erros_seguidos": erros_seguidos})
            espera = min(_BACKOFF_MAX_SEGUNDOS, intervalo * max(1, erros_seguidos))
            await asyncio.sleep(espera)
    except asyncio.CancelledError:
        raise
    finally:
        await cliente.fechar()
