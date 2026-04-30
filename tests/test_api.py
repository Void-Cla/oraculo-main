import os

from fastapi.testclient import TestClient

from src.main import app


def _payload_previsao() -> dict:
    klines = []
    base = 100.0
    for idx in range(1, 26):
        close = base + (idx * 0.4)
        klines.append(
            {
                "ts": idx,
                "open": close - 0.2,
                "high": close + 0.4,
                "low": close - 0.5,
                "close": close,
                "volume": 10 + idx,
            }
        )
    return {
        "simbolo": "BTCUSDT",
        "klines": klines,
        "livro_topo": {"bid_price": 110.1, "bid_qty": 5.0, "ask_price": 110.3, "ask_qty": 4.0},
        "noticias": [{"titulo": "ETF de bitcoin registra inflow forte", "sentimento": 0.8, "fonte": "teste"}],
        "saldo": {"saldo_total": 1000.0, "saldo_livre": 800.0},
        "salvar": True,
    }


def test_api_previsao_manual_e_exports(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "api.sqlite")

    with TestClient(app) as client:
        resposta = client.post("/v1/previsao/manual", json=_payload_previsao())
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["simbolo"] == "BTCUSDT"
        assert "decisao" in corpo
        assert "peso_modelo_llm" in corpo["decisao"]

        health = client.get("/v1/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        predicoes = client.get("/v1/export/predicoes?simbolo=BTCUSDT&limite=5")
        assert predicoes.status_code == 200
        assert len(predicoes.json()["itens"]) >= 1

        auditoria = client.get("/v1/export/auditoria?simbolo=BTCUSDT&limite=5")
        assert auditoria.status_code == 200
        assert len(auditoria.json()["itens"]) >= 1
