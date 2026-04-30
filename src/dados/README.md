# Dados de Src

## Papel

Esta pasta nao e codigo-fonte. Quando existir, ela deve ser tratada como legado de execucoes antigas ou artefato residual.

## Regra atual

O local correto para banco e modelos e a pasta de topo [`dados/`](../../dados/README.md), resolvida a partir da raiz do projeto.

## Razao logica

Manter runtime fora de `src/` reduz ambiguidade semantica e evita efeitos colaterais quando a aplicacao e executada de diretórios diferentes.
