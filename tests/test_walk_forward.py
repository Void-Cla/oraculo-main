import numpy as np
import pytest

from src.backtester.walk_forward import (
    backtest_walk_forward,
    bruto_necessario_para_liquido_pct,
    bruto_necessario_para_liquido_usdt,
    custo_pct_round_trip,
    liquido_de_bruto_pct,
)


# ── Matemática do lucro LÍQUIDO (o ponto do usuário: bruto = líquido + taxas) ──────────
def test_custo_round_trip_e_duas_pernas():
    # (fee + slippage) * 2 + spread
    assert custo_pct_round_trip(0.001, 0.0005) == pytest.approx(0.003)
    assert custo_pct_round_trip(0.001, 0.0005, spread=0.0002) == pytest.approx(0.0032)


def test_bruto_necessario_usdt_separa_lucro_de_taxa():
    # Para sobrar 1.00 USDT LÍQUIDO em notional 1000, com custo 0.2% (=2.00 USDT de taxa):
    bruto = bruto_necessario_para_liquido_usdt(1.0, 1000.0, fee=0.001, slippage=0.0)
    assert bruto == pytest.approx(3.0)           # 1.00 livre + 2.00 de taxa
    assert bruto - 1.0 == pytest.approx(2.0)     # a parte de taxa NÃO é lucro


def test_bruto_e_liquido_sao_inversos():
    bruto = bruto_necessario_para_liquido_pct(0.001, fee=0.001, slippage=0.0005)  # 0.001 + 0.003
    assert bruto == pytest.approx(0.004)
    assert liquido_de_bruto_pct(bruto, fee=0.001, slippage=0.0005) == pytest.approx(0.001)


# ── Motor walk-forward (contabilidade sempre LÍQUIDA) ─────────────────────────────────
def _oraculo(X_tr, y_tr, X_te):
    # Preditor determinístico: a feature 0 É o retorno futuro (testa o motor, não o modelo).
    return X_te[:, 0]


def test_backtest_detecta_edge_quando_move_supera_custo():
    n = 500
    rng = np.random.default_rng(0)
    y = rng.choice([0.01, -0.01], size=n)          # moves de 1% >> custo 0.3%
    X = np.column_stack([y, rng.normal(size=n)])    # feature 0 = retorno futuro
    r = backtest_walk_forward(
        X, y, simbolo="T", horizonte=5, fee=0.001, slippage=0.0005,
        alvo_liquido_pct=0.0, min_treino=400, n_folds=5, treinar_predizer=_oraculo,
    )
    assert r.n_trades > 20
    assert r.retorno_liquido_medio_trade == pytest.approx(0.007, abs=1e-9)  # 0.01 - 0.003
    assert r.win_rate_liquido == 1.0
    assert r.tem_edge_liquido is True


def test_gross_up_bloqueia_entrada_quando_move_nao_cobre_custo():
    # Mesmo prevendo direção PERFEITA, se o move (0.1%) < custo (0.3%), o filtro de entrada
    # (bruto previsto >= alvo + custo) NÃO deixa entrar — não cria perdedor. n_trades=0.
    n = 500
    rng = np.random.default_rng(1)
    y = rng.choice([0.001, -0.001], size=n)
    X = np.column_stack([y, rng.normal(size=n)])
    r = backtest_walk_forward(
        X, y, simbolo="T", horizonte=5, fee=0.001, slippage=0.0005,
        alvo_liquido_pct=0.0, min_treino=400, n_folds=5, treinar_predizer=_oraculo,
    )
    assert r.n_trades == 0
    assert r.tem_edge_liquido is False


def test_contabilidade_liquida_e_negativa_se_forcar_trade_subcusto():
    # Forçando entrada (alvo muito negativo baixa o limiar), o resultado LÍQUIDO é negativo:
    # comprova que o custo é descontado de verdade (move 0.1% - custo 0.3% = -0.2%).
    n = 500
    rng = np.random.default_rng(2)
    y = rng.choice([0.001, -0.001], size=n)
    X = np.column_stack([y, rng.normal(size=n)])
    r = backtest_walk_forward(
        X, y, simbolo="T", horizonte=5, fee=0.001, slippage=0.0005,
        alvo_liquido_pct=-1.0, min_treino=400, n_folds=5, treinar_predizer=_oraculo,
    )
    assert r.n_trades > 20
    assert r.retorno_liquido_medio_trade == pytest.approx(-0.002, abs=1e-9)
    assert r.tem_edge_liquido is False


def test_backtest_dados_insuficientes_retorna_vazio():
    X = np.zeros((50, 2))
    y = np.zeros(50)
    r = backtest_walk_forward(X, y, simbolo="T", horizonte=5, min_treino=400)
    assert r.n_trades == 0
    assert r.n_amostras_teste == 0
