import json

from fastapi.testclient import TestClient

from src.main import app


class _ClienteBinanceFalso:
    def __init__(self, **_kwargs):
        pass

    async def obter_conta_raw(self):
        return {"accountType": "SPOT", "uid": 1}

    async def fechar(self):
        return None


def test_status_chaves_ia_exige_sessao_autenticada():
    with TestClient(app) as client:
        resposta = client.get("/v1/sessao/ia/chaves")

    assert resposta.status_code == 401


def test_status_chaves_ia_nao_vaza_segredo_nem_aceita_escrita(monkeypatch):
    segredo = "segredo-externo-que-nunca-pode-sair"
    for variavel in (
        "CLAUDE_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GEMINI_API_KEYS",
        "GPT_API_KEY",
        "OPENAI_API_KEY",
        "NVIDIA_API_KEY",
        "NVIDIA_API_KEYS",
        "NVAPI_KEY",
    ):
        monkeypatch.delenv(variavel, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", segredo)
    monkeypatch.setattr("src.servicos.sessoes.ClienteBinance", _ClienteBinanceFalso)

    with TestClient(app) as client:
        login = client.post(
            "/v1/sessao/entrar",
            json={"api_key": "binance-chave", "api_secret": "binance-segredo", "testnet": True},
        )
        assert login.status_code == 200

        resposta = client.get("/v1/sessao/ia/chaves")
        escrita = client.put(
            "/v1/sessao/ia/chaves",
            json={"provedor": "gpt", "chave": segredo},
        )

    assert resposta.status_code == 200
    assert resposta.json()["provedores"] == [
        {"provedor": "claude", "configurada": False},
        {"provedor": "gemini", "configurada": False},
        {"provedor": "gpt", "configurada": True},
        {"provedor": "nvidia", "configurada": False},
    ]
    assert segredo not in json.dumps(resposta.json())
    assert escrita.status_code == 405
