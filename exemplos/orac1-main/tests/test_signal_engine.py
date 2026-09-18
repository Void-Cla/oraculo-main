import pytest

from src.estrategias.volatility_scalping import gerar_sinal_volatility_scalping
from src.meta_strategy.regime_detector import detectar_regime
from src.sinais.signal_engine import gerar_sinal_orquestrado


def _klines_tendencia_alta():
    klines = []
    for idx in range(1, 31):
        close = 100.0 + (idx * 0.6)
        klines.append([idx, close - 0.2, close + 0.3, close - 0.4, close, 20.0 + idx])
    return klines


def test_signal_engine_gera_sinal_com_regime_e_estrategia():
    klines = _klines_tendencia_alta()
    sinal = gerar_sinal_orquestrado(
        simbolo="BTCUSDT",
        klines=klines,
        livro_topo={"bid_price": 117.89, "bid_qty": 5.0, "ask_price": 117.91, "ask_qty": 4.0},
        noticias=[{"titulo": "ETF de bitcoin com entrada liquida", "sentimento": 0.7}],
        saldo={"saldo_total": 1000.0, "saldo_livre": 900.0},
    )

    regime = detectar_regime(sinal["features"])
    assert regime["regime"] in {"TREND_UP", "HIGH_VOL", "RANGE", "LOW_VOL", "TREND_DOWN"}
    assert sinal["simbolo"] == "BTCUSDT"
    assert "estrategia" in sinal
    assert "previsao_modelo" in sinal
    assert "regime" in sinal
    assert "confirmacao_multi_timeframe" in sinal
    assert sinal["confirmacao_multi_timeframe"]["score_buy"] >= 3
    assert "probabilidade_trade" in sinal
    assert "lucro_liquido_esperado_pct" in sinal
    assert "janela_decisao" in sinal


def test_signal_engine_repassa_parametros_probabilisticos_personalizados(monkeypatch):
    from src.sinais import signal_engine

    capturado = {}

    class _PTEFake:
        def __init__(self, **kwargs):
            capturado.update(kwargs)

        def evaluate_trade(self, **kwargs):
            return {
                "action": "BUY",
                "prob_up": 0.72,
                "prob_down": 0.28,
                "ev_buy": 0.0015,
                "ev_sell": -0.0007,
                "ajuste_externo": 0.0,
                "logit": 0.0,
                "custos_totais_pct": 0.0012,
            }

    monkeypatch.setattr(
        signal_engine,
        "calcular_features_1m",
        lambda *args, **kwargs: {
            "ts": 1,
            "close": 100.0,
            "spread_rel": 0.0002,
            "vol5": 0.003,
            "vol10": 0.0035,
        },
    )
    monkeypatch.setattr(signal_engine, "detectar_regime", lambda features: {"regime": "TREND_UP", "score_regime": 1.0, "detalhes": {}})
    monkeypatch.setattr(
        signal_engine,
        "preditor_end_to_end",
        lambda **kwargs: {
            "y_hat": 100.5,
            "y_cal": 101.0,
            "p_conf": 0.7,
            "direcao": "BUY",
            "decisao": {
                "score_numerico": 0.4,
                "variacao_prevista": 0.005,
                "llm": {"sentimento_noticias": 0.2},
            },
        },
    )
    monkeypatch.setattr(
        signal_engine,
        "gerar_sinal_meta",
        lambda *args, **kwargs: {
            "simbolo": "BTCUSDT",
            "estrategia": "momentum",
            "acao": "BUY",
            "confianca": 0.7,
            "stop_loss_pct": 0.003,
            "take_profit_pct": 0.009,
            "motivo": "microtrade",
        },
    )
    monkeypatch.setattr(signal_engine, "ProbabilisticTradeEngine", _PTEFake)

    sinal = gerar_sinal_orquestrado(
        simbolo="BTCUSDT",
        klines=_klines_tendencia_alta(),
        livro_topo={"bid_price": 100.0, "bid_qty": 2.0, "ask_price": 100.1, "ask_qty": 2.0},
        noticias=[],
        saldo={"saldo_total": 50.0, "saldo_livre": 5.0},
        ajustes_sinal={
            "signal_trade_fee_pct": 0.0009,
            "signal_slippage_pct": 0.0003,
            "signal_min_ev": 0.0002,
            "signal_min_prob": 0.55,
            "signal_prob_temperature": 0.7,
            "signal_prob_scale": 6.0,
        },
    )

    assert sinal["probabilidade_trade"]["action"] == "BUY"
    assert capturado == {
        "fee": 0.0009,
        "slippage": 0.0003,
        "min_ev": 0.0002,
        "min_prob": 0.55,
        "temperature": 0.7,
        "scale": 6.0,
    }


