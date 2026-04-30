# Scripts

## Papel

Scripts pequenos de apoio para bootstrap local e automacao de ambiente.

## Arquivos

- `inicializar_db.py`: chama `src.persistencia.conexao.inicializar_db()` e cria o banco com o schema atual.
- `rodar_local.bat`: fluxo rapido para Windows com venv, instalacao de dependencias, inicializacao do banco e subida da API.

## Razao logica

Esses scripts existem para reduzir erro operacional manual. O codigo de negocio nao mora aqui; aqui so entram rotinas de entrada e inicializacao.
