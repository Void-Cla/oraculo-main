from __future__ import annotations

from typing import Any

# Hardcoded — sem os.getenv
_MINIMO_PCT_PADRAO: float = 0.0005      # 0.05% mínimo de lucro pct (micro-trading)
_MINIMO_USDT_PADRAO: float = 0.01       # $0.01 USDT — hard floor
_SPREAD_MAXIMO_PADRAO: float = 0.003    # 0.3% spread máximo

# Slippage incide na entrada E na saída (round-trip). A taxa já chega round-trip do chamador. (DA-02)
_NUMERO_DE_PERNAS: int = 2
# Margem de robustez (INC-04): o lucro líquido precisa ter folga sobre o custo de transação
# reconstruído aqui — protege contra erro de estimativa de custo (slippage real > estimado).
# 0.10 = o lucro líquido deve ser ao menos 10% do custo round-trip estimado.
_MARGEM_ROBUSTEZ_CUSTO: float = 0.10


def avaliar_profit_guard(
    *,
    lucro_liquido_pct: float,
    notional_usdt: float,
    spread_rel: float,
    taxas_totais_pct: float,
    slippage_pct: float,
    minimo_pct: float | None = None,
    minimo_usdt: float | None = None,
    spread_maximo: float | None = None,
) -> dict[str, Any]:
    lucro_pct    = float(lucro_liquido_pct or 0.0)
    notional     = max(0.0, float(notional_usdt or 0.0))
    lucro_usdt   = notional * lucro_pct
    min_pct      = max(0.0, float(minimo_pct  if minimo_pct  is not None else _MINIMO_PCT_PADRAO))
    min_usdt     = max(0.0, float(minimo_usdt if minimo_usdt is not None else _MINIMO_USDT_PADRAO))
    spread_max   = max(0.0, float(spread_maximo if spread_maximo is not None else _SPREAD_MAXIMO_PADRAO))

    # Defense in depth (INC-04, PSF-02): o profit_guard NÃO confia cegamente que o chamador
    # descontou os custos corretamente. Reconstrói o custo round-trip a partir dos componentes
    # recebidos e exige que o lucro líquido tenha folga real sobre ele.
    taxa_round_trip = max(0.0, float(taxas_totais_pct or 0.0))          # já chega round-trip do chamador
    slippage_round_trip = max(0.0, float(slippage_pct or 0.0)) * _NUMERO_DE_PERNAS
    custo_round_trip_pct = taxa_round_trip + slippage_round_trip + max(0.0, float(spread_rel or 0.0))
    margem_minima_pct = custo_round_trip_pct * _MARGEM_ROBUSTEZ_CUSTO

    motivos: list[str] = []
    if lucro_pct < min_pct:
        motivos.append("lucro_liquido_pct_abaixo_do_minimo")
    if lucro_usdt < min_usdt:
        motivos.append("lucro_liquido_usdt_abaixo_do_minimo")
    if lucro_pct < margem_minima_pct:
        motivos.append("margem_insuficiente_sobre_custo")
    if float(spread_rel or 0.0) > spread_max:
        motivos.append("spread_alto")
    if notional <= 0.0:
        motivos.append("notional_invalido")

    return {
        "aprovado":         not motivos,
        "motivos":          motivos,
        "lucro_liquido_pct":  lucro_pct,
        "lucro_liquido_usdt": round(lucro_usdt, 8),
        "minimo_pct":       min_pct,
        "minimo_usdt":      min_usdt,
        "spread_rel":       float(spread_rel or 0.0),
        "spread_maximo":    spread_max,
        "taxas_totais_pct": float(taxas_totais_pct or 0.0),
        "slippage_pct":     float(slippage_pct or 0.0),
        "custo_round_trip_pct":  round(custo_round_trip_pct, 10),
        "margem_minima_pct":     round(margem_minima_pct, 10),
    }
