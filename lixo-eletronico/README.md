# LIXO ELETRONICO

Quarentena reversivel para arquivos comprovadamente obsoletos, nao utilizados e sem responsabilidade ativa no runtime.

## Regra

Nao mover nada para esta pasta apenas por nome, idade ou ausencia de uma busca textual. Antes de mover, verificar imports, referencias semanticas, entrypoints, scripts, testes, CI, configuracoes, documentacao e historico Git.

## Registro obrigatorio

Para cada item movido, registrar em uma entrada do historico:

- caminho original;
- caminho nesta pasta;
- data;
- motivo;
- evidencia de que nao esta sendo usado;
- testes executados;
- aprovacao humana, quando aplicavel.

Nao colocar aqui secrets, `.env`, bancos ativos, backups, logs de producao, dados de usuario, migracoes ou artefatos do CI. A remocao permanente exige nova validacao e aprovacao explicita.
