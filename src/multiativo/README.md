# Multiativo

## Papel

Adicionar uma camada de leitura cruzada entre pares, capital, taxas e arbitragem sem duplicar o pipeline central de previsao.

## Arquivos e funcoes

- `config.py`
  - define ativos, pares monitorados, rotas triangulares e validacao de simbolo.
- `fee_optimizer.py`
  - `_taxa_decimal` e `montar_perfil_taxas`: consolidam taxa nominal e taxa efetiva com desconto de BNB.
- `capital_manager.py`
  - `calcular_plano_capital`: estima faixa de alocacao por trade e notional de referencia.
- `profit_guard.py`
  - `avaliar_profit_guard`: bloqueia operacao sem lucro liquido real suficiente.
- `bnb_manager.py`
  - `avaliar_saldo_bnb`: verifica se o saldo de BNB suporta desconto de taxa e sugere reposicao.
- `opportunity_scanner.py`
  - funcoes `_score_*`: medem volatilidade, volume, momentum, spread e risco.
  - `ranquear_oportunidades`: ordena pares pela qualidade liquida da oportunidade.
- `triangular_arbitrage.py`
  - `avaliar_rotas_triangular`: simula rotas `USDT -> ativo -> ativo -> USDT` com taxa e slippage.
- `orquestrador.py`
  - coleta snapshots por par, consulta noticias, gera sinais, calcula scanner, arbitragem e resumo de carteira.

## Razao logica

Essa pasta existe para nao contaminar `signal_engine.py` com tudo que envolve comparacao entre pares. O sinal continua focado em um simbolo; o scanner multiativo decide onde faz mais sentido olhar primeiro.
