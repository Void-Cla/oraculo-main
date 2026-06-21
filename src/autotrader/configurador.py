"""Calibração de risco e sinal do auto-trader (FASE 6 — extraído do god-file).

Funções puras que ajustam thresholds para micro-trading e montam o "usuário virtual"
com freios de segurança conservadores. Sem I/O e sem estado.
"""
from __future__ import annotations

from typing import Any

from src.autotrader.calculos import _piso_lucro_percentual


def _ajustes_microtrading_auto(
    ajustes_sinal: dict[str, Any],
    *,
    notional_usdt: float,
    lucro_liquido_minimo_usdt: float,
    state: dict[str, Any] | None = None,
    modo_testnet: bool = False,
) -> dict[str, Any]:
    ajustes_auto = dict(ajustes_sinal)
    notional_base = max(0.0, float(notional_usdt or 0.0))
    # Hard floor $0.01 em qualquer modo
    lucro_minimo_usdt = max(0.01, float(lucro_liquido_minimo_usdt or 0.01))
    if modo_testnet:
        # Testnet permite validar o fluxo com micro-lucros — limita alvos herdados altos.
        lucro_minimo_usdt = min(lucro_minimo_usdt, 0.001)
    piso_lucro_pct = _piso_lucro_percentual(
        ajustes_auto,
        notional_usdt=notional_base,
        lucro_liquido_minimo_usdt=lucro_minimo_usdt,
    )
    ajustes_auto["auto_lucro_liquido_minimo_usdt"] = lucro_minimo_usdt
    ajustes_auto["signal_min_net_profit_pct"] = max(0.0002, piso_lucro_pct)
    # Thresholds agressivos para scalping
    ajustes_auto["signal_confirm_threshold"] = max(int(ajustes_auto.get("signal_confirm_threshold", 1) or 1), 1)
    ajustes_auto["signal_decision_window_minutes"] = max(int(ajustes_auto.get("signal_decision_window_minutes", 5) or 5), 1)
    ajustes_auto["limiar_score_operacao"] = max(float(ajustes_auto.get("limiar_score_operacao", 0.18) or 0.18), 0.15)
    # Alarga levemente (1.2x) o limiar de variação numérica para reduzir ruído de entrada.
    ajustes_auto["limiar_variacao_numerica"] = max(
        float(ajustes_auto.get("limiar_variacao_numerica", 0.0015) or 0.0015) * 1.2, 0.001
    )
    ev_minimo = max(float(ajustes_auto.get("signal_min_ev", 0.0001) or 0.0001), max(0.0001, piso_lucro_pct * 0.30))
    prob_minima = max(float(ajustes_auto.get("signal_min_prob", 0.55) or 0.55), 0.50)
    if modo_testnet:
        # Testnet limita filtros herdados altos para não travar o aprendizado em micro-trades.
        ev_minimo = min(ev_minimo, 0.0008)
        prob_minima = min(prob_minima, 0.62)
    ajustes_auto["signal_min_ev"] = ev_minimo
    ajustes_auto["signal_min_prob"] = prob_minima
    # Autoajuste rápido baseado no histórico local (complementar ao ControladorAdaptativo)
    historico = list(((state or {}).get("historico_ciclos")) or [])[-6:]
    if historico:
        ganhos = [float(item.get("lucro_liquido_usdt", 0.0) or 0.0) for item in historico]
        retornos = [float(item.get("retorno_liquido_pct", 0.0) or 0.0) for item in historico]
        win_rate = sum(1 for item in ganhos if item > 0.0) / max(len(ganhos), 1)
        lucro_medio = sum(ganhos) / max(len(ganhos), 1)
        retorno_medio = sum(retornos) / max(len(retornos), 1)
        if win_rate >= 0.75 and lucro_medio > lucro_minimo_usdt and retorno_medio > piso_lucro_pct:
            ajustes_auto["signal_min_prob"] = max(0.50, float(ajustes_auto["signal_min_prob"]) - 0.008)
            ajustes_auto["signal_min_ev"] = max(0.0001, float(ajustes_auto["signal_min_ev"]) * 0.92)
            ajustes_auto["limiar_score_operacao"] = max(0.13, float(ajustes_auto["limiar_score_operacao"]) - 0.01)
            ajustes_auto["signal_min_net_profit_pct"] = max(0.0002, float(ajustes_auto["signal_min_net_profit_pct"]) * 0.92)
        elif win_rate <= 0.50 or lucro_medio <= 0.0 or retorno_medio <= 0.0:
            ajustes_auto["signal_min_prob"] = min(0.65, float(ajustes_auto["signal_min_prob"]) + 0.01)
            ajustes_auto["signal_min_ev"] = min(0.001, float(ajustes_auto["signal_min_ev"]) * 1.08)
            ajustes_auto["limiar_score_operacao"] = min(0.25, float(ajustes_auto["limiar_score_operacao"]) + 0.01)
            ajustes_auto["signal_min_net_profit_pct"] = min(0.002, float(ajustes_auto["signal_min_net_profit_pct"]) * 1.08)
    return ajustes_auto


