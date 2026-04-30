# Estrategias

## Papel

Conter estrategias elementares, cada uma especialista em um tipo de contexto.

## Arquivos e funcoes

- `base.py`
  - `clamp`: limite numerico reutilizavel.
  - `montar_sinal`: padroniza a estrutura do sinal retornado por qualquer estrategia.
- `momentum.py`
  - `gerar_sinal_momentum`: favorece continuidade de movimento.
- `mean_reversion.py`
  - `gerar_sinal_mean_reversion`: busca retorno a media.
- `breakout.py`
  - `gerar_sinal_breakout`: reage a rompimento de faixa.
- `volatility_scalping.py`
  - `gerar_sinal_volatility_scalping`: procura movimentos curtos com volatilidade suficiente.

## Razao logica

As estrategias ficam separadas para que o `meta_strategy` escolha a melhor conforme o regime, sem misturar heuristicas opostas dentro de uma funcao unica gigante.
