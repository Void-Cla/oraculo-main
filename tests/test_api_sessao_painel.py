import os

from fastapi.testclient import TestClient

from src.main import app


class _ClienteBinanceFalso:
    ultimo_testnet = None

    def __init__(self, *args, **kwargs):
        type(self).ultimo_testnet = kwargs.get("testnet")

    async def obter_conta_raw(self):
        return {
            "accountType": "SPOT",
            "uid": 998877,
            "canTrade": True,
            "permissions": ["SPOT"],
            "commissionRates": {
                "maker": "0.00100000",
                "taker": "0.00100000",
                "buyer": "0.00100000",
                "seller": "0.00100000",
            },
            "balances": [
                {"asset": "BTC", "free": "0.07000000", "locked": "0.00000000"},
                {"asset": "USDT", "free": "1250.00000000", "locked": "50.00000000"},
            ],
        }

    async def obter_trades_conta(self, simbolo="BTCUSDT", limit=1000):
        return [
            {
                "id": 1,
                "orderId": 11,
                "price": "30000",
                "qty": "0.10000000",
                "quoteQty": "3000",
                "commission": "3",
                "commissionAsset": "USDT",
                "time": 1000,
                "isBuyer": True,
                "isMaker": False,
            },
            {
                "id": 2,
                "orderId": 12,
                "price": "32000",
                "qty": "0.05000000",
                "quoteQty": "1600",
                "commission": "1.6",
                "commissionAsset": "USDT",
                "time": 2000,
                "isBuyer": True,
                "isMaker": False,
            },
            {
                "id": 3,
                "orderId": 13,
                "price": "35000",
                "qty": "0.08000000",
                "quoteQty": "2800",
                "commission": "2.8",
                "commissionAsset": "USDT",
                "time": 3000,
                "isBuyer": False,
                "isMaker": False,
            },
        ]

    async def obter_ordens_abertas(self, simbolo="BTCUSDT"):
        return [
            {
                "orderId": 21,
                "clientOrderId": "abc",
                "updateTime": 4000,
                "side": "BUY",
                "type": "LIMIT",
                "status": "NEW",
                "price": "39000",
                "stopPrice": "0",
                "origQty": "0.01000000",
                "executedQty": "0.00000000",
                "cummulativeQuoteQty": "0",
            }
        ]

    async def obter_todas_ordens(self, simbolo="BTCUSDT", limit=1000):
        return [
            {
                "orderId": 21,
                "clientOrderId": "abc",
                "updateTime": 4000,
                "side": "BUY",
                "type": "LIMIT",
                "status": "NEW",
                "price": "39000",
                "stopPrice": "0",
                "origQty": "0.01000000",
                "executedQty": "0.00000000",
                "cummulativeQuoteQty": "0",
            },
            {
                "orderId": 22,
                "clientOrderId": "def",
                "updateTime": 3500,
                "side": "SELL",
                "type": "MARKET",
                "status": "FILLED",
                "price": "35000",
                "stopPrice": "0",
                "origQty": "0.08000000",
                "executedQty": "0.08000000",
                "cummulativeQuoteQty": "2800",
            },
            {
                "orderId": 23,
                "clientOrderId": "ghi",
                "updateTime": 3200,
                "side": "BUY",
                "type": "LIMIT",
                "status": "CANCELED",
                "price": "28000",
                "stopPrice": "0",
                "origQty": "0.02000000",
                "executedQty": "0.00000000",
                "cummulativeQuoteQty": "0",
            },
        ]

    async def obter_preco_atual(self, simbolo="BTCUSDT"):
        if simbolo == "BNBUSDT":
            return 600.0
        return 40000.0

    async def fechar(self):
        return None


async def _coletar_sem_rede(*args, **kwargs):
    return None


async def _gerar_sem_rede(*args, **kwargs):
    return {}


async def _noticias_sem_rede(*args, **kwargs):
    return {
        "simbolo": "BTCUSDT",
        "meta": {"fontes_monitoradas": 24, "buscas_hoje": 1, "max_buscas_dia": 5},
        "itens": [
            {"titulo": "ETF atrai fluxo para bitcoin", "fonte": "Reuters", "sentimento": 0.6, "fonte_analise": "heuristica_local"}
        ],
    }


