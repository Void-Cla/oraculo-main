from __future__ import annotations

import asyncio
import time
from typing import Any

from src.binance_api.cliente import ClienteBinance
from src.calculos.gerador_features import calcular_features_1m
from src.observabilidade.logger import get_logger
from src.persistencia.repositorio_features import RepositorioFeatures
from src.persistencia.repositorio_livro_topo import RepositorioLivroTopo
from src.persistencia.repositorio_ohlcv import RepositorioOhlcv
from src.servicos.noticias import obter_noticias_para_peso
from src.sinais.signal_engine import gerar_sinal_orquestrado

from .bnb_manager import avaliar_saldo_bnb
from .capital_manager import calcular_plano_capital
from .config import ativo_base, ativos_monitorados, pares_monitorados, pares_primarios_usdt, par_usdt_do_ativo
from .fee_optimizer import montar_perfil_taxas
from .opportunity_scanner import ranquear_oportunidades
from .triangular_arbitrage import avaliar_rotas_triangular

LOG = get_logger("multiativo_orquestrador")


def _saldo_ativo(conta: dict[str, Any], ativo: str) -> dict[str, float]:
    for balance in conta.get("balances", []):
        if str(balance.get("asset", "")).upper() != ativo.upper():
            continue
        livre = float(balance.get("free", 0.0) or 0.0)
        travado = float(balance.get("locked", 0.0) or 0.0)
        return {"livre": livre, "travado": travado, "total": livre + travado}
    return {"livre": 0.0, "travado": 0.0, "total": 0.0}


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


def _payload_ohlcv(simbolo: str, klines: list[list[Any]]) -> list[dict[str, Any]]:
    return [
        {
            "ts": int(item[0]),
            "simbolo": simbolo,
            "open": float(item[1]),
            "high": float(item[2]),
            "low": float(item[3]),
            "close": float(item[4]),
            "volume": float(item[5]),
        }
        for item in klines
    ]


async def _persistir_snapshot(simbolo: str, klines: list[list[Any]], livro_topo: dict[str, float], features: dict[str, Any]) -> None:
    await RepositorioOhlcv.inserir_varias(_payload_ohlcv(simbolo, klines))
    ts = int(features.get("ts", 0) or 0)
    await RepositorioFeatures.salvar(ts, simbolo, features)
    await RepositorioLivroTopo.salvar(
        ts=ts,
        simbolo=simbolo,
        bid_price=livro_topo.get("bid_price"),
        bid_qty=livro_topo.get("bid_qty"),
        ask_price=livro_topo.get("ask_price"),
        ask_qty=livro_topo.get("ask_qty"),
    )


async def _snapshot_par(cliente: ClienteBinance, simbolo: str, persistir: bool) -> dict[str, Any]:
    klines_brutas, livro_bruto = await asyncio.gather(
        cliente.obter_klines(simbolo=simbolo, limit=60),
        cliente.obter_order_book_top(simbolo=simbolo, limit=20),
    )
    livro_topo = _extrair_livro_topo(livro_bruto)
    features = calcular_features_1m(klines_brutas, livro_topo=livro_topo)
    snapshot = {
        "simbolo": simbolo,
        "klines": klines_brutas,
        "livro_topo": livro_topo,
        "features": features,
        "preco_atual": float(features.get("close", 0.0) or 0.0),
        "volume_atual": float((klines_brutas[-1][5]) if klines_brutas else 0.0),
    }
    if persistir and klines_brutas:
        await _persistir_snapshot(simbolo, klines_brutas, livro_topo, features)
    return snapshot


def _resumo_noticias(noticias_por_simbolo: dict[str, dict[str, Any]]) -> dict[str, Any]:
    itens = []
    for simbolo, payload in noticias_por_simbolo.items():
        meta = payload.get("meta") or {}
        itens.append(
            {
                "simbolo": simbolo,
                "sentimento_geral": round(float(meta.get("sentimento_geral", 0.0) or 0.0), 4),
                "confianca": round(float(meta.get("confianca", 0.0) or 0.0), 4),
                "resumo": meta.get("resumo"),
                "fontes_com_retorno": int(meta.get("fontes_com_retorno", 0) or 0),
                "buscas_hoje": int(meta.get("buscas_hoje", 0) or 0),
            }
        )
    return {"itens": itens}


