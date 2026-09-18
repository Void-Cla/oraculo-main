from __future__ import annotations

"""Coletor REST de velas e persistência.

Este módulo baixa klines via `ClienteBinance`, extrai o topo do livro,
gera features e persiste OHLCV, livro e features no repositório.
"""

from typing import Any

from src.binance_api.cliente import ClienteBinance
from src.calculos.gerador_features import calcular_features_1m
from src.persistencia.repositorio_features import RepositorioFeatures
from src.persistencia.repositorio_livro_topo import RepositorioLivroTopo
from src.persistencia.repositorio_ohlcv import RepositorioOhlcv


def _extrair_livro_topo(livro: dict[str, Any] | None) -> dict[str, float]:
    livro = livro or {}
    melhor_bid = (livro.get("bids") or [[0.0, 0.0]])[0]
    melhor_ask = (livro.get("asks") or [[0.0, 0.0]])[0]
    return {
        "bid_price": float(melhor_bid[0]) if melhor_bid and melhor_bid[0] is not None else 0.0,
        "bid_qty": float(melhor_bid[1]) if melhor_bid and melhor_bid[1] is not None else 0.0,
        "ask_price": float(melhor_ask[0]) if melhor_ask and melhor_ask[0] is not None else 0.0,
        "ask_qty": float(melhor_ask[1]) if melhor_ask and melhor_ask[1] is not None else 0.0,
    }


async def coletar_e_persistir(simbolo: str = "BTCUSDT", limit: int = 60, cliente: ClienteBinance | None = None) -> dict[str, Any]:
    cliente_local = cliente or ClienteBinance()
    try:
        klines = await cliente_local.obter_klines(simbolo=simbolo, limit=limit)
        livro_bruto = await cliente_local.obter_order_book_top(simbolo=simbolo, limit=20)
        if not klines:
            return {}

        registros = [
            {
                "ts": int(item[0]),
                "simbolo": simbolo.upper(),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            }
            for item in klines
        ]
        await RepositorioOhlcv.inserir_varias(registros)

        livro_topo = _extrair_livro_topo(livro_bruto)
        ts_final = int(registros[-1]["ts"])
        await RepositorioLivroTopo.salvar(
            ts=ts_final,
            simbolo=simbolo,
            bid_price=livro_topo["bid_price"],
            bid_qty=livro_topo["bid_qty"],
            ask_price=livro_topo["ask_price"],
            ask_qty=livro_topo["ask_qty"],
        )

        features = calcular_features_1m(klines, livro_topo=livro_topo)
        await RepositorioFeatures.salvar(ts_final, simbolo, features)
        return {"ts": ts_final, "simbolo": simbolo.upper(), "features": features, "qtd_klines": len(registros)}
    finally:
        if cliente is None:
            await cliente_local.fechar()
