"""Backtester WALK-FORWARD com matemática de lucro LÍQUIDO correta (QNT).

PRINCÍPIO CENTRAL (a matemática que o usuário pediu para acertar):
  O lucro líquido é o que SOBRA depois de pagar TODAS as taxas. Para realizar um alvo
  líquido (ex.: 1,00 USDT), o trade precisa render BRUTO = alvo_líquido + custo_round_trip
  (ex.: 1,00 + 0,50 = 1,50). Os 0,50 de custo NÃO são lucro — são pedágio (taxa de entrada
  + taxa de saída + slippage nas 2 pernas + spread). Só 1,00 fica realmente livre.

  Por isso: (a) só ENTRA trade cujo ganho bruto ESPERADO cobre alvo_líquido + custo; e
  (b) o resultado SEMPRE contabilizado é o LÍQUIDO (bruto − custo). Nada de inflar P&L.

WALK-FORWARD: treina numa janela passada, testa no futuro imediato e ROLA a janela —
out-of-sample honesto, sem vazamento de futuro. O custo round-trip vem do EVCalculator
(fonte única do projeto, DA-02) para não divergir do caminho vivo (ver INC-07).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np

from src.observabilidade.qualidade_sinal import calcular_drawdown_maximo, calcular_ic
from src.probabilidade.ev_calculator import EVCalculator


# ── Matemática de custo/lucro líquido (QNT — fonte única via EVCalculator) ───────────────
def custo_pct_round_trip(fee: float, slippage: float, spread: float = 0.0) -> float:
    """Custo total round-trip como FRAÇÃO do notional: (fee+slippage)*2 + spread. (DA-02)"""
    return EVCalculator(fee=fee, slippage=slippage).custos_totais(spread)


def bruto_necessario_para_liquido_pct(
    alvo_liquido_pct: float, fee: float, slippage: float, spread: float = 0.0
) -> float:
    """Retorno BRUTO (fração) necessário para sobrar `alvo_liquido_pct` LÍQUIDO após custos."""
    return float(alvo_liquido_pct) + custo_pct_round_trip(fee, slippage, spread)


def liquido_de_bruto_pct(bruto_pct: float, fee: float, slippage: float, spread: float = 0.0) -> float:
    """Lucro LÍQUIDO (fração) a partir do retorno bruto, descontando o custo round-trip."""
    return float(bruto_pct) - custo_pct_round_trip(fee, slippage, spread)


def bruto_necessario_para_liquido_usdt(
    alvo_liquido_usdt: float, notional_usdt: float, fee: float, slippage: float, spread: float = 0.0
) -> float:
    """Versão em USDT do alvo do usuário: quanto BRUTO (USDT) p/ sobrar `alvo_liquido_usdt`.
    Ex.: alvo 1,00 e custo 0,50 → 1,50. Os 0,50 pagam taxas; 1,00 fica livre."""
    custo_usdt = max(0.0, float(notional_usdt)) * custo_pct_round_trip(fee, slippage, spread)
    return float(alvo_liquido_usdt) + custo_usdt


@dataclass
class ResultadoBacktest:
    simbolo: str
    horizonte: int
    n_amostras_teste: int
    n_trades: int
    ic_walk_forward: float
    retorno_liquido_medio_trade: float
    retorno_liquido_total: float
    win_rate_liquido: float
    max_drawdown: float
    custo_pct_round_trip: float
    alvo_liquido_pct: float
    bruto_necessario_pct: float
    tem_edge_liquido: bool

    def resumo(self) -> dict[str, Any]:
        return {
            "simbolo": self.simbolo,
            "horizonte": self.horizonte,
            "n_amostras_teste": self.n_amostras_teste,
            "n_trades": self.n_trades,
            "ic_walk_forward": round(self.ic_walk_forward, 4),
            "retorno_liquido_medio_trade": round(self.retorno_liquido_medio_trade, 6),
            "retorno_liquido_total": round(self.retorno_liquido_total, 6),
            "win_rate_liquido": round(self.win_rate_liquido, 4),
            "max_drawdown": round(self.max_drawdown, 6),
            "custo_pct_round_trip": round(self.custo_pct_round_trip, 6),
            "alvo_liquido_pct": round(self.alvo_liquido_pct, 6),
            "bruto_necessario_pct": round(self.bruto_necessario_pct, 6),
            "tem_edge_liquido": self.tem_edge_liquido,
        }


def _treinar_predizer_padrao(X_tr: np.ndarray, y_tr: np.ndarray, X_te: np.ndarray) -> np.ndarray:
    """Modelo padrão: HistGradientBoosting + RobustScaler (mesmo do harness de edge)."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import RobustScaler

    pipe = Pipeline([("sc", RobustScaler()), ("est", HistGradientBoostingRegressor(random_state=42))])
    pipe.fit(X_tr, y_tr)
    return np.asarray(pipe.predict(X_te), dtype=float)