def test_volatility_scalping_permite_entrada_em_low_vol_com_micro_pressao_favoravel():
    features = {
        "vol5": 0.0006,
        "vol10": 0.0007,
        "r_5m": 0.0004,
        "r_15m": 0.0,
        "ema5": 100.0,
        "ema10": 100.0,
        "amplitude_rel": 0.0012,
        "spread_rel": 0.0002,
        "pressao_rel": 0.22,
        "diff_close_micro_rel": 0.00018,
    }

    regime = detectar_regime(features)
    sinal = gerar_sinal_volatility_scalping("BTCUSDT", features)

    assert regime["regime"] == "LOW_VOL"
    assert sinal["acao"] == "BUY"
    assert sinal["estrategia"] == "volatility_scalping"


def test_signal_engine_usa_ev_probabilistico_para_validar_microtrade(monkeypatch):
    from src.sinais import signal_engine

    class _PTEFake:
        def __init__(self, **kwargs):
            return None

        def evaluate_trade(self, **kwargs):
            return {
                "action": "BUY",
                "prob_up": 0.69,
                "prob_down": 0.31,
                "ev_buy": 0.00135,
                "ev_sell": -0.0008,
                "ajuste_externo": 0.0,
                "logit": 0.0,
                "custos_totais_pct": 0.0013,
            }

    monkeypatch.setattr(
        signal_engine,
        "calcular_features_1m",
        lambda *args, **kwargs: {
            "ts": 1,
            "close": 100.0,
            "spread_rel": 0.0001,
            "vol5": 0.00023,
            "vol10": 0.00024,
            "pressao_rel": 0.94,
            "diff_close_micro_rel": 0.0,
            "r_5m": 0.0004,
            "r_15m": 0.0,
            "ema5": 100.0,
            "ema10": 100.0,
            "amplitude_rel": 0.0011,
        },
    )
    monkeypatch.setattr(
        signal_engine,
        "_confirmacao_multi_timeframe",
        lambda *args, **kwargs: {
            "janelas": {},
            "score_buy": 3,
            "score_sell": 0,
            "score_direcional": 0.6,
            "permitir_buy": True,
            "permitir_sell": False,
            "retorno_medio": 0.0004,
        },
    )
    monkeypatch.setattr(
        signal_engine,
        "preditor_end_to_end",
        lambda **kwargs: {
            "y_hat": 100.03,
            "y_cal": 100.04,
            "p_conf": 0.7,
            "direcao": "BUY",
            "decisao": {
                "score_numerico": 0.31,
                "variacao_prevista": 0.0004,
                "llm": {"sentimento_noticias": 0.15},
            },
        },
    )
    monkeypatch.setattr(signal_engine, "ProbabilisticTradeEngine", _PTEFake)

    sinal = gerar_sinal_orquestrado(
        simbolo="ETHUSDT",
        klines=_klines_tendencia_alta(),
        livro_topo={"bid_price": 100.0, "bid_qty": 2.0, "ask_price": 100.01, "ask_qty": 2.0},
        noticias=[],
        saldo={"saldo_total": 50.0, "saldo_livre": 5.0},
        ajustes_sinal={
            "signal_min_net_profit_pct": 0.0005,
            "signal_min_ev": 0.0002,
            "signal_min_prob": 0.55,
        },
    )

    assert sinal["regime"] == "LOW_VOL"
    assert sinal["estrategia"] == "volatility_scalping"
    assert sinal["acao"] == "BUY"
    assert sinal["lucro_liquido_esperado_pct"] == pytest.approx(0.00135)


