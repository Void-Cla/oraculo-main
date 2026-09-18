# Src

`src/` concentra o codigo operacional do Oraculo separado por responsabilidade.

## Espinha dorsal

- `main.py`: API e contratos HTTP.
- `servicos/fluxo_usuario_sinais.py`: fluxo de sinal por usuario.
- `sinais/signal_engine.py`: montagem do sinal final.
- `risco/risk_engine.py`: aprovacao e sizing.
- `executor/`: simulacao e execucao.
- `modelagem/`: previsao e treino.
- `persistencia/`: banco e historico.

## Regra de arquitetura

- coleta nao decide trade;
- modelo nao cuida de risco;
- risco nao envia ordem;
- executor nao recalcula sinal.

Essa separacao e o caminho recomendado para novas manutencoes.
