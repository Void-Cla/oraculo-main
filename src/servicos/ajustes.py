from __future__ import annotations

from typing import Any

from src.core.settings import env_float, env_int, env_str
from src.persistencia.repositorio_config import RepositorioConfig
from src.risco.risk_engine import config_risco_padrao


_SINAL_CHAVES = {
    "peso_modelo_numerico",
    "peso_modelo_llm",
    "limiar_variacao_numerica",
    "limiar_score_operacao",
    "max_spread_rel",
    "max_vol5",
    "max_posicao_fracao",
    "signal_trade_fee_pct",
    "signal_slippage_pct",
    "signal_min_net_profit_pct",
    "signal_min_ev",
    "signal_min_prob",
    "signal_prob_temperature",
    "signal_prob_scale",
    "signal_confirm_threshold",
    "signal_decision_window_minutes",
}

_RETOMADA_CHAVES = {
    "simbolo_principal",
    "pausa_media_h",
    "pausa_longa_h",
    "variacao_pct",
    "candles_observacao",
    "recalibracao_candles",
    "drift_volatilidade_threshold",
    "drift_janela_candles",
}


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def ajustes_sinal_padrao() -> dict[str, Any]:
    return {
        "peso_modelo_numerico": env_float("PESO_MODELO_NUMERICO", 0.65, minimo=0.0),
        "peso_modelo_llm": env_float("PESO_MODELO_LLM", 0.35, minimo=0.0),
        "limiar_variacao_numerica": env_float("LIMIAR_VARIACAO_NUMERICA", 0.0015, minimo=0.0),
        "limiar_score_operacao": env_float("LIMIAR_SCORE_OPERACAO", 0.18, minimo=0.0),
        "max_spread_rel": env_float("MAX_SPREAD_REL", 0.003, minimo=0.0),
        "max_vol5": env_float("MAX_VOL5", 0.02, minimo=0.0),
        "max_posicao_fracao": env_float("MAX_POSICAO_FRACAO", 0.05, minimo=0.0),
        "signal_trade_fee_pct": env_float("SIGNAL_TRADE_FEE_PCT", 0.0012),
        "signal_slippage_pct": env_float("SIGNAL_SLIPPAGE_PCT", 0.0005),
        "signal_min_net_profit_pct": env_float("SIGNAL_MIN_NET_PROFIT_PCT", 0.0045),
        "signal_min_ev": env_float("SIGNAL_MIN_EV", 0.0020),
        "signal_min_prob": env_float("SIGNAL_MIN_PROB", 0.62),
        "signal_prob_temperature": env_float("SIGNAL_PROB_TEMPERATURE", 1.0, minimo=0.0),
        "signal_prob_scale": env_float("SIGNAL_PROB_SCALE", 10.0, minimo=0.0),
        "signal_confirm_threshold": env_int("SIGNAL_CONFIRMATION_THRESHOLD", 3, minimo=0),
        "signal_decision_window_minutes": env_int("SIGNAL_DECISION_WINDOW_MINUTES", 20, minimo=0),
    }


def ajustes_testnet_padrao() -> dict[str, Any]:
    return {
        "simbolo": "BTCUSDT",
        "intervalo_segundos": 30,
        "notional_usdt": 5.0,
        "lado_inicial": "BUY",
    }


def ajustes_retomada_padrao() -> dict[str, Any]:
    return {
        "simbolo_principal": env_str("SIMBOLO_PRINCIPAL", "BTCUSDT").upper(),
        "pausa_media_h": env_float("RETOMADA_PAUSA_MEDIA_H", 4.0, minimo=0.0),
        "pausa_longa_h": env_float("RETOMADA_PAUSA_LONGA_H", 24.0, minimo=0.0),
        "variacao_pct": env_float("RETOMADA_VARIACAO_PCT", 3.0, minimo=0.0),
        "candles_observacao": env_int("RETOMADA_CANDLES_OBSERVACAO", 5, minimo=1),
        "recalibracao_candles": env_int("RECALIBRACAO_CANDLES", 60, minimo=1),
        "drift_volatilidade_threshold": env_float("DRIFT_VOLATILIDADE_THRESHOLD", 2.0, minimo=1.0),
        "drift_janela_candles": env_int("DRIFT_JANELA_CANDLES", 30, minimo=2),
    }


