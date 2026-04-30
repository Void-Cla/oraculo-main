"""Backtester simples que simula execução com custos e slippage.
Produz métricas básicas: profit_factor, sharpe (simples), max_drawdown.
"""
from typing import List, Dict
import pandas as pd
import numpy as np


def simular(df: pd.DataFrame, sinais: List[Dict], custo_por_trade: float = 0.0005, slippage: float = 0.0005) -> Dict:
    """df deve conter coluna 'close' indexado por ts. sinais: list de {'ts','acao','tamanho'}"""
    # simples: aplicar sinais sequencialmente
    capital = 1.0
    pos = 0.0
    equity = []
    for s in sinais:
        ts = s['ts']
        acao = s['acao']
        tamanho = s.get('tamanho', 0.0)
        price = df.loc[df['ts'] == ts, 'close']
        if price.empty:
            continue
        price = float(price.iloc[0])
        if acao == 'BUY':
            # comprar
            notional = capital * tamanho
            executed_price = price * (1 + slippage)
            qty = notional / executed_price
            capital = capital - notional - (notional * custo_por_trade)
            pos += qty
        elif acao == 'SELL' and pos > 0:
            executed_price = price * (1 - slippage)
            proceeds = pos * executed_price
            capital = capital + proceeds - (proceeds * custo_por_trade)
            pos = 0
        equity.append(capital + pos * price)

    serie = pd.Series(equity)
    returns = serie.pct_change().dropna()
    pf = serie[serie > serie.shift(1)].sum() / abs(serie[serie < serie.shift(1)].sum()) if not serie.empty else 0
    sharpe = returns.mean() / (returns.std() + 1e-9) * np.sqrt(252) if not returns.empty else 0
    drawdown = (serie.cummax() - serie).max() if not serie.empty else 0
    return {'equity_final': float(serie.iloc[-1]) if not serie.empty else float(capital), 'profit_factor': float(pf), 'sharpe': float(sharpe), 'max_drawdown': float(drawdown)}