async def _montar_dashboard_base(*args, **kwargs):
    return {
        "ts_atualizacao": 5000,
        "operacional": {
            "api": "operacional",
            "loop_previsao": "operacional",
            "mercado": "sincronizado",
            "trava_risco": "operacional",
        },
        "mercado": {
            "preco_atual": 40000.0,
            "variacao_1m_pct": 1.25,
            "livro_topo": {"bid_price": 39990.0, "ask_price": 40010.0},
            "historico_precos": [
                {"ts": 1, "close": 39600.0},
                {"ts": 2, "close": 39800.0},
                {"ts": 3, "close": 40000.0},
            ],
        },
        "modelos": {
            "temperatura_modelo": 76,
            "temperatura_llm": 62,
            "hit_rate_modelo": 58.0,
            "hit_rate_llm": 54.0,
            "predicao_atual": {
                "created_ts": 4800,
                "p_conf": 0.64,
                "y_cal": 40500.0,
                "meta": {"preco_atual": 40000.0, "decisao": {"acao": "BUY"}},
            },
            "decisao_atual": {"acao": "BUY", "motivo": "forca compradora no curto prazo"},
            "llm_atual": {"insight": "contexto favoravel ao bitcoin"},
        },
        "historico": {
            "predicoes": [
                {
                    "created_ts": 4800,
                    "p_conf": 0.64,
                    "y_cal": 40500.0,
                    "meta": {"preco_atual": 40000.0, "decisao": {"acao": "BUY"}},
                }
            ],
            "auditoria": [
                {
                    "created_ts": 4900,
                    "tipo": "previsao_hibrida",
                    "payload": {
                        "predicao": {"y_cal": 40500.0},
                        "decisao": {"motivo": "convergencia numerica e contextual"},
                    },
                }
            ],
        },
    }


def test_fluxo_sessao_login_status_logout(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "sessao.sqlite")
    monkeypatch.setattr("src.servicos.sessoes.ClienteBinance", _ClienteBinanceFalso)

    with TestClient(app) as client:
        resposta = client.post(
            "/v1/sessao/entrar",
            json={"api_key": "abcd1234key", "api_secret": "secret9876"},
        )
        assert resposta.status_code == 200
        assert resposta.json()["autenticado"] is True
        assert resposta.json()["id_conta"] == "998877"
        assert "oraculo_sessao=" in resposta.headers.get("set-cookie", "")

        status = client.get("/v1/sessao/status")
        assert status.status_code == 200
        assert status.json()["autenticado"] is True
        assert status.json()["api_key_mascarada"].startswith("abcd")

        sair = client.post("/v1/sessao/sair", json={})
        assert sair.status_code == 200
        assert sair.json()["autenticado"] is False

        status_final = client.get("/v1/sessao/status")
        assert status_final.status_code == 200
        assert status_final.json()["autenticado"] is False


def test_fluxo_sessao_login_testnet_inicia_pausado(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "sessao_testnet.sqlite")
    _ClienteBinanceFalso.ultimo_testnet = None
    monkeypatch.setattr("src.servicos.sessoes.ClienteBinance", _ClienteBinanceFalso)
    chamadas_auto_trade = []

    async def _obter_ajustes_testnet():
        return {
            "aplicado": {
                "simbolo": "BTCUSDT",
                "intervalo_segundos": 30,
                "notional_usdt": 5.0,
            }
        }

    def _status_auto_trade(token):
        return {"ativo": False, "config": {}, "estado_ciclo": None, "ultimo_motivo": None}

    async def _iniciar_auto_trade(token, sessao, config):
        chamadas_auto_trade.append({"token": token, "sessao": sessao, "config": config})
        return {"ativo": True, "estado_ciclo": "AGUARDANDO_ENTRADA"}

    monkeypatch.setattr("src.main.obter_ajustes_testnet", _obter_ajustes_testnet)
    monkeypatch.setattr("src.main.TESTNET_TRADER.status", _status_auto_trade)
    monkeypatch.setattr("src.main.TESTNET_TRADER.iniciar", _iniciar_auto_trade)

    with TestClient(app) as client:
        resposta = client.post(
            "/v1/sessao/entrar",
            json={"api_key": "abcd1234key", "api_secret": "secret9876", "testnet": True},
        )
        assert resposta.status_code == 200
        assert resposta.json()["modo_testnet"] is True
        assert resposta.json()["auto_trade"]["ativo"] is False
        assert resposta.json()["auto_trade"]["estado_ciclo"] == "PAUSADO"
        assert resposta.json()["auto_trade"]["config"]["notional_usdt"] == 5.0
        assert _ClienteBinanceFalso.ultimo_testnet is True
        assert len(chamadas_auto_trade) == 0

        status = client.get("/v1/sessao/status")
        assert status.status_code == 200
        assert status.json()["auto_trade"]["ativo"] is False
        assert status.json()["auto_trade"]["estado_ciclo"] == "PAUSADO"