def _normalizar_num(valor: Any) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _normalizar_int(valor: Any) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def normalizar_ajustes_sinal(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    saida: dict[str, Any] = {}
    for chave in _SINAL_CHAVES:
        if chave not in payload:
            continue
        valor = payload.get(chave)
        if chave in {"signal_confirm_threshold", "signal_decision_window_minutes"}:
            valor_int = _normalizar_int(valor)
            if valor_int is not None:
                saida[chave] = max(0, valor_int)
            continue
        valor_num = _normalizar_num(valor)
        if valor_num is None:
            continue
        if chave in {"peso_modelo_numerico", "peso_modelo_llm"}:
            saida[chave] = _clamp(valor_num, 0.0, 1.0)
        elif chave in {"limiar_variacao_numerica", "limiar_score_operacao"}:
            saida[chave] = max(0.0, valor_num)
        elif chave in {"max_spread_rel", "max_vol5", "max_posicao_fracao"}:
            saida[chave] = max(0.0, valor_num)
        elif chave in {
            "signal_trade_fee_pct",
            "signal_slippage_pct",
            "signal_min_net_profit_pct",
            "signal_min_ev",
            "signal_min_prob",
            "signal_prob_temperature",
            "signal_prob_scale",
        }:
            saida[chave] = valor_num
        else:
            saida[chave] = valor_num
    return saida


def normalizar_ajustes_risco(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    base = config_risco_padrao()
    saida: dict[str, Any] = {}
    for chave in base.keys():
        if chave not in payload:
            continue
        valor = payload.get(chave)
        if isinstance(base[chave], bool):
            saida[chave] = bool(valor)
            continue
        if isinstance(base[chave], int):
            valor_int = _normalizar_int(valor)
            if valor_int is not None:
                saida[chave] = valor_int
            continue
        valor_num = _normalizar_num(valor)
        if valor_num is not None:
            saida[chave] = float(valor_num)
    return saida


def normalizar_ajustes_testnet(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    base = ajustes_testnet_padrao()
    saida: dict[str, Any] = {}
    simbolo = payload.get("simbolo")
    if isinstance(simbolo, str) and simbolo:
        saida["simbolo"] = simbolo.upper()
    intervalo = _normalizar_int(payload.get("intervalo_segundos"))
    if intervalo is not None:
        saida["intervalo_segundos"] = max(5, intervalo)
    notional = _normalizar_num(payload.get("notional_usdt"))
    if notional is not None:
        saida["notional_usdt"] = max(0.0, float(notional))
    lado_inicial = payload.get("lado_inicial")
    if isinstance(lado_inicial, str) and lado_inicial.upper() in {"BUY", "SELL"}:
        saida["lado_inicial"] = lado_inicial.upper()
    return saida


def normalizar_ajustes_retomada(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    saida: dict[str, Any] = {}
    simbolo = payload.get("simbolo_principal")
    if isinstance(simbolo, str) and simbolo.strip():
        saida["simbolo_principal"] = simbolo.strip().upper()

    for chave in _RETOMADA_CHAVES - {"simbolo_principal", "candles_observacao", "recalibracao_candles", "drift_janela_candles"}:
        if chave not in payload:
            continue
        valor_num = _normalizar_num(payload.get(chave))
        if valor_num is not None:
            saida[chave] = max(0.0, float(valor_num))

    for chave in {"candles_observacao", "recalibracao_candles", "drift_janela_candles"}:
        if chave not in payload:
            continue
        valor_int = _normalizar_int(payload.get(chave))
        if valor_int is not None:
            saida[chave] = max(1, valor_int)
    if "drift_volatilidade_threshold" in saida:
        saida["drift_volatilidade_threshold"] = max(1.0, float(saida["drift_volatilidade_threshold"]))
    return saida


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged.update(override)
    return merged


async def obter_ajustes_sinal() -> dict[str, Any]:
    base = ajustes_sinal_padrao()
    override_raw = await RepositorioConfig.obter("ajustes_sinal")
    override = normalizar_ajustes_sinal(override_raw)
    return {
        "padrao": base,
        "configurado": override,
        "aplicado": _merge(base, override),
    }


async def obter_ajustes_risco() -> dict[str, Any]:
    base = config_risco_padrao()
    override_raw = await RepositorioConfig.obter("ajustes_risco")
    override = normalizar_ajustes_risco(override_raw)
    return {
        "padrao": base,
        "configurado": override,
        "aplicado": _merge(base, override),
    }


async def obter_ajustes_testnet() -> dict[str, Any]:
    base = ajustes_testnet_padrao()
    override_raw = await RepositorioConfig.obter("ajustes_testnet")
    override = normalizar_ajustes_testnet(override_raw)
    return {
        "padrao": base,
        "configurado": override,
        "aplicado": _merge(base, override),
    }


async def obter_ajustes_retomada() -> dict[str, Any]:
    base = ajustes_retomada_padrao()
    override_raw = await RepositorioConfig.obter("ajustes_retomada")
    override = normalizar_ajustes_retomada(override_raw)
    return {
        "padrao": base,
        "configurado": override,
        "aplicado": _merge(base, override),
    }


async def salvar_ajustes_sinal(payload: Any) -> dict[str, Any]:
    override = normalizar_ajustes_sinal(payload)
    await RepositorioConfig.definir("ajustes_sinal", override)
    return await obter_ajustes_sinal()


async def salvar_ajustes_risco(payload: Any) -> dict[str, Any]:
    override = normalizar_ajustes_risco(payload)
    await RepositorioConfig.definir("ajustes_risco", override)
    return await obter_ajustes_risco()


async def salvar_ajustes_testnet(payload: Any) -> dict[str, Any]:
    override = normalizar_ajustes_testnet(payload)
    await RepositorioConfig.definir("ajustes_testnet", override)
    return await obter_ajustes_testnet()


async def salvar_ajustes_retomada(payload: Any) -> dict[str, Any]:
    override = normalizar_ajustes_retomada(payload)
    await RepositorioConfig.definir("ajustes_retomada", override)
    return await obter_ajustes_retomada()


async def garantir_ajustes_padrao() -> None:
    defaults = {
        "ajustes_sinal": ajustes_sinal_padrao(),
        "ajustes_risco": config_risco_padrao(),
        "ajustes_testnet": ajustes_testnet_padrao(),
        "ajustes_retomada": ajustes_retomada_padrao(),
    }
    for chave, valor in defaults.items():
        if await RepositorioConfig.obter(chave) is None:
            await RepositorioConfig.definir(chave, valor)