def test_signal_engine_nao_mata_compra_forte_por_multi_timeframe_parcial(monkeypatch):
    from src.sinais import signal_engine

    class _PTEFake:
        def __init__(self, **kwargs):
            return None

        def evaluate_trade(self, **kwargs):
            return {
                "action": "BUY",
                "prob_up": 0.68,
                "prob_down": 0.32,
                "ev_buy": 0.0012,
                "ev_sell": -0.0005,
                "ajuste_externo": 0.0,
                "logit": 0.0,
                "custos_totais_pct": 0.0010,
            }

    monkeypatch.setattr(
        signal_engine,
        "calcular_features_1m",
        lambda *args, **kwargs: {
            "ts": 1,
            "close": 100.0,
            "spread_rel": 0.0001,
            "vol5": 0.00022,
            "vol10": 0.00024,
            "pressao_rel": 0.88,
            "diff_close_micro_rel": 0.0002,
            "r_5m": 0.0005,
            "r_15m": 0.0001,
            "ema5": 100.0,
            "ema10": 99.9,
            "amplitude_rel": 0.001,
        },
    )
    monkeypatch.setattr(signal_engine, "detectar_regime", lambda features: {"regime": "LOW_VOL", "score_regime": 1.0, "detalhes": {}})
    monkeypatch.setattr(
        signal_engine,
        "_confirmacao_multi_timeframe",
        lambda *args, **kwargs: {
            "janelas": {},
            "score_buy": 1,
            "score_sell": 0,
            "score_direcional": 0.22,
            "permitir_buy": False,
            "permitir_sell": False,
            "confirmado": False,
            "acao_dominante": "BUY",
            "retorno_medio": 0.0003,
        },
    )
    monkeypatch.setattr(
        signal_engine,
        "preditor_end_to_end",
        lambda **kwargs: {
            "y_hat": 100.08,
            "y_cal": 100.12,
            "p_conf": 0.82,
            "direcao": "BUY",
            "decisao": {
                "score_numerico": 0.42,
                "variacao_prevista": 0.0012,
                "llm": {"sentimento_noticias": 0.25, "score_direcional": 0.24},
            },
        },
    )
    monkeypatch.setattr(
        signal_engine,
        "gerar_sinal_meta",
        lambda *args, **kwargs: {
            "simbolo": "BTCUSDT",
            "estrategia": "volatility_scalping",
            "regime": "LOW_VOL",
            "acao": "BUY",
            "confianca": 0.74,
            "stop_loss_pct": 0.002,
            "take_profit_pct": 0.006,
            "motivo": "microtrade",
        },
    )
    monkeypatch.setattr(signal_engine, "ProbabilisticTradeEngine", _PTEFake)

    sinal = gerar_sinal_orquestrado(
        simbolo="BTCUSDT",
        klines=_klines_tendencia_alta(),
        livro_topo={"bid_price": 100.0, "bid_qty": 2.0, "ask_price": 100.01, "ask_qty": 2.0},
        noticias=[],
        saldo={"saldo_total": 300.0, "saldo_livre": 300.0},
        ajustes_sinal={
            "signal_min_net_profit_pct": 0.0004,
            "signal_min_ev": 0.0005,
            "signal_min_prob": 0.56,
        },
    )

    assert sinal["acao"] == "BUY"
    assert "confirmacao_multi_timeframe_superada_por_consenso" in sinal["motivo"]
