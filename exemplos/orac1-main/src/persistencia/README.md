# Persistencia

## Papel

Concentrar a infraestrutura de banco, serializacao e repositorios.

## Arquivos principais

- `conexao.py`
  - resolve caminho do banco a partir da raiz;
  - cria schema SQLite com WAL;
  - entrega conexao assíncrona.
- `base.py`
  - `BaseRepositorio`: base abstrata para repositorios.
- `uow.py`
  - `UnidadeDeTrabalho`: agrupamento transacional.
- `repositorio_ohlcv.py`
  - CRUD de klines persistidos.
- `repositorio_livro_topo.py`
  - armazena snapshots do topo do livro.
- `repositorio_features.py`
  - persiste vetor de features.
- `repositorio_predicoes.py`
  - salva saidas do modelo.
- `repositorio_outcomes.py`
  - salva verdade observada apos a previsao.
- `repositorio_config.py`
  - chave/valor tipado para configuracao e cache.
- `repositorio_auditoria.py`
  - trilha de auditoria estruturada.
- `repositorio_ordens.py`
  - persistencia do ciclo de ordens.
- `repositorio_usuarios.py`
  - cadastro e configuracao de usuarios internos.

## Razao logica

Repositorio existe para tirar SQL de dentro de servicos e endpoints. Isso melhora separacao de responsabilidade e reduz erro semantico de acesso ao banco.
