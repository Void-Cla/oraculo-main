from __future__ import annotations

from typing import Any

from src.calibracao.bandit import CalibradorBandit
from src.modelagem.gerenciador_modelo import GerenciadorModelo
from src.servicos.decisor_hibrido import decidir


def preditor_end_to_end(
    simbolo: str,
    features: dict[str, Any],
    noticias: list[Any] | None = None,
    saldo: dict[str, Any] | None = None,
    ajustes_sinal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gerenciador = GerenciadorModelo(simbolo=simbolo)
    y_hat = gerenciador.predict(features)

    calibrador = CalibradorBandit()
    y_cal, p_conf = calibrador.calibrar(y_hat, features)

    close = float(features.get("close", 0.0) or 0.0)
    vol = max(float(features.get("vol5", 0.0) or 0.0), float(features.get("vol10", 0.0) or 0.0))
    amplitude = max(close * max(vol, 0.0005), close * 0.0005 if close else 0.0)
    decisao = decidir(
        simbolo=simbolo,
        features=features,
        y_hat=y_hat,
        y_cal=y_cal,
        conf_num=float(p_conf),
        noticias=noticias,
        saldo=saldo,
        ajustes_sinal=ajustes_sinal,
    )

    direcao = "HOLD"
    if y_cal > close:
        direcao = "BUY"
    elif y_cal < close:
        direcao = "SELL"

    return {
        "simbolo": simbolo.upper(),
        "preco_atual": close,
        "y_hat": float(y_hat),
        "y_cal": float(y_cal),
        "ic68_low": float(y_cal - amplitude),
        "ic68_high": float(y_cal + amplitude),
        "p_conf": float(p_conf),
        "direcao": direcao,
        "features": features,
        "decisao": decisao,
        "modelo_status": gerenciador.status(),
    }
