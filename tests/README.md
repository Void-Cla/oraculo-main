# Tests

## Papel

A pasta de testes existe para validar comportamento, regressao e compatibilidade entre camadas.

## Cobertura atual

- `test_api.py`: smoke tests da API.
- `test_api_sessao_painel.py`: login Binance, sessao e painel autenticado.
- `test_api_usuario_sinais.py`: fluxo de usuario, sinal, fila e ordem.
- `test_gerador_features.py`: consistencia das features.
- `test_noticias_service.py`: cache, limite diario e endpoint de noticias.
- `test_repositorio_ohlcv.py` e `test_repositorios_skip_if_no_db.py`: persistencia basica.
- `test_risk_and_execution.py`: risco e planejamento de ordem.
- `test_signal_engine.py`: sinal orquestrado.
- `test_multiativo.py` e `test_api_multiativo.py`: scanner multiativos e rota dedicada.

## Razao logica

Os testes priorizam comportamento observavel, nao implementacao interna. Isso da liberdade para refatorar modulo sem perder contrato operacional.
