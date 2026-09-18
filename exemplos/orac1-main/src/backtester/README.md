# Backtester

## Papel

Executar simulacao offline para validar a qualidade de sinais sem usar conta real.

## Arquivo

- `simple_backtester.py`
  - `simular`: recebe dataframe e lista de sinais, aplica custo por trade e slippage, e devolve uma leitura simplificada de performance.

## Razao logica

Essa pasta existe para separar avaliacao historica de execucao operacional. O backtest nao deve contaminar o fluxo online com atalhos ou suposicoes de mercado em tempo real.
