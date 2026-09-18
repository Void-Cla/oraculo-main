from __future__ import annotations
from typing import Any
import time

# Guardrails de segurança (Hard Limits que a autonomia nao pode quebrar)
GUARDRAILS = {
    "min_lucro_liquido_pct": 0.0001,
    "max_cooldown_minutos": 5,
    "min_cooldown_segundos": 5,
}

def governar_risco_autonomo(estado_execucao: dict[str, Any], risk_cfg: dict[str, Any]) -> dict[str, Any]:
    """
    Analisa o estado do bot e ajusta o risk_cfg automaticamente.
    """
    if not risk_cfg.get("autonomia_ativa", False):
        return risk_cfg

    nova_cfg = risk_cfg.copy()

    # Exemplo: Monitorar rejeicoes frequentes por 'lucro_liquido_usdt_abaixo_do_minimo'
    # Se rejeitou muito, relaxa o filtro de lucro minimo
    rejeicoes = estado_execucao.get("rejeicoes_recentes", [])
    if len([r for r in rejeicoes if "lucro_liquido_usdt_abaixo_do_minimo" in r]) > 3:
        nova_cfg["lucro_liquido_minimo_usdt"] = max(GUARDRAILS["min_lucro_liquido_pct"], nova_cfg.get("lucro_liquido_minimo_usdt", 0.01) * 0.9)
        nova_cfg["performance_mode"] = True

    # Se o drawdown diario estiver subindo rápido, endurece o risco
    drawdown_diario = float(estado_execucao.get("drawdown_diario", 0.0))
    if drawdown_diario > 0.015: # > 1.5% drawdown
        nova_cfg["performance_mode"] = False
        nova_cfg["risk_per_trade"] = max(0.001, nova_cfg.get("risk_per_trade", 0.005) * 0.8)

    return nova_cfg
