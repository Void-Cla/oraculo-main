from fastapi.testclient import TestClient

from src.main import app


async def _monitoramento_falso(*args, **kwargs):
    return {
        "ativos_monitorados": ["BTC", "ETH", "BNB", "USDT"],
        "pares_monitorados": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ETHBTC", "BNBBTC", "BNBETH"],
        "scanner": {
            "total_validas": 1,
            "sem_vantagem_real": False,
            "melhor_oportunidade": {"simbolo": "BTCUSDT", "acao_sugerida": "BUY"},
            "pares": [{"simbolo": "BTCUSDT", "valida": True}],
        },
        "arbitragem_triangular": {"oportunidades_validas": 0, "sem_vantagem_real": True, "rotas": []},
        "sem_vantagem_estatistica": False,
    }


def test_endpoint_multiativo_oportunidades_retorna_monitoramento(monkeypatch):
    monkeypatch.setattr("src.main.montar_monitoramento_multiativo", _monitoramento_falso)

    with TestClient(app) as client:
        resposta = client.get("/v1/multiativo/oportunidades")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["scanner"]["melhor_oportunidade"]["simbolo"] == "BTCUSDT"
        assert corpo["sem_vantagem_estatistica"] is False
