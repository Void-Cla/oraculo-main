from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd


def _normalizar_klines(klines: list[Any]) -> pd.DataFrame:
    registros: list[dict[str, float]] = []
    for item in klines:
        if isinstance(item, dict):
            registros.append(
                {
                    "ts": float(item["ts"]),
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item["volume"]),
                }
            )
            continue

        if len(item) < 6:
            raise ValueError("kline invalido: sao esperados pelo menos 6 campos")
        registros.append(
            {
                "ts": float(item[0]),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            }
        )

    if not registros:
        raise ValueError("nenhum kline valido recebido")

    return pd.DataFrame(registros).sort_values("ts").reset_index(drop=True)


def _retorno(serie: pd.Series, passos: int) -> float:
    # Dados insuficientes p/ este horizonte — NÃO degradar silenciosamente p/ uma janela
    # menor (ex.: r_15m calculado com 5 barras). Isso contaminaria o dataset: o modelo
    # aprenderia "r_15m" misturando horizontes de fato distintos sob o mesmo rótulo.
    # 0.0 é mais honesto que um valor aproximado de janela errada.
    if len(serie) <= passos:
        return 0.0
    atual = float(serie.iloc[-1])
    anterior = float(serie.iloc[-1 - passos])
    return ((atual / anterior) - 1.0) if anterior else 0.0


def _media_movel(serie: pd.Series, janela: int) -> float:
    return float(serie.rolling(janela, min_periods=1).mean().iloc[-1])


def _ema(serie: pd.Series, janela: int) -> float:
    return float(serie.ewm(span=janela, adjust=False).mean().iloc[-1])


def _volatilidade(serie: pd.Series, janela: int) -> float:
    retornos = serie.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return float(retornos.rolling(janela, min_periods=1).std(ddof=0).iloc[-1])


def _ts_para_datetime(ts: float) -> datetime:
    ts_segundos = ts / 1000.0 if ts > 10_000_000_000 else ts
    return datetime.fromtimestamp(ts_segundos, tz=timezone.utc)


def _sanear_numero(valor: Any) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(numero) or math.isinf(numero):
        return 0.0
    return numero


def calcular_features_1m(
    klines: list[Any],
    livro_topo: dict[str, Any] | None = None,
    sent_score: float = 0.0,
) -> dict[str, Any]:
    if not klines:
        return {}

    df = _normalizar_klines(klines)
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    ts = int(df["ts"].iloc[-1])
    ultimo_close = float(close.iloc[-1])
    # shift(1) exclui a barra CORRENTE da média — incluí-la fazia o próprio valor atual
    # compor ~10% do denominador, puxando volume_ratio p/ sempre perto de 1.0 e comprimindo
    # a dispersão útil da feature. Com shift(1), a 1ª barra vira NaN — pd.isna() cobre o
    # caso de borda (poucos klines) já que `nan or 1.0` não funciona como fallback em Python.
    media_sem_barra_atual = float(volume.shift(1).rolling(10, min_periods=1).mean().iloc[-1])
    volume_medio = 1.0 if pd.isna(media_sem_barra_atual) else (media_sem_barra_atual or 1.0)

    bid_price = _sanear_numero((livro_topo or {}).get("bid_price"))
    ask_price = _sanear_numero((livro_topo or {}).get("ask_price"))
    bid_qty = _sanear_numero((livro_topo or {}).get("bid_qty"))
    ask_qty = _sanear_numero((livro_topo or {}).get("ask_qty"))

    spread_rel = 0.0
    book_imb = 0.0
    microprice = ultimo_close
    pressao_rel = 0.0
    # pressao_compra/venda normalizadas pelo total do book (não quantidade bruta) — a
    # quantidade bruta depende da granularidade de agregação (depth) e do lot size de cada
    # símbolo, ficando inconsistente entre símbolos. book_imb já cobre parcialmente o
    # conceito; aqui mantemos as duas pernas separadas, mas em fração do book (0..1).
    pressao_compra_norm = 0.0
    pressao_venda_norm = 0.0
    if bid_price and ask_price:
        mid = (bid_price + ask_price) / 2.0
        spread_rel = ((ask_price - bid_price) / mid) if mid else 0.0
        total_book = bid_qty + ask_qty
        book_imb = ((bid_qty - ask_qty) / total_book) if total_book else 0.0
        microprice = (
            ((bid_price * ask_qty) + (ask_price * bid_qty)) / total_book
            if total_book
            else ultimo_close
        )
        pressao_rel = book_imb
        pressao_compra_norm = (bid_qty / total_book) if total_book else 0.0
        pressao_venda_norm = (ask_qty / total_book) if total_book else 0.0

    ret_log = np.log(close.replace(0.0, np.nan)).diff().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    diff_close_micro_rel = ((microprice - ultimo_close) / ultimo_close) if ultimo_close else 0.0
    amplitude_rel = ((float(high.iloc[-1]) - float(low.iloc[-1])) / ultimo_close) if ultimo_close else 0.0
    dt = _ts_para_datetime(ts)

    hora_decimal = dt.hour + (dt.minute / 60.0)
    hora_rad = 2.0 * math.pi * (hora_decimal / 24.0)
    dia_rad = 2.0 * math.pi * (dt.weekday() / 7.0)

    features = {
        "ts": ts,
        "close": ultimo_close,
        "r_1m": _retorno(close, 1),
        "r_3m": _retorno(close, 3),
        "r_5m": _retorno(close, 5),
        "r_15m": _retorno(close, 15),
        "ma3": _media_movel(close, 3),
        "ma6": _media_movel(close, 6),
        "ma10": _media_movel(close, 10),
        "ema5": _ema(close, 5),
        "ema10": _ema(close, 10),
        "vol5": _volatilidade(close, 5),
        "vol10": _volatilidade(close, 10),
        "amplitude_rel": amplitude_rel,
        "volume_ratio": (float(volume.iloc[-1]) / volume_medio) if volume_medio else 0.0,
        "book_imb": book_imb,
        "spread_rel": spread_rel,
        "microprice": microprice,
        "pressao_compra": pressao_compra_norm,
        "pressao_venda": pressao_venda_norm,
        "pressao_rel": pressao_rel,
        "ret_log_1m": float(ret_log.iloc[-1]) if not ret_log.empty else 0.0,
        "ret_log_cum_3m": float(ret_log.rolling(3, min_periods=1).sum().iloc[-1]) if not ret_log.empty else 0.0,
        "diff_close_micro_rel": diff_close_micro_rel,
        # Normalizado pelo preço atual: em unidade absoluta, BTC (~$60k) e um token de
        # centavos produziriam escalas completamente diferentes p/ o mesmo conceito,
        # quebrando a premissa de normalização de features entre símbolos.
        "slope_ma": (_media_movel(close, 3) - _media_movel(close, 10)) / (ultimo_close or 1.0),
        "hora_sin": math.sin(hora_rad),
        "hora_cos": math.cos(hora_rad),
        "dia_sin": math.sin(dia_rad),
        "dia_cos": math.cos(dia_rad),
        "sent_score": _sanear_numero(sent_score),
    }
    return {chave: _sanear_numero(valor) if chave != "ts" else int(valor) for chave, valor in features.items()}
