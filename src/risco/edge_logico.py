"""EDGE LÓGICO — gate determinístico de entrada por-ciclo (o "edge lógico" do usuário).

Diferente do `edge_config` (que diz se há um edge ESTATÍSTICO validado por walk-forward para
arriscar dinheiro real), o EDGE LÓGICO responde, A CADA CICLO, uma pergunta simples e honesta:

    "O movimento LÍQUIDO esperado deste sinal cobre o pedágio (custo round-trip) com uma margem,
     e a confiança é suficiente?"

Matemática do usuário (a regra do 1,00 livre / 0,50 de taxa):
    bruto_esperado = retorno_líquido_esperado + custo_round_trip
    entra  ⇔  retorno_líquido_esperado >= margem_mínima  E  confiança >= confiança_mínima

É PURO (sem I/O), determinístico e testável. O custo round-trip vem do EVCalculator (fonte
única, DA-02), então concorda com o resto do projeto. Trabalha EM CONJUNTO com o veto do
Gemini (que só pode VETAR) e, em conta real, com o `edge_config` (que precisa estar validado).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.settings import env_float
from src.probabilidade.ev_calculator import EVCalculator


def custo_round_trip_pct(fee: float, slippage: float, spread: float = 0.0) -> float:
    """Custo total round-trip como fração do notional: (fee+slippage)*2 + spread (DA-02)."""
    return EVCalculator(fee=fee, slippage=slippage).custos_totais(spread)


def _margem_minima_pct(modo_exploracao: bool) -> float:
    """Margem líquida mínima exigida. Exploração aceita break-even (0); real exige folga."""
    if modo_exploracao:
        return env_float("EDGE_LOGICO_MARGEM_EXPLORACAO_PCT", 0.0)
    return env_float("EDGE_LOGICO_MARGEM_REAL_PCT", 0.0005, minimo=0.0)


def _confianca_minima(modo_exploracao: bool) -> float:
    if modo_exploracao:
        return env_float("EDGE_LOGICO_CONFIANCA_MIN_EXPLORACAO", 0.50, minimo=0.0)
    return env_float("EDGE_LOGICO_CONFIANCA_MIN_REAL", 0.55, minimo=0.0)


@dataclass
class ResultadoEdgeLogico:
    aprovado: bool
    motivo: str
    retorno_liquido_esperado_pct: float
    custo_round_trip_pct: float
    bruto_esperado_pct: float
    margem_minima_pct: float
    confianca: float
    confianca_minima: float
    detalhe: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "aprovado": self.aprovado,
            "motivo": self.motivo,
            "retorno_liquido_esperado_pct": round(self.retorno_liquido_esperado_pct, 6),
            "custo_round_trip_pct": round(self.custo_round_trip_pct, 6),
            "bruto_esperado_pct": round(self.bruto_esperado_pct, 6),
            "margem_minima_pct": round(self.margem_minima_pct, 6),
            "confianca": round(self.confianca, 4),
            "confianca_minima": round(self.confianca_minima, 4),
        }


def avaliar_edge_logico(
    *,
    retorno_liquido_esperado_pct: float,
    confianca: float,
    fee: float,
    slippage: float,
    spread: float = 0.0,
    modo_exploracao: bool,
) -> ResultadoEdgeLogico:
    """Decide se o sinal tem edge lógico para ABRIR posição. NEGA por padrão se não cobrir custo.

    `retorno_liquido_esperado_pct` é o retorno ESPERADO já LÍQUIDO (após custos) do sinal.
    """
    retorno_liq = float(retorno_liquido_esperado_pct or 0.0)
    conf = float(confianca or 0.0)
    custo = custo_round_trip_pct(fee, slippage, spread)
    margem = _margem_minima_pct(modo_exploracao)
    conf_min = _confianca_minima(modo_exploracao)
    bruto = retorno_liq + custo

    def _resultado(aprovado: bool, motivo: str) -> ResultadoEdgeLogico:
        return ResultadoEdgeLogico(
            aprovado=aprovado, motivo=motivo,
            retorno_liquido_esperado_pct=retorno_liq, custo_round_trip_pct=custo,
            bruto_esperado_pct=bruto, margem_minima_pct=margem,
            confianca=conf, confianca_minima=conf_min,
        )

    if conf < conf_min:
        return _resultado(False, "confianca_insuficiente")
    if retorno_liq < margem:
        # Movimento líquido esperado não cobre a margem mínima sobre o custo round-trip.
        return _resultado(False, "retorno_liquido_nao_cobre_custo_mais_margem")
    return _resultado(True, "edge_logico_ok")
