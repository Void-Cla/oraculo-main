from __future__ import annotations

"""Filtro determinístico de expected value líquido em USDT."""

import math


def _validar_probabilidade(valor: float, nome: str) -> float:
    numero = float(valor)
    if not math.isfinite(numero) or numero < 0.0 or numero > 1.0:
        raise ValueError(f"{nome}_invalida")
    return numero


def _validar_valor_nao_negativo(valor: float, nome: str) -> float:
    numero = float(valor)
    if not math.isfinite(numero) or numero < 0.0:
        raise ValueError(f"{nome}_invalido")
    return numero


def calcular_ev_liquido(
    prob_up: float,
    prob_down: float,
    ganho_bruto_usdt: float,
    perda_bruta_usdt: float,
    valor_ordem_usdt: float,
    *,
    taxa_maker_pct: float = 0.075,
    taxa_taker_pct: float = 0.075,
    slippage_pct: float = 0.05,
    usar_taker: bool = True,
) -> float:
    """Calcula EV líquido em USDT descontando taxa de entrada, saída e slippage."""
    prob_up = _validar_probabilidade(prob_up, "prob_up")
    prob_down = _validar_probabilidade(prob_down, "prob_down")
    ganho = _validar_valor_nao_negativo(ganho_bruto_usdt, "ganho_bruto_usdt")
    perda = _validar_valor_nao_negativo(perda_bruta_usdt, "perda_bruta_usdt")
    valor_ordem = _validar_valor_nao_negativo(valor_ordem_usdt, "valor_ordem_usdt")
    taxa_pct = _validar_valor_nao_negativo(taxa_taker_pct if usar_taker else taxa_maker_pct, "taxa_pct") / 100.0
    slippage = _validar_valor_nao_negativo(slippage_pct, "slippage_pct") / 100.0

    custo_taxa = valor_ordem * taxa_pct * 2.0
    custo_slippage = valor_ordem * slippage
    ev_bruto = (prob_up * ganho) - (prob_down * perda)
    return ev_bruto - custo_taxa - custo_slippage


def sinal_passa_filtro_ev(
    prob_up: float,
    prob_down: float,
    ganho_bruto_usdt: float,
    perda_bruta_usdt: float,
    valor_ordem_usdt: float,
    *,
    ev_minimo_usdt: float = 1.0,
    taxa_maker_pct: float = 0.075,
    taxa_taker_pct: float = 0.075,
    slippage_pct: float = 0.05,
    usar_taker: bool = True,
) -> tuple[bool, float]:
    """Retorna se o EV líquido supera o mínimo configurado."""
    ev = calcular_ev_liquido(
        prob_up=prob_up,
        prob_down=prob_down,
        ganho_bruto_usdt=ganho_bruto_usdt,
        perda_bruta_usdt=perda_bruta_usdt,
        valor_ordem_usdt=valor_ordem_usdt,
        taxa_maker_pct=taxa_maker_pct,
        taxa_taker_pct=taxa_taker_pct,
        slippage_pct=slippage_pct,
        usar_taker=usar_taker,
    )
    return ev >= float(ev_minimo_usdt), ev
