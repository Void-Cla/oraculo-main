# Tarefas

## Papel

Executar rotinas assíncronas e loops de previsao desacoplados da API.

## Arquivo

- `tarefas_previsao.py`
  - `_klines_brutos_de_registros` e `_payload_ohlcv_de_klines`: adaptadores entre formatos;
  - `_persistir_base_mercado`: grava mercado e features;
  - `_auditar_previsao`: registra o evento previsao;
  - `verificar_outcome_apos_atraso`: mede resultado real apos atraso configurado;
  - `gerar_previsao_por_klines`: pipeline completo a partir de dados fornecidos;
  - `gerar_previsao_dados_persistidos`: pipeline a partir do banco;
  - `loop_previsao`: varre os simbolos monitorados continuamente.

## Razao logica

Loop, atraso de outcome e persistencia recorrente nao devem ficar presos ao request HTTP. Essa pasta separa o tempo do mercado do tempo da API.
