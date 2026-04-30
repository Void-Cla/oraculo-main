# Dados

## Finalidade

Esta pasta e o destino canonico dos artefatos de runtime do projeto.

## O que fica aqui

- `oraculo.sqlite`: banco SQLite principal quando `DB_PATH=./dados/oraculo.sqlite`.
- `modelos/`: modelos online e metadados por simbolo quando `MODEL_DIR=./dados/modelos`.

## Razao logica

Separar runtime de `src/` evita misturar codigo-fonte com estado mutavel. Isso melhora:

- reproducibilidade;
- limpeza semantica do repositorio;
- compatibilidade entre execucao pela raiz e execucao por subpasta.

## Observacao importante

Se existir `src/dados/`, trate como legado ou resquicio de execucoes antigas. O caminho oficial do runtime deve apontar para esta pasta de topo.