def _saldos_monitorados(conta: dict[str, Any], precos_usdt: dict[str, float]) -> dict[str, dict[str, float]]:
    saldo_total = 0.0
    saida: dict[str, dict[str, float]] = {}
    for ativo in ativos_monitorados():
        saldo = _saldo_ativo(conta, ativo)
        preco_usdt = 1.0 if ativo == "USDT" else max(0.0, float(precos_usdt.get(ativo, 0.0) or 0.0))
        valor_usdt = saldo["total"] * preco_usdt if ativo != "USDT" else saldo["total"]
        saldo_total += valor_usdt
        saida[ativo] = {
            **saldo,
            "preco_usdt": round(preco_usdt, 8),
            "valor_estimado_usdt": round(valor_usdt, 8),
        }

    for saldo in saida.values():
        peso = (saldo["valor_estimado_usdt"] / saldo_total) if saldo_total > 0 else 0.0
        saldo["peso_carteira_pct"] = round(peso * 100.0, 4)
    return saida


async def montar_monitoramento_multiativo(
    *,
    sessao: dict[str, Any] | None = None,
    cliente: ClienteBinance | None = None,
    conta_raw: dict[str, Any] | None = None,
    persistir_mercado: bool = False,
    ajustes_sinal: dict[str, Any] | None = None,
    capital_planejado_usdt: float | None = None,
    lucro_liquido_minimo_usdt: float | None = None,
) -> dict[str, Any]:
    cliente_local = cliente
    if cliente_local is None:
        if sessao is not None:
            cliente_local = ClienteBinance(
                api_key=str(sessao["api_key"]),
                api_secret=str(sessao["api_secret"]),
                testnet=bool(sessao.get("modo_testnet")),
            )
        else:
            cliente_local = ClienteBinance()

    try:
        pares = pares_monitorados()
        noticias_base = await asyncio.gather(
            *(obter_noticias_para_peso(simbolo=simbolo) for simbolo in pares_primarios_usdt()),
            return_exceptions=True,
        )
        noticias_por_simbolo: dict[str, dict[str, Any]] = {}
        for simbolo, payload in zip(pares_primarios_usdt(), noticias_base):
            if isinstance(payload, Exception):
                LOG.warning("falha_noticias_multiativo", extra={"simbolo": simbolo, "erro": str(payload)})
                noticias_por_simbolo[simbolo] = {"simbolo": simbolo, "meta": {}, "itens": []}
            else:
                noticias_por_simbolo[simbolo] = payload

        snapshots_lista = await asyncio.gather(
            *(_snapshot_par(cliente_local, simbolo, persistir_mercado) for simbolo in pares),
            return_exceptions=True,
        )
        snapshots: dict[str, dict[str, Any]] = {}
        for simbolo, snapshot in zip(pares, snapshots_lista):
            if isinstance(snapshot, Exception):
                LOG.warning("falha_snapshot_multiativo", extra={"simbolo": simbolo, "erro": str(snapshot)})
                continue
            snapshots[simbolo] = snapshot

        precos_usdt = {"USDT": 1.0}
        for simbolo in pares_primarios_usdt():
            snapshot = snapshots.get(simbolo)
            if snapshot:
                precos_usdt[ativo_base(simbolo)] = float(snapshot.get("preco_atual", 0.0) or 0.0)

        conta = conta_raw or {}
        saldos = _saldos_monitorados(conta, precos_usdt) if conta else {}
        saldo_total_estimado = sum(float(item.get("valor_estimado_usdt", 0.0) or 0.0) for item in saldos.values())
        perfil_taxas = montar_perfil_taxas(conta=conta, saldos=saldos)
        capital_info = calcular_plano_capital(
            saldos=saldos,
            saldo_total_estimado_usdt=saldo_total_estimado,
            capital_planejado_usdt=capital_planejado_usdt,
            lucro_liquido_minimo_usdt=lucro_liquido_minimo_usdt,
        )
        ajustes_sinal_exec = dict(ajustes_sinal or {})
        taxa_taker_efetiva = float(perfil_taxas.get("taker_decimal_efetiva", 0.0) or 0.0)
        if taxa_taker_efetiva > 0.0:
            ajustes_sinal_exec["signal_trade_fee_pct"] = taxa_taker_efetiva

        sinais: dict[str, dict[str, Any]] = {}
        saldo_contexto = {
            "saldo_total": capital_info["saldo_total_estimado_usdt"],
            "saldo_livre": capital_info["saldo_usdt_livre"],
        }
        for simbolo, snapshot in snapshots.items():
            simbolo_noticias = par_usdt_do_ativo(ativo_base(simbolo))
            noticias = list((noticias_por_simbolo.get(simbolo_noticias) or {}).get("itens", []))
            sinais[simbolo] = gerar_sinal_orquestrado(
                simbolo=simbolo,
                klines=snapshot.get("klines") or [],
                livro_topo=snapshot.get("livro_topo"),
                noticias=noticias,
                saldo=saldo_contexto,
                ajustes_sinal=ajustes_sinal_exec,
            )

        scanner = ranquear_oportunidades(
            snapshots=snapshots,
            sinais=sinais,
            saldos=saldos if saldos else None,
            precos_usdt=precos_usdt,
            capital_info=capital_info,
            perfil_taxas=perfil_taxas,
            min_prob=float(ajustes_sinal_exec.get("signal_min_prob", 0.55) or 0.55),
            min_score=float(ajustes_sinal_exec.get("limiar_score_operacao", 0.35) or 0.35),
            slippage_pct=float(ajustes_sinal_exec.get("signal_slippage_pct", 0.0005) or 0.0005),
            max_spread_rel=float(ajustes_sinal_exec.get("max_spread_rel", 0.003) or 0.003),
        )
        notional_arbitragem = float(capital_info.get("trade_referencia_usdt", 0.0) or 0.0)
        if saldos:
            notional_arbitragem = min(
                notional_arbitragem,
                max(0.0, float(((saldos.get("USDT") or {}).get("livre")) or 0.0)),
            )
        arbitragem = avaliar_rotas_triangular(
            snapshots,
            notional_inicial_usdt=notional_arbitragem,
            taxa_por_perna=float(perfil_taxas.get("taker_decimal_efetiva", 0.001) or 0.001),
            slippage_pct=float(ajustes_sinal_exec.get("signal_slippage_pct", 0.0005) or 0.0005),
        )
        bnb_manager = avaliar_saldo_bnb(
            saldos=saldos,
            preco_bnb_usdt=float(precos_usdt.get("BNB", 0.0) or 0.0),
        )

        return {
            "ts_atualizacao": int(time.time() * 1000),
            "ativos_monitorados": list(ativos_monitorados()),
            "pares_monitorados": list(pares),
            "precos_usdt": {chave: round(float(valor or 0.0), 8) for chave, valor in precos_usdt.items()},
            "saldos_monitorados": saldos,
            "perfil_taxas": perfil_taxas,
            "capital_manager": capital_info,
            "bnb_manager": bnb_manager,
            "sinais": sinais,
            "scanner": scanner,
            "arbitragem_triangular": arbitragem,
            "noticias_contexto": _resumo_noticias(noticias_por_simbolo),
            "sem_vantagem_estatistica": bool(scanner["sem_vantagem_real"] and arbitragem["sem_vantagem_real"]),
        }
    finally:
        if cliente is None and cliente_local is not None:
            await cliente_local.fechar()
