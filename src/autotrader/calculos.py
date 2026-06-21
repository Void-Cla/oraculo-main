"""Funções puras de cálculo do ciclo de trading (FASE 6 — extraído do god-file).

Sem I/O e sem estado: custos round-trip, pisos de lucro, teto de notional e datas.
Reaproveitáveis e testáveis isoladamente.
"""
from __future__ import annotations

import os
import time
from typing import Any


def _teto_notional_operacional_usdt() -> float:
    # Teto de segurança de notional por operação (USDT), lido de AUTO_MAX_NOTIONAL_USDT.
    # Ausente ou <= 0 = sem teto (preserva o uso intencional de notional alto em testnet).
    try:
        return max(0.0, float(os.getenv("AUTO_MAX_NOTIONAL_USDT", "0") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _normalizar_notional_operacional(valor: Any) -> float:
    # Aceita qualquer notional não-negativo informado pelo cliente e aplica o teto
    # operacional quando configurado (defesa contra notional acidentalmente enorme).
    notional = max(0.0, float(valor or 0.0))
    teto = _teto_notional_operacional_usdt()
    if teto > 0.0:
        notional = min(notional, teto)
    return notional


def _valor_posicao_usdt(saldo_base: float, preco_atual_usdt: float) -> float:
    return max(0.0, saldo_base) * max(0.0, preco_atual_usdt)


def _custos_ciclo_pct(ajustes_sinal: dict[str, Any], spread_rel: float) -> float:
    taxa_trade = max(0.0, float(ajustes_sinal.get("signal_trade_fee_pct", 0.0012) or 0.0))
    slippage = max(0.0, float(ajustes_sinal.get("signal_slippage_pct", 0.0005) or 0.0))
    return (taxa_trade * 2.0) + (slippage * 2.0) + max(0.0, spread_rel)


def _piso_lucro_percentual(
    ajustes_sinal: dict[str, Any],
    *,
    notional_usdt: float,
    lucro_liquido_minimo_usdt: float,
) -> float:
    notional_base = max(0.0, float(notional_usdt or 0.0))
    spread_piso = 0.0002
    multiplicador_seguranca = 1.05
    piso_pct_env = 0.0004
    custos_pct = _custos_ciclo_pct(ajustes_sinal, spread_piso)
    # `lucro_liquido_esperado_pct` ja vem liquido de custos do signal engine.
    # Aqui entra apenas uma margem operacional extra, nao o custo inteiro novamente.
    piso_por_buffer = custos_pct * max(0.0, multiplicador_seguranca - 1.0)
    piso_por_usdt = (float(lucro_liquido_minimo_usdt or 0.0) / notional_base) if notional_base > 0.0 else 0.0
    # No modo auto, o piso de lucro precisa responder ao capital e ao alvo
    # liquido real do perfil. Nao reutilizamos cegamente o override manual
    # salvo em `ajustes_sinal`, porque ele pode ficar muito alto para
    # micro-oportunidades e travar o bot inteiro.
    return max(piso_por_buffer, piso_por_usdt, piso_pct_env)


def _data_operacional() -> str:
    return time.strftime("%Y-%m-%d")
