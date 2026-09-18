# Calculos

## Papel

Transformar mercado bruto em features numericas consistentes para modelo, sinal e scanner.

## Arquivo

- `gerador_features.py`
  - `_normalizar_klines`: converte listas e dicts em estrutura tabular coerente.
  - `_retorno`: calcula retorno relativo em janela especifica.
  - `_media_movel` e `_ema`: resumem tendencia local.
  - `_volatilidade`: mede ruido recente.
  - `_ts_para_datetime`: converte timestamp para contexto temporal.
  - `_sanear_numero`: remove `NaN`, infinito e entradas quebradas.
  - `calcular_features_1m`: monta o vetor final de features usado pelo sistema.

## Razao logica

Essa pasta existe para impedir que cada modulo recalcule retorno, spread, volume ou book imbalance de forma diferente. Um unico gerador reduz divergencia semantica e melhora treinamento.