def test_atualiza_capital_do_auto_bot(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "sessao_testnet_capital.sqlite")
    monkeypatch.setattr("src.servicos.sessoes.ClienteBinance", _ClienteBinanceFalso)
    chamadas_atualizacao = []

    async def _obter_ajustes_testnet():
        return {
            "aplicado": {
                "simbolo": "BTCUSDT",
                "intervalo_segundos": 10,
                "notional_usdt": 5.0,
            }
        }

    def _status_auto_trade(token):
        return {"ativo": False, "config": {}, "estado_ciclo": None, "ultimo_motivo": None}

    async def _atualizar_auto_trade(token, config):
        chamadas_atualizacao.append({"token": token, "config": config})
        return {"ativo": False, "config": config, "estado_ciclo": "PAUSADO", "ultimo_motivo": "bot_pausado"}

    monkeypatch.setattr("src.main.obter_ajustes_testnet", _obter_ajustes_testnet)
    monkeypatch.setattr("src.main.TESTNET_TRADER.status", _status_auto_trade)
    monkeypatch.setattr("src.main.TESTNET_TRADER.atualizar_config", _atualizar_auto_trade)

    with TestClient(app) as client:
        login = client.post(
            "/v1/sessao/entrar",
            json={"api_key": "abcd1234key", "api_secret": "secret9876", "testnet": True},
        )
        assert login.status_code == 200

        resposta = client.put("/v1/testnet/auto/config", json={"notional_usdt": 17.5})
        assert resposta.status_code == 200
        assert resposta.json()["ajustes"]["aplicado"]["notional_usdt"] == 17.5
        assert resposta.json()["status"]["config"]["notional_usdt"] == 17.5
        assert len(chamadas_atualizacao) == 1
        assert chamadas_atualizacao[0]["config"]["notional_usdt"] == 17.5


def test_inicia_e_pausa_auto_bot_manualmente(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "sessao_testnet_manual.sqlite")
    monkeypatch.setattr("src.servicos.sessoes.ClienteBinance", _ClienteBinanceFalso)
    estado_auto_trade = {
        "ativo": False,
        "config": {"simbolo": "BTCUSDT", "intervalo_segundos": 10, "notional_usdt": 5.0},
    }
    chamadas_iniciar = []
    chamadas_parar = []

    async def _obter_ajustes_testnet():
        return {"aplicado": dict(estado_auto_trade["config"])}

    def _status_auto_trade(token):
        return {
            "ativo": estado_auto_trade["ativo"],
            "config": dict(estado_auto_trade["config"]),
            "estado_ciclo": "AGUARDANDO_ENTRADA" if estado_auto_trade["ativo"] else None,
            "ultimo_motivo": "aguardando_primeira_leitura" if estado_auto_trade["ativo"] else None,
        }

    async def _iniciar_auto_trade(token, sessao, config):
        chamadas_iniciar.append({"token": token, "sessao": sessao, "config": config})
        estado_auto_trade["ativo"] = True
        estado_auto_trade["config"] = dict(config)
        return _status_auto_trade(token)

    async def _parar_auto_trade(token):
        chamadas_parar.append(token)
        estado_auto_trade["ativo"] = False
        return {"ativo": False}

    monkeypatch.setattr("src.main.obter_ajustes_testnet", _obter_ajustes_testnet)
    monkeypatch.setattr("src.main.TESTNET_TRADER.status", _status_auto_trade)
    monkeypatch.setattr("src.main.TESTNET_TRADER.iniciar", _iniciar_auto_trade)
    monkeypatch.setattr("src.main.TESTNET_TRADER.parar", _parar_auto_trade)

    with TestClient(app) as client:
        login = client.post(
            "/v1/sessao/entrar",
            json={"api_key": "abcd1234key", "api_secret": "secret9876", "testnet": True},
        )
        assert login.status_code == 200
        assert login.json()["auto_trade"]["ativo"] is False

        iniciar = client.post(
            "/v1/testnet/auto/start",
            json={"simbolo": "BTCUSDT", "intervalo_segundos": 10, "notional_usdt": 12.5, "lado_inicial": "BUY"},
        )
        assert iniciar.status_code == 200
        assert iniciar.json()["status"]["ativo"] is True
        assert iniciar.json()["status"]["config"]["notional_usdt"] == 12.5
        assert len(chamadas_iniciar) == 1
        assert chamadas_iniciar[0]["sessao"]["modo_testnet"] is True
        assert chamadas_iniciar[0]["config"]["notional_usdt"] == 12.5

        parar = client.post("/v1/testnet/auto/stop", json={})
        assert parar.status_code == 200
        assert parar.json()["ativo"] is False
        assert parar.json()["estado_ciclo"] == "PAUSADO"
        assert parar.json()["config"]["notional_usdt"] == 12.5
        assert len(chamadas_parar) == 1


