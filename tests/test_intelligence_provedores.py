"""Provedores de IA plugáveis (gemini|gpt|claude) + factory `criar_provedor_ia`.

Tudo MOCKADO — nenhuma chamada de rede real. Replica o padrão de `test_intelligence_gemini.py`:
monkeypatch de `_executar_chamada`/`_chamar_api` retornando um JSON string, verificando que
`analisar` parseia, que sem-chave ⇒ `disponivel()=False`/`analisar()=None`, que JSON inválido ⇒
None (fail-safe) e que timeout ⇒ None. Cobre GPTClient, ClaudeClient e a factory.
"""
import asyncio

import pytest


@pytest.fixture(autouse=True)
def _isolar_credenciais_de_provedor(monkeypatch):
    """Evita que chaves locais do `.env` alterem as expectativas dos testes mockados."""
    nomes = [
        "AI_PROVIDER",
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


# ── NVIDIA Client ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nvidia_sem_chave_retorna_none(monkeypatch):
    for nome in ("NVIDIA_API_KEY", "Nvidia_API_Key", "Nvidia_API_KEY", "NVAPI_KEY"):
        monkeypatch.delenv(nome, raising=False)
    from src.intelligence.nvidia_client import NvidiaClient

    cli = NvidiaClient(api_key="")
    assert cli.disponivel() is False
    assert await cli.analisar("sys", "ctx") is None


@pytest.mark.asyncio
async def test_nvidia_parseia_resposta(monkeypatch):
    from src.intelligence.nvidia_client import NvidiaClient

    cli = NvidiaClient(api_key="fake-key")

    async def _fake(system_prompt, user_context, temperature):
        return '{"action": "PROCEED", "confidence_score": 0.2}'

    monkeypatch.setattr(cli, "_executar_chamada", _fake)
    r = await cli.analisar("sys", "ctx")
    assert r["action"] == "PROCEED"
    assert cli.health()["provedor"] == "nvidia"


@pytest.mark.asyncio
async def test_nvidia_aceita_nvidia_api_key_variante(monkeypatch):
    for nome in ("NVIDIA_API_KEY", "Nvidia_API_Key", "Nvidia_API_KEY", "NVAPI_KEY"):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("Nvidia_API_Key", "chave-nvidia")
    from src.intelligence.nvidia_client import NvidiaClient

    cli = NvidiaClient()
    assert cli.disponivel() is True


# ── GPTClient ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_gpt_sem_chave_retorna_none(monkeypatch):
    monkeypatch.delenv("GPT_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from src.intelligence.gpt_client import GPTClient

    cli = GPTClient(api_key="")
    assert cli.disponivel() is False
    assert await cli.analisar("sys", "ctx") is None


@pytest.mark.asyncio
async def test_gpt_parseia_resposta(monkeypatch):
    from src.intelligence.gpt_client import GPTClient

    cli = GPTClient(api_key="fake-key")

    async def _fake(system_prompt, user_context, temperature):
        return '{"action": "PROCEED", "confidence_score": 0.2}'

    monkeypatch.setattr(cli, "_executar_chamada", _fake)
    r = await cli.analisar("sys", "ctx")
    assert r["action"] == "PROCEED"
    assert cli.health()["chamadas_dia"] == 1
    assert cli.health()["provedor"] == "gpt"


@pytest.mark.asyncio
async def test_gpt_json_invalido_fail_safe(monkeypatch):
    from src.intelligence.gpt_client import GPTClient

    cli = GPTClient(api_key="fake-key")

    async def _lixo(system_prompt, user_context, temperature):
        return "isto nao eh json {{{"

    monkeypatch.setattr(cli, "_executar_chamada", _lixo)
    assert await cli.analisar("sys", "ctx") is None
    assert cli.health()["falhas_consecutivas"] == 1


@pytest.mark.asyncio
async def test_gpt_fail_open_em_excecao(monkeypatch):
    from src.intelligence.gpt_client import GPTClient

    cli = GPTClient(api_key="fake-key")

    async def _boom(system_prompt, user_context, temperature):
        raise RuntimeError("rede caiu")

    monkeypatch.setattr(cli, "_executar_chamada", _boom)
    assert await cli.analisar("sys", "ctx") is None  # nunca lança
    assert cli.health()["falhas_consecutivas"] == 1


@pytest.mark.asyncio
async def test_gpt_timeout_fail_safe(monkeypatch):
    from src.intelligence.gpt_client import GPTClient

    cli = GPTClient(api_key="fake-key")
    # O timeout interno da base tem piso de 1.0s (env clamp); aqui forçamos um valor curto
    # direto no atributo lido por `asyncio.wait_for`, para testar o caminho de timeout sem espera.
    cli._timeout = 0.05

    async def _lento(system_prompt, user_context, temperature):
        await asyncio.sleep(0.2)
        return '{"action": "PROCEED"}'

    monkeypatch.setattr(cli, "_executar_chamada", _lento)
    assert await cli.analisar("sys", "ctx") is None
    assert cli.health()["falhas_consecutivas"] == 1


@pytest.mark.asyncio
async def test_gpt_aceita_openai_api_key(monkeypatch):
    # Retrocompat: se GPT_API_KEY ausente mas OPENAI_API_KEY presente, o cliente ativa.
    monkeypatch.delenv("GPT_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "chave-openai")
    from src.intelligence.gpt_client import GPTClient

    cli = GPTClient()
    assert cli.disponivel() is True
    assert cli.health()["provedor"] == "gpt"


# ── ClaudeClient ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_claude_sem_chave_retorna_none(monkeypatch):
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from src.intelligence.claude_client import ClaudeClient

    cli = ClaudeClient(api_key="")
    assert cli.disponivel() is False
    assert await cli.analisar("sys", "ctx") is None


@pytest.mark.asyncio
async def test_claude_parseia_resposta(monkeypatch):
    from src.intelligence.claude_client import ClaudeClient

    cli = ClaudeClient(api_key="fake-key")

    async def _fake(system_prompt, user_context, temperature):
        return '{"action": "ABORT", "confidence_score": 0.9}'

    monkeypatch.setattr(cli, "_executar_chamada", _fake)
    r = await cli.analisar("sys", "ctx")
    assert r["action"] == "ABORT"
    assert cli.health()["provedor"] == "claude"
    assert cli.health()["modelo"] == "claude-haiku-4-5"  # default barato p/ JSON


@pytest.mark.asyncio
async def test_claude_json_invalido_fail_safe(monkeypatch):
    from src.intelligence.claude_client import ClaudeClient

    cli = ClaudeClient(api_key="fake-key")

    async def _lixo(system_prompt, user_context, temperature):
        return "nao eh json"

    monkeypatch.setattr(cli, "_executar_chamada", _lixo)
    assert await cli.analisar("sys", "ctx") is None


@pytest.mark.asyncio
async def test_claude_timeout_fail_safe(monkeypatch):
    from src.intelligence.claude_client import ClaudeClient

    cli = ClaudeClient(api_key="fake-key")
    cli._timeout = 0.05  # piso de 1.0s na base; forçamos curto p/ testar o caminho de timeout

    async def _lento(system_prompt, user_context, temperature):
        await asyncio.sleep(0.2)
        return '{"action": "PROCEED"}'

    monkeypatch.setattr(cli, "_executar_chamada", _lento)
    assert await cli.analisar("sys", "ctx") is None


@pytest.mark.asyncio
async def test_claude_nao_envia_temperature_no_payload(monkeypatch):
    """Regressão de API: modelos novos da Anthropic rejeitam `temperature` (HTTP 400). O
    payload montado por `_executar_chamada` NÃO pode conter o campo `temperature`."""
    from src.intelligence.claude_client import ClaudeClient

    cli = ClaudeClient(api_key="fake-key")
    capturado = {}

    class _RespFake:
        def raise_for_status(self):
            return None

        def json(self):
            return {"content": [{"type": "text", "text": '{"action": "PROCEED"}'}]}

    class _ClienteFake:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            capturado["url"] = url
            capturado["headers"] = headers
            capturado["json"] = json
            return _RespFake()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _ClienteFake)
    r = await cli.analisar("sys", "ctx", temperature=0.7)
    assert r == {"action": "PROCEED"}
    assert "temperature" not in capturado["json"]  # NÃO enviado ao Claude
    assert "top_p" not in capturado["json"]
    assert capturado["json"]["system"] == "sys"
    assert capturado["json"]["messages"] == [{"role": "user", "content": "ctx"}]
    # Chave no header x-api-key, nunca na URL.
    assert capturado["headers"]["x-api-key"] == "fake-key"
    assert "fake-key" not in capturado["url"]


@pytest.mark.asyncio
async def test_gpt_envia_temperature_e_system_user(monkeypatch):
    """OpenAI ACEITA temperature e usa mensagens por papel (system+user). Verifica o payload."""
    from src.intelligence.gpt_client import GPTClient

    cli = GPTClient(api_key="fake-key")
    capturado = {}

    class _RespFake:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"action": "PROCEED"}'}}]}

    class _ClienteFake:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            capturado["headers"] = headers
            capturado["json"] = json
            return _RespFake()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _ClienteFake)
    r = await cli.analisar("sys", "ctx", temperature=0.3)
    assert r == {"action": "PROCEED"}
    assert capturado["json"]["temperature"] == pytest.approx(0.3)  # repassado
    papeis = [m["role"] for m in capturado["json"]["messages"]]
    assert papeis == ["system", "user"]
    assert capturado["headers"]["Authorization"] == "Bearer fake-key"


