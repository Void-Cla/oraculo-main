"""Testes do módulo de alertas (Telegram/webhook) — fail-safe, cooldown, NO-OP sem config.

Tudo mockado — nenhuma chamada de rede real. Cobre: sem config = NO-OP silencioso; envio via
Telegram; envio via webhook; falha de rede NUNCA lança (fail-safe); cooldown evita flood do
mesmo tipo de alerta; `disparar_alerta_background` funciona dentro de um loop async e não lança
mesmo se a rede falhar.
"""
from __future__ import annotations

import pytest

from src.observabilidade import alertas


@pytest.fixture(autouse=True)
def _limpar_estado_alertas(monkeypatch):
    monkeypatch.delenv("ALERTA_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("ALERTA_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("ALERTA_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("ALERTA_COOLDOWN_SEGUNDOS", raising=False)
    alertas._resetar_estado_teste()
    yield
    alertas._resetar_estado_teste()


@pytest.mark.asyncio
async def test_sem_config_e_noop_silencioso(monkeypatch):
    chamou = {"telegram": False, "webhook": False}

    async def _fake_telegram(msg):
        chamou["telegram"] = True
        return True

    async def _fake_webhook(msg, ctx):
        chamou["webhook"] = True
        return True

    monkeypatch.setattr(alertas, "_enviar_telegram", _fake_telegram)
    monkeypatch.setattr(alertas, "_enviar_webhook", _fake_webhook)
    await alertas.disparar_alerta(chave="teste", titulo="algo")
    assert chamou == {"telegram": False, "webhook": False}


@pytest.mark.asyncio
async def test_envia_telegram_quando_configurado(monkeypatch):
    monkeypatch.setenv("ALERTA_TELEGRAM_BOT_TOKEN", "token-fake")
    monkeypatch.setenv("ALERTA_TELEGRAM_CHAT_ID", "123")
    capturado = {}

    class _RespFake:
        def raise_for_status(self):
            return None

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
    await alertas.disparar_alerta(chave="halt_teste", titulo="HALT de teste", perda_usdt=1.23)
    assert "token-fake" in capturado["url"]
    assert capturado["json"]["chat_id"] == "123"
    assert "HALT de teste" in capturado["json"]["text"]
    assert "perda_usdt=1.23" in capturado["json"]["text"]


@pytest.mark.asyncio
async def test_envia_webhook_quando_configurado(monkeypatch):
    monkeypatch.setenv("ALERTA_WEBHOOK_URL", "https://hooks.exemplo/x")
    capturado = {}

    class _RespFake:
        def raise_for_status(self):
            return None

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
    await alertas.disparar_alerta(chave="erro_teste", titulo="Erro de teste")
    assert capturado["url"] == "https://hooks.exemplo/x"
    assert "Erro de teste" in capturado["json"]["texto"]


@pytest.mark.asyncio
async def test_falha_de_rede_nunca_lanca(monkeypatch):
    monkeypatch.setenv("ALERTA_TELEGRAM_BOT_TOKEN", "token-fake")
    monkeypatch.setenv("ALERTA_TELEGRAM_CHAT_ID", "123")

    class _ClienteFakeQuebrado:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            raise RuntimeError("rede caiu")

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _ClienteFakeQuebrado)
    # Não deve lançar — fail-safe absoluto.
    await alertas.disparar_alerta(chave="x", titulo="y")


@pytest.mark.asyncio
async def test_cooldown_evita_flood_do_mesmo_tipo(monkeypatch):
    monkeypatch.setenv("ALERTA_WEBHOOK_URL", "https://hooks.exemplo/x")
    monkeypatch.setenv("ALERTA_COOLDOWN_SEGUNDOS", "300")
    chamadas = []

    class _RespFake:
        def raise_for_status(self):
            return None

    class _ClienteFake:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            chamadas.append(json)
            return _RespFake()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _ClienteFake)
    await alertas.disparar_alerta(chave="mesma_chave", titulo="1a vez")
    await alertas.disparar_alerta(chave="mesma_chave", titulo="2a vez (deve ser suprimida)")
    assert len(chamadas) == 1

    # Chave DIFERENTE não é afetada pelo cooldown da outra.
    await alertas.disparar_alerta(chave="outra_chave", titulo="chave diferente")
    assert len(chamadas) == 2


@pytest.mark.asyncio
async def test_disparar_alerta_background_nao_lanca_e_dispara(monkeypatch):
    monkeypatch.setenv("ALERTA_WEBHOOK_URL", "https://hooks.exemplo/x")
    chamadas = []

    class _RespFake:
        def raise_for_status(self):
            return None

    class _ClienteFake:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            chamadas.append(json)
            return _RespFake()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _ClienteFake)
    alertas.disparar_alerta_background(chave="bg", titulo="background")
    # A task foi agendada no loop corrente — cede o controle p/ ela rodar.
    import asyncio

    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(chamadas) == 1


def test_disparar_alerta_background_sem_loop_ativo_nao_lanca():
    # Fora de contexto async (sem loop rodando) — deve apenas logar aviso, nunca lançar.
    alertas.disparar_alerta_background(chave="sem_loop", titulo="sem loop ativo")
