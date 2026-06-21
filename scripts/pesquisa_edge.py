"""Harness de pesquisa de EDGE — mede honestamente se o modelo prevê retorno futuro.

Para cada símbolo e horizonte: monta features (de features_1m) + alvo (retorno futuro de
ohlcv_1m), faz split temporal (out-of-sample), treina HistGradientBoosting e reporta:
  - IC (Spearman) entre predição e retorno real  [>0.05 útil; <0 pior que aleatório]
  - acurácia direcional                            [>50% = melhor que cara/coroa]
  - retorno médio/trade líquido de fee round-trip

Uso:  DB_PATH=./dados/oraculo.sqlite python scripts/pesquisa_edge.py
NÃO faz deploy de modelo — é só avaliação. A decisão de operar depende de IC>0 estável.
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

from src.modelagem.gerenciador_modelo import FEATURE_ORDER  # noqa: E402
from src.observabilidade.qualidade_sinal import calcular_ic  # noqa: E402

HORIZONTES = (1, 3, 5, 15, 30, 60)
FEE_ROUND_TRIP = 0.0012 * 2  # taxa testnet round-trip (taker estimado) — veredito principal
# Sensibilidade de fee: quanto custa o round-trip em cada cenário realista.
FEES_CENARIOS = {
    "taker_est_0.24%": 0.0012 * 2,   # estimativa testnet
    "taker_base_0.20%": 0.0010 * 2,  # taker spot base
    "bnb_0.15%": 0.00075 * 2,        # com desconto BNB (-25%) — alavanca nº1
}
MIN_AMOSTRAS = 400


def _carregar(con: sqlite3.Connection, simbolo: str) -> tuple[np.ndarray, dict[int, float], list[int]]:
    closes = {int(r[0]): float(r[1]) for r in con.execute(
        "SELECT ts, close FROM ohlcv_1m WHERE simbolo=? ORDER BY ts", (simbolo,))}
    ts_ord = sorted(closes)
    feats = list(con.execute(
        "SELECT ts, features_json FROM features_1m WHERE simbolo=? ORDER BY ts", (simbolo,)))
    return feats, closes, ts_ord


def avaliar(con: sqlite3.Connection, simbolo: str, horizonte: int) -> dict | None:
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import RobustScaler

    feats, closes, ts_ord = _carregar(con, simbolo)
    idx = {t: i for i, t in enumerate(ts_ord)}
    X, y = [], []
    for ts, fjson in feats:
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
    if len(y) < MIN_AMOSTRAS:
        return None
    X = np.asarray(X)
    y = np.asarray(y)
    k = int(len(y) * 0.8)
    pipe = Pipeline([("sc", RobustScaler()), ("est", HistGradientBoostingRegressor(random_state=42))])
    pipe.fit(X[:k], y[:k])
    pred = pipe.predict(X[k:])
    real = y[k:]
    ic = calcular_ic(pred.tolist(), real.tolist())
    dir_acc = float(np.mean(np.sign(pred) == np.sign(real)))
    ret_bruto = float((np.sign(pred) * real).mean())  # antes de fee
    ret_trade = ret_bruto - FEE_ROUND_TRIP
    net_por_fee = {nome: round(ret_bruto - fee, 6) for nome, fee in FEES_CENARIOS.items()}
    return {
        "simbolo": simbolo,
        "horizonte": horizonte,
        "amostras": len(y),
        "ic": round(ic, 4),
        "acc_direcional": round(dir_acc, 4),
        "ret_bruto_trade": round(ret_bruto, 6),
        "ret_medio_trade_liq": round(ret_trade, 6),
        "net_por_fee": net_por_fee,
        # Fee máximo round-trip que o sinal aguenta e ainda fica positivo (bruto > fee).
        "fee_breakeven": round(ret_bruto, 6),
        "tem_edge": ic > 0.05 and dir_acc > 0.52 and ret_bruto > min(FEES_CENARIOS.values()),
    }


def main() -> None:
    db = os.path.abspath(os.getenv("DB_PATH", "./dados/oraculo.sqlite"))
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    simbolos = [r[0] for r in con.execute(
        "SELECT DISTINCT simbolo FROM features_1m ORDER BY simbolo")]
    print(f"DB={db}\nsimbolos={simbolos}\n")
    cab = f"{'simbolo':10} {'h':>3} {'amostras':>8} {'IC':>8} {'acc_dir':>8} {'bruto':>9}"
    for nome in FEES_CENARIOS:
        cab += f" {nome:>16}"
    cab += " edge"
    print(cab)
    achou = False
    melhor = None
    for s in simbolos:
        for h in HORIZONTES:
            r = avaliar(con, s, h)
            if r is None:
                continue
            achou = achou or r["tem_edge"]
            if melhor is None or r["ret_bruto_trade"] > melhor["ret_bruto_trade"]:
                melhor = r
            flag = "✅" if r["tem_edge"] else ""
            linha = (f"{r['simbolo']:10} {r['horizonte']:>3} {r['amostras']:>8} "
                     f"{r['ic']:>8.4f} {r['acc_direcional']:>8.2%} {r['ret_bruto_trade']:>9.5f}")
            for nome in FEES_CENARIOS:
                linha += f" {r['net_por_fee'][nome]:>16.5f}"
            linha += f" {flag}"
            print(linha)
    con.close()
    if melhor:
        print(f"\nMelhor sinal bruto: {melhor['simbolo']} h{melhor['horizonte']} "
              f"ret_bruto/trade={melhor['ret_bruto_trade']:.5f} (fee_breakeven={melhor['fee_breakeven']:.5f}) "
              f"IC={melhor['ic']:.4f} acc={melhor['acc_direcional']:.2%}")
    print("VEREDITO:", "EDGE encontrado em ≥1 config (bruto > menor fee) ✅" if achou
          else "NENHUM edge — nem com fee BNB (0,15%) o sinal bruto cobre o custo. Focar em features/dados/horizonte.")


if __name__ == "__main__":
    main()
