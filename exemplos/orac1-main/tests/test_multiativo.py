from src.multiativo.capital_manager import calcular_plano_capital
from src.multiativo.fee_optimizer import montar_perfil_taxas
from src.multiativo.opportunity_scanner import ranquear_oportunidades
from src.multiativo.triangular_arbitrage import avaliar_rotas_triangular


def test_arbitragem_triangular_detecta_rota_com_lucro_liquido():
    snapshots = {
        "BTCUSDT": {"livro_topo": {"bid_price": 100000.0, "ask_price": 100100.0}},
        "BNBBTC": {"livro_topo": {"bid_price": 0.00499, "ask_price": 0.00501}},
        "BNBUSDT": {"livro_topo": {"bid_price": 510.0, "ask_price": 511.0}},
        "ETHUSDT": {"livro_topo": {"bid_price": 3500.0, "ask_price": 3502.0}},
        "ETHBTC": {"livro_topo": {"bid_price": 0.0348, "ask_price": 0.0349}},
        "BNBETH": {"livro_topo": {"bid_price": 0.1450, "ask_price": 0.1452}},
    }

    resultado = avaliar_rotas_triangular(
        snapshots,
        notional_inicial_usdt=100.0,
        taxa_por_perna=0.001,
        slippage_pct=0.0001,
    )

    assert resultado["melhor_rota"] is not None
    assert resultado["melhor_rota"]["valida"] is True
    assert resultado["melhor_rota"]["lucro_liquido_usdt"] > 0.05


def test_scanner_prioriza_par_com_probabilidade_ev_e_lucro_validos():
    snapshots = {
        "BTCUSDT": {
            "features": {
                "vol5": 0.004,
                "vol10": 0.005,
                "amplitude_rel": 0.007,
                "volume_ratio": 1.8,
                "r_1m": 0.002,
                "r_3m": 0.004,
                "r_5m": 0.006,
                "book_imb": 0.18,
                "spread_rel": 0.0005,
            }
        },
        "ETHUSDT": {
            "features": {
                "vol5": 0.002,
                "vol10": 0.0025,
                "amplitude_rel": 0.003,
                "volume_ratio": 0.9,
                "r_1m": 0.0001,
                "r_3m": 0.0002,
                "r_5m": 0.0003,
                "book_imb": 0.01,
                "spread_rel": 0.0025,
            }
        },
    }
    sinais = {
        "BTCUSDT": {
            "acao": "BUY",
            "lucro_liquido_esperado_pct": 0.006,
            "movimento_previsto_pct": 0.008,
            "regime": "TREND_UP",
            "estrategia": "momentum",
            "probabilidade_trade": {"prob_up": 0.74, "prob_down": 0.26, "ev_buy": 0.0024, "ev_sell": -0.0010},
            "confirmacao_multi_timeframe": {"score_buy": 4},
        },
        "ETHUSDT": {
            "acao": "HOLD",
            "lucro_liquido_esperado_pct": 0.0004,
            "movimento_previsto_pct": 0.0008,
            "regime": "RANGE",
            "estrategia": "mean_reversion",
            "probabilidade_trade": {"prob_up": 0.51, "prob_down": 0.49, "ev_buy": -0.0002, "ev_sell": -0.0001},
            "confirmacao_multi_timeframe": {"score_buy": 2},
        },
    }
    saldos = {
        "USDT": {"livre": 50.0, "travado": 0.0, "total": 50.0},
        "BTC": {"livre": 0.0, "travado": 0.0, "total": 0.0},
        "ETH": {"livre": 0.0, "travado": 0.0, "total": 0.0},
        "BNB": {"livre": 6.0, "travado": 0.0, "total": 6.0},
    }
    precos_usdt = {"USDT": 1.0, "BTC": 100000.0, "ETH": 3500.0, "BNB": 600.0}
    capital = calcular_plano_capital(saldos=saldos, saldo_total_estimado_usdt=3650.0)
    perfil_taxas = montar_perfil_taxas(saldos=saldos)

    resultado = ranquear_oportunidades(
        snapshots=snapshots,
        sinais=sinais,
        saldos=saldos,
        precos_usdt=precos_usdt,
        capital_info=capital,
        perfil_taxas=perfil_taxas,
    )

    assert resultado["melhor_oportunidade"]["simbolo"] == "BTCUSDT"
    assert resultado["melhor_oportunidade"]["valida"] is True
    assert resultado["total_validas"] >= 1
    assert any(item["simbolo"] == "ETHUSDT" and item["valida"] is False for item in resultado["pares"])


def test_scanner_respeita_capital_planejado_e_meta_de_microtrade():
    snapshots = {
        "BTCUSDT": {
            "features": {
                "vol5": 0.004,
                "vol10": 0.005,
                "amplitude_rel": 0.007,
                "volume_ratio": 1.8,
                "r_1m": 0.002,
                "r_3m": 0.004,
                "r_5m": 0.006,
                "book_imb": 0.18,
                "spread_rel": 0.0005,
            }
        }
    }
    sinais = {
        "BTCUSDT": {
            "acao": "BUY",
            "lucro_liquido_esperado_pct": 0.0022,
            "movimento_previsto_pct": 0.0045,
            "regime": "TREND_UP",
            "estrategia": "momentum",
            "probabilidade_trade": {"prob_up": 0.72, "prob_down": 0.28, "ev_buy": 0.0016, "ev_sell": -0.0008},
            "confirmacao_multi_timeframe": {"score_buy": 4},
        }
    }
    saldos = {
        "USDT": {"livre": 100.0, "travado": 0.0, "total": 100.0},
        "BTC": {"livre": 0.0, "travado": 0.0, "total": 0.0},
        "ETH": {"livre": 0.0, "travado": 0.0, "total": 0.0},
        "BNB": {"livre": 6.0, "travado": 0.0, "total": 6.0},
    }
    precos_usdt = {"USDT": 1.0, "BTC": 100000.0, "ETH": 3500.0, "BNB": 600.0}
    capital = calcular_plano_capital(
        saldos=saldos,
        saldo_total_estimado_usdt=3700.0,
        capital_planejado_usdt=5.0,
        lucro_liquido_minimo_usdt=0.01,
    )
    perfil_taxas = montar_perfil_taxas(saldos=saldos)

    resultado = ranquear_oportunidades(
        snapshots=snapshots,
        sinais=sinais,
        saldos=saldos,
        precos_usdt=precos_usdt,
        capital_info=capital,
        perfil_taxas=perfil_taxas,
    )

    melhor = resultado["melhor_oportunidade"]
    assert capital["trade_referencia_usdt"] == 5.0
    assert capital["lucro_liquido_minimo_usdt"] == 0.01
    assert melhor["simbolo"] == "BTCUSDT"
    assert melhor["notional_sugerido_usdt"] == 5.0
    assert melhor["lucro_liquido_esperado_usdt"] == 0.011
    assert melhor["valida"] is True
