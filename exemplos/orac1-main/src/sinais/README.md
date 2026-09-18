# Sinais

## Papel

Montar o sinal final de operacao a partir de features, modelo, noticias, probabilidade e confirmacao multi-timeframe.

## Arquivos

- `signal_engine.py`
  - normaliza klines;
  - calcula contexto de mercado;
  - gera confirmacao `1m/5m/10m/15m`;
  - monta janela de decisao;
  - `gerar_sinal_orquestrado` devolve acao, confianca, custos e metadados.
- `fila_sinais.py`
  - `FilaSinaisMemoria`: fila simples de sinais para observacao local.

## Razao logica

Essa pasta existe para evitar que o endpoint HTTP vire um "script gigante". O sinal ja sai daqui pronto para risco, auditoria e executor.
