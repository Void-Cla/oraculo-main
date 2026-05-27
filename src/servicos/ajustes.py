from __future__ import annotations

from typing import Any

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


# Hardcoded — sem os.getenv
def ajustes_sinal_padrao() -> dict[str, Any]:
    return {
        "peso_modelo_numerico":         0.65,
        "peso_modelo_llm":              0.35,
        "limiar_variacao_numerica":     0.0015,
        "limiar_score_operacao":        0.18,
        "max_spread_rel":               0.003,
        "max_vol5":                     0.02,
        "max_posicao_fracao":           0.05,
        "signal_trade_fee_pct":         0.001,    # decimal — 0.1%
        "signal_slippage_pct":          0.0005,   # decimal — 0.05%
        "signal_min_net_profit_pct":    0.0005,   # 0.05% mínimo
        "signal_min_ev":                0.0001,   # EV mínimo reduzido para micro-trading
        "signal_min_prob":              0.55,
        "signal_prob_temperature":      1.0,
        "signal_prob_scale":            10.0,
        "signal_confirm_threshold":     1,        # 1 confirmação — agressivo
        "signal_decision_window_minutes": 5,
    }


def ajustes_testnet_padrao() -> dict[str, Any]:
    return {
        "simbolo":             "BTCUSDT",
        "intervalo_segundos":  15,               # mais rápido — scalping
        "notional_usdt":       10.0,
        "lado_inicial":        "BUY",
    }


def ajustes_retomada_padrao() -> dict[str, Any]:
    return {
        "simbolo_principal":         "BTCUSDT",
        "pausa_media_h":             4.0,
        "pausa_longa_h":             24.0,
        "variacao_pct":              3.0,
        "candles_observacao":        5,
        "recalibracao_candles":      10,
        "drift_volatilidade_threshold": 0.02,
        "drift_janela_candles":      20,
    }


def _mesclar(base: dict, sobrescrever: dict, chaves: set) -> dict:
    resultado = dict(base)
    for chave, valor in sobrescrever.items():
        if chave in chaves:
            resultado[chave] = valor
    return resultado


async def obter_ajustes_sinal(
    repo: RepositorioConfig | None = None,
    usuario_id: str | None = None,
) -> dict[str, Any]:
    base = ajustes_sinal_padrao()
    if repo and usuario_id:
        try:
            persistido = await repo.obter_config(usuario_id, "ajustes_sinal") or {}
            base = _mesclar(base, persistido, _SINAL_CHAVES)
        except Exception:
            pass
    return {"aplicado": base, "padrao": ajustes_sinal_padrao()}


async def obter_ajustes_retomada(
    repo: RepositorioConfig | None = None,
    usuario_id: str | None = None,
) -> dict[str, Any]:
    base = ajustes_retomada_padrao()
    if repo and usuario_id:
        try:
            persistido = await repo.obter_config(usuario_id, "ajustes_retomada") or {}
            base = _mesclar(base, persistido, _RETOMADA_CHAVES)
        except Exception:
            pass
    return {"aplicado": base, "padrao": ajustes_retomada_padrao()}


async def salvar_ajustes_sinal(
    repo: RepositorioConfig,
    usuario_id: str,
    dados: dict[str, Any],
) -> dict[str, Any]:
    filtrado = {k: v for k, v in dados.items() if k in _SINAL_CHAVES}
    await repo.salvar_config(usuario_id, "ajustes_sinal", filtrado)
    return await obter_ajustes_sinal(repo, usuario_id)


async def salvar_ajustes_retomada(
    repo: RepositorioConfig,
    usuario_id: str,
    dados: dict[str, Any],
) -> dict[str, Any]:
    filtrado = {k: v for k, v in dados.items() if k in _RETOMADA_CHAVES}
    await repo.salvar_config(usuario_id, "ajustes_retomada", filtrado)
    return await obter_ajustes_retomada(repo, usuario_id)


# ── Risco ──────────────────────────────────────────────────────────────────

_RISCO_CHAVES = {
    "risk_per_trade",
    "max_drawdown",
    "max_drawdown_diario",
    "max_daily_loss_usdt",
    "max_loss_trade_usdt",
    "max_exposicao_ativo",
    "max_trades_abertos",
    "max_trades_por_hora",
    "cooldown_minutos",
    "bloquear_flip_flop",
    "lucro_liquido_minimo",
    "lucro_liquido_minimo_usdt",
    "filtro_ev_minimo_usdt",
    "binance_taxa_maker_pct",
    "binance_taxa_taker_pct",
    "slippage_pct",
    "paper_trading",
}


def ajustes_risco_padrao() -> dict[str, Any]:
    from src.risco.risk_engine import config_risco_padrao
    return config_risco_padrao()


async def obter_ajustes_risco(
    repo: RepositorioConfig | None = None,
    usuario_id: str | None = None,
) -> dict[str, Any]:
    base = ajustes_risco_padrao()
    if repo and usuario_id:
        try:
            persistido = await repo.obter_config(usuario_id, "ajustes_risco") or {}
            base = _mesclar(base, persistido, _RISCO_CHAVES)
        except Exception:
            pass
    return {"aplicado": base, "padrao": ajustes_risco_padrao()}


async def salvar_ajustes_risco(
    dados: dict[str, Any],
    repo: RepositorioConfig | None = None,
    usuario_id: str | None = None,
) -> dict[str, Any]:
    filtrado = {k: v for k, v in dados.items() if k in _RISCO_CHAVES}
    if repo and usuario_id:
        await repo.salvar_config(usuario_id, "ajustes_risco", filtrado)
    return await obter_ajustes_risco(repo, usuario_id)


# ── Testnet ────────────────────────────────────────────────────────────────

_TESTNET_CHAVES = {
    "simbolo", "intervalo_segundos", "notional_usdt", "lado_inicial",
}


async def obter_ajustes_testnet(
    repo: RepositorioConfig | None = None,
    usuario_id: str | None = None,
) -> dict[str, Any]:
    base = ajustes_testnet_padrao()
    if repo and usuario_id:
        try:
            persistido = await repo.obter_config(usuario_id, "ajustes_testnet") or {}
            base = _mesclar(base, persistido, _TESTNET_CHAVES)
        except Exception:
            pass
    return {"aplicado": base, "padrao": ajustes_testnet_padrao()}


async def salvar_ajustes_testnet(
    dados: dict[str, Any],
    repo: RepositorioConfig | None = None,
    usuario_id: str | None = None,
) -> dict[str, Any]:
    filtrado = {k: v for k, v in dados.items() if k in _TESTNET_CHAVES}
    if repo and usuario_id:
        await repo.salvar_config(usuario_id, "ajustes_testnet", filtrado)
    return await obter_ajustes_testnet(repo, usuario_id)


# ── Bootstrap ──────────────────────────────────────────────────────────────

async def garantir_ajustes_padrao(
    repo: RepositorioConfig | None = None,
    usuario_id: str | None = None,
) -> dict[str, Any]:
    """Garante que todos os ajustes estão persistidos com valores padrão."""
    return {
        "sinal":    await obter_ajustes_sinal(repo, usuario_id),
        "risco":    await obter_ajustes_risco(repo, usuario_id),
        "testnet":  await obter_ajustes_testnet(repo, usuario_id),
        "retomada": await obter_ajustes_retomada(repo, usuario_id),
    }
