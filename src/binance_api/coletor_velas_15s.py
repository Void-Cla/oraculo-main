"""
Coletor de velas 15s (scaffold)
Este módulo fornece um esqueleto assíncrono para coletar snapshots a cada 15 segundos
para os símbolos definidos em `SYMBOLS` no ambiente. Não faz chamadas concretas
à API da Binance neste scaffold — apenas a interface para integrar depois.
"""
from __future__ import annotations

import os
import asyncio
from typing import List, Dict, Any
from src.observabilidade.logger import get_logger
from src.binance_api.cliente import ClienteBinance
from src.persistencia.repositorio_ohlcv import RepositorioOhlcv

LOG = get_logger("coletor_15s")


def simbolos_monitorados() -> List[str]:
    s = os.getenv("SYMBOLS") or os.getenv("MONITORED_PAIRS") or ""
    return [x.strip().upper() for x in s.split(",") if x.strip()]


async def coletar_snapshot_15s(simbolo: str) -> Dict[str, Any]:
    """Retorna um dicionário representando uma vela 15s.
    Substituir essa função por chamada real a `ClienteBinance`.
    """
    # Exemplo de payload minimal
    # Implementação segura: pegar preço atual e livro topo e armazenar como snapshot 15s.
    cliente = ClienteBinance()
    try:
        preco = await cliente.obter_preco_atual(simbolo)
    except Exception:
        preco = 0.0
    ts = int(asyncio.get_event_loop().time() * 1000)
    payload = {
        "simbolo": simbolo,
        "ts": ts,
        "open": preco,
        "high": preco,
        "low": preco,
        "close": preco,
        "volume": 0.0,
    }
    LOG.debug("snapshot_15s_coletado", extra={"simbolo": simbolo, "preco": preco})
    return payload


async def loop_coleta_15s(poll_interval: int = 15) -> None:
    simbolos = simbolos_monitorados()
    LOG.info("iniciando_coletor_15s", extra={"simbolos": simbolos})
    try:
        while True:
            tarefas = [coletar_snapshot_15s(s) for s in simbolos]
            resultados = await asyncio.gather(*tarefas, return_exceptions=True)
            registros: list[dict[str, Any]] = []
            for r in resultados:
                if isinstance(r, Exception) or not isinstance(r, dict):
                    continue
                registros.append(r)
            if registros:
                try:
                    await RepositorioOhlcv.inserir_varias_15s(registros)
                except Exception as exc:
                    LOG.warning("falha_persistir_15s", extra={"erro": str(exc)})
            LOG.debug("coleta_15s_batch", extra={"contagem": len(registros)})
            await asyncio.sleep(poll_interval)
    except asyncio.CancelledError:
        LOG.info("coletor_15s_cancelado")


if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(loop_coleta_15s())
    except KeyboardInterrupt:
        print("encerrado")
