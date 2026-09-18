# Servicos

## Papel

Agrupar orquestracoes de alto nivel que combinam varias camadas sem pertencer a API, persistencia ou estrategia individual.

## Arquivos e responsabilidades

- `dashboard.py`
  - monta o resumo publico do simbolo com mercado, modelos, ordens e historico.
- `painel_conta.py`
  - monta o payload autenticado com conta Binance, PnL, ordens, trades e bloco multiativos.
- `sessoes.py`
  - cria, renova e encerra sessao Binance em memoria.
- `noticias.py`
  - coleta noticias, classifica impacto, faz cache e audita o fetch.
- `llm_analista.py`
  - converte noticias em contexto textual numerico e explicavel.
- `decisor_hibrido.py`
  - combina modelo numerico e leitura contextual numa decisao auditavel.

## Razao logica

Servico e a camada de costura. Ele existe para nao empurrar orquestracao nem para o banco nem para o endpoint.
