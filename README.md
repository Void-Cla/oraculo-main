.venv\Scripts\Activate.ps1

# Oraculo

Bot de trade automatico com foco no fluxo minimo que realmente importa:

1. coletar mercado,
2. gerar features,
3. produzir sinal com modelo + LLM/local + confirmacao,
4. validar risco,
5. planejar e executar ordem,
6. reaprender com o outcome.

## Nucleo atual

- `src/main.py`: API FastAPI e contratos HTTP.
- `src/servicos/fluxo_usuario_sinais.py`: fluxo fechado de sinal por usuario.
- `src/sinais/signal_engine.py`: orquestracao do sinal final.
- `src/sinais/consenso.py`: consenso entre estrategia, modelo, LLM e probabilidade.
- `src/risco/risk_engine.py`: aprovacao final de risco e sizing.
- `src/executor/`: simulacao e execucao de ordens.
- `src/modelagem/`: modelo online, batch e preditor hibrido.
- `src/servicos/testnet_auto_trader.py`: loop automatico de compra e venda.
- `src/persistencia/`: banco, auditoria e historico operacional.

## Estrutura resumida

- `src/binance_api/`: acesso a mercado e conta.
- `src/calculos/`: geracao de features.
- `src/estrategias/`: estrategias base por regime.
- `src/meta_strategy/`: escolha da estrategia conforme regime.
- `src/probabilidade/`: EV e calibracao probabilistica.
- `src/servicos/`: sessao, dashboard, ajustes e fluxos aplicacionais.
- `src/tarefas/`: loops assincronos.
- `tests/`: testes unitarios e de integracao.
- `dados/`: banco local e artefatos de modelo.

## Fluxo logico

1. `calculos/gerador_features.py` transforma klines em features.
2. `modelagem/preditor.py` consulta o gerenciador de modelo.
3. `sinais/signal_engine.py` junta estrategia, modelo, LLM/local e EV.
4. `sinais/consenso.py` evita que uma unica fonte contraditoria mate um trade bom.
5. `risco/risk_engine.py` decide se o trade pode acontecer e quanto capital usar.
6. `executor/` monta a ordem.
7. `servicos/testnet_auto_trader.py` roda o ciclo automatico.
8. `modelagem/treinador_online.py` recebe outcome e ajusta o modelo.

## Modelo

O `GerenciadorModelo` agora trabalha com tres camadas:

- fallback heuristico para cold start,
- modelo batch canonico para estabilidade,
- modelo online incremental para adaptacao.

Isso reduz dependencia de um unico artefato salvo em disco e deixa o treino mais robusto.

## Execucao local

Instalar dependencias:

```bash
python -m pip install -r requirements.txt
```

Inicializar o banco:

```bash
python scripts/inicializar_db.py
```

Subir a API:

```bash
python -m uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
```

Rodar testes:

```bash
.venv\Scripts\python.exe -m pytest -q
```

## Variaveis de ambiente principais

- `DB_PATH`: caminho do sqlite.
- `MODEL_DIR`: pasta dos artefatos de modelo.
- `ATIVAR_LOOP_PREVISAO`: ativa o loop de previsao.
- `ATIVAR_CONSUMIDOR_SINAIS`: ativa o consumidor da fila.
- `PERMITIR_CONTA_REAL`: libera operacao fora da testnet.
- `SESSION_TTL_HOURS`: tempo de sessao HTTP.

## Configuracao operacional persistida

Parametros de trading ficam em `config`, nao em `.env`. No primeiro startup,
o sistema materializa defaults em:

- `ajustes_sinal`: pesos, fees, slippage e limiares probabilisticos.
- `ajustes_risco`: drawdown, sizing, limites e `filtro_ev_minimo_usdt`.
- `ajustes_testnet`: simbolo, intervalo e notional de teste.
- `ajustes_retomada`: pausa media/longa, candles de observacao, recalibracao e drift.

Use `/v1/config` ou `/v1/ajustes` para auditar e alterar esses valores.

## Observacao

Ainda existem modulos legados e experimentais no repositorio, mas o caminho recomendado de manutencao agora e sempre passar pelo nucleo acima: sinal, risco, execucao e treino.
