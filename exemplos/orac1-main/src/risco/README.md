# Risco

## Papel

Aplicar o veto final antes de qualquer plano de execucao.

## Arquivo

- `risk_engine.py`
  - `config_risco_padrao`: base de politicas de risco.
  - `_clamp`: utilitario interno.
  - `avaliar_sinal_para_usuario`: verifica saldo, drawdown, cooldown, limite por hora, flip-flop, perda diaria, perda maxima por trade e lucro minimo.

## Razao logica

O risco fica isolado para que a regra de seguranca seja central, previsivel e facil de auditar. Nenhum endpoint deveria aprovar operacao pulando esta pasta.