def _usuario_virtual(ajustes_risco: dict[str, Any], *, modo_testnet: bool) -> dict[str, Any]:
    risk_config = dict(ajustes_risco)
    # Freios de segurança do auto-trader — sempre conservadores (defense in depth):
    # no máximo 1 trade aberto, 3 por hora, cooldown mínimo de 10 min e anti flip-flop.
    risk_config["max_trades_abertos"] = min(int(risk_config.get("max_trades_abertos", 1) or 1), 1)
    risk_config["max_trades_por_hora"] = min(int(risk_config.get("max_trades_por_hora", 3) or 3), 3)
    risk_config["cooldown_minutos"] = max(int(risk_config.get("cooldown_minutos", 10) or 10), 10)
    risk_config["bloquear_flip_flop"] = True
    risk_config["max_exposicao_ativo"] = min(max(0.0, float(risk_config.get("max_exposicao_ativo", 0.20) or 0.20)), 0.20)
    risk_config["risk_per_trade"] = min(max(0.0, float(risk_config.get("risk_per_trade", 0.005) or 0.005)), 0.005)
    risk_config["max_loss_trade_usdt"] = min(max(0.01, float(risk_config.get("max_loss_trade_usdt", 0.20) or 0.20)), 0.20)
    risk_config["modo_testnet"] = bool(modo_testnet)
    exploracao = bool(risk_config.get("permitir_ev_negativo", False))
    if modo_testnet and exploracao:
        # Modo exploração (TESTNET-ONLY, ver _aplicar_modo_exploracao): pisos permissivos p/ o
        # micro-trading 1-15m OPERAR de fato, aceitando EV potencialmente NEGATIVO. Só validação.
        risk_config["lucro_liquido_minimo"] = -1.0
        risk_config["lucro_liquido_minimo_usdt"] = -1e9
        risk_config["filtro_ev_minimo_usdt"] = float(risk_config.get("filtro_ev_minimo_usdt", -1e9) or -1e9)
    elif modo_testnet:
        # Testnet calibra os pisos de lucro para micro-trading (valida o fluxo com lucros ínfimos).
        risk_config["lucro_liquido_minimo"] = 0.0002
        risk_config["lucro_liquido_minimo_usdt"] = 0.001
        risk_config["filtro_ev_minimo_usdt"] = 0.001
    else:
        # Conta real mantém pisos de lucro mínimos absolutos (hard floor $0.01).
        # SEGURANÇA: EV negativo é PROIBIDO em conta real, independente de qualquer flag.
        risk_config["permitir_ev_negativo"] = False
        risk_config["lucro_liquido_minimo"] = max(0.0002, float(risk_config.get("lucro_liquido_minimo", 0.0005) or 0.0002))
        risk_config["lucro_liquido_minimo_usdt"] = max(0.01, float(risk_config.get("lucro_liquido_minimo_usdt", 0.01) or 0.01))
        risk_config["filtro_ev_minimo_usdt"] = max(0.01, float(risk_config.get("filtro_ev_minimo_usdt", 0.01) or 0.01))
    return {
        "id": 0,
        "nome": "auto_trader",
        "testnet": bool(modo_testnet),
        "ativo": True,
        "risk_config": risk_config,
    }
