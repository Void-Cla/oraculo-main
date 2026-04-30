from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from src.binance_api.coletor_velas_rest import coletar_e_persistir
from src.calculos.gerador_features import calcular_features_1m
from src.modelagem.preditor import preditor_end_to_end
from src.multiativo.config import pares_monitorados
from src.observabilidade.logger import get_logger
from src.persistencia.repositorio_auditoria import RepositorioAuditoria
from src.persistencia.repositorio_features import RepositorioFeatures
from src.persistencia.repositorio_livro_topo import RepositorioLivroTopo
from src.persistencia.repositorio_ohlcv import RepositorioOhlcv
from src.persistencia.repositorio_outcomes import RepositorioOutcomes
from src.persistencia.repositorio_predicoes import RepositorioPredicoes
from src.servicos.noticias import obter_noticias_para_peso

LOG = get_logger("tarefas_previsao")

_SYMBOLS = list(pares_monitorados())
_INTERVALO = int(os.getenv("COLETOR_INTERVAL_SECONDS", "15"))
_ATRASO_OUTCOME = int(os.getenv("ATRASO_OUTCOME_SEGUNDOS", "60"))


def _klines_brutos_de_registros(registros: list[dict[str, Any]]) -> list[list[Any]]:
    return [[item["ts"], item["open"], item["high"], item["low"], item["close"], item["volume"]] for item in registros]


def _payload_ohlcv_de_klines(simbolo: str, klines: list[Any]) -> list[dict[str, Any]]:
    saida = []
    for item in klines:
        if isinstance(item, dict):
            saida.append(
                {
                    "ts": int(item["ts"]),
                    "simbolo": simbolo.upper(),
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item["volume"]),
                }
            )
        else:
            saida.append(
                {
                    "ts": int(item[0]),
                    "simbolo": simbolo.upper(),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                }
            )
    return saida


async def _persistir_base_mercado(simbolo: str, klines: list[Any], livro_topo: dict[str, Any] | None, features: dict[str, Any]) -> None:
    await RepositorioOhlcv.inserir_varias(_payload_ohlcv_de_klines(simbolo, klines))
    ts_referencia = int(features["ts"])
    await RepositorioFeatures.salvar(ts_referencia, simbolo, features)
    if livro_topo:
        await RepositorioLivroTopo.salvar(
            ts=ts_referencia,
            simbolo=simbolo,
            bid_price=livro_topo.get("bid_price"),
            bid_qty=livro_topo.get("bid_qty"),
            ask_price=livro_topo.get("ask_price"),
            ask_qty=livro_topo.get("ask_qty"),
        )


async def _auditar_previsao(ts_pred: int, simbolo: str, resultado: dict[str, Any], origem: str) -> None:
    await RepositorioAuditoria.registrar(
        simbolo=simbolo,
        tipo="previsao_hibrida",
        created_ts=ts_pred,
        payload={
            "origem": origem,
            "predicao": {
                "y_hat": resultado["y_hat"],
                "y_cal": resultado["y_cal"],
                "p_conf": resultado["p_conf"],
                "ic68_low": resultado["ic68_low"],
                "ic68_high": resultado["ic68_high"],
            },
            "decisao": resultado["decisao"],
        },
    )


async def verificar_outcome_apos_atraso(ts_previsao: int, simbolo: str) -> None:
    await asyncio.sleep(_ATRASO_OUTCOME)
    pred = await RepositorioPredicoes.obter(ts_previsao, simbolo)
    ultimas = await RepositorioOhlcv.obter_ultimas(simbolo, limite=1)
    if pred is None or not ultimas:
        return
    y_true = float(ultimas[-1]["close"])
    y_hat = float(pred["y_cal"] if pred["y_cal"] is not None else pred["y_hat"])
    await RepositorioOutcomes.salvar(
        ts_previsao=ts_previsao,
        ts_target=int(ultimas[-1]["ts"]),
        simbolo=simbolo,
        y_true=y_true,
        y_hat=y_hat,
    )


async def gerar_previsao_por_klines(
    simbolo: str,
    klines: list[Any],
    livro_topo: dict[str, Any] | None = None,
    noticias: list[Any] | None = None,
    saldo: dict[str, Any] | None = None,
    ajustes_sinal: dict[str, Any] | None = None,
    persistir: bool = True,
    origem: str = "manual",
) -> dict[str, Any]:
    noticias_normalizadas = noticias
    if not noticias_normalizadas:
        noticias_cache = await obter_noticias_para_peso(simbolo)
        noticias_normalizadas = noticias_cache.get("itens", [])
    features = calcular_features_1m(klines, livro_topo=livro_topo)
    resultado = preditor_end_to_end(
        simbolo=simbolo,
        features=features,
        noticias=noticias_normalizadas,
        saldo=saldo,
        ajustes_sinal=ajustes_sinal,
    )

    if persistir:
        await _persistir_base_mercado(simbolo, klines, livro_topo, features)
        ts_pred = int(time.time() * 1000)
        await RepositorioPredicoes.salvar(
            created_ts=ts_pred,
            simbolo=simbolo,
            y_hat=resultado["y_hat"],
            y_cal=resultado["y_cal"],
            ic68_low=resultado["ic68_low"],
            ic68_high=resultado["ic68_high"],
            p_conf=resultado["p_conf"],
            meta={
                "origem": origem,
                "preco_atual": resultado["preco_atual"],
                "direcao": resultado["direcao"],
                "decisao": resultado["decisao"],
                "noticias_usadas": len(noticias_normalizadas or []),
            },
        )
        await _auditar_previsao(ts_pred, simbolo, resultado, origem)
        asyncio.create_task(verificar_outcome_apos_atraso(ts_pred, simbolo))
        resultado["created_ts"] = ts_pred

    return resultado


async def gerar_previsao_dados_persistidos(
    simbolo: str,
    noticias: list[Any] | None = None,
    saldo: dict[str, Any] | None = None,
    coletar_mercado: bool = False,
    limite_klines: int = 60,
    ajustes_sinal: dict[str, Any] | None = None,
    persistir: bool = True,
    origem: str = "persistido",
) -> dict[str, Any]:
    if coletar_mercado:
        await coletar_e_persistir(simbolo=simbolo, limit=max(20, limite_klines))

    registros = await RepositorioOhlcv.obter_ultimas(simbolo, limite=limite_klines)
    if not registros:
        raise ValueError(f"nao ha dados persistidos para {simbolo.upper()}")

    livro_topo = await RepositorioLivroTopo.obter_ultimo(simbolo)
    return await gerar_previsao_por_klines(
        simbolo=simbolo,
        klines=_klines_brutos_de_registros(registros),
        livro_topo=livro_topo,
        noticias=noticias,
        saldo=saldo,
        ajustes_sinal=ajustes_sinal,
        persistir=persistir,
        origem=origem,
    )


async def loop_previsao() -> None:
    while True:
        for simbolo in _SYMBOLS:
            try:
                await gerar_previsao_dados_persistidos(
                    simbolo=simbolo,
                    coletar_mercado=True,
                    persistir=True,
                    origem="loop",
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOG.warning("falha_loop_previsao", extra={"simbolo": simbolo, "erro": str(exc)})
        await asyncio.sleep(_INTERVALO)
