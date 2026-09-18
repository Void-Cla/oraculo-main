import asyncio
import os

from fastapi.testclient import TestClient

from src.main import app
from src.persistencia.conexao import inicializar_db
from src.persistencia.repositorio_config import RepositorioConfig


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


def test_api_ajustes_operacionais_automaticos_bloqueiam_override_manual(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "ajustes_operacionais.sqlite")

    with TestClient(app) as client:
        listar = client.get("/v1/ajustes")
        assert listar.status_code == 200
        assert listar.json()["operacional"]["aplicado"]["auto_trades_ilimitados"] is True
        assert listar.json()["operacional"]["modo"] == "automatico"

        resposta = client.put(
            "/v1/ajustes/operacional",
            json={
                "valor": {
                    "auto_trades_ilimitados": True,
                    "auto_max_idade_dados_ms": 100,
                    "auto_max_desvio_relogio_ms": 100,
                    "api_key": "nao_deve_persistir",
                }
            },
        )

        assert resposta.status_code == 403
        assert resposta.json()["detail"] == "ajustes_operacionais_automaticos"
        assert client.put("/v1/ajustes/sinal", json={"valor": {"peso_modelo_llm": 1.0}}).status_code == 403
        assert client.put("/v1/ajustes/risco", json={"valor": {"max_daily_loss_usdt": 1.0}}).status_code == 403
        assert client.put("/v1/config/ajustes_sinal", json={"valor": {"peso_modelo_llm": 1.0}}).status_code == 403
        assert client.put("/v1/config/segredo_teste", json={"valor": {"api_key": "x"}}).status_code == 403

        asyncio.run(RepositorioConfig.definir("ajustes_operacionais", {"auto_max_idade_dados_ms": 100}))
        asyncio.run(RepositorioConfig.definir("ajustes_sinal", {"peso_modelo_llm": 1.0}))
        ajustes = client.get("/v1/ajustes").json()
        assert ajustes["operacional"]["configurado"] == {}
        assert ajustes["operacional"]["aplicado"]["auto_max_idade_dados_ms"] >= 5000
        assert ajustes["sinal"]["configurado"] == {}
        assert ajustes["sinal"]["modo"] == "automatico"


def test_api_ajustes_testnet_aceita_capital_por_perfil(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "ajustes_testnet_perfis.sqlite")

    async def _sessao_fake(request):
        return {"modo_testnet": True, "api_key": "k", "api_secret": "s"}

    monkeypatch.setattr("src.main._sessao_autenticada", _sessao_fake)

    with TestClient(app) as client:
        resposta = client.put(
            "/v1/ajustes/testnet",
            json={
                "valor": {
                    "perfis_capital": {
                        "mini": {"ativo": True, "capital_usdt": 12.5},
                        "ganancioso": {"ativo": False, "capital_usdt": 5},
                        "diario": {"ativo": True, "capital_usdt": 7.5},
                    },
                }
            },
        )
        assert resposta.status_code == 200
        aplicado = resposta.json()["aplicado"]
        assert aplicado["intervalo_segundos"] == 5
        assert aplicado["notional_usdt"] == 20.0
        assert aplicado["perfis_capital"]["mini"]["capital_usdt"] == 12.5
        assert aplicado["perfis_capital"]["ganancioso"]["ativo"] is False
        assert aplicado["perfis_capital"]["diario"]["capital_usdt"] == 7.5


def test_api_ajustes_testnet_rejeita_payload_hostil(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "ajustes_testnet_hostil.sqlite")

    async def _sessao_fake(request):
        return {"modo_testnet": True, "api_key": "k", "api_secret": "s"}

    monkeypatch.setattr("src.main._sessao_autenticada", _sessao_fake)

    with TestClient(app) as client:
        notional = client.put("/v1/ajustes/testnet", json={"valor": {"notional_usdt": 123.0}})
        assert notional.status_code == 422

        infinito = client.put(
            "/v1/ajustes/testnet",
            json={"valor": {"perfis_capital": {"mini": {"ativo": True, "capital_usdt": "Infinity"}}}},
        )
        assert infinito.status_code == 422

        bool_string = client.put(
            "/v1/ajustes/testnet",
            json={"valor": {"perfis_capital": {"mini": {"ativo": "false", "capital_usdt": 10.0}}}},
        )
        assert bool_string.status_code == 422


