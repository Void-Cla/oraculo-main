# Modelo BTCUSDT Legado

## Papel

Sinalizar que esta subpasta representa um ponto historico de persistencia de modelos dentro de `src/dados/modelos/BTCUSDT`.

## Razao logica

Ela existe para compatibilidade com execucoes antigas que salvaram artefatos nesse local antes da padronizacao para `dados/modelos/BTCUSDT`.

## Regra operacional

- o destino oficial atual dos modelos e a arvore `oraculo/dados/modelos`;
- esta pasta nao deve receber dependencias novas do fluxo principal;
- se um artefato antigo estiver apenas aqui, a migracao recomendada e copiar ou retreinar para o caminho oficial.

## Limite de responsabilidade

Esta pasta nao define regra de negocio. Ela apenas evita perda de contexto durante a transicao estrutural do projeto.
