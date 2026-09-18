"""Testes do OllamaClient (LLM local, 4º provedor plugável) + factory.

Tudo MOCKADO — nenhuma chamada de rede real (nem local). Replica o padrão de
`test_intelligence_provedores.py` (GPT/Claude): parseia resposta, JSON inválido é fail-safe,
exceção/timeout é fail-safe, e a diferença estrutural do Ollama (sem API key — disponível por
padrão assim que escolhido via AI_PROVIDER, servidor local fora do ar cai no MESMO fail-open).
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_ollama_disponivel_por_padrao_sem_chave(monkeypatch):
    # Ollama não usa API key — ao contrário de gemini/gpt/claude, não precisa de credencial
    # para ficar "disponível" (o opt-in é escolher AI_PROVIDER=ollama).
    from src.intelligence.ollama_client import OllamaClient

    cli = OllamaClient()
    assert cli.disponivel() is True
    assert cli.health()["chave_presente"] is True
    assert cli.health()["provedor"] == "ollama"


@pytest.mark.asyncio
async def test_ollama_usa_url_e_modelo_padrao(monkeypatch):
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    from src.intelligence.ollama_client import OllamaClient

    cli = OllamaClient()
    assert cli._url_base == "http://127.0.0.1:11434"
    assert cli.health()["modelo"] == "qwen2.5:7b-instruct"


@pytest.mark.asyncio
async def test_ollama_respeita_env_de_url_e_modelo(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://minha-maquina:11500/")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1:8b")
    from src.intelligence.ollama_client import OllamaClient

    cli = OllamaClient()
    assert cli._url_base == "http://minha-maquina:11500"  # rstrip da barra final
    assert cli.health()["modelo"] == "llama3.1:8b"


@pytest.mark.asyncio
async def test_ollama_parseia_resposta(monkeypatch):
    from src.intelligence.ollama_client import OllamaClient

    cli = OllamaClient()

    async def _fake(system_prompt, user_context, temperature):
        return '{"action": "PROCEED", "confidence_score": 0.4}'

    monkeypatch.setattr(cli, "_executar_chamada", _fake)
    r = await cli.analisar("sys", "ctx")
    assert r["action"] == "PROCEED"
    assert cli.health()["chamadas_dia"] == 1


@pytest.mark.asyncio
async def test_ollama_json_invalido_fail_safe(monkeypatch):
    from src.intelligence.ollama_client import OllamaClient

    cli = OllamaClient()

    async def _lixo(system_prompt, user_context, temperature):
        return "isto nao eh json {{{"

    monkeypatch.setattr(cli, "_executar_chamada", _lixo)
    assert await cli.analisar("sys", "ctx") is None
    assert cli.health()["falhas_consecutivas"] == 1


@pytest.mark.asyncio
async def test_ollama_fail_open_servidor_fora_do_ar(monkeypatch):
    """Simula o cenário central do desenho: servidor Ollama não está rodando (connection
    refused). Deve cair no MESMO fail-open de qualquer provedor — nunca lançar, nunca travar."""
    from src.intelligence.ollama_client import OllamaClient

    cli = OllamaClient()

    async def _boom(system_prompt, user_context, temperature):
        raise ConnectionRefusedError("servidor ollama nao esta rodando")

    monkeypatch.setattr(cli, "_executar_chamada", _boom)
    assert await cli.analisar("sys", "ctx") is None
    assert cli.health()["falhas_consecutivas"] == 1


@pytest.mark.asyncio
async def test_ollama_timeout_fail_safe(monkeypatch):
    from src.intelligence.ollama_client import OllamaClient

    cli = OllamaClient()
    cli._timeout = 0.05

    async def _lento(system_prompt, user_context, temperature):
        await asyncio.sleep(0.2)
        return '{"action": "PROCEED"}'

    monkeypatch.setattr(cli, "_executar_chamada", _lento)
    assert await cli.analisar("sys", "ctx") is None


@pytest.mark.asyncio
async def test_ollama_payload_chat_formato_json_e_papeis(monkeypatch):
    from src.intelligence.ollama_client import OllamaClient

    cli = OllamaClient(url_base="http://localhost:11434", modelo="qwen2.5:7b-instruct")
    capturado = {}

    class _RespFake:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": '{"action": "PROCEED"}'}}

    class _ClienteFake:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            capturado["url"] = url
            capturado["json"] = json
            return _RespFake()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _ClienteFake)
    r = await cli.analisar("sys", "ctx", temperature=0.3)
    assert r == {"action": "PROCEED"}
    assert capturado["url"] == "http://localhost:11434/api/chat"
    assert capturado["json"]["format"] == "json"
    assert capturado["json"]["stream"] is False
    papeis = [m["role"] for m in capturado["json"]["messages"]]
    assert papeis == ["system", "user"]
    assert capturado["json"]["options"]["temperature"] == pytest.approx(0.3)
    # Sem chave nenhuma vazando na URL/payload (Ollama não tem chave, mas o contrato geral vale).
    assert "sem_chave" not in capturado["url"]


# ── Factory: AI_PROVIDER=ollama ──────────────────────────────────────────────
def test_factory_ollama_ativa_sem_precisar_de_chave(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    from src.intelligence.ollama_client import OllamaClient
    from src.intelligence.provedor_ia import criar_provedor_ia

    prov = criar_provedor_ia()
    assert isinstance(prov, OllamaClient)
    assert prov.health()["provedor"] == "ollama"


def test_factory_ollama_case_insensitive(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "OLLAMA")
    from src.intelligence.ollama_client import OllamaClient
    from src.intelligence.provedor_ia import criar_provedor_ia

    assert isinstance(criar_provedor_ia(), OllamaClient)


def test_ollama_e_instancia_de_provedor_ia():
    from src.intelligence.ollama_client import OllamaClient
    from src.intelligence.provedor_ia import ProvedorIA

    assert isinstance(OllamaClient(), ProvedorIA)
