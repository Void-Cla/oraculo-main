"""Blindagem AA+ (blueprint botai.md) — kill-switch, integridade de modelo, whitelist SQL,
path-traversal. Trava propriedades de segurança contra regressão.
"""
import os

import pytest
from fastapi.testclient import TestClient


def _isolar_ia_e_background(monkeypatch):
    """Remove credenciais locais e tarefas externas para teste unitario da API."""
    nomes = [
        "NVIDIA_API_KEYS",
        "NVIDIA_API_KEY",
        "Nvidia_API_Key",
        "Nvidia_API_KEY",
        "NVAPI_KEY",
        "GEMINI_API_KEYS",
        "GEMINI_API_KEY",
        "GPT_API_KEY",
        "OPENAI_API_KEY",
        "CLAUDE_API_KEY",
        "ANTHROPIC_API_KEY",
    ]
    nomes.extend(f"GEMINI_API_KEY_{indice}" for indice in range(1, 21))
    nomes.extend(f"NVIDIA_API_KEY_{indice}" for indice in range(1, 21))
    for nome in nomes:
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("ATIVAR_CONSUMIDOR_SINAIS", "false")
    monkeypatch.setenv("ATIVAR_COLETA_CONTINUA", "false")
    monkeypatch.setenv("AI_AUDITOR_ENABLED", "false")


# ── A1: Kill-switch financeiro ───────────────────────────────────────────────
def _limpar_kill(monkeypatch, tmp_path):
    monkeypatch.setenv("KILL_SWITCH_PATH", str(tmp_path / "KILL_SWITCH"))


def test_kill_switch_engatar_e_destravar(monkeypatch, tmp_path):
    _limpar_kill(monkeypatch, tmp_path)
    from src.core import kill_switch

    assert kill_switch.esta_engatado() is False
    kill_switch.engatar("teste")
    assert kill_switch.esta_engatado() is True
    assert kill_switch.estado()["engatado"] is True
    assert kill_switch.destravar() is True
    assert kill_switch.esta_engatado() is False


def test_kill_switch_bloqueia_ordem(monkeypatch, tmp_path):
    _limpar_kill(monkeypatch, tmp_path)
    from src.core import kill_switch

    kill_switch.engatar("panico")
    with pytest.raises(kill_switch.KillSwitchEngatadoError):
        kill_switch.exigir_desengatado(simbolo="BTCUSDT", lado="BUY")


@pytest.mark.asyncio
async def test_kill_switch_bloqueia_create_order_no_gerenciador(monkeypatch, tmp_path):
    _limpar_kill(monkeypatch, tmp_path)
    from src.core import kill_switch
    from src.executor.gerenciador_ordens import GerenciadorOrdens

    kill_switch.engatar("panico_total")
    ger = GerenciadorOrdens(api_key="x", api_secret="y", testnet=True)
    with pytest.raises(kill_switch.KillSwitchEngatadoError):
        await ger.criar_ordem_market("BTCUSDT", "BUY", quote_order_qty=10.0)
    with pytest.raises(kill_switch.KillSwitchEngatadoError):
        await ger.criar_ordem_limit("BTCUSDT", "BUY", quantidade=0.001, preco=60000.0)


# ── A3: Whitelist de DDL dinâmica (anti SQL injection) ───────────────────────
def test_whitelist_ddl_recusa_tabela_fora(tmp_path):
    from src.persistencia.conexao import _validar_identificador_tabela

    assert _validar_identificador_tabela("ordens") == "ordens"
    with pytest.raises(ValueError):
        _validar_identificador_tabela("ordens; DROP TABLE usuarios")
    with pytest.raises(ValueError):
        _validar_identificador_tabela("tabela_inexistente")


def test_schema_evolutivo_idempotente(tmp_path):
    # inicializar_db roda o schema evolutivo (que usa _garantir_coluna nas tabelas da whitelist).
    os.environ["DB_PATH"] = str(tmp_path / "ddl.sqlite")
    from src.persistencia.conexao import inicializar_db

    inicializar_db()
    inicializar_db()  # 2ª vez não pode falhar (idempotência)


