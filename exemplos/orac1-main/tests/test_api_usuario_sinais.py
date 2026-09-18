import os

from fastapi.testclient import TestClient

from src.main import app


def _payload_klines():
    klines = []
    for idx in range(1, 31):
        close = 100.0 + (idx * 0.5)
        klines.append(
            {
                "ts": idx,
                "open": close - 0.2,
                "high": close + 0.4,
                "low": close - 0.5,
                "close": close,
                "volume": 15 + idx,
            }
        )
    return klines


def test_fluxo_usuario_signal_queue(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "usuario_signal.sqlite")

    with TestClient(app) as client:
        usuario = client.post(
            "/v1/usuarios",
            json={
                "nome": "trader_a",
                "testnet": True,
                "ativo": True,
                "risk_config": {"risk_per_trade": 0.01, "max_drawdown": 0.05, "max_exposicao_ativo": 0.2},
            },
        )
        assert usuario.status_code == 200
        usuario_id = usuario.json()["id"]

        resposta = client.post(
            f"/v1/usuarios/{usuario_id}/sinais/gerar",
            json={
                "simbolo": "BTCUSDT",
                "klines": _payload_klines(),
                "livro_topo": {"bid_price": 115.04, "bid_qty": 5.0, "ask_price": 115.06, "ask_qty": 4.0},
                "noticias": [{"titulo": "Fluxo positivo para bitcoin", "sentimento": 0.6}],
                "saldo": {"saldo_total": 1000.0, "saldo_livre": 950.0},
                "estado_execucao": {"drawdown_atual": 0.01, "exposicao_ativo": 0.0, "trades_abertos": 0},
                "publicar_fila": True,
            },
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["usuario"]["id"] == usuario_id
        assert "sinal" in corpo
        assert "aprovacao_risco" in corpo
        assert corpo["ordem_id"] is not None

        ordens = client.get(f"/v1/ordens?usuario_id={usuario_id}&simbolo=BTCUSDT&limite=10")
        assert ordens.status_code == 200
        assert len(ordens.json()["itens"]) >= 1

        alterar = client.put(
            f"/v1/ordens/{corpo['ordem_id']}/status",
            json={"status": "EXECUTADA", "detalhe_extra": {"origem_teste": True}},
        )
        assert alterar.status_code == 200
        assert alterar.json()["status"] == "EXECUTADA"

        fila = client.get("/v1/sinais/fila?limite=20")
        assert fila.status_code == 200
        assert any(item["usuario_id"] == usuario_id for item in fila.json()["itens"])

        dashboard = client.get(f"/v1/dashboard/resumo?simbolo=BTCUSDT&usuario_id={usuario_id}&coletar_mercado=false")
        assert dashboard.status_code == 200
        resumo = dashboard.json()
        assert resumo["usuario"]["id"] == usuario_id
        assert "ordens" in resumo
        assert "modelos" in resumo
