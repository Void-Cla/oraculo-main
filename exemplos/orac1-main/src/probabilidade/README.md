# Probabilidade

## Papel

Traduzir previsao numerica em probabilidade operavel e valor esperado.

## Arquivos

- `probability_calibrator.py`
  - `ProbabilityCalibrator`: calibra probabilidade de alta e baixa.
- `ev_calculator.py`
  - `EVCalculator`: calcula EV descontando custo e spread.
- `trade_selector.py`
  - `TradeSelector`: decide entre `BUY`, `SELL` e `HOLD`.
- `probabilistic_engine.py`
  - `ProbabilisticTradeEngine`: junta calibracao, EV e seletor final.

## Razao logica

Uma previsao de preco sozinha nao responde se a operacao vale a pena. Essa pasta existe para transformar previsao em vantagem estatistica explicita.