# ── A4: Integridade de modelo (HMAC anti-RCE) ────────────────────────────────
def test_integridade_desligada_sem_chave(monkeypatch, tmp_path):
    monkeypatch.delenv("MODELO_HMAC_KEY", raising=False)
    import joblib

    from src.core.integridade_modelo import carregar_joblib_verificado, verificacao_ativa

    assert verificacao_ativa() is False
    artefato = tmp_path / "m.joblib"
    joblib.dump({"x": 1}, artefato)
    # Sem chave → carrega normalmente (comportamento legado).
    assert carregar_joblib_verificado(artefato)["x"] == 1


def test_integridade_assina_e_verifica(monkeypatch, tmp_path):
    monkeypatch.setenv("MODELO_HMAC_KEY", "chave-secreta-de-teste")
    import joblib

    from src.core.integridade_modelo import (
        assinar_artefato,
        carregar_joblib_verificado,
        verificar_artefato,
    )

    artefato = tmp_path / "m.joblib"
    joblib.dump({"x": 42}, artefato)
    assinar_artefato(artefato)
    assert verificar_artefato(artefato) is True
    assert carregar_joblib_verificado(artefato)["x"] == 42


def test_integridade_recusa_sem_assinatura_com_chave(monkeypatch, tmp_path):
    monkeypatch.setenv("MODELO_HMAC_KEY", "chave-secreta-de-teste")
    import joblib

    from src.core.integridade_modelo import IntegridadeModeloError, carregar_joblib_verificado

    artefato = tmp_path / "sem_sig.joblib"
    joblib.dump({"x": 1}, artefato)  # sem assinar
    with pytest.raises(IntegridadeModeloError):
        carregar_joblib_verificado(artefato)


def test_integridade_recusa_artefato_adulterado(monkeypatch, tmp_path):
    monkeypatch.setenv("MODELO_HMAC_KEY", "chave-secreta-de-teste")
    import joblib

    from src.core.integridade_modelo import assinar_artefato, verificar_artefato

    artefato = tmp_path / "m.joblib"
    joblib.dump({"x": 1}, artefato)
    assinar_artefato(artefato)
    joblib.dump({"x": 999, "payload_malicioso": True}, artefato)  # adultera após assinar
    assert verificar_artefato(artefato) is False


# ── A2: Path traversal em /v1/img ────────────────────────────────────────────
def test_img_path_traversal_bloqueado(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "img.sqlite")
    from src.main import app

    with TestClient(app) as client:
        # Tentativa de escapar do diretório frontend/img.
        resp = client.get("/img/..%2f..%2f..%2f.env")
        assert resp.status_code in (403, 404)
        resp2 = client.get("/img/inexistente.png")
        assert resp2.status_code == 404


# ── Endpoints operacionais novos ─────────────────────────────────────────────
def test_endpoint_kill_switch_status(tmp_path, monkeypatch):
    monkeypatch.setenv("KILL_SWITCH_PATH", str(tmp_path / "KILL_SWITCH"))
    os.environ["DB_PATH"] = str(tmp_path / "ks.sqlite")
    from src.main import app

    with TestClient(app) as client:
        resp = client.get("/v1/kill-switch")
        assert resp.status_code == 200
        assert resp.json()["engatado"] is False


def test_endpoint_gemini_saude_desativado_sem_chave(tmp_path, monkeypatch):
    _isolar_ia_e_background(monkeypatch)
    # Saúde específica do Gemini: nenhum fallback de outro provedor pode mascarar ausência de chave.
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    os.environ["DB_PATH"] = str(tmp_path / "g.sqlite")
    from src.main import app

    with TestClient(app) as client:
        resp = client.get("/v1/ai/gemini/saude")
        assert resp.status_code == 200
        assert resp.json()["disponivel"] is False


# ── D: hardening de produção (COOKIE_SECURE) ─────────────────────────────────
def test_validacao_producao_exige_cookie_secure(monkeypatch, tmp_path):
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "prod.sqlite"))
    monkeypatch.delenv("PERMITIR_CONTA_REAL", raising=False)
    from src.core.validacao_config import validar_config

    erros = validar_config()
    assert any("COOKIE_SECURE" in e for e in erros)
