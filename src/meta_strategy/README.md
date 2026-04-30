# Meta Strategy

## Papel

Escolher qual estrategia faz sentido para o regime de mercado atual.

## Arquivos

- `regime_detector.py`
  - `detectar_regime`: classifica o mercado em estados como tendencia, lateralizacao ou volatilidade elevada.
- `meta_controller.py`
  - `selecionar_estrategia`: resolve qual modulo estrategico deve ser usado.
  - `gerar_sinal_meta`: aplica a estrategia escolhida e devolve um sinal padronizado.

## Razao logica

Um mesmo ativo nao se comporta igual o tempo todo. Essa pasta existe para evitar usar momentum em mercado lateral ou mean reversion em rompimento forte por default.
