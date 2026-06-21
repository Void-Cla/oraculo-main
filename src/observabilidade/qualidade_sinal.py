"""Métricas de QUALIDADE de sinal/modelo (FASE 7) — medem se há edge, não só acurácia.

- IC (Information Coefficient): correlação de Spearman entre predição e retorno real.
  IC > 0.05 = sinal utilizável; IC < 0 = pior que aleatório.
- Brier score: erro quadrático médio entre probabilidade e outcome binário (calibração).
  0 = perfeito; 0.25 = modelo nulo (sempre 50%); > 0.25 = pior que aleatório.
- Drawdown máximo: pior queda do pico ao vale — métrica primária de risco de ruína.

Implementado só com numpy (dependência direta) para manter o módulo enxuto e sem acoplar scipy.
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def _rank_medio(valores: np.ndarray) -> np.ndarray:
    """Ranks com média em empates (base correta do Spearman)."""
    ordem = valores.argsort(kind="mergesort")
    ordenados = valores[ordem]
    ranks_ordenados = np.arange(len(valores), dtype=float)
    inicio = 0
    n = len(valores)
    while inicio < n:
        fim = inicio
        while fim + 1 < n and ordenados[fim + 1] == ordenados[inicio]:
            fim += 1
        if fim > inicio:
            ranks_ordenados[inicio : fim + 1] = (inicio + fim) / 2.0
        inicio = fim + 1
    ranks = np.empty(n, dtype=float)
    ranks[ordem] = ranks_ordenados
    return ranks


def calcular_ic(predicoes: Sequence[float], retornos_reais: Sequence[float]) -> float:
    """Information Coefficient (Spearman). Retorna 0.0 para entrada insuficiente/degenerada."""
    p = np.asarray(predicoes, dtype=float)
    r = np.asarray(retornos_reais, dtype=float)
    if p.size < 2 or p.size != r.size:
        return 0.0
    rp, rr = _rank_medio(p), _rank_medio(r)
    if rp.std() == 0.0 or rr.std() == 0.0:
        return 0.0
    return float(np.corrcoef(rp, rr)[0, 1])


def calcular_brier(probabilidades: Sequence[float], outcomes: Sequence[float]) -> float:
    """Brier score = média de (prob - outcome)^2. Outcomes binários (0/1)."""
    p = np.asarray(probabilidades, dtype=float)
    o = np.asarray(outcomes, dtype=float)
    if p.size == 0 or p.size != o.size:
        return 0.0
    return float(np.mean((p - o) ** 2))


def calcular_drawdown_maximo(curva_capital: Sequence[float]) -> float:
    """Pior queda percentual do pico ao vale (0.0 a 1.0)."""
    curva = [float(x) for x in curva_capital]
    if len(curva) < 2:
        return 0.0
    pico = curva[0]
    max_dd = 0.0
    for valor in curva:
        if valor > pico:
            pico = valor
        if pico > 0.0:
            max_dd = max(max_dd, (pico - valor) / pico)
    return max_dd
