from __future__ import annotations

import os
from typing import Any

from .config import ROTAS_TRIANGULARES


def _extrair_bid_ask(snapshot: dict[str, Any]) -> tuple[float, float]:
    livro = snapshot.get("livro_topo") or {}
    bid = float(livro.get("bid_price", 0.0) or 0.0)
    ask = float(livro.get("ask_price", 0.0) or 0.0)
    return bid, ask


def avaliar_rotas_triangular(
    snapshots: dict[str, dict[str, Any]],
    *,
    notional_inicial_usdt: float,
    taxa_por_perna: float,
    slippage_pct: float,
) -> dict[str, Any]:
    rotas_saida: list[dict[str, Any]] = []
    # Default to 0.01 USDT for micro-trading profitability targets
    lucro_minimo = max(0.0, float(os.getenv("LUCRO_LIQUIDO_MINIMO_USDT", "0.01") or 0.01))
    notional = max(0.0, float(notional_inicial_usdt or 0.0))

    for rota in ROTAS_TRIANGULARES:
        quantidade = notional
        legs_saida: list[dict[str, Any]] = []
        motivo_bloqueio = None
        for leg in rota["legs"]:
            snapshot = snapshots.get(leg["simbolo"]) or {}
            bid, ask = _extrair_bid_ask(snapshot)
            if bid <= 0.0 or ask <= 0.0:
                motivo_bloqueio = f"livro_incompleto_{leg['simbolo'].lower()}"
                break

            if leg["tipo"] == "buy_base":
                preco = ask * (1.0 + slippage_pct)
                quantidade = (quantidade / preco) * (1.0 - taxa_por_perna)
            else:
                preco = bid * (1.0 - slippage_pct)
                quantidade = (quantidade * preco) * (1.0 - taxa_por_perna)

            legs_saida.append(
                {
                    "simbolo": leg["simbolo"],
                    "de": leg["from"],
                    "para": leg["to"],
                    "tipo": leg["tipo"],
                    "preco_efetivo": preco,
                    "quantidade_resultante": quantidade,
                }
            )

        lucro = quantidade - notional
        lucro_pct = (lucro / notional) if notional > 0 else 0.0
        valido = motivo_bloqueio is None and lucro > lucro_minimo
        rotas_saida.append(
            {
                "nome": rota["nome"],
                "legs": legs_saida,
                "notional_inicial_usdt": round(notional, 8),
                "usdt_final": round(quantidade, 8),
                "lucro_liquido_usdt": round(lucro, 8),
                "lucro_liquido_pct": round(lucro_pct * 100.0, 6),
                "motivo_bloqueio": motivo_bloqueio,
                "valida": valido,
            }
        )

    rotas_ordenadas = sorted(
        rotas_saida,
        key=lambda item: (bool(item["valida"]), float(item["lucro_liquido_usdt"])),
        reverse=True,
    )
    melhor = rotas_ordenadas[0] if rotas_ordenadas else None
    return {
        "notional_referencia_usdt": round(notional, 8),
        "rotas": rotas_ordenadas,
        "melhor_rota": melhor,
        "oportunidades_validas": sum(1 for item in rotas_ordenadas if item["valida"]),
        "sem_vantagem_real": not any(item["valida"] for item in rotas_ordenadas),
    }
