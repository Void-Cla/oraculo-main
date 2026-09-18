import asyncio

from src.servicos.contabilidade_painel import patrimonio_monitorado, resumo_contabil, valorizar_saldos_reais
from src.servicos.sessoes import _SESSOES, comparar_patrimonio_sessao, resetar_sessoes_teste


def test_patrimonio_recusa_preco_ausente_sem_substituir_por_zero():
    conta = {
        "balances": [
            {"asset": "USDT", "free": "100", "locked": "0"},
            {"asset": "BTC", "free": "0.01", "locked": "0"},
        ]
    }

    patrimonio, escopo = patrimonio_monitorado(
        conta, {"ativos_monitorados": ["USDT", "BTC"], "precos_usdt": {"USDT": 1.0}},
    )

    assert patrimonio is None
    assert escopo == ("BTC", "USDT")


def test_patrimonio_nao_omite_ativo_fora_do_escopo_monitorado():
    conta = {
        "balances": [
            {"asset": "USDT", "free": "100", "locked": "5"},
            {"asset": "BTC", "free": "0.01", "locked": "0"},
            {"asset": "ETH", "free": "4", "locked": "0"},
        ]
    }

    patrimonio, escopo = patrimonio_monitorado(
        conta,
        {"ativos_monitorados": ["BTC", "USDT"], "precos_usdt": {"USDT": 1.0, "BTC": 50_000}},
    )

    assert patrimonio is None
    assert escopo == ("BTC", "ETH", "USDT")


def test_valorizar_saldos_reais_exige_cotacao_de_todo_ativo_nao_zero():
    resumo = valorizar_saldos_reais(
        {"balances": [
            {"asset": "USDT", "free": "100", "locked": "5"},
            {"asset": "BTC", "free": "0.01", "locked": "0.002"},
            {"asset": "XYZ", "free": "1", "locked": "0"},
        ]},
        {"USDT": 1.0, "BTC": 50_000.0},
    )

    assert resumo["patrimonio_usdt"] is None
    assert resumo["conversao_completa"] is False
    assert resumo["ativos_sem_cotacao"] == ["XYZ"]
    assert resumo["ativos"][1]["livre"] == 0.01
    assert resumo["ativos"][1]["travado"] == 0.002


def test_primeira_fotografia_valida_e_imutavel_por_sessao():
    resetar_sessoes_teste()
    _SESSOES["teste"] = {"expira_em": 9_999_999_999_999}

    primeira = asyncio.run(comparar_patrimonio_sessao("teste", 100.0, ("BTC", "USDT")))
    segunda = asyncio.run(comparar_patrimonio_sessao("teste", 125.0, ("BTC", "USDT")))

    assert primeira["saldo_inicial_usdt"] == 100.0
    assert primeira["variacao_usdt"] == 0.0
    assert segunda["saldo_inicial_usdt"] == 100.0
    assert segunda["saldo_atual_usdt"] == 125.0
    assert segunda["variacao_usdt"] == 25.0
    assert segunda["motivo"] == "variacao_patrimonial_nao_conciliada_com_fluxos"


def test_comparacao_mantem_baseline_quando_carteira_muda():
    resetar_sessoes_teste()
    _SESSOES["teste"] = {"expira_em": 9_999_999_999_999}
    asyncio.run(comparar_patrimonio_sessao("teste", 100.0, ("BTC", "USDT")))

    resposta = asyncio.run(comparar_patrimonio_sessao("teste", 140.0, ("ETH", "USDT")))

    assert resposta["disponivel"] is True
    assert resposta["saldo_inicial_usdt"] == 100.0
    assert resposta["saldo_atual_usdt"] == 140.0
    assert resposta["motivo"] == "variacao_patrimonial_nao_conciliada_com_fluxos"


def test_fluxo_externo_nao_concilia_resultado_de_trading():
    resetar_sessoes_teste()
    _SESSOES["teste"] = {"expira_em": 9_999_999_999_999}
    asyncio.run(comparar_patrimonio_sessao("teste", 100.0, ("BTC", "USDT")))

    resposta = asyncio.run(comparar_patrimonio_sessao(
        "teste", 150.0, ("BTC", "USDT"), fluxos_externos_usdt=40.0,
    ))

    assert resposta["variacao_usdt"] == 50.0
    assert resposta["aportes_saques_ajustados"] is True
    assert resposta["resultado_trading_usdt"] is None
    assert resposta["resultado_trading_conciliado"] is False
    assert resposta["motivo"] == "fluxos_externos_informados_sem_conciliacao_de_fills_e_taxas"


def test_resumo_nao_chama_pnl_parcial_de_confiavel():
    resumo = resumo_contabil(
        {
            "pnl_realizado_liquido_usdt": -74.4952649,
            "pnl_nao_realizado_usdt": 0.0017862,
            "cobertura_fifo_incompleta": True,
            "historico": [{"time": 1_000}, {"time": 2_000}],
        },
        [{"time": 1_000}, {"time": 2_000}],
        disponivel=True,
        modo_testnet=True,
        simbolo="BTCUSDT",
    )

    assert resumo["confiavel"] is False
    assert resumo["total_usdt"] == -74.4934787
    assert resumo["modo_testnet"] is True
    assert resumo["simulacao_custos"]["disponivel"] is False
