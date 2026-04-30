# Modelagem

## Papel

Concentrar previsao e treino sem misturar regra de risco nem regra de execucao.

## Componentes

- `gerenciador_modelo.py`: carrega e combina fallback heuristico, modelo batch e modelo online.
- `preditor.py`: gera a previsao final e entrega contexto para o motor de decisao.
- `treinador_online.py`: atualiza o modelo incremental com outcomes reais.
- `treinador_batch.py`: treina um artefato batch canonico por simbolo.

## Regra de uso

- se nao houver modelo treinado, o fallback ainda produz uma previsao segura;
- se houver batch, ele estabiliza o sistema;
- se houver online, ele adapta o comportamento ao mercado recente.

O contrato publico continua simples: entrar com `features`, sair com um preco previsto e metadados do modelo.
