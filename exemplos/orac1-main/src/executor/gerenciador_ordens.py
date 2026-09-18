from __future__ import annotations

import asyncio
import math
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any

from binance import AsyncClient

from src.core.settings import env_bool, env_int, env_str, env_float
from src.observabilidade.logger import get_logger

LOG = get_logger("gerenciador_ordens")


class NotionalTooSmall(Exception):
    """Raised when an order's estimated notional is below the symbol MIN_NOTIONAL."""
    pass


def _is_precision_error(exc: Exception) -> bool:
    mensagem = str(exc or "").lower()
    return "too much precision" in mensagem or "-1111" in mensagem


def _is_notional_error(exc: Exception) -> bool:
    mensagem = str(exc or "").upper()
    return "FILTER FAILURE: NOTIONAL" in mensagem or "FILTER FAILURE: MIN_NOTIONAL" in mensagem


class GerenciadorOrdens:
    def __init__(self, api_key: str | None = None, api_secret: str | None = None, testnet: bool | None = None) -> None:
        self._cliente: AsyncClient | None = None
        self._timeout = env_int("BINANCE_TIMEOUT_SECONDS", 12, minimo=1)
        self._api_key = api_key or env_str("BINANCE_API_KEY")
        self._api_secret = api_secret or env_str("BINANCE_API_SECRET")
        if testnet is None:
            self._usa_testnet = env_bool("BINANCE_TESTNET", False)
        else:
            self._usa_testnet = bool(testnet)

    async def _obter_cliente(self) -> AsyncClient:
        if self._cliente is None:
            api_key = self._api_key
            api_secret = self._api_secret
            self._cliente = await AsyncClient.create(api_key, api_secret, testnet=self._usa_testnet)
        return self._cliente

    async def obter_info_simbolo(self, simbolo: str) -> dict[str, Any]:
        cliente = await self._obter_cliente()
        info = await asyncio.wait_for(cliente.get_symbol_info(symbol=simbolo.upper()), timeout=self._timeout)
        if not info:
            raise ValueError(f"simbolo_invalido:{simbolo}")
        return info

    @staticmethod
    def _extrair_filtro(info: dict[str, Any], filtro: str) -> dict[str, Any]:
        for item in info.get("filters", []):
            if item.get("filterType") == filtro:
                return item
        return {}

    @staticmethod
    def ajustar_quantidade(quantidade: float, step_size: float, min_qty: float) -> float:
        if quantidade <= 0.0:
            return 0.0
        if step_size > 0:
            quantidade = math.floor(quantidade / step_size) * step_size
        if quantidade < min_qty:
            return 0.0
        return float(quantidade)

    async def obter_filtros_simbolo(self, simbolo: str) -> dict[str, float]:
        info = await self.obter_info_simbolo(simbolo)
        lot = self._extrair_filtro(info, "LOT_SIZE")
        min_notional = self._extrair_filtro(info, "MIN_NOTIONAL")
        notional = self._extrair_filtro(info, "NOTIONAL")
        step_size = float(lot.get("stepSize", 0.0) or 0.0)
        min_qty = float(lot.get("minQty", 0.0) or 0.0)
        min_notional_val = max(
            float(min_notional.get("minNotional", 0.0) or 0.0),
            float(notional.get("minNotional", 0.0) or 0.0),
        )
        return {
            "step_size": step_size,
            "min_qty": min_qty,
            "min_notional": min_notional_val,
        }

    def simular_ordem(
        self,
        lado: str,
        quantidade: float,
        preco: float,
        taxa: float = 0.0004,
        slippage: float = 0.0005,
        preco_gatilho: float | None = None,
        executar_apos_ts: int | None = None,
        janela_decisao_minutos: int | None = None,
    ) -> dict[str, Any]:
        lado = lado.upper()
        preco_base = float(preco_gatilho if preco_gatilho is not None else preco)
        fator_slippage = 1.0 + slippage if lado == "BUY" else 1.0 - slippage
        preco_exec = preco_base * fator_slippage
        notional = quantidade * preco_exec
        custo_total = notional * taxa
        return {
            "lado": lado,
            "quantidade": quantidade,
            "preco_referencia": preco_base,
            "preco_mercado_origem": preco,
            "preco_gatilho": preco_base,
            "preco_estimado_execucao": preco_exec,
            "notional_estimado": notional,
            "custo_estimado": custo_total,
            "executar_apos_ts": int(executar_apos_ts or time.time() * 1000),
            "janela_decisao_minutos": int(janela_decisao_minutos or 0),
            "tipo_ordem_planejada": "LIMIT_AGENDADA",
        }

    async def criar_ordem_limit(self, simbolo: str, lado: str, quantidade: float, preco: float) -> dict[str, Any]:
        lado = lado.upper()
        if lado not in {"BUY", "SELL"}:
            raise ValueError("lado invalido")
        if quantidade <= 0.0 or preco <= 0.0:
            raise ValueError("quantidade e preco devem ser positivos")
        if not self._usa_testnet and not env_bool("PERMITIR_CONTA_REAL", False):
            raise RuntimeError("conta real bloqueada; habilite PERMITIR_CONTA_REAL=true para prosseguir")

        # Ensure quantity matches symbol precision (step_size) and min_qty
        filtros = await self.obter_filtros_simbolo(simbolo)
        step_size = float(filtros.get("step_size", 0.0) or 0.0)
        min_qty = float(filtros.get("min_qty", 0.0) or 0.0)
        quantidade_ajustada = self.ajustar_quantidade(quantidade, step_size, min_qty)
        if quantidade_ajustada <= 0.0:
            raise ValueError("quantidade_ajustada_invalida")
        # Format quantity with decimal places matching step_size
        decimals = max(0, -Decimal(str(step_size)).as_tuple().exponent) if step_size > 0 else 8
        q_dec = Decimal(str(quantidade_ajustada)).quantize(Decimal((0, (1,), -decimals)) if decimals > 0 else Decimal(1), rounding=ROUND_DOWN)
        quantidade_str = format(q_dec.normalize(), 'f')
        cliente = await self._obter_cliente()
        # Try creating order; if Binance complains about precision, retry
        # with fewer decimals progressively.
        ordem = None
        last_exc = None
        for d in range(decimals, -1, -1):
            try:
                qd = Decimal(str(quantidade_ajustada)).quantize(Decimal((0, (1,), -d)) if d > 0 else Decimal(1), rounding=ROUND_DOWN)
                q_str_try = format(qd.normalize(), 'f')
                ordem = await asyncio.wait_for(
                    cliente.create_order(
                        symbol=simbolo.upper(),
                        side=lado,
                        type="LIMIT",
                        timeInForce="GTC",
                        quantity=q_str_try,
                        price=str(preco),
                    ),
                    timeout=self._timeout,
                )
                break
            except Exception as e:
                last_exc = e
                if "too much precision" in str(e) or "-1111" in str(e):
                    continue
                raise
        if ordem is None:
            raise last_exc
        LOG.info("ordem_limit_criada", extra={"simbolo": simbolo.upper(), "lado": lado, "quantidade": quantidade, "preco": preco})
        return ordem

    async def criar_ordem_market(
        self,
        simbolo: str,
        lado: str,
        quantidade: float | None = None,
        quote_order_qty: float | None = None,
    ) -> dict[str, Any]:
        lado = lado.upper()
        if lado not in {"BUY", "SELL"}:
            raise ValueError("lado invalido")
        if not self._usa_testnet and not env_bool("PERMITIR_CONTA_REAL", False):
            raise RuntimeError("conta real bloqueada; habilite PERMITIR_CONTA_REAL=true para prosseguir")

        payload: dict[str, Any] = {
            "symbol": simbolo.upper(),
            "side": lado,
            "type": "MARKET",
        }
        # configurable cap: max factor by which we may increase user-requested
        # amount to meet MIN_NOTIONAL. Default 1.2 (20% increase max).
        max_increase_factor = env_float("NOTIONAL_AUTO_INCREASE_MAX_FACTOR", 1.2, minimo=1.0)

        async def _ensure_min_notional(
            simbolo_local: str,
            lado_local: str,
            quantidade_local: float | None,
            quote_order_qty_local: float | None,
        ) -> tuple[float | None, float | None]:
            """Ensure the proposed quantity or quoteOrderQty meets MIN_NOTIONAL.

            Returns adjusted (quantidade, quote_order_qty) or raises NotionalTooSmall.
            """
            try:
                filtros = await self.obter_filtros_simbolo(simbolo_local)
            except Exception:
                filtros = {"min_notional": 0.0, "step_size": 0.0, "min_qty": 0.0}
            min_notional = float(filtros.get("min_notional", 0.0) or 0.0)
            step_size = float(filtros.get("step_size", 0.0) or 0.0)
            min_qty = float(filtros.get("min_qty", 0.0) or 0.0)

            if lado_local == "BUY" and quote_order_qty_local is not None:
                q_requested = Decimal(str(quote_order_qty_local))
                if min_notional > 0:
                    min_not_d = Decimal(str(min_notional))
                    allowed_max = q_requested * Decimal(str(max_increase_factor))
                    if min_not_d > allowed_max:
                        raise NotionalTooSmall(
                            f"required_notional {min_not_d} exceeds allowed max {allowed_max}"
                        )
                    q_effective = max(q_requested, min_not_d)
                else:
                    q_effective = q_requested

                q = q_effective.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
                if min_notional > 0 and q < Decimal(str(min_notional)):
                    increment = Decimal("0.00000001")
                    while q < Decimal(str(min_notional)):
                        q += increment
                        if q > q_requested * Decimal(str(max_increase_factor)):
                            raise NotionalTooSmall(
                                "cannot reach MIN_NOTIONAL within allowed increase cap after quantization"
                            )
                return None, float(q)

            if quantidade_local is not None:
                quantidade_adj = float(quantidade_local)
                if step_size > 0:
                    quantidade_adj = math.floor(quantidade_adj / step_size) * step_size
                if quantidade_adj < min_qty:
                    quantidade_adj = 0.0

                if min_notional > 0:
                    cliente_tmp = await self._obter_cliente()
                    try:
                        ticker = await asyncio.wait_for(
                            cliente_tmp.get_symbol_ticker(symbol=simbolo_local.upper()), timeout=self._timeout
                        )
                        preco_referencia = float(ticker.get("price", 0.0) or 0.0)
                    except Exception:
                        preco_referencia = 0.0
                    notional_estimado = quantidade_adj * (preco_referencia or 0.0)
                    if notional_estimado < min_notional and preco_referencia > 0.0:
                        required_qty = float(Decimal(str(min_notional)) / Decimal(str(preco_referencia)))
                        if step_size > 0:
                            required_steps = math.ceil(required_qty / step_size)
                            required_qty_adj = required_steps * step_size
                        else:
                            required_qty_adj = required_qty
                        if required_qty_adj < min_qty:
                            required_qty_adj = min_qty
                        max_allowed_qty = float(quantidade_local) * max_increase_factor
                        if required_qty_adj > max_allowed_qty:
                            raise NotionalTooSmall(
                                f"required_qty {required_qty_adj} exceeds allowed max {max_allowed_qty}"
                            )
                        quantidade_adj = required_qty_adj

                if quantidade_adj <= 0.0:
                    raise ValueError("quantidade_ajustada_invalida")
                return float(quantidade_adj), None

            raise ValueError("quantidade ou quote_order_qty obrigatorio")

        if lado == "BUY" and quote_order_qty is not None:
            # centralize and ensure MIN_NOTIONAL is satisfied (may adjust quoteOrderQty)
            _, quote_adj = await _ensure_min_notional(simbolo, lado, None, quote_order_qty)
            q = Decimal(str(quote_adj)).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
            payload["quoteOrderQty"] = format(q.normalize(), 'f')
        elif quantidade is not None:
            # centralize and ensure MIN_NOTIONAL is satisfied (may adjust quantity)
            quantidade_adj, _ = await _ensure_min_notional(simbolo, lado, quantidade, None)
            try:
                filtros_local = await self.obter_filtros_simbolo(simbolo)
                step_size_local = float(filtros_local.get("step_size", 0.0) or 0.0)
            except Exception:
                step_size_local = 0.0
            decimals = max(0, -Decimal(str(step_size_local)).as_tuple().exponent) if step_size_local > 0 else 8
            q_dec = Decimal(str(quantidade_adj)).quantize(Decimal((0, (1,), -decimals)) if decimals > 0 else Decimal(1), rounding=ROUND_DOWN)
            payload["quantity"] = format(q_dec.normalize(), 'f')
        else:
            raise ValueError("quantidade ou quote_order_qty obrigatorio")

        cliente = await self._obter_cliente()
        # If payload contains 'quantity', ensure it matches allowed precision;
        # try progressive truncation on API precision errors.
        ordem = None
        last_exc = None
        if "quantity" in payload:
            # determine decimals from step_size if available
            try:
                filtros_local = filtros
            except NameError:
                try:
                    filtros_local = await self.obter_filtros_simbolo(simbolo)
                except Exception:
                    filtros_local = {"step_size": 0.0}
            step_size_local = float(filtros_local.get("step_size", 0.0) or 0.0)
            max_decimals = max(0, -Decimal(str(step_size_local)).as_tuple().exponent) if step_size_local > 0 else 8
            for d in range(max_decimals, -1, -1):
                try:
                    qd = Decimal(str(payload["quantity"]))
                    q_try = qd.quantize(Decimal((0, (1,), -d)) if d > 0 else Decimal(1), rounding=ROUND_DOWN)
                    payload_try = dict(payload)
                    payload_try["quantity"] = format(q_try.normalize(), 'f')
                    ordem = await asyncio.wait_for(cliente.create_order(**payload_try), timeout=self._timeout)
                    break
                except Exception as e:
                    last_exc = e
                    if _is_precision_error(e):
                        continue
                    if _is_notional_error(e):
                        raise NotionalTooSmall(str(e)) from e
                    raise
            if ordem is None:
                raise last_exc
        else:
            try:
                ordem = await asyncio.wait_for(cliente.create_order(**payload), timeout=self._timeout)
            except Exception as e:
                if _is_notional_error(e):
                    raise NotionalTooSmall(str(e)) from e
                raise
        LOG.info(
            "ordem_market_criada",
            extra={
                "simbolo": simbolo.upper(),
                "lado": lado,
                "quantidade": quantidade,
                "quote_order_qty": quote_order_qty,
            },
        )
        return ordem

    async def cancelar_ordem(self, simbolo: str, order_id: int) -> dict[str, Any]:
        cliente = await self._obter_cliente()
        resposta = await asyncio.wait_for(
            cliente.cancel_order(symbol=simbolo.upper(), orderId=order_id),
            timeout=self._timeout,
        )
        LOG.info("ordem_cancelada", extra={"simbolo": simbolo.upper(), "order_id": order_id})
        return resposta

    async def fechar(self) -> None:
        if self._cliente is not None:
            try:
                await self._cliente.close_connection()
            finally:
                self._cliente = None
