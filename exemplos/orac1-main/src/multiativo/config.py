from __future__ import annotations

import os

ATIVOS_MONITORADOS_PADRAO = ("BTC", "ETH", "BNB", "USDT")
PARES_MONITORADOS_PADRAO = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "ETHBTC",
    "BNBBTC",
    "BNBETH",
)
PARES_PRIMARIOS_USDT = ("BTCUSDT", "ETHUSDT", "BNBUSDT")

_METADADOS_PARES = {
    "BTCUSDT": {"base": "BTC", "quote": "USDT"},
    "ETHUSDT": {"base": "ETH", "quote": "USDT"},
    "BNBUSDT": {"base": "BNB", "quote": "USDT"},
    "ETHBTC": {"base": "ETH", "quote": "BTC"},
    "BNBBTC": {"base": "BNB", "quote": "BTC"},
    "BNBETH": {"base": "BNB", "quote": "ETH"},
}

ROTAS_TRIANGULARES = (
    {
        "nome": "USDT_BTC_BNB_USDT",
        "legs": (
            {"from": "USDT", "to": "BTC", "simbolo": "BTCUSDT", "tipo": "buy_base"},
            {"from": "BTC", "to": "BNB", "simbolo": "BNBBTC", "tipo": "buy_base"},
            {"from": "BNB", "to": "USDT", "simbolo": "BNBUSDT", "tipo": "sell_base"},
        ),
    },
    {
        "nome": "USDT_ETH_BNB_USDT",
        "legs": (
            {"from": "USDT", "to": "ETH", "simbolo": "ETHUSDT", "tipo": "buy_base"},
            {"from": "ETH", "to": "BNB", "simbolo": "BNBETH", "tipo": "buy_base"},
            {"from": "BNB", "to": "USDT", "simbolo": "BNBUSDT", "tipo": "sell_base"},
        ),
    },
    {
        "nome": "USDT_BTC_ETH_USDT",
        "legs": (
            {"from": "USDT", "to": "BTC", "simbolo": "BTCUSDT", "tipo": "buy_base"},
            {"from": "BTC", "to": "ETH", "simbolo": "ETHBTC", "tipo": "buy_base"},
            {"from": "ETH", "to": "USDT", "simbolo": "ETHUSDT", "tipo": "sell_base"},
        ),
    },
)


def _lista_env(chave: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
    bruto = os.getenv(chave, "").strip()
    itens = [item.strip().upper() for item in bruto.split(",") if item.strip()]
    filtrados = [item for item in itens if item in _METADADOS_PARES]
    if filtrados:
        return tuple(dict.fromkeys(filtrados))
    return fallback


def pares_monitorados() -> tuple[str, ...]:
    return _lista_env("MONITORED_PAIRS", _lista_env("SYMBOLS", PARES_MONITORADOS_PADRAO))


def pares_primarios_usdt() -> tuple[str, ...]:
    ativos = set(pares_monitorados())
    return tuple(par for par in PARES_PRIMARIOS_USDT if par in ativos)


def ativos_monitorados() -> tuple[str, ...]:
    ativos: list[str] = []
    for simbolo in pares_monitorados():
        meta = _METADADOS_PARES[simbolo]
        for ativo in (meta["base"], meta["quote"]):
            if ativo not in ativos:
                ativos.append(ativo)
    for ativo in ATIVOS_MONITORADOS_PADRAO:
        if ativo not in ativos:
            ativos.append(ativo)
    return tuple(ativos)


def metadados_par(simbolo: str) -> dict[str, str]:
    simbolo = simbolo.upper()
    if simbolo not in _METADADOS_PARES:
        raise ValueError(f"simbolo_nao_monitorado: {simbolo}")
    return dict(_METADADOS_PARES[simbolo])


def ativo_base(simbolo: str) -> str:
    return metadados_par(simbolo)["base"]


def ativo_cotacao(simbolo: str) -> str:
    return metadados_par(simbolo)["quote"]


def validar_par_monitorado(simbolo: str) -> str:
    simbolo = simbolo.upper()
    if simbolo not in pares_monitorados():
        raise ValueError(f"simbolo_nao_monitorado: {simbolo}")
    return simbolo


def par_usdt_do_ativo(ativo: str) -> str:
    ativo = ativo.upper()
    if ativo == "USDT":
        return "USDT"
    candidato = f"{ativo}USDT"
    if candidato not in _METADADOS_PARES:
        raise ValueError(f"ativo_sem_par_usdt: {ativo}")
    return candidato
