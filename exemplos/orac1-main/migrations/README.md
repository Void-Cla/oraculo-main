# Migrations

## Papel

Esta pasta guarda o schema SQL de referencia para ambiente MySQL.

## Arquivo

- `schema_mysql.sql`: estrutura de banco alternativa ao SQLite operacional.

## Razao logica

O backend atual roda em SQLite por padrao para simplicidade local. O schema MySQL permanece como ponte para integracao futura com ambiente relacional externo, phpMyAdmin ou migracao operacional.

## Observacao

O schema aqui nao e a fonte viva da API local enquanto `DB_PATH` apontar para SQLite. Ele deve ser tratado como artefato de compatibilidade e expansao futura.
