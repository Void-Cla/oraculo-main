# Modelos de Compatibilidade

## Papel

Registrar a pasta historica de modelos localizada dentro de `src/`.

## Razao logica

O projeto evoluiu para usar `dados/modelos` como destino oficial dos artefatos. Esta pasta foi mantida por compatibilidade local com execucoes antigas, testes manuais e rastreamento de transicao.

## Regra atual

- novos artefatos devem preferir `oraculo/dados/modelos`;
- esta pasta nao deve virar a fonte canonica da aplicacao;
- se existir conteudo aqui, ele deve ser tratado como legado ou espelho temporario.

## Beneficio

Documentar a pasta evita ambiguidade para quem encontra modelos tanto em `dados/` quanto em `src/dados/`, deixando claro qual caminho e oficial e qual caminho e residual.
