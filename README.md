# Oraculo — Bot de Trading Algorítmico (Binance)

Micro-trading autônomo na Binance (spot): **mercado → features → sinal → risco → execução → reaprendizado**.

> **Estado (2026-06):** engenharia sólida e validada no testnet. Walk-forward rigoroso mostra **sem edge líquido** nos dados atuais — retorno bruto não cobre taxas. Próximo passo: **mais dado + melhor sinal**, não mais código. Ver `.claude/run_analise_2026-06-20.md`.

## Pipeline

1. **Features** — `calculos/gerador_features.py` (klines 1m).
2. **Modelo** — `modelagem/`: heurística + batch + online, com gate anti-divergência.
3. **Sinal** — `sinais/signal_engine.py` + `consenso.py` (estratégia, modelo, LLM, EV).
4. **Risco** — `risco/risk_engine.py` (sizing, EV líquido round-trip).
5. **Execução** — `executor/` (idempotência, confirmação de fill).
6. **Loop** — `servicos/testnet_auto_trader.py` (saída inteligente).
7. **Feedback** — treino online + `RepositorioOutcomes`.

## Segurança

- Fail-fast de config; conta real **bloqueada por padrão** (`PERMITIR_CONTA_REAL=false`).
- Breaker de perda diária persistido; anti-posição-fantasma.
- Custo round-trip coeso em EV, filtro e backtester.
- Gate de edge (`risco/edge_config.py`): conta real só com edge walk-forward validado e fresco.

## Execução local

```bash
python -m pip install -r requirements.txt
python -c "from src.persistencia.conexao import inicializar_db; inicializar_db()"
uvicorn src.main:app --host 0.0.0.0 --port 8000
.venv/Scripts/python.exe -m pytest -q   # DB_PATH obrigatório
```

## Pesquisa de edge

```bash
# Coletar dados: ATIVAR_COLETA_CONTINUA=true (dias)
DB_PATH=./dados/oraculo.sqlite python scripts/backtest_walkforward.py
DB_PATH=./dados/oraculo.sqlite python scripts/pesquisa_edge.py
# Liberar gate (só com edge comprovado):
DB_PATH=./dados/oraculo.sqlite ATUALIZAR_EDGE=1 python scripts/backtest_walkforward.py
# Confira GET /v1/edge
```

## API (principais)

| Rota | Função |
|------|--------|
| `GET /v1/health` · `/v1/diagnostico` | Saúde e diagnóstico consolidado |
| `GET /v1/modelos/treino` · `/v1/ai/saude` · `/v1/edge` | Treino, LLM, governança de edge |
| `GET/POST /v1/auto/*` | Auto-trader |
| `GET /v1/previsao` · `/v1/multiativo/oportunidades` | Previsões e scanner |
| `GET/PUT /v1/ajustes/*` · `/v1/export/*` | Config (DB) e export de dados |

## `.env` (mínimo)

- `DB_PATH`, `BINANCE_API_KEY/SECRET`, `BINANCE_TESTNET`
- `PERMITIR_CONTA_REAL` (default false)
- `ATIVAR_COLETA_CONTINUA`, `AUTO_MODO_EXPLORACAO` (testnet)
- `NVIDIA_API_KEY`/`Nvidia_API_Key`, `GPT_API_KEY`/`OPENAI_API_KEY` (opcional; sem chave → heurística local)

Parâmetros operacionais ficam no DB via `/v1/ajustes`, não no `.env`.

## Estrutura

`src/{binance_api,calculos,estrategias,sinais,risco,executor,modelagem,multiativo,persistencia,servicos,...}` · `scripts/` · `tests/` · `dados/`

Manutenção: leia `.claude/contexto.md` e `.claude/skill.md` antes de alterar código.
