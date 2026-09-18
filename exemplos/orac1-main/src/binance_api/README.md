# Binance API

## Papel

Isolar todo contato com Binance em uma camada unica, com retry, timeout e fallback previsivel.

## Arquivos e unidades

- `cliente.py`
  - `ClienteBinance`: facade assíncrona para klines, livro, preco, conta, trades e ordens.
  - a classe centraliza retry, timeout, rotacao de chaves legadas e fechamento de conexao.
- `coletor_velas_rest.py`
  - `_extrair_livro_topo`: normaliza a melhor ponta do order book.
  - `coletar_e_persistir`: baixa klines e livro, gera features e grava no banco.
- `coletor_velas_ws.py`
  - `conectar_e_ouvir`: esqueleto de stream websocket para observacao em tempo real.

## Razao logica

O resto do sistema nao precisa conhecer detalhes da SDK da Binance. Essa pasta absorve:

- formato bruto da exchange;
- politicas de retry;
- timeout de rede;
- diferenca entre conta publica e autenticada.
