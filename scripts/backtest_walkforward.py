"""Runner do backtester WALK-FORWARD com contabilidade de lucro LÍQUIDO (QNT).

Para cada símbolo × horizonte: monta (features, retorno futuro), roda walk-forward
out-of-sample e reporta o resultado SEMPRE LÍQUIDO (bruto − todas as taxas round-trip).

Demonstra a matemática do usuário: p/ sobrar `ALVO_LIQUIDO_USDT` livre, o trade precisa
render bruto = alvo + custo. Só entra trade cujo bruto previsto cobre alvo + custo.

Uso:  DB_PATH=./dados/oraculo.sqlite python scripts/backtest_walkforward.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backtester.walk_forward import (  # noqa: E402
    backtest_walk_forward,
    bruto_necessario_para_liquido_usdt,
    custo_pct_round_trip,
)
from src.modelagem.gerenciador_modelo import FEATURE_ORDER  # noqa: E402

HORIZONTES = (5, 15, 30, 60)
FEE = 0.001        # taxa por perna (taker base ~0.1%)
SLIPPAGE = 0.0005  # decimal
ALVOS_LIQUIDOS_PCT = (0.0, 0.001, 0.002)  # alvo líquido por trade: break-even, 0.1%, 0.2%
MIN_TREINO = 400
NOTIONAL_EXEMPLO = 12.0
ALVO_LIQUIDO_USDT_EXEMPLO = 1.0
# Só grava o registro de edge durável quando ATUALIZAR_EDGE=1 (rodar o backtest é seguro p/ inspeção;
# escrever no gate de produção é uma ação explícita). Sem edge, o registro fica fechado (fail-safe).
_ATUALIZAR_EDGE = os.getenv("ATUALIZAR_EDGE", "0").strip() in {"1", "true", "True"}


def _carregar(con: sqlite3.Connection, simbolo: str, horizonte: int):
    closes = {int(r[0]): float(r[1]) for r in con.execute(
        "SELECT ts, close FROM ohlcv_1m WHERE simbolo=? ORDER BY ts", (simbolo,))}
    ts_ord = sorted(closes)
    idx = {t: i for i, t in enumerate(ts_ord)}
    X, y = [], []
    for ts, fjson in con.execute(
        "SELECT ts, features_json FROM features_1m WHERE simbolo=? ORDER BY ts", (simbolo,)):
        t = int(ts)
        i = idx.get(t)
        if i is None or i + horizonte >= len(ts_ord):
            continue
        c0 = closes[t]
        c1 = closes[ts_ord[i + horizonte]]
        if c0 <= 0:
            continue
        f = json.loads(fjson)
        X.append([float(f.get(k, 0.0) or 0.0) for k in FEATURE_ORDER])
        y.append((c1 - c0) / c0)
    return np.asarray(X), np.asarray(y)


def main() -> None:
    db = os.path.abspath(os.getenv("DB_PATH", "./dados/oraculo.sqlite"))
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    simbolos = [r[0] for r in con.execute("SELECT DISTINCT simbolo FROM features_1m ORDER BY simbolo")]
    custo = custo_pct_round_trip(FEE, SLIPPAGE)
    print(f"DB={db}\nsimbolos={simbolos}")
    print(f"custo round-trip = {custo:.4%} do notional (taxa {FEE:.3%}/perna ×2 + slippage {SLIPPAGE:.3%} ×2)")
    bruto_ex = bruto_necessario_para_liquido_usdt(ALVO_LIQUIDO_USDT_EXEMPLO, NOTIONAL_EXEMPLO, FEE, SLIPPAGE)
    print(
        f"MATEMÁTICA DO ALVO LÍQUIDO: p/ sobrar {ALVO_LIQUIDO_USDT_EXEMPLO:.2f} USDT LIVRE em notional "
        f"{NOTIONAL_EXEMPLO:.2f}, o trade precisa render BRUTO {bruto_ex:.4f} USDT "
        f"(custo {bruto_ex - ALVO_LIQUIDO_USDT_EXEMPLO:.4f} são taxas, NÃO lucro).\n"
    )

    print(f"{'simbolo':10} {'h':>3} {'alvoLiq':>8} {'trades':>7} {'IC_wf':>7} {'netLiq/trade':>13} {'win%':>6} {'maxDD':>7} edge")
    achou = False
    resultados = []
    for s in simbolos:
        for h in HORIZONTES:
            X, y = _carregar(con, s, h)
            if len(y) < MIN_TREINO + 5:
                continue
            for alvo in ALVOS_LIQUIDOS_PCT:
                r = backtest_walk_forward(
                    X, y, simbolo=s, horizonte=h, fee=FEE, slippage=SLIPPAGE,
                    alvo_liquido_pct=alvo, min_treino=MIN_TREINO,
                )
                resultados.append(r)
                achou = achou or r.tem_edge_liquido
                flag = "✅" if r.tem_edge_liquido else ""
                print(f"{s:10} {h:>3} {alvo:>8.4f} {r.n_trades:>7} {r.ic_walk_forward:>7.4f} "
                      f"{r.retorno_liquido_medio_trade:>13.6f} {r.win_rate_liquido:>6.1%} "
                      f"{r.max_drawdown:>7.4f} {flag}")
    con.close()
    print("\nVEREDITO:", "EDGE LÍQUIDO walk-forward em ≥1 config ✅" if achou
          else "NENHUM edge líquido walk-forward — net/trade ≤ 0 após custos. Não operar p/ lucro.")

    # Persiste o veredito no REGISTRO DE EDGE durável — rodar o backtest CONFIGURA o gate do bot.
    # Sem edge ⇒ registro fica fechado ⇒ entrada real bloqueada (fail-safe). Com edge ⇒ libera
    # automaticamente o símbolo aprovado para conta real (dentro da janela de frescor).
    if not _ATUALIZAR_EDGE:
        print("\n(edge não atualizado — ATUALIZAR_EDGE!=1)")
        return
    import asyncio

    from src.risco.edge_config import persistir_resultados_edge

    resumo = asyncio.run(persistir_resultados_edge(resultados))
    aprovados = resumo.get("simbolos_aprovados_para_real") or []
    print(f"\nREGISTRO DE EDGE atualizado: aprovados p/ conta real = {aprovados or 'NENHUM (fail-safe)'}")


if __name__ == "__main__":
    main()
