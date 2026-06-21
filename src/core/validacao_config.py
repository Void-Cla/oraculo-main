"""Validação fail-fast de configuração — PSF-01.

O sistema deve RECUSAR-SE a iniciar com configuração crítica inválida ou ambígua,
em vez de descobrir o problema horas depois operando com dinheiro real.
"""
from __future__ import annotations

import os

from src.core.settings import env_bool


class ConfiguracaoInvalida(RuntimeError):
    """Erro de configuração crítica que impede a inicialização segura."""


# Faixa aceitável para o limite de drawdown do circuit breaker (%).
_DRAWDOWN_MIN: float = 0.0
_DRAWDOWN_MAX: float = 50.0
# Marcadores que denunciam um banco de TESTE sendo usado em modo real.
_MARCADORES_BANCO_TESTE: tuple[str, ...] = ("pytest", "tmp_pytest", "test_", "/test")


def validar_config() -> list[str]:
    """Retorna a lista de erros de configuração. Lista vazia = pode iniciar."""
    erros: list[str] = []
    modo_real = env_bool("PERMITIR_CONTA_REAL", False)
    api_key = (os.getenv("BINANCE_API_KEY", "") or "").strip()
    api_secret = (os.getenv("BINANCE_API_SECRET", "") or "").strip()

    if modo_real and not api_key:
        erros.append("CRITICO: PERMITIR_CONTA_REAL=true mas BINANCE_API_KEY ausente")
    if modo_real and not api_secret:
        erros.append("CRITICO: PERMITIR_CONTA_REAL=true mas BINANCE_API_SECRET ausente")

    db_path = (os.getenv("DB_PATH", "") or "").strip()
    if not db_path:
        erros.append("DB_PATH nao configurado")
    elif modo_real and any(m in db_path.lower() for m in _MARCADORES_BANCO_TESTE):
        erros.append("CRITICO: PERMITIR_CONTA_REAL=true mas DB_PATH aponta para banco de teste")

    bruto = os.getenv("CIRCUIT_BREAKER_DRAWDOWN_PCT", "5.0")
    try:
        limite = float(bruto)
        if not (_DRAWDOWN_MIN < limite <= _DRAWDOWN_MAX):
            erros.append(f"CIRCUIT_BREAKER_DRAWDOWN_PCT invalido: {limite} (esperado 0 < x <= 50)")
    except (TypeError, ValueError):
        erros.append(f"CIRCUIT_BREAKER_DRAWDOWN_PCT nao e numero valido: {bruto!r}")

    return erros


def exigir_config_valida() -> None:
    """Levanta ConfiguracaoInvalida se houver qualquer erro crítico. Use no startup."""
    erros = validar_config()
    if erros:
        raise ConfiguracaoInvalida("; ".join(erros))
