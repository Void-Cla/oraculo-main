# Executor

## Papel

Traduzir sinal aprovado em plano de ordem e simulacao operacional.

## Arquivos

- `gerenciador_ordens.py`
  - `GerenciadorOrdens`: prepara simulacao, cria ordem limit e cancela ordem.
  - `simular_ordem` calcula preco gatilho, slippage e custo estimado.
- `executor_usuario.py`
  - `ExecutorIsoladoUsuario`: aplica contexto do usuario e gera um plano pronto para fila ou auditoria.

## Razao logica

Risco decide se pode operar. Executor decide como ficaria a ordem. Essa separacao evita que regra de sizing, gatilho e modo paper/real fique espalhada pela API.
