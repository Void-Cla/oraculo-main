# Observabilidade

## Papel

Padronizar log estruturado e metricas operacionais.

## Arquivos

- `logger.py`
  - `JsonFormatter`: transforma logs em JSON consistente.
  - `get_logger`: devolve logger configurado por nome.
- `metricas.py`
  - registra contadores e histogramas Prometheus;
  - `exportar_metricas`: expoe o payload da rota `/v1/metrics`.

## Razao logica

Sem observabilidade, erro de modelo, falha de coleta e rejeicao de risco viram "sintoma visual". Essa camada existe para tornar o sistema auditavel e medivel.
