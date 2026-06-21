# Oraculo — Bot de Trading Algorítmico (Binance)

Sistema autônomo de micro-trading na Binance (spot), com pipeline fechado:
**coletar mercado → gerar features → sinal (modelo + LLM/heurística + consenso) → risco → execução → reaprender com o outcome.**

> **Estado honesto (2026-06):** a engenharia está sólida, segura e validada ao vivo no testnet.
> Porém a pesquisa rigorosa (walk-forward, custo round-trip real) mostra que **não há edge líquido
> nos dados atuais** — o retorno bruto por trade não cobre as taxas. O caminho para lucro é **mais
> dado real + melhor sinal**, não mais código. Ver `.claude/run_analise_2026-06-20.md`.

## Pipeline (núcleo)

1. `calculos/gerador_features.py` — klines (1m) → features.
2. `modelagem/` — `GerenciadorModelo`: 3 camadas (heurística cold-start + batch + online incremental),
   com **gate anti-divergência** (modelo sub-treinado/saturado é descartado, não polui o sinal).
3. `sinais/signal_engine.py` + `sinais/consenso.py` — junta estratégia, modelo, LLM/heurística e EV.
4. `risco/risk_engine.py` — aprovação final de risco, sizing, e filtro de EV **líquido** (custo round-trip).
5. `executor/` — simulação e execução de ordens (idempotência via `newClientOrderId`; verificação de fill).
6. `servicos/testnet_auto_trader.py` — loop automático com saída inteligente (lucro-mínimo + trailing + stop).
7. `modelagem` (online) + `RepositorioOutcomes` — recebe o outcome e reajusta.

## Segurança (validada)

- **Fail-fast de config** no startup (`core/validacao_config.py`): recusa iniciar com config insegura.
- **Conta real bloqueada por padrão** (`PERMITIR_CONTA_REAL=false`), verificada em múltiplos pontos.
- **Breaker de perda diária** persistido (`retomada_operacoes_bloqueadas`) — sobrevive a restart, reset humano.
- **Custo round-trip** (taxa+slippage nas 2 pernas) coeso em EV, filtro, profit-guard e backtester.
- **Anti-posição-fantasma**: só abre/encerra ciclo após confirmar o fill real da ordem.
- **EV negativo proibido em conta real** (mesmo no modo exploração).
- **Gate de edge** (`risco/edge_config.py`): abertura em conta real exige edge líquido **validado
  (walk-forward) e fresco** — default-closed, auto-expira, fail-closed. Sem edge ⇒ real bloqueado.

## Matemática do lucro LÍQUIDO

Lucro líquido = o que sobra **depois de todas as taxas**. Para sobrar X líquido, o trade precisa render
**bruto = X + custo_round_trip**; o custo NÃO é lucro. Implementado em `backtester/walk_forward.py`
(`bruto_necessario_para_liquido_*`) e usado no filtro de EV/profit-guard.

## Execução local

```bash
python -m pip install -r requirements.txt              # dependências
python -c "from src.persistencia.conexao import inicializar_db; inicializar_db()"  # banco
uvicorn src.main:app --host 0.0.0.0 --port 8000        # API (ou use start.sh / start.bat)
.venv/Scripts/python.exe -m pytest -q                  # testes (186, DB_PATH obrigatório)
```

## Pesquisa de edge (pré-requisito honesto para operar com lucro)

```bash
# 1) Acumular dado real contínuo (REST público, sem credenciais):
#    ligue ATIVAR_COLETA_CONTINUA=true e deixe rodando por dias.
# 2) Avaliar edge LÍQUIDO walk-forward (sem deployar nada):
DB_PATH=./dados/oraculo.sqlite python scripts/backtest_walkforward.py
DB_PATH=./dados/oraculo.sqlite python scripts/pesquisa_edge.py   # IC/acc + sensibilidade de fee
# 3) Só operar para lucro se net/trade > 0 ESTÁVEL aparecer. Para LIBERAR o gate de conta real
#    com o veredito do backtest (auto-ativa só símbolos com edge):
DB_PATH=./dados/oraculo.sqlite ATUALIZAR_EDGE=1 python scripts/backtest_walkforward.py
#    Confira em GET /v1/edge. Sem edge, o gate permanece fechado (fail-safe).
```

## API — principais endpoints

| Rota | Função |
|------|--------|
| `GET /v1/health` | Saúde da app + estado de retomada |
| `GET /v1/diagnostico` | **Consolidado**: health + treino online + LLM + edge |
| `GET /v1/modelos/treino` | Treino online runtime: gate de amostras, divergência (`coef_norm`), IC de **retorno** recente |
| `GET /v1/ai/saude` | Vida do LLM: chave presente, modo fallback, último insight |
| `GET /v1/edge` | Governança de edge: símbolos com edge líquido **validado e fresco** (gate de conta real) |
| `GET /v1/auto/status` · `POST /v1/auto/{start,stop}` | Controle do auto-trader |
| `GET /v1/previsao` · `POST /v1/previsao/manual` | Previsões |
| `GET /v1/multiativo/oportunidades` | Scanner multiativo |
| `GET/PUT /v1/ajustes/*` · `/v1/config` | Parâmetros operacionais (persistidos no DB, não no `.env`) |
| `GET /v1/export/*` | Dump de ohlcv/features/predicoes/outcomes/auditoria |

## Variáveis de ambiente

Operacionais ficam no DB (`/v1/ajustes`), não no `.env`. No `.env`, apenas:

- `DB_PATH` — caminho do SQLite. `BINANCE_API_KEY/SECRET`, `BINANCE_TESTNET`.
- `PERMITIR_CONTA_REAL` — libera conta real (default false; **mantenha false sem edge comprovado**).
- `ATIVAR_LOOP_PREVISAO`, `ATIVAR_CONSUMIDOR_SINAIS` — loops opcionais.
- `ATIVAR_COLETA_CONTINUA` (+ `COLETA_SIMBOLOS`, `COLETA_INTERVALO_SEGUNDOS`) — coletor contínuo de dados.
- `AUTO_MODO_EXPLORACAO` — liga o micro-trading 1-15m no **testnet** relaxando pisos (EV negativo permitido;
  recusa engatar em conta real). Só para validação/exploração.
- `GPT_API_KEY`/`OPENAI_API_KEY` — opcional; sem chave, o LLM cai em heurística local (honesto).

## Estrutura

`src/{binance_api,calculos,estrategias,meta_strategy,probabilidade,sinais,risco,executor,modelagem,`
`multiativo,persistencia,observabilidade,servicos,tarefas,backtester,core,contratos}` · `scripts/` · `tests/` · `dados/`.

Convenção de manutenção: leia `.claude/contexto.md` (estado vivo) e `.claude/skill.md` (lições) antes de mexer.