def test_api_ajustes_testnet_merge_parcial_preserva_perfis(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "ajustes_testnet_merge.sqlite")

    async def _sessao_fake(request):
        return {"modo_testnet": True, "api_key": "k", "api_secret": "s"}

    monkeypatch.setattr("src.main._sessao_autenticada", _sessao_fake)

    with TestClient(app) as client:
        primeira = client.put(
            "/v1/ajustes/testnet",
            json={
                "valor": {
                    "perfis_capital": {
                        "mini": {"ativo": True, "capital_usdt": 10.0},
                        "ganancioso": {"ativo": True, "capital_usdt": 12.0},
                        "diario": {"ativo": False, "capital_usdt": 8.0},
                    },
                }
            },
        )
        assert primeira.status_code == 200

        segunda = client.put(
            "/v1/ajustes/testnet",
            json={
                "valor": {
                    "perfis_capital": {
                        "mini": {"ativo": True, "capital_usdt": 10.0},
                    },
                }
            },
        )
        assert segunda.status_code == 200
        aplicado = segunda.json()["aplicado"]
        assert aplicado["intervalo_segundos"] == 5
        assert aplicado["notional_usdt"] == 22.0
        assert aplicado["perfis_capital"]["mini"]["capital_usdt"] == 10.0
        assert aplicado["perfis_capital"]["ganancioso"]["capital_usdt"] == 12.0
        assert aplicado["perfis_capital"]["diario"]["ativo"] is False


def test_api_ajustes_testnet_deriva_notional_de_perfis_persistidos(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "ajustes_testnet_notional_derivado.sqlite")
    inicializar_db()
    asyncio.run(
        RepositorioConfig.definir(
            "ajustes_testnet",
            {
                "notional_usdt": 999.0,
                "intervalo_segundos": 60,
                "perfis_capital": {
                    "mini": {"ativo": True, "capital_usdt": 12.0, "prioridade_entrada": 9.0},
                    "ganancioso": {"ativo": False, "capital_usdt": 80.0},
                },
            },
        )
    )

    with TestClient(app) as client:
        bruto = client.put("/v1/config/ajustes_testnet", json={"valor": {"perfis_capital": {}}})
        assert bruto.status_code == 403

        aplicado = client.get("/v1/ajustes").json()["testnet"]["aplicado"]
        assert aplicado["notional_usdt"] == 12.0
        assert aplicado["intervalo_segundos"] == 5
        assert "prioridade_entrada" not in aplicado["perfis_capital"]["mini"]


def test_api_ajustes_testnet_sincroniza_auto_trader_ativo_quando_ha_sessao(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "ajustes_testnet_sync.sqlite")
    chamadas: list[dict] = []

    async def _obter_sessao_fake(token):
        return {"modo_testnet": True, "api_key": "k", "api_secret": "s"}

    async def _atualizar_config_fake(token, config):
        chamadas.append({"token": token, "config": dict(config)})
        return {"ativo": True, "config": dict(config)}

    monkeypatch.setattr("src.main.obter_sessao", _obter_sessao_fake)
    monkeypatch.setattr("src.main.AUTO_TRADER.atualizar_config", _atualizar_config_fake)

    with TestClient(app) as client:
        client.cookies.set("oraculo_sessao", "token-teste")
        resposta = client.put(
            "/v1/ajustes/testnet",
            json={
                "valor": {
                    "perfis_capital": {
                        "mini": {"ativo": True, "capital_usdt": 10.0},
                    },
                }
            },
        )
        assert resposta.status_code == 200
        assert len(chamadas) == 1
        assert chamadas[0]["token"] == "token-teste"
        assert chamadas[0]["config"]["modo_testnet"] is True
        assert chamadas[0]["config"]["perfis_capital"]["mini"]["capital_usdt"] == 10.0


def test_api_auto_start_preserva_perfis_salvos_quando_payload_omitido(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "auto_start_preserva_perfis.sqlite")

    async def _sessao_fake(request):
        return {"modo_testnet": True, "api_key": "k", "api_secret": "s"}

    async def _iniciar_fake(token, sessao, config):
        return {"ativo": True, "config": config}

    monkeypatch.setattr("src.main._sessao_autenticada", _sessao_fake)
    monkeypatch.setattr("src.main.AUTO_TRADER.iniciar", _iniciar_fake)

    with TestClient(app) as client:
        resposta_ajustes = client.put(
            "/v1/ajustes/testnet",
            json={
                "valor": {
                    "perfis_capital": {
                        "mini": {"ativo": True, "capital_usdt": 10.0},
                        "ganancioso": {"ativo": True, "capital_usdt": 12.0},
                        "diario": {"ativo": True, "capital_usdt": 8.0},
                    },
                }
            },
        )
        assert resposta_ajustes.status_code == 200
        client.cookies.set("oraculo_sessao", "token-teste")

        resposta_start = client.post(
            "/v1/auto/start",
            json={},
        )

        assert resposta_start.status_code == 200
        aplicado = resposta_start.json()["ajustes"]["aplicado"]
        assert aplicado["perfis_capital"]["mini"]["capital_usdt"] == 10.0
        assert aplicado["perfis_capital"]["ganancioso"]["capital_usdt"] == 12.0
        assert aplicado["perfis_capital"]["diario"]["capital_usdt"] == 8.0
