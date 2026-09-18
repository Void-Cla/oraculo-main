from __future__ import annotations

"""Coletor via WebSocket para velas (1m) com fallback REST.

Abre um socket de klines da Binance e persiste updates em tempo real;
se o WS falhar utiliza fallback REST (`coletar_e_persistir`).
"""

import asyncio

from binance import AsyncClient, BinanceSocketManager

from src.binance_api.coletor_velas_rest import coletar_e_persistir
from src.observabilidade.logger import get_logger
from src.persistencia.repositorio_ohlcv import RepositorioOhlcv

LOG = get_logger("coletor_velas_ws")


async def conectar_e_ouvir(simbolo: str = "BTCUSDT") -> None:
    backoff = 1
    while True:
        cliente: AsyncClient | None = None
        socket_manager: BinanceSocketManager | None = None
        try:
            cliente = await AsyncClient.create()
            socket_manager = BinanceSocketManager(cliente)
            async with socket_manager.kline_socket(symbol=simbolo.lower(), interval="1m") as stream:
                async for msg in stream:
                    kline = (msg or {}).get("k")
                    if not kline:
                        continue
                    await RepositorioOhlcv.inserir_ohlcv(
                        ts=int(kline["t"]),
                        simbolo=(msg.get("s") or simbolo).upper(),
                        open_p=float(kline["o"]),
                        high=float(kline["h"]),
                        low=float(kline["l"]),
                        close=float(kline["c"]),
                        volume=float(kline["v"]),
                    )
            backoff = 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOG.warning("falha_ws_binance", extra={"simbolo": simbolo.upper(), "erro": str(exc), "backoff": backoff})
            try:
                await coletar_e_persistir(simbolo=simbolo, limit=60)
            except Exception as fallback_exc:
                LOG.warning("falha_fallback_rest", extra={"simbolo": simbolo.upper(), "erro": str(fallback_exc)})
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
        finally:
            if cliente is not None:
                try:
                    await cliente.close_connection()
                except Exception:
                    LOG.warning("falha_fechar_ws_binance", extra={"simbolo": simbolo.upper()})