def test_auto_bot_real_usa_mesmo_fluxo_quando_liberado(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "sessao_real_auto.sqlite")
    os.environ["PERMITIR_CONTA_REAL"] = "true"
    _ClienteBinanceFalso.ultimo_testnet = None
    monkeypatch.setattr("src.servicos.sessoes.ClienteBinance", _ClienteBinanceFalso)
    chamadas_iniciar = []

    async def _obter_ajustes_testnet():
        return {
            "aplicado": {
                "simbolo": "ETHUSDT",
                "intervalo_segundos": 15,
                "notional_usdt": 11.0,
            }
        }

    def _status_auto_trade(token):
        return {
            "ativo": False,
            "modo": "real",
            "modo_testnet": False,
            "config": {"simbolo": "ETHUSDT", "intervalo_segundos": 15, "notional_usdt": 11.0},
            "estado_ciclo": None,
            "ultimo_motivo": None,
        }

    async def _iniciar_auto_trade(token, sessao, config):
        chamadas_iniciar.append({"token": token, "sessao": sessao, "config": config})
        return {
            "ativo": True,
            "modo": "real",
            "modo_testnet": False,
            "config": dict(config),
            "estado_ciclo": "AGUARDANDO_ENTRADA",
            "ultimo_motivo": "aguardando_primeira_leitura",
        }

    monkeypatch.setattr("src.main.obter_ajustes_testnet", _obter_ajustes_testnet)
    monkeypatch.setattr("src.main.AUTO_TRADER.status", _status_auto_trade)
    monkeypatch.setattr("src.main.AUTO_TRADER.iniciar", _iniciar_auto_trade)

    try:
        with TestClient(app) as client:
            login = client.post(
                "/v1/sessao/entrar",
                json={"api_key": "abcd1234key", "api_secret": "secret9876", "testnet": False},
            )
            assert login.status_code == 200
            assert login.json()["modo_testnet"] is False
            assert login.json()["auto_trade"]["modo_testnet"] is False
            assert login.json()["auto_trade"]["config"]["notional_usdt"] == 11.0
            assert _ClienteBinanceFalso.ultimo_testnet is False

            iniciar = client.post(
                "/v1/auto/start",
                json={"simbolo": "ETHUSDT", "intervalo_segundos": 15, "notional_usdt": 14.0, "lado_inicial": "BUY"},
            )
            assert iniciar.status_code == 200
            assert iniciar.json()["status"]["ativo"] is True
            assert iniciar.json()["status"]["modo_testnet"] is False
            assert chamadas_iniciar[0]["sessao"]["modo_testnet"] is False
            assert chamadas_iniciar[0]["config"]["notional_usdt"] == 14.0
    finally:
        os.environ["PERMITIR_CONTA_REAL"] = "false"


def test_painel_conta_retorna_saldos_ordens_e_pnl(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "painel.sqlite")
    monkeypatch.setattr("src.servicos.sessoes.ClienteBinance", _ClienteBinanceFalso)
    monkeypatch.setattr("src.servicos.painel_conta.ClienteBinance", _ClienteBinanceFalso)
    monkeypatch.setattr("src.servicos.painel_conta.coletar_e_persistir", _coletar_sem_rede)
    monkeypatch.setattr("src.servicos.painel_conta.gerar_previsao_dados_persistidos", _gerar_sem_rede)
    monkeypatch.setattr("src.servicos.painel_conta.montar_dashboard", _montar_dashboard_base)
    monkeypatch.setattr("src.servicos.painel_conta.obter_noticias_para_peso", _noticias_sem_rede)

    with TestClient(app) as client:
        login = client.post(
            "/v1/sessao/entrar",
            json={"api_key": "abcd1234key", "api_secret": "secret9876"},
        )
        assert login.status_code == 200

        resposta = client.get("/v1/painel/conta?simbolo=BTCUSDT")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["simbolo"] == "BTCUSDT"
        assert corpo["conta"]["saldo_btc"]["total"] == 0.07
        assert corpo["conta"]["saldo_usdt"]["total"] == 1300.0
        assert corpo["ordens"]["resumo"]["executadas"] == 1
        assert corpo["ordens"]["resumo"]["canceladas"] == 1
        assert corpo["ordens"]["resumo"]["abertas"] == 1
        assert len(corpo["historico_negociacoes"]) == 3
        assert round(corpo["pnl"]["taxas_totais_usdt"], 2) == 7.40
        assert round(corpo["pnl"]["pnl_realizado_liquido_usdt"], 2) == 394.80
        assert round(corpo["pnl"]["pnl_nao_realizado_usdt"], 2) == 597.80
        assert round(corpo["pnl"]["pnl_total_liquido_usdt"], 2) == 992.60
