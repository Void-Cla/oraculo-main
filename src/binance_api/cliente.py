from __future__ import annotations

"""Cliente Binance assíncrono.

Este módulo fornece uma fachada resiliente para chamadas à API da Binance
com retry, sincronização de timestamp e rotação opcional de chaves.
Use `ClienteBinance` para obter klines, livro, ordens e informações de conta.
"""

import asyncio
import time
from typing import Any

from binance import AsyncClient

from src.core.settings import env_bool, env_csv, env_int, env_str
from src.observabilidade.logger import get_logger

LOG = get_logger("cliente_binance")


def _erro_timestamp_binance(exc: Exception) -> bool:
    mensagem = str(exc)
    return "code=-1021" in mensagem or "Timestamp for this request" in mensagem


class ClienteBinance:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool | None = None,
    ) -> None:
        pares_ambiente = env_csv("BINANCE_API_KEYS")
        if api_key and api_secret:
            self._pares_chave = [f"{api_key.strip()}:{api_secret.strip()}"]
        else:
            api_key_env = env_str("BINANCE_API_KEY")
            api_secret_env = env_str("BINANCE_API_SECRET")
            if not pares_ambiente and api_key_env and api_secret_env:
                pares_ambiente = [f"{api_key_env}:{api_secret_env}"]
            self._pares_chave = pares_ambiente
        self._rotacionar = env_bool("API_ROTATE_ON_EACH_CALL", False)
        self._timeout = env_int("BINANCE_TIMEOUT_SECONDS", 12, minimo=1)
        self._max_tentativas = env_int("BINANCE_MAX_TENTATIVAS", 3, minimo=1)
        if testnet is None:
            self._usa_testnet = env_bool("BINANCE_TESTNET", False)
        else:
            self._usa_testnet = bool(testnet)
        self._indice = 0
        self._clientes: list[AsyncClient] = []

    async def _obter_cliente(self) -> AsyncClient:
        if not self._pares_chave:
            if not self._clientes:
                self._clientes.append(await AsyncClient.create(testnet=self._usa_testnet))
            return self._clientes[0]

        if self._rotacionar:
            self._indice = (self._indice + 1) % max(1, len(self._pares_chave))

        while len(self._clientes) <= self._indice:
            par = self._pares_chave[len(self._clientes)]
            if ":" in par:
                api_key, api_secret = par.split(":", 1)
            else:
                api_key, api_secret = par, env_str("BINANCE_API_SECRET")
            cliente = await AsyncClient.create(api_key, api_secret, testnet=self._usa_testnet)
            self._clientes.append(cliente)

        return self._clientes[self._indice]

    async def _sincronizar_timestamp(self) -> None:
        cliente = await self._obter_cliente()
        servidor = await cliente.get_server_time()
        ts_servidor = int(servidor.get("serverTime", 0) or 0)
        if ts_servidor <= 0:
            return
        cliente.timestamp_offset = ts_servidor - int(time.time() * 1000)
        LOG.info(
            "timestamp_binance_sincronizado",
            extra={"offset_ms": int(cliente.timestamp_offset or 0), "testnet": self._usa_testnet},
        )

    async def _executar_com_retry(self, nome_operacao: str, callback) -> Any:
        ultimo_erro: Exception | None = None
        for tentativa in range(1, self._max_tentativas + 1):
            try:
                return await asyncio.wait_for(callback(), timeout=self._timeout)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                ultimo_erro = exc
                if _erro_timestamp_binance(exc):
                    try:
                        await self._sincronizar_timestamp()
                    except Exception as sync_exc:
                        LOG.warning(
                            "falha_sincronizar_timestamp_binance",
                            extra={"operacao": nome_operacao, "erro": str(sync_exc)},
                        )
                    if tentativa < self._max_tentativas:
                        continue
                if tentativa >= self._max_tentativas:
                    break
                espera = min(2 ** (tentativa - 1), 8)
                LOG.warning(
                    "falha_operacao_binance",
                    extra={"operacao": nome_operacao, "tentativa": tentativa, "espera_segundos": espera, "erro": str(exc)},
                )
                await asyncio.sleep(espera)

        assert ultimo_erro is not None
        raise ultimo_erro

    async def obter_klines(self, simbolo: str = "BTCUSDT", intervalo: str = "1m", limit: int = 60) -> list[list[Any]]:
        async def _callback():
            cliente = await self._obter_cliente()
            return await cliente.get_klines(symbol=simbolo.upper(), interval=intervalo, limit=limit)

        return await self._executar_com_retry("obter_klines", _callback)

    async def obter_order_book_top(self, simbolo: str = "BTCUSDT", limit: int = 20) -> dict[str, Any]:
        async def _callback():
            cliente = await self._obter_cliente()
            return await cliente.get_order_book(symbol=simbolo.upper(), limit=limit)

        return await self._executar_com_retry("obter_order_book_top", _callback)

    async def obter_preco_atual(self, simbolo: str = "BTCUSDT") -> float:
        async def _callback():
            cliente = await self._obter_cliente()
            return await cliente.get_symbol_ticker(symbol=simbolo.upper())

        ticker = await self._executar_com_retry("obter_preco_atual", _callback)
        return float(ticker["price"])

    async def obter_conta_raw(self) -> dict[str, Any]:
        if not self._pares_chave:
            raise ValueError("credenciais_binance_ausentes")

        async def _callback():
            cliente = await self._obter_cliente()
            return await cliente.get_account()

        return await self._executar_com_retry("obter_conta", _callback)

    async def obter_trades_conta(self, simbolo: str = "BTCUSDT", limit: int = 200) -> list[dict[str, Any]]:
        if not self._pares_chave:
            raise ValueError("credenciais_binance_ausentes")

        async def _callback():
            cliente = await self._obter_cliente()
            return await cliente.get_my_trades(symbol=simbolo.upper(), limit=max(1, min(limit, 1000)))

        return await self._executar_com_retry("obter_trades_conta", _callback)

    async def obter_ordens_abertas(self, simbolo: str = "BTCUSDT") -> list[dict[str, Any]]:
        if not self._pares_chave:
            raise ValueError("credenciais_binance_ausentes")

        async def _callback():
            cliente = await self._obter_cliente()
            return await cliente.get_open_orders(symbol=simbolo.upper())

        return await self._executar_com_retry("obter_ordens_abertas", _callback)

    async def obter_todas_ordens(self, simbolo: str = "BTCUSDT", limit: int = 200) -> list[dict[str, Any]]:
        if not self._pares_chave:
            raise ValueError("credenciais_binance_ausentes")

        async def _callback():
            cliente = await self._obter_cliente()
            return await cliente.get_all_orders(symbol=simbolo.upper(), limit=max(1, min(limit, 1000)))

        return await self._executar_com_retry("obter_todas_ordens", _callback)

    async def obter_resumo_conta(self, simbolo_referencia: str = "BTCUSDT", preco_referencia: float | None = None) -> dict[str, Any]:
        if not self._pares_chave:
            return {"disponivel": False, "motivo": "credenciais_binance_ausentes"}
        conta = await self.obter_conta_raw()
        btc = {"livre": 0.0, "travado": 0.0}
        usdt = {"livre": 0.0, "travado": 0.0}
        ativos_relevantes: list[dict[str, Any]] = []

        for balance in conta.get("balances", []):
            livre = float(balance.get("free", 0.0) or 0.0)
            travado = float(balance.get("locked", 0.0) or 0.0)
            total = livre + travado
            if total <= 0.0:
                continue
            ativo = balance.get("asset", "")
            if ativo in {"BTC", "USDT"}:
                if ativo == "BTC":
                    btc = {"livre": livre, "travado": travado}
                else:
                    usdt = {"livre": livre, "travado": travado}
            ativos_relevantes.append({"ativo": ativo, "livre": livre, "travado": travado})

        preco_btc = preco_referencia if preco_referencia is not None else await self.obter_preco_atual(simbolo_referencia)
        saldo_total_estimado_usdt = (usdt["livre"] + usdt["travado"]) + ((btc["livre"] + btc["travado"]) * preco_btc)

        return {
            "disponivel": True,
            "modo_testnet": self._usa_testnet,
            "btc": btc,
            "usdt": usdt,
            "preco_btcusdt": preco_btc,
            "saldo_total_estimado_usdt": saldo_total_estimado_usdt,
            "ativos_relevantes": ativos_relevantes[:10],
        }

    async def fechar(self) -> None:
        for cliente in self._clientes:
            try:
                await cliente.close_connection()
            except Exception:
                LOG.warning("falha_fechar_cliente_binance")
        self._clientes = []