# ── criar_provedor_ia (factory) ──────────────────────────────────────────────
def test_factory_default_e_nvidia(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "chave-nvidia")
    from src.intelligence.nvidia_client import NvidiaClient
    from src.intelligence.provedor_ia import criar_provedor_ia

    prov = criar_provedor_ia()
    assert isinstance(prov, NvidiaClient)
    assert prov.health()["provedor"] == "nvidia"


def test_factory_nvidia_sem_chave_retorna_none(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    for nome in ("NVIDIA_API_KEY", "Nvidia_API_Key", "Nvidia_API_KEY", "NVAPI_KEY"):
        monkeypatch.delenv(nome, raising=False)
    from src.intelligence.provedor_ia import criar_provedor_ia

    assert criar_provedor_ia() is None


def test_factory_faz_fallback_de_nvidia_para_gemini(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    monkeypatch.setenv("GEMINI_API_KEY", "chave-gemini")
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.provedor_ia import criar_provedor_ia

    prov = criar_provedor_ia()

    assert isinstance(prov, GeminiClient)


def test_factory_gemini_com_chave(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "chave-gemini")
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    for indice in range(1, 21):
        monkeypatch.delenv(f"GEMINI_API_KEY_{indice}", raising=False)
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.provedor_ia import criar_provedor_ia

    prov = criar_provedor_ia()
    assert isinstance(prov, GeminiClient)
    assert prov.health()["provedor"] == "gemini"


def test_factory_gpt_sem_chave_retorna_none(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gpt")
    monkeypatch.delenv("GPT_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from src.intelligence.provedor_ia import criar_provedor_ia

    assert criar_provedor_ia() is None


def test_factory_claude_com_chave(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "claude")
    monkeypatch.setenv("CLAUDE_API_KEY", "chave-claude")
    from src.intelligence.claude_client import ClaudeClient
    from src.intelligence.provedor_ia import criar_provedor_ia

    prov = criar_provedor_ia()
    assert isinstance(prov, ClaudeClient)
    assert prov.health()["provedor"] == "claude"


def test_factory_gpt_com_chave(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "GPT")  # case-insensitive
    monkeypatch.setenv("GPT_API_KEY", "chave-gpt")
    from src.intelligence.gpt_client import GPTClient
    from src.intelligence.provedor_ia import criar_provedor_ia

    prov = criar_provedor_ia()
    assert isinstance(prov, GPTClient)
    assert prov.health()["provedor"] == "gpt"


def test_factory_gemini_multiplas_chaves_cria_rotacao(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEYS", "chave-um,chave-dois")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    for indice in range(1, 21):
        monkeypatch.delenv(f"GEMINI_API_KEY_{indice}", raising=False)
    from src.intelligence.provedor_ia import ProvedorIARotativo, criar_provedor_ia

    prov = criar_provedor_ia()

    assert isinstance(prov, ProvedorIARotativo)
    assert prov.health()["chaves_configuradas"] == 2


@pytest.mark.asyncio
async def test_rotacao_avanca_apos_falha_sem_repetir_a_mesma_chave():
    from src.intelligence.provedor_ia import ProvedorIARotativo

    class ProvedorFake:
        def __init__(self, resultado):
            self.resultado = resultado
            self.chamadas = 0

        async def analisar(self, *_args, **_kwargs):
            self.chamadas += 1
            return self.resultado

        def disponivel(self):
            return True

        def health(self):
            return {"chave_presente": True, "chamadas_dia": self.chamadas, "chamadas_hora": self.chamadas}

    primeiro = ProvedorFake(None)
    segundo = ProvedorFake({"action": "BUY"})
    rotativo = ProvedorIARotativo([primeiro, segundo])

    assert await rotativo.analisar("sys", "ctx") == {"action": "BUY"}
    assert primeiro.chamadas == 1
    assert segundo.chamadas == 1


def test_factory_nvidia_multiplas_chaves_cria_rotacao(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEYS", "chave-um,chave-dois")
    for nome in ("NVIDIA_API_KEY", "Nvidia_API_Key", "Nvidia_API_KEY", "NVAPI_KEY"):
        monkeypatch.delenv(nome, raising=False)
    from src.intelligence.provedor_ia import ProvedorIARotativo, criar_provedor_ia

    prov = criar_provedor_ia()

    assert isinstance(prov, ProvedorIARotativo)
    assert prov.health()["chaves_configuradas"] == 2


def test_factory_valor_invalido_cai_no_nvidia(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "provedor_inexistente_123")
    monkeypatch.setenv("NVIDIA_API_KEY", "chave-nvidia")
    from src.intelligence.nvidia_client import NvidiaClient
    from src.intelligence.provedor_ia import criar_provedor_ia

    prov = criar_provedor_ia()
    assert isinstance(prov, NvidiaClient)  # valor inválido → default nvidia


def test_factory_gemini_sem_chave_retorna_none(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    for indice in range(1, 21):
        monkeypatch.delenv(f"GEMINI_API_KEY_{indice}", raising=False)
    from src.intelligence.provedor_ia import criar_provedor_ia

    assert criar_provedor_ia() is None


# ── Protocol: os clientes concretos satisfazem ProvedorIA ────────────────────
def test_clientes_sao_instancias_de_provedor_ia(monkeypatch):
    from src.intelligence.claude_client import ClaudeClient
    from src.intelligence.gemini_client import GeminiClient
    from src.intelligence.gpt_client import GPTClient
    from src.intelligence.nvidia_client import NvidiaClient
    from src.intelligence.provedor_ia import ProvedorIA

    # runtime_checkable Protocol: verifica presença dos métodos analisar/disponivel/health.
    assert isinstance(GeminiClient(api_key="k"), ProvedorIA)
    assert isinstance(GPTClient(api_key="k"), ProvedorIA)
    assert isinstance(ClaudeClient(api_key="k"), ProvedorIA)
    assert isinstance(NvidiaClient(api_key="k"), ProvedorIA)
