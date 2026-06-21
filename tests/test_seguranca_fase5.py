"""FASE 5 — segurança financeira multicamada: idempotência, circuit breaker, fail-fast."""
from __future__ import annotations

import os

import pytest

from src.core.validacao_config import ConfiguracaoInvalida, exigir_config_valida, validar_config
from src.executor.circuit_breaker import CircuitBreaker
from src.executor.idempotencia import gerar_client_order_id


# ── Idempotência (PSF-03) ───────────────────────────────────────────────────
def test_mesma_intencao_gera_mesmo_client_order_id():
    a = gerar_client_order_id(simbolo="BTCUSDT", lado="BUY", notional=12.5, chave_intencao=1001)
    b = gerar_client_order_id(simbolo="btcusdt", lado="buy", notional=12.5, chave_intencao=1001)
    assert a == b  # mesma intenção (case-insensitive) → mesmo ID


def test_intencoes_diferentes_geram_ids_diferentes():
    a = gerar_client_order_id(simbolo="BTCUSDT", lado="BUY", notional=12.5, chave_intencao=1001)
    b = gerar_client_order_id(simbolo="BTCUSDT", lado="SELL", notional=12.5, chave_intencao=1001)
    c = gerar_client_order_id(simbolo="BTCUSDT", lado="BUY", notional=12.5, chave_intencao=1002)
    assert a != b and a != c


def test_client_order_id_respeita_limite_binance_36_chars():
    coid = gerar_client_order_id(simbolo="BTCUSDT", lado="BUY", notional=999999.9, chave_intencao="x" * 200)
    assert 0 < len(coid) <= 36
    assert coid.isalnum()  # charset seguro


# ── Circuit breaker (PSF-04 / DA-03) ────────────────────────────────────────
def test_halt_ativa_ao_exceder_drawdown():
    cb = CircuitBreaker(limite_drawdown_pct=5.0, janela_horas=24)
    assert cb.esta_em_halt() is False
    # Perda de 60 sobre capital 1000 = 6% > 5% → halt.
    cb.registrar_resultado(pnl_usdt=-60.0, capital_total=1000.0)
    assert cb.esta_em_halt() is True
    assert cb.estado()["motivo"] == "drawdown_excedeu_limite"


def test_halt_nao_reseta_automaticamente_em_novos_resultados():
    cb = CircuitBreaker(limite_drawdown_pct=5.0)
    cb.registrar_resultado(pnl_usdt=-60.0, capital_total=1000.0)
    assert cb.esta_em_halt() is True
    # Mesmo com lucro posterior, NÃO se reseta sozinho.
    cb.registrar_resultado(pnl_usdt=+500.0, capital_total=1000.0)
    assert cb.esta_em_halt() is True


def test_reset_exige_autorizacao_humana_explicita():
    cb = CircuitBreaker(limite_drawdown_pct=5.0)
    cb.registrar_resultado(pnl_usdt=-100.0, capital_total=1000.0)
    with pytest.raises(ValueError):
        cb.resetar_halt(autorizado_por="")
    estado = cb.resetar_halt(autorizado_por="operador_humano")
    assert estado["em_halt"] is False
    assert cb.esta_em_halt() is False


@pytest.mark.asyncio
async def test_halt_persiste_entre_instancias(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "cb.sqlite")
    from src.persistencia.conexao import inicializar_db

    inicializar_db()
    cb = CircuitBreaker(limite_drawdown_pct=5.0)
    cb.registrar_resultado(pnl_usdt=-100.0, capital_total=1000.0)
    await cb.salvar()

    # Nova instância (simula restart do processo) deve recuperar o halt.
    cb2 = CircuitBreaker(limite_drawdown_pct=5.0)
    await cb2.carregar()
    assert cb2.esta_em_halt() is True


# ── Validação fail-fast (PSF-01) ────────────────────────────────────────────
def test_config_valida_em_modo_paper(monkeypatch):
    monkeypatch.setenv("PERMITIR_CONTA_REAL", "false")
    monkeypatch.setenv("DB_PATH", "./dados/oraculo.sqlite")
    monkeypatch.setenv("CIRCUIT_BREAKER_DRAWDOWN_PCT", "5.0")
    assert validar_config() == []


def test_config_invalida_conta_real_sem_chave(monkeypatch):
    monkeypatch.setenv("PERMITIR_CONTA_REAL", "true")
    monkeypatch.setenv("BINANCE_API_KEY", "")
    monkeypatch.setenv("BINANCE_API_SECRET", "")
    monkeypatch.setenv("DB_PATH", "./dados/prod.sqlite")
    erros = validar_config()
    assert any("BINANCE_API_KEY" in e for e in erros)
    with pytest.raises(ConfiguracaoInvalida):
        exigir_config_valida()


def test_config_invalida_drawdown_fora_da_faixa(monkeypatch):
    monkeypatch.setenv("PERMITIR_CONTA_REAL", "false")
    monkeypatch.setenv("DB_PATH", "./dados/oraculo.sqlite")
    monkeypatch.setenv("CIRCUIT_BREAKER_DRAWDOWN_PCT", "999")
    assert any("CIRCUIT_BREAKER_DRAWDOWN_PCT" in e for e in validar_config())
