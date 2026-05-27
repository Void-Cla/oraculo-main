from __future__ import annotations

# Sem os.getenv — pares hardcoded com suporte dinâmico por inferência

ATIVOS_MONITORADOS_PADRAO = ("BTC", "ETH", "BNB", "USDT")
PARES_MONITORADOS_PADRAO = (
    "BTCUSDT", "ETHUSDT", "BNBUSDT",
    "ETHBTC", "BNBBTC", "BNBETH",
)
PARES_PRIMARIOS_USDT = ("BTCUSDT", "ETHUSDT", "BNBUSDT")

_METADADOS_PARES: dict[str, dict[str, str]] = {
    "BTCUSDT": {"base": "BTC",  "quote": "USDT"},
    "ETHUSDT": {"base": "ETH",  "quote": "USDT"},
    "BNBUSDT": {"base": "BNB",  "quote": "USDT"},
    "ETHBTC":  {"base": "ETH",  "quote": "BTC"},
    "BNBBTC":  {"base": "BNB",  "quote": "BTC"},
    "BNBETH":  {"base": "BNB",  "quote": "ETH"},
}

ROTAS_TRIANGULARES = (
    {
        "nome": "USDT_BTC_BNB_USDT",
        "legs": (
            {"from": "USDT", "to": "BTC", "simbolo": "BTCUSDT", "tipo": "buy_base"},
            {"from": "BTC",  "to": "BNB", "simbolo": "BNBBTC",  "tipo": "buy_base"},
            {"from": "BNB",  "to": "USDT","simbolo": "BNBUSDT", "tipo": "sell_base"},
        ),
    },
    {
        "nome": "USDT_ETH_BNB_USDT",
        "legs": (
            {"from": "USDT", "to": "ETH", "simbolo": "ETHUSDT", "tipo": "buy_base"},
            {"from": "ETH",  "to": "BNB", "simbolo": "BNBETH",  "tipo": "buy_base"},
            {"from": "BNB",  "to": "USDT","simbolo": "BNBUSDT", "tipo": "sell_base"},
        ),
    },
    {
        "nome": "USDT_BTC_ETH_USDT",
        "legs": (
            {"from": "USDT", "to": "BTC", "simbolo": "BTCUSDT", "tipo": "buy_base"},
            {"from": "BTC",  "to": "ETH", "simbolo": "ETHBTC",  "tipo": "buy_base"},
            {"from": "ETH",  "to": "USDT","simbolo": "ETHUSDT", "tipo": "sell_base"},
        ),
    },
)


# ── Inferência dinâmica de metadados ─────────────────────────────────────────

_QUOTES_CONHECIDOS = ("USDT", "BTC", "ETH", "BNB", "BUSD", "EUR", "BRL")


def _inferir_metadados(simbolo: str) -> dict[str, str] | None:
    """Infere base/quote de qualquer par válido da Binance."""
    if simbolo in _METADADOS_PARES:
        return _METADADOS_PARES[simbolo]
    for q in _QUOTES_CONHECIDOS:
        if simbolo.endswith(q) and len(simbolo) > len(q):
            base = simbolo[: -len(q)]
            if len(base) >= 2:
                return {"base": base, "quote": q}
    return None


def registrar_par(simbolo: str) -> bool:
    """Registra um par dinamicamente se ainda não conhecido. Retorna True se novo."""
    simbolo = simbolo.upper()
    if simbolo in _METADADOS_PARES:
        return False
    meta = _inferir_metadados(simbolo)
    if meta is None:
        return False
    _METADADOS_PARES[simbolo] = meta
    return True


# ── Funções públicas ──────────────────────────────────────────────────────────

def pares_monitorados() -> tuple[str, ...]:
    return PARES_MONITORADOS_PADRAO


def pares_primarios_usdt() -> tuple[str, ...]:
    ativos = set(pares_monitorados())
    return tuple(par for par in PARES_PRIMARIOS_USDT if par in ativos)


def ativos_monitorados() -> tuple[str, ...]:
    ativos: list[str] = []
    for simbolo in pares_monitorados():
        meta = _inferir_metadados(simbolo) or {}
        for ativo in (meta.get("base", ""), meta.get("quote", "")):
            if ativo and ativo not in ativos:
                ativos.append(ativo)
    for ativo in ATIVOS_MONITORADOS_PADRAO:
        if ativo not in ativos:
            ativos.append(ativo)
    return tuple(ativos)


def metadados_par(simbolo: str) -> dict[str, str]:
    simbolo = simbolo.upper()
    meta = _inferir_metadados(simbolo)
    if meta is None:
        raise ValueError(f"simbolo_nao_suportado: {simbolo}")
    return dict(meta)


def ativo_base(simbolo: str) -> str:
    return metadados_par(simbolo)["base"]


def ativo_cotacao(simbolo: str) -> str:
    return metadados_par(simbolo)["quote"]


def validar_par_monitorado(simbolo: str) -> str:
    simbolo = simbolo.upper()
    if simbolo not in set(pares_monitorados()):
        raise ValueError(f"simbolo_nao_monitorado: {simbolo}")
    return simbolo


def par_usdt_do_ativo(ativo: str) -> str:
    ativo = ativo.upper()
    if ativo == "USDT":
        return "USDT"
    candidato = f"{ativo}USDT"
    meta = _inferir_metadados(candidato)
    if meta is None:
        raise ValueError(f"ativo_sem_par_usdt: {ativo}")
    return candidato