def backtest_walk_forward(
    X: Sequence[Sequence[float]],
    y: Sequence[float],
    *,
    simbolo: str,
    horizonte: int,
    fee: float = 0.001,
    slippage: float = 0.0005,
    spread: float = 0.0,
    alvo_liquido_pct: float = 0.0,
    n_folds: int = 5,
    min_treino: int = 400,
    treinar_predizer: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray] | None = None,
) -> ResultadoBacktest:
    """Avalia walk-forward com contabilidade LÍQUIDA.

    Entra trade no passo de teste quando |predição| >= bruto_necessário (= alvo + custo);
    o resultado de cada trade é o LÍQUIDO: sinal(pred)*retorno_real − custo_round_trip.
    """
    X_arr = np.asarray(X, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    custo = custo_pct_round_trip(fee, slippage, spread)
    limiar_entrada = bruto_necessario_para_liquido_pct(alvo_liquido_pct, fee, slippage, spread)
    treinar = treinar_predizer or _treinar_predizer_padrao

    n = len(y_arr)
    vazio = ResultadoBacktest(
        simbolo=simbolo, horizonte=horizonte, n_amostras_teste=0, n_trades=0,
        ic_walk_forward=0.0, retorno_liquido_medio_trade=0.0, retorno_liquido_total=0.0,
        win_rate_liquido=0.0, max_drawdown=0.0, custo_pct_round_trip=custo,
        alvo_liquido_pct=alvo_liquido_pct, bruto_necessario_pct=limiar_entrada, tem_edge_liquido=False,
    )
    if n < min_treino + max(1, n_folds):
        return vazio

    # Blocos de teste contíguos após a janela mínima de treino; treino EXPANDE até o bloco.
    inicio_teste = min_treino
    tamanho_bloco = max(1, (n - inicio_teste) // n_folds)
    if tamanho_bloco <= 0:
        return vazio

    preds_all: list[float] = []
    reais_all: list[float] = []
    liquidos_trades: list[float] = []   # P&L líquido por trade efetivamente aberto
    equity: list[float] = [0.0]

    for f in range(n_folds):
        ini = inicio_teste + f * tamanho_bloco
        fim = n if f == n_folds - 1 else min(n, ini + tamanho_bloco)
        if ini >= fim or ini < min_treino:
            continue
        X_tr, y_tr = X_arr[:ini], y_arr[:ini]
        X_te, y_te = X_arr[ini:fim], y_arr[ini:fim]
        if len(y_tr) < min_treino or len(y_te) == 0:
            continue
        try:
            pred = treinar(X_tr, y_tr, X_te)
        except Exception:
            continue
        for p, real in zip(pred, y_te):
            preds_all.append(float(p))
            reais_all.append(float(real))
            if abs(float(p)) >= limiar_entrada:   # só entra se o bruto previsto cobre alvo+custo
                liquido = float(np.sign(p) * real) - custo
                liquidos_trades.append(liquido)
                equity.append(equity[-1] + liquido)

    if not preds_all:
        return vazio

    ic = calcular_ic(preds_all, reais_all)
    n_trades = len(liquidos_trades)
    ret_medio = float(np.mean(liquidos_trades)) if n_trades else 0.0
    ret_total = float(np.sum(liquidos_trades)) if n_trades else 0.0
    win_rate = float(np.mean([1.0 if x > 0 else 0.0 for x in liquidos_trades])) if n_trades else 0.0
    # Drawdown sobre a curva de equity em base 1.0 (evita divisão por zero no pico inicial).
    curva = [1.0 + e for e in equity]
    max_dd = calcular_drawdown_maximo(curva)
    tem_edge = n_trades >= 20 and ret_medio > 0.0 and ic > 0.0

    return ResultadoBacktest(
        simbolo=simbolo, horizonte=horizonte, n_amostras_teste=len(preds_all), n_trades=n_trades,
        ic_walk_forward=ic, retorno_liquido_medio_trade=ret_medio, retorno_liquido_total=ret_total,
        win_rate_liquido=win_rate, max_drawdown=max_dd, custo_pct_round_trip=custo,
        alvo_liquido_pct=alvo_liquido_pct, bruto_necessario_pct=limiar_entrada, tem_edge_liquido=tem_edge,
    )
