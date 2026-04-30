from __future__ import annotations

"""Detector enxuto de drift de volatilidade pós-pausa."""

import math
from datetime import datetime, timezone

from src.core.settings import env_float, env_int
from src.observabilidade.logger import get_logger
from src.persistencia.conexao import get_conexao

LOG = get_logger("detector_drift")


def _ts_para_ms(valor: str | int | float) -> int:
    if isinstance(valor, str):
        try:
            texto = valor.replace("Z", "+00:00")
            return int(datetime.fromisoformat(texto).timestamp() * 1000)
        except ValueError:
            return int(float(valor))
    numero = int(valor)
    return numero * 1000 if numero < 10_000_000_000 else numero


def _desvio_padrao(valores: list[float]) -> float | None:
    """Desvio padrão populacional. Retorna None com menos de 2 pontos."""
    if len(valores) < 2:
        return None
    numeros = [float(valor) for valor in valores]
    media = sum(numeros) / len(numeros)
    variancia = sum((valor - media) ** 2 for valor in numeros) / len(numeros)
    return math.sqrt(variancia)


async def _calcular_volatilidade(simbolo: str, *, antes_de_ms: int, janela: int) -> float | None:
    async with get_conexao() as conn:
        cursor = await conn.execute(
            """
            SELECT close
            FROM ohlcv_1m
            WHERE simbolo = ? AND ts < ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (simbolo.upper(), antes_de_ms, janela),
        )
        linhas = await cursor.fetchall()
    return _desvio_padrao([float(linha["close"]) for linha in linhas if linha["close"] is not None])


async def _calcular_volatilidade_recente(simbolo: str, *, janela: int) -> float | None:
    async with get_conexao() as conn:
        cursor = await conn.execute(
            """
            SELECT close
            FROM ohlcv_1m
            WHERE simbolo = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (simbolo.upper(), janela),
        )
        linhas = await cursor.fetchall()
    return _desvio_padrao([float(linha["close"]) for linha in linhas if linha["close"] is not None])


async def detectar_drift(
    simbolo: str,
    ts_pausa_inicio: str | int | float,
    *,
    threshold: float | None = None,
    janela_candles: int | None = None,
) -> dict[str, object]:
    """Compara volatilidade pré-pausa e recente; drift força modo observação."""
    limite = float(threshold if threshold is not None else env_float("DRIFT_VOLATILIDADE_THRESHOLD", 2.0, minimo=1.0))
    janela = int(janela_candles if janela_candles is not None else env_int("DRIFT_JANELA_CANDLES", 30, minimo=2))
    ts_pausa_ms = _ts_para_ms(ts_pausa_inicio)

    vol_pre = await _calcular_volatilidade(simbolo, antes_de_ms=ts_pausa_ms, janela=janela)
    vol_pos = await _calcular_volatilidade_recente(simbolo, janela=janela)
    if vol_pre is None or vol_pos is None or vol_pre == 0.0:
        return {
            "drift_detectado": False,
            "razao_volatilidade": None,
            "mensagem": "dados_insuficientes_para_drift",
        }

    razao = vol_pos / vol_pre
    drift = razao >= limite or razao <= (1.0 / limite)
    LOG.info(
        "drift_avaliado",
        extra={"simbolo": simbolo.upper(), "vol_pre": vol_pre, "vol_pos": vol_pos, "razao": razao, "drift": drift},
    )
    return {
        "drift_detectado": drift,
        "razao_volatilidade": round(razao, 6),
        "mensagem": f"vol_pre={vol_pre:.6f} vol_pos={vol_pos:.6f} razao={razao:.3f}",
    }
