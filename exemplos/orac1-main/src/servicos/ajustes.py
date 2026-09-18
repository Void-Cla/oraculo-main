from __future__ import annotations

import math
from typing import Any

from src.core.settings import env_float, env_int
from src.persistencia.repositorio_config import RepositorioConfig
from src.risco.risk_engine import config_risco_padrao


_PERFIS_AUTO_IDS = {"mini", "ganancioso", "diario"}


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
        "intervalo_segundos": env_int("AUTO_INTERVALO_SEGUNDOS", 5, minimo=5),
        "notional_usdt": 5.0,
        "lado_inicial": "BUY",
        "perfis_capital": {},
    }


def ajustes_operacionais_padrao() -> dict[str, Any]:
    return {
        "auto_trades_ilimitados": True,
        "auto_max_idade_dados_ms": env_int("AUTO_MAX_IDADE_DADOS_MS", 60_000, minimo=5_000),
        "auto_max_desvio_relogio_ms": env_int("AUTO_MAX_DESVIO_RELOGIO_MS", 15_000, minimo=1_000),
        "auto_bloquear_saldo_sem_historico": True,
    }


def _normalizar_num(valor: Any) -> float | None:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def normalizar_ajustes_testnet(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    saida: dict[str, Any] = {}
    perfis_raw = payload.get("perfis_capital")
    if isinstance(perfis_raw, dict):
        perfis_norm: dict[str, dict[str, Any]] = {}
        for perfil_id, perfil_cfg in perfis_raw.items():
            perfil_id_norm = str(perfil_id or "").strip().lower()
            if perfil_id_norm not in _PERFIS_AUTO_IDS:
                continue
            if not isinstance(perfil_cfg, dict):
                continue
            perfil_saida: dict[str, Any] = {}
            if isinstance(perfil_cfg.get("ativo"), bool):
                perfil_saida["ativo"] = perfil_cfg["ativo"]
            capital = _normalizar_num(perfil_cfg.get("capital_usdt"))
            if capital is not None:
                perfil_saida["capital_usdt"] = max(0.0, float(capital))
            if perfil_saida:
                perfis_norm[perfil_id_norm] = perfil_saida
        if perfis_norm:
            saida["perfis_capital"] = perfis_norm
    return saida


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged.update(override)
    return merged


async def obter_ajustes_sinal() -> dict[str, Any]:
    base = ajustes_sinal_padrao()
    return {
        "padrao": base,
        "configurado": {},
        "aplicado": base,
        "modo": "automatico",
    }


async def obter_ajustes_risco() -> dict[str, Any]:
    base = config_risco_padrao()
    return {
        "padrao": base,
        "configurado": {},
        "aplicado": base,
        "modo": "automatico",
    }


async def obter_ajustes_testnet() -> dict[str, Any]:
    base = ajustes_testnet_padrao()
    override_raw = await RepositorioConfig.obter("ajustes_testnet")
    override = normalizar_ajustes_testnet(override_raw)
    if override.get("perfis_capital"):
        override = dict(override)
        override["notional_usdt"] = _soma_capital_perfis(dict(override.get("perfis_capital") or {}))
    return {
        "padrao": base,
        "configurado": override,
        "aplicado": _merge(base, override),
    }


async def obter_ajustes_operacionais() -> dict[str, Any]:
    base = ajustes_operacionais_padrao()
    return {
        "padrao": base,
        "configurado": {},
        "aplicado": base,
        "modo": "automatico",
    }


def _soma_capital_perfis(perfis_cfg: dict[str, dict[str, Any]]) -> float:
    soma = 0.0
    for perfil_id in _PERFIS_AUTO_IDS:
        bloco = dict(perfis_cfg.get(perfil_id) or {})
        if not bool(bloco.get("ativo", True)):
            continue
        capital = _normalizar_num(bloco.get("capital_usdt"))
        if capital is not None:
            soma += max(0.0, float(capital))
    return soma


async def salvar_ajustes_testnet(payload: Any) -> dict[str, Any]:
    override = normalizar_ajustes_testnet(payload)
    atual_raw = await RepositorioConfig.obter("ajustes_testnet")
    atual = normalizar_ajustes_testnet(atual_raw)
    merged = dict(atual)
    merged.update({k: v for k, v in override.items() if k != "perfis_capital"})

    perfis_atual = dict(atual.get("perfis_capital") or {})
    perfis_override = dict(override.get("perfis_capital") or {})
    if perfis_override:
        for perfil_id, perfil_cfg in perfis_override.items():
            bloco_atual = dict(perfis_atual.get(perfil_id) or {})
            bloco_atual.update(dict(perfil_cfg or {}))
            perfis_atual[perfil_id] = bloco_atual
    if perfis_atual:
        merged["perfis_capital"] = perfis_atual
        merged["notional_usdt"] = _soma_capital_perfis(perfis_atual)

    await RepositorioConfig.definir("ajustes_testnet", merged)
    return await obter_ajustes_testnet()
