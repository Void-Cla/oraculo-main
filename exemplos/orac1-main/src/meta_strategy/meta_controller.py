from __future__ import annotations

from typing import Any, Callable

from src.estrategias.breakout import gerar_sinal_breakout
from src.estrategias.mean_reversion import gerar_sinal_mean_reversion
from src.estrategias.momentum import gerar_sinal_momentum
from src.estrategias.volatility_scalping import gerar_sinal_volatility_scalping

_MAPA_ESTRATEGIAS: dict[str, Callable[[str, dict[str, Any], dict[str, Any] | None], dict[str, Any]]] = {
    "TREND_UP": gerar_sinal_momentum,
    "TREND_DOWN": gerar_sinal_momentum,
    "RANGE": gerar_sinal_mean_reversion,
    "HIGH_VOL": gerar_sinal_breakout,
    "LOW_VOL": gerar_sinal_volatility_scalping,
}


def selecionar_estrategia(regime: str) -> Callable[[str, dict[str, Any], dict[str, Any] | None], dict[str, Any]]:
    return _MAPA_ESTRATEGIAS.get(regime, gerar_sinal_mean_reversion)


def gerar_sinal_meta(
    simbolo: str,
    regime_info: dict[str, Any],
    features: dict[str, Any],
    contexto_mercado: dict[str, Any] | None = None,
) -> dict[str, Any]:
    estrategia = selecionar_estrategia(regime_info["regime"])
    sinal = estrategia(simbolo, features, contexto_mercado)
    sinal["regime"] = regime_info["regime"]
    sinal["score_regime"] = float(regime_info.get("score_regime", 0.5))
    sinal["detector_regime"] = regime_info.get("detalhes", {})
    sinal["confianca"] = min(0.99, float(sinal["confianca"]) * float(regime_info.get("score_regime", 0.5)) + 0.15)
    return sinal
