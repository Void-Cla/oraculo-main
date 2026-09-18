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


def _klines_mercado_plano():
    """Preço parado (sem movimento/edge) — gera EV líquido NEGATIVO (custo > sinal),
    o cenário mais comum em produção (a maioria dos ciclos não tem oportunidade real).
    Usado para provar o GATE DE MOMENTO CRÍTICO (DA-30): a IA não deve ser consultada aqui."""
    klines = []
    for idx in range(1, 31):
        close = 100.0
        klines.append([idx, close - 0.01, close + 0.01, close - 0.01, close, 20.0])
    return klines


async def test_signal_engine_gera_sinal_com_regime_e_estrategia():
    klines = _klines_tendencia_alta()
    sinal = await gerar_sinal_orquestrado(
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


def _klines_subida_suave_012pct():
    """+0.12% em TODAS as janelas (1/5/10/15m): abaixo do limiar padrão de janela (0.15%)
    e acima do limiar relaxado do modo exploração (0.08%)."""
    klines = [[idx, 100.0, 100.2, 99.8, 100.0, 20.0] for idx in range(1, 30)]
    klines.append([30, 100.0, 100.3, 99.9, 100.12, 20.0])
    return klines


async def test_confirmacao_multi_timeframe_limiar_de_janela_parametrizavel():
    """`signal_janela_limiar_pct` (escrito pelo modo exploração testnet — decisão do dono,
    2026-07-12) relaxa a classificação UP/FLAT das janelas SEM tocar o default de produção:
    sem o ajuste, 0.12% segue FLAT (bloqueia BUY); com 0.08%, vira UP nas 4 janelas."""
    klines = _klines_subida_suave_012pct()
    livro = {"bid_price": 100.11, "bid_qty": 5.0, "ask_price": 100.13, "ask_qty": 4.0}

    padrao = await gerar_sinal_orquestrado(
        simbolo="BTCUSDT",
        klines=klines,
        livro_topo=livro,
        saldo={"saldo_total": 1000.0, "saldo_livre": 900.0},
    )
    assert padrao["confirmacao_multi_timeframe"]["permitir_buy"] is False  # 0.12% < 0.15% → FLAT

    relaxado = await gerar_sinal_orquestrado(
        simbolo="BTCUSDT",
        klines=klines,
        livro_topo=livro,
        saldo={"saldo_total": 1000.0, "saldo_livre": 900.0},
        ajustes_sinal={"signal_confirm_threshold": 1, "signal_janela_limiar_pct": 0.0008},
    )
    confirmacao = relaxado["confirmacao_multi_timeframe"]
    assert confirmacao["score_buy"] == 4          # 0.12% ≥ 0.08% → UP nas 4 janelas
    assert confirmacao["permitir_buy"] is True


async def test_signal_engine_repassa_parametros_probabilisticos_personalizados(monkeypatch):
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

    sinal = await gerar_sinal_orquestrado(
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


async def test_signal_engine_usa_ev_probabilistico_para_validar_microtrade(monkeypatch):
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

    sinal = await gerar_sinal_orquestrado(
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


# ── Voto direcional de peso igual da IA (Parte C — wiring async ponta a ponta) ──────────────
async def test_signal_engine_sem_analista_ia_usa_voto_neutro_default():
    """Sem `analista_ia` injetado (comportamento padrão, sem GEMINI_API_KEY) — a fonte
    "ia_gemini" deve existir no consenso com voto neutro (confianca=0.0), preservando o
    comportamento anterior à mudança de arquitetura."""
    sinal = await gerar_sinal_orquestrado(
        simbolo="BTCUSDT",
        klines=_klines_tendencia_alta(),
        livro_topo={"bid_price": 117.89, "bid_qty": 5.0, "ask_price": 117.91, "ask_qty": 4.0},
        noticias=[],
        saldo={"saldo_total": 1000.0, "saldo_livre": 900.0},
    )
    assert sinal["voto_ia"]["acao"] == "HOLD"
    assert sinal["voto_ia"]["confianca"] == 0.0
    assert sinal["voto_ia"]["fonte"] == "indisponivel"
    fontes = {f["nome"]: f for f in sinal["consenso"]["fontes"]}
    assert "ia_gemini" in fontes
    assert fontes["ia_gemini"]["score"] == 0.0


async def test_signal_engine_com_analista_ia_propaga_voto_para_consenso():
    """Com `analista_ia` injetado (mock, sem rede real) — o voto direcional deve chegar ao
    consenso com o score/confiança reportados pela IA, provando o wiring assíncrono ponta a
    ponta (signal_engine → AnalistaMercadoIA.avaliar_direcional → consolidar_decisao)."""
    from src.intelligence.market_analyst import VotoIA

    class _AnalistaFake:
        async def avaliar_direcional(self, *, simbolo, sinal_mecanico=None, saldo=0.0, noticias=None):
            assert sinal_mecanico is not None  # é passado, mas o fake não precisa usá-lo
            return VotoIA(acao="BUY", score_direcional=0.8, confianca=0.9, rationale="teste", fonte="gemini", sentimento_mercado=0.4)

    sinal = await gerar_sinal_orquestrado(
        simbolo="BTCUSDT",
        klines=_klines_tendencia_alta(),
        livro_topo={"bid_price": 117.89, "bid_qty": 5.0, "ask_price": 117.91, "ask_qty": 4.0},
        noticias=[],
        saldo={"saldo_total": 1000.0, "saldo_livre": 900.0},
        analista_ia=_AnalistaFake(),
    )
    assert sinal["voto_ia"]["acao"] == "BUY"
    assert sinal["voto_ia"]["confianca"] == pytest.approx(0.9)
    fontes = {f["nome"]: f for f in sinal["consenso"]["fontes"]}
    assert fontes["ia_gemini"]["score"] == pytest.approx(0.8 * 0.9)
    assert fontes["ia_gemini"]["peso"] == fontes["estrategia"]["peso"]  # peso nominal igual


async def test_signal_engine_sem_ev_acionavel_nao_consulta_ia():
    """GATE DE MOMENTO CRÍTICO (DA-30): mercado plano ⇒ EV líquido mecânico não passa do
    piso `signal_min_ev` ⇒ `avaliar_direcional` NUNCA é chamado (economiza cota de IA nos
    ciclos sem oportunidade real, que são a maioria). O voto permanece neutro/indisponível
    — mesmo resultado de "sem analista_ia", mas por motivo diferente (gate, não ausência)."""
    chamadas = {"n": 0}

    class _AnalistaEspiao:
        async def avaliar_direcional(self, *, simbolo, sinal_mecanico=None, saldo=0.0, noticias=None):
            chamadas["n"] += 1
            from src.intelligence.market_analyst import VotoIA

            return VotoIA(acao="BUY", score_direcional=0.9, confianca=0.9, fonte="gemini")

    sinal = await gerar_sinal_orquestrado(
        simbolo="BTCUSDT",
        klines=_klines_mercado_plano(),
        livro_topo={"bid_price": 99.99, "bid_qty": 5.0, "ask_price": 100.01, "ask_qty": 4.0},
        noticias=[],
        saldo={"saldo_total": 1000.0, "saldo_livre": 900.0},
        analista_ia=_AnalistaEspiao(),
    )

    pt = sinal["probabilidade_trade"]
    assert max(float(pt.get("ev_buy", 0.0)), float(pt.get("ev_sell", 0.0))) <= 0.0001  # sem EV acionável
    assert chamadas["n"] == 0  # a IA NÃO foi consultada
    assert sinal["voto_ia"]["acao"] == "HOLD"
    assert sinal["voto_ia"]["confianca"] == 0.0
    assert sinal["voto_ia"]["fonte"] == "indisponivel"


async def test_signal_engine_com_ev_acionavel_consulta_ia():
    """Contraprova do gate: quando o EV mecânico JÁ é acionável (tendência clara), a IA
    é sim consultada — o gate filtra por qualidade do sinal, não desliga a camada agêntica."""
    chamadas = {"n": 0}

    class _AnalistaEspiao:
        async def avaliar_direcional(self, *, simbolo, sinal_mecanico=None, saldo=0.0, noticias=None):
            chamadas["n"] += 1
            from src.intelligence.market_analyst import VotoIA

            return VotoIA(acao="BUY", score_direcional=0.8, confianca=0.9, fonte="gemini")

    sinal = await gerar_sinal_orquestrado(
        simbolo="BTCUSDT",
        klines=_klines_tendencia_alta(),
        livro_topo={"bid_price": 117.89, "bid_qty": 5.0, "ask_price": 117.91, "ask_qty": 4.0},
        noticias=[],
        saldo={"saldo_total": 1000.0, "saldo_livre": 900.0},
        analista_ia=_AnalistaEspiao(),
    )

    pt = sinal["probabilidade_trade"]
    assert max(float(pt.get("ev_buy", 0.0)), float(pt.get("ev_sell", 0.0))) > 0.0001
    assert chamadas["n"] == 1  # a IA FOI consultada — havia oportunidade mecânica real


async def test_signal_engine_gate_respeita_piso_customizado_de_ev(monkeypatch):
    """`signal_min_ev` customizado via `ajustes_sinal` recalibra o gate (mesmo piso usado
    pelo gate de EV mecânico — não é uma constante nova e desalinhada)."""
    chamadas = {"n": 0}

    class _AnalistaEspiao:
        async def avaliar_direcional(self, *, simbolo, sinal_mecanico=None, saldo=0.0, noticias=None):
            chamadas["n"] += 1
            from src.intelligence.market_analyst import VotoIA

            return VotoIA(acao="HOLD", score_direcional=0.0, confianca=0.1, fonte="gemini")

    # Piso ABSURDAMENTE alto — nem a tendência de alta (EV~0.004) deve passar.
    await gerar_sinal_orquestrado(
        simbolo="BTCUSDT",
        klines=_klines_tendencia_alta(),
        livro_topo={"bid_price": 117.89, "bid_qty": 5.0, "ask_price": 117.91, "ask_qty": 4.0},
        noticias=[],
        saldo={"saldo_total": 1000.0, "saldo_livre": 900.0},
        ajustes_sinal={"signal_min_ev": 10.0},
        analista_ia=_AnalistaEspiao(),
    )
    assert chamadas["n"] == 0


async def test_signal_engine_analista_ia_com_falha_nao_derruba_o_sinal(monkeypatch):
    """Se `analista_ia.avaliar_direcional` lançar (bug no mock/implementação externa), o
    sinal mecânico ainda deve ser gerado normalmente (fail-safe belt-and-suspenders em
    signal_engine, além do fail-safe interno do AnalistaMercadoIA)."""

    class _AnalistaQuebrado:
        async def avaliar_direcional(self, **kwargs):
            raise RuntimeError("falha inesperada no analista")

    sinal = await gerar_sinal_orquestrado(
        simbolo="BTCUSDT",
        klines=_klines_tendencia_alta(),
        livro_topo={"bid_price": 117.89, "bid_qty": 5.0, "ask_price": 117.91, "ask_qty": 4.0},
        noticias=[],
        saldo={"saldo_total": 1000.0, "saldo_livre": 900.0},
        analista_ia=_AnalistaQuebrado(),
    )
    assert sinal["voto_ia"]["acao"] == "HOLD"
    assert sinal["voto_ia"]["confianca"] == 0.0
    assert "acao" in sinal  # o sinal mecanico foi gerado normalmente, apesar da falha na IA


async def test_signal_engine_nao_mata_compra_forte_por_multi_timeframe_parcial(monkeypatch):
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

    sinal = await gerar_sinal_orquestrado(
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
