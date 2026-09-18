# 🗺️ MAPA MENTAL EXAUSTIVO — ORACULO TRADING BOT (Estado Real para Auditoria de IA)

> **Autoria:** Arquiteto de Software Sênior · Especialista em Segurança de Missão Crítica (AA+) · Engenheiro de Dados
> **Destino:** Ingestão por IA auditora — alvos: *gargalos de performance, vulnerabilidades (exploits, vazamento de memória, injeção), falhas de fluxo lógico, ineficiências arquitetônicas*.
> **Princípio de verdade:** Este mapa descreve o **código REAL auditado linha-a-linha** (não a estrutura-ALVO do `CLAUDE.md`). Onde a realidade diverge do ideal de "produção robusta/escalável", isso é **declarado explicitamente como achado de auditoria**, não mascarado. Honestidade técnica > estética.
> **Data do snapshot:** 2026-06-21 · **Suíte:** 186 testes verdes · **Veredito de edge:** *sem edge líquido nos dados atuais* (gate de conta real fechado por desenho).

---

## 1. SUMÁRIO EXECUTIVO DA TOPOLOGIA REAL

- **Padrão arquitetural REAL:** *Monólito modular assíncrono* (FastAPI + asyncio single-process), **não** microserviços.
  - *Concorrência:* cooperativa via `asyncio` event-loop único (I/O-bound). **Sem paralelismo de CPU** (limitado pelo GIL do CPython 3.14); cargas de ML (`scikit-learn`) rodam **inline no event-loop** — *risco de bloqueio (head-of-line blocking) do loop durante `fit`/`predict`*.
  - *Estado:* **stateful em memória de processo** (sessões, credenciais, estado do autotrader, cache de modelo) + **persistência durável** em SQLite local.
  - *Escalabilidade horizontal:* **inexistente** — SQLite local single-writer + estado de processo não compartilhado ⇒ *não há sharding, nem réplicas, nem load-balancing stateless*. **Escala apenas verticalmente.**
  - *Failover / redundância:* **ausente** — single-node, single-process, single-DB-file. *Não há HA, nem replicação, nem quorum.* Tolerância a falhas é **intra-processo** (retry, breaker, halt persistido), não **inter-nó**.
- **Domínio:** trading algorítmico spot na **Binance** (testnet por padrão; conta real *quádruplo-gated*).
- **Bounded contexts (DDD-ish):** `coleta de mercado` · `feature engineering` · `inferência/ML` · `geração de sinal` · `gestão de risco` · `execução financeira` · `observabilidade` · `governança de edge`.
- **Idioma de domínio:** PT-BR (nomes de negócio); padrões técnicos em inglês (`repository`, `handler`, `factory`).

---

## 2. STACK TECNOLÓGICO E SUPERFÍCIE DE DEPENDÊNCIAS

- **Runtime:** *Python ≥3.11* (venv local em **3.14**).
- **Camada Web/API:** **FastAPI** `>=0.135` + **Uvicorn** `>=0.41` (ASGI).
- **Persistência:** **SQLite** via **aiosqlite** `>=0.22` (async) + `sqlite3` (sync, só no bootstrap/DDL). Modo **WAL**.
- **HTTP clients:** **aiohttp** `>=3.13`, **httpx** `>=0.28`.
- **Exchange SDK:** **python-binance** `>=1.0.35` (`AsyncClient`), **websockets** `>=16`.
- **Ciência de dados / ML:** **numpy** `>=2.4`, **pandas** `>=3.0`, **scikit-learn** `>=1.8`, **joblib** `>=1.5` (serialização de modelo).
- **Config/Secrets:** **python-dotenv** `>=1.2` (`.env`).
- **Métricas:** **prometheus-client** `>=0.24`.
- **Testes:** **pytest** `>=9.0` + **pytest-asyncio** `>=1.3` (`asyncio_mode=auto`).
- **Qualidade (extras `[dev]`, advisory na CI):** `mypy`, `ruff`, `black`, `isort`, `pytest-cov`.
- **⚠️ Achado de superfície (cadeia de suprimentos):** dependências **pinadas por faixa** (`>=x,<y`), não por *hash/lockfile* (sem `pip-tools`/`poetry.lock`). *Risco:* build não-determinístico e exposição a *dependency confusion / versão maliciosa* numa faixa. `joblib.load` de modelo é **desserialização de pickle** — *vetor de RCE se `MODEL_DIR` for adulterado*.

---

## 3. ESTRUTURA REAL DE DIRETÓRIOS (mapa de módulos por camada)

- **`src/` — núcleo (≈70+ módulos, ~13k LOC)**
  - **`api/`** — `app.py` (router auxiliar), `__init__.py`
  - **`main.py`** *(≈1190 LOC — 2º maior arquivo; God-API)* — composição raiz: lifespan, endpoints, auth, frontend estático
  - **`core/`** — `settings.py` (env loaders), `segredos.py` (resolução de secret-id), `constantes_mercado.py` (fonte única de limiares), `validacao_config.py` (fail-fast)
  - **`contratos/`** — `trading.py` (`Protocol`/ABC — interfaces sem implementação) *(F3 parcial)*
  - **`binance_api/`** — `cliente.py` (fachada resiliente read-only + conta), `coletor_velas_rest.py`
  - **`calculos/`** — `gerador_features.py` (feature engineering)
  - **`meta_strategy/`** — `regime_detector.py`, `meta_controller.py`
  - **`estrategias/`** — `base.py` (Protocol) + `momentum.py`, `mean_reversion.py`, `breakout.py`, `volatility_scalping.py`
  - **`sinais/`** — `signal_engine.py`, `consenso.py`, `fila_sinais.py`, `detector_drift.py`
  - **`probabilidade/`** — `ev_calculator.py` *(fonte única de custo round-trip)*, `probability_calibrator.py`, `trade_selector.py`, `probabilistic_engine.py`
  - **`risco/`** — `risk_engine.py` (gates determinísticos), `filtro_ev.py` (EV em USDT), **`edge_config.py` (NOVO — gate de lucratividade)**
  - **`modelagem/`** — `gerenciador_modelo.py` (orquestra online+batch, cache mtime), `preditor.py`, `treinador_online.py` (SGD incremental), `treinador_batch.py` (HistGradientBoosting)
  - **`executor/`** *(tudo que MOVE dinheiro)* — `gerenciador_ordens.py`, `executor_usuario.py`, **`idempotencia.py`**, **`circuit_breaker.py`** *(implementado, NÃO wireado — DA-16)*
  - **`servicos/`** — **`testnet_auto_trader.py` (God-file ≈2480 LOC — núcleo autônomo)**, `sessoes.py` (auth/credenciais em memória), `ai_advisor.py`, `llm_analista.py`, `noticias.py`, `ajustes.py`, `fluxo_usuario_sinais.py`, `decisor_hibrido.py`, `dashboard.py`, `painel_conta.py`
  - **`multiativo/`** — `orquestrador.py`, `capital_manager.py`, `opportunity_scanner.py`, `triangular_arbitrage.py`, `profit_guard.py` (defense-in-depth de custo), `fee_optimizer.py` (taxa efetiva/BNB), `bnb_manager.py`, `config.py`
  - **`persistencia/`** — `conexao.py` (DDL + pragmas + schema evolutivo), `repositorio_*.py` (≈12 repositórios), `uow.py` *(Unit of Work — implementado, MORTO/não-wireado)*
  - **`observabilidade/`** — `logger.py` (JSON), `audit.py`, `metricas.py` (Prometheus), `qualidade_sinal.py` (IC/Brier/drawdown), `correlacao.py` (correlation_id), `saude_modelo.py`
  - **`adaptacao/`** — `controlador_adaptativo.py`
  - **`calibracao/`** — `bandit.py`
  - **`tarefas/`** — `coletor_continuo.py`, `consumidor_sinais.py`, `observacao.py`, `recalibracao_startup.py`, `retomada.py`, `tarefas_previsao.py`, `carga_teste_rapida.py`
  - **`backtester/`** — `walk_forward.py` (out-of-sample, contabilidade líquida)
- **`tests/`** — 186 testes (pytest + asyncio)
- **`scripts/`** — `backtest_walkforward.py`, `pesquisa_edge.py` (harness de pesquisa de edge)
- **`frontend/public/`** — `index.html`, `app.js` (≈12KB), `estilos.css` (SPA vanilla, servida pela própria API)
- **`.github/workflows/ci.yml`** — pipeline CI
- **`.claude/`** — `contexto.md` (estado vivo), `skill.md` (lições), agentes `00..09_*.md`, este `mapa.md`
- **`dados/`** — `oraculo.db` (SQLite, gitignored), `modelos/` (joblib)

> **⚠️ Divergência REAL×ALVO (DA-06):** O `CLAUDE.md` descreve uma estrutura-ALVO (`src/dominio/`, `src/execucao/`, `src/sinais/probabilidade/`) que **NÃO existe**. Auditar pelos caminhos REAIS acima. Migração de pastas é a Fase 6 (não iniciada para a maioria).

---

## 4. CAMADA DE APRESENTAÇÃO (Frontend)

- **Tipo:** *SPA minimalista vanilla* (sem framework, sem build step) servida **estaticamente pela própria API** (`GET /`, `/app.js`, `/estilos.css`, `/img/{filename}`).
- **Artefatos:** `frontend/public/{index.html, app.js (~12.5KB), estilos.css (~9.6KB)}`.
- **Acoplamento:** consome a API REST `v1` via `fetch`; autenticação por **cookie de sessão** (`oraculo_sessao`).
- **⚠️ Achados de auditoria (Frontend):**
  - `GET /img/{filename}` — *potencial path traversal* se `filename` não for sanitizado (validar canonicalização do path contra o diretório base).
  - Sem CSP (Content-Security-Policy), sem SRI — *superfície de XSS* se qualquer dado refletido não for escapado no `app.js`.
  - `GET /v1/noticias/frame` retorna **HTML** (`HTMLResponse`) — *auditar injeção/escape de conteúdo de notícias de terceiros (stored/reflected XSS via iframe)*.

---

## 5. CAMADA DE API (FastAPI) — Interface, Ciclo de Vida e Tarefas

### 5.1. Bootstrap e ciclo de vida (`lifespan` assíncrono — `src/main.py:264`)
- **Fail-fast (PSF-01 / DA-15):** `exigir_config_valida()` é a **primeira** instrução — *recusa o boot* com config crítica inválida (conta real sem chave, DB de teste em modo real, drawdown fora de faixa).
- **Inicialização idempotente do schema:** `inicializar_db()` (DDL + pragmas + schema evolutivo).
- **`garantir_ajustes_padrao()`** + **`_inicializar_retomada(app)`** (recupera halt financeiro persistido).
- **Orquestração de tarefas em background (`asyncio.create_task`)** — *workers cooperativos no mesmo loop*:
  - `loop_previsao()` — *flag* `ATIVAR_LOOP_PREVISAO`
  - `loop_consumidor_sinais()` — *flag* `ATIVAR_CONSUMIDOR_SINAIS` (default ON); alerta se desativado **com fila pendente**
  - `executar_carga_testes()` — *flag* `ATIVAR_CARGA_TESTE`
  - `loop_coleta_continua()` — *flag* `ATIVAR_COLETA_CONTINUA` (coletor REST público)
  - `tarefa_observacao` (via retomada)
- **Graceful shutdown:** cada tarefa é `.cancel()`-ada e aguardada via `asyncio.gather(..., return_exceptions=True)` no `finally` do lifespan. *(Handlers de sinal SIGTERM/SIGINT ainda não wireados — pendência F5.)*
- **Handles em `app.state`** para health checks.

### 5.2. Autenticação, Sessão e Cookies
- **Modelo:** token opaco `secrets.token_urlsafe(32)` (entropia 256-bit) → **session store em memória de processo** (`_SESSOES` dict) + **credenciais em memória** (`_CREDENCIAIS` dict, gated por `SESSION_STORE_CREDENTIALS=True`).
- **Cookie:** `oraculo_sessao` — `httponly=True`, `samesite="lax"`, `secure=COOKIE_SECURE` (**default `false`**).
- **TTL deslizante:** `SESSION_TTL_HOURS` (default 12h); renovação a cada acesso.
- **Validação de credencial:** `criar_sessao_binance` chama a Binance (`get_account`) — *autenticação por prova de posse de API key válida*.
- **⚠️ Achados de auditoria (AuthN/AuthZ):**
  - **Sem CSRF token** com `SameSite=Lax` + cookie auth — *mutações via `POST` cross-site mitigadas só parcialmente*; endpoints de trading mudam estado ⇒ avaliar CSRF defense-in-depth.
  - `COOKIE_SECURE` default `false` ⇒ *em produção sob HTTPS deve ser `true`* (senão cookie trafega em claro / downgrade).
  - **Session store/credenciais em RAM do processo** (SEC-01) ⇒ *single point of memory exposure*; dump de processo expõe segredos. **Mitigado** (limpa no logout/expiração; `/v1/sessao/status` não puxa segredo), mas o armazenamento durante sessão ativa é requisito do loop autônomo.
  - **Sem rate-limiting / brute-force protection** no `POST /v1/sessao/entrar` — *auditar abuso/enumeração*.

### 5.3. Mapa de Endpoints (interface pública `v1`)
- **Saúde/Observabilidade:** `GET /v1/health`, `GET /v1/metrics` (Prometheus), `GET /v1/modelos/status`, `GET /v1/modelos/treino` (gate online/IC), `GET /v1/ai/saude`, **`GET /v1/edge`** (governança de edge), `GET /v1/diagnostico` (consolidado: health+treino+LLM+edge), `GET /v1/dashboard/resumo`, `GET /v1/painel/conta`.
- **Sessão:** `POST /v1/sessao/entrar`, `GET /v1/sessao/status`, `POST /v1/sessao/sair`.
- **Auto-trader (testnet):** `GET /v1/testnet/auto/status`, `POST /v1/testnet/auto/{start,stop}`, `PUT /v1/testnet/auto/config` — *gate `modo_testnet_obrigatorio` (403)*.
- **Auto-trader (real):** `GET /v1/auto/status`, `POST /v1/auto/{start,stop}`, `PUT /v1/auto/config` — *gate `conta_real_bloqueada` (403)* + `_exigir_auto_operacional()` (*halt → 423*).
- **Trading manual:** `POST /v1/trading/manual` — *gate conta real (403) + halt (423) + validação de quantidade/notional (400)*.
- **Previsão:** `GET /v1/previsao`, `POST /v1/previsao/manual`.
- **Multiativo/IA:** `GET /v1/multiativo/oportunidades`, `GET /v1/ai/insight`, `GET /v1/noticias`, `/v1/noticias/multi`, `/v1/noticias/frame`.
- **Config/Ajustes:** `GET /v1/config`, `GET/PUT /v1/config/{chave}` (*chaves operacionais protegidas → 403*), `GET /v1/ajustes`, `PUT /v1/ajustes/{sinal,risco,testnet,retomada}`.
- **Export (data lake read):** `GET /v1/export/{ohlcv,livro-topo,features,predicoes,outcomes,auditoria}`.
- **⚠️ Achados de auditoria (API):**
  - **Sem `CORSMiddleware`** registrado — *se o frontend for servido de origem distinta, quebra; se aberto indevidamente no futuro, vira superfície*. Hoje same-origin (frontend servido pela API).
  - **Sem rate-limit global** nem *throttling* por IP/sessão — *DoS de baixo esforço* nos endpoints de export/insight (que disparam I/O/LLM).
  - `GET /v1/export/*` pode **dumpar tabelas inteiras** (ohlcv/features/auditoria) — *exfiltração / pressão de memória*; auditar paginação e autorização.
  - `GET /v1/ai/insight` e `/v1/noticias*` disparam **chamadas externas pagas (GPT)** — *amplificação de custo financeiro via requisições não autenticadas?* (verificar gate de sessão por endpoint).

---

## 6. CAMADA DE DOMÍNIO — ALGORITMOS DE DECISÃO (Pipeline de Sinal)

> *Fluxo lógico determinístico, sem I/O no núcleo de decisão (testável/auditável).* Ordem canônica:

- **(1) Coleta de mercado** → `binance_api/cliente.py` (`obter_klines` *interval `1m`*, `obter_order_book_top`, `obter_preco_atual`).
- **(2) Feature engineering** → `calculos/gerador_features.py` → persiste em `features_1m` (`features_json`).
- **(3) Detecção de regime** → `meta_strategy/regime_detector.py` (limiar `vol_regime` canônico **0.0035**, fonte única `core/constantes_mercado.py` — INC-06).
- **(4) Estratégias** → `estrategias/{momentum,mean_reversion,breakout,volatility_scalping}.py` (cada uma implementa `base.py` Protocol).
- **(5) Consenso** → `sinais/consenso.py` — *agregação multi-estratégia*. **⚠️ INC-01:** limiares **assimétricos** (confirmar ≥0.10 vs vetar ≥0.35 — *viés a abrir trade*). **Mitigado** (constantes nomeadas + documentado); **NÃO simetrizado** sem backtest (DA-09: alterar threshold de risco sem dado é, por si, risco).
- **(6) Calibração de probabilidade** → `probabilidade/probability_calibrator.py` (sigmoid estável, clamp `_MAX_EXP_ARG` — BUG-06 corrigido contra `OverflowError`).
- **(7) Cálculo de EV (fonte única de custo)** → `probabilidade/ev_calculator.py`:
  - `EV = p_win·avg_win − p_loss·avg_loss − custo_round_trip`.
  - **Custo round-trip (DA-02):** `(fee + slippage)·NUMERO_DE_PERNAS(=2) + spread`. *Invariante de não-inflar EV.*
- **(8) Seleção de trade** → `probabilidade/trade_selector.py`.
- **(9) Motor de sinal** → `sinais/signal_engine.py` (orquestra 1→8, emite `acao ∈ {BUY,SELL,HOLD}`).
- **(10) Detector de drift** → `sinais/detector_drift.py` (degradação de distribuição).

---

## 7. CAMADA DE GESTÃO DE RISCO E VALIDAÇÃO DE ASSERTIVIDADE *(isolada — pedido explícito)*

> **Defense-in-depth:** múltiplas camadas independentes; *nenhuma confia cegamente na anterior* (PSF-02 / DA-10). Capital perdido não volta → **na dúvida, NÃO opera**.

- **7.1. `risco/risk_engine.py` — gates determinísticos puros** (`avaliar_sinal_para_usuario`). Ordem de veto (cada motivo nomeado):
  1. `sinal_hold` (ação = HOLD)
  2. `saldo_insuficiente`
  3. `drawdown_excedido` (`max_drawdown` 5%)
  4. `drawdown_diario_excedido` (`max_drawdown_diario` 3%)
  5. `perda_diaria_usdt_excedida` (`max_daily_loss_usdt`)
  6. `exposicao_excedida` (`max_exposicao_ativo` 20%)
  7. `limite_trades_abertos`
  8. `limite_trades_por_hora`
  9. `cooldown_ativo`
  10. `flip_flop_bloqueado` (*anti-oscilação BUY↔SELL em 2×cooldown*)
  11. `lucro_liquido_abaixo_do_minimo` (pct)
  12. `fracao_calculada_invalida`
  13. `lucro_liquido_usdt_abaixo_do_minimo`
  14. `ev_insuficiente` / `ev_parametros_invalidos` (via `filtro_ev`)
  - **Sizing:** `notional = min(capital_risco/stop, exposição_restante·saldo, saldo_livre) · max(0.35, confiança)`. *Position sizing por risco fixo + cap de exposição.*
  - **Flag `permitir_ev_negativo`** (exploração testnet-only): `ev_minimo_liquido_usdt` respeita o flag; **conta real força piso $0.01** (mecanismo separado da política).
- **7.2. `risco/filtro_ev.py` — EV líquido em USDT** (`sinal_passa_filtro_ev`). **INC-07:** `custo_slippage = valor·slippage·2` (round-trip; antes era 1× → EV inflado). *Convenção de unidade:* taxa em **%** (÷100), slippage em **decimal** — não misturar (erro de 100×).
- **7.3. `multiativo/profit_guard.py` — guardião de margem independente** (INC-04/DA-10). Reconstrói custo round-trip e veta `margem_insuficiente_sobre_custo` (exige margem ≥10% do custo). *Segunda verdade que não confia no risk_engine.*
- **7.4. `risco/edge_config.py` — GATE DE LUCRATIVIDADE (NOVO, DA-19)** *(detalhado em §9.4)*.
- **7.5. Halt financeiro persistido** (DA-16): breaker de **perda diária** inline no autotrader + `retomada_operacoes_bloqueadas` (RepositorioConfig) ⇒ **sobrevive a restart**; **reset só humano** (DA-03). API responde **423**. `daily_loss_usdt` reseta no virar do dia operacional (DA-17), mas **não** destrava o halt.
- **7.6. `executor/circuit_breaker.py`** — breaker de **drawdown%** em janela rolante, halt persistido, reset humano. **Implementado e testado, porém NÃO wireado** (DA-16: evitar segundo breaker redundante; o inline já é canônico). *Achado: código de segurança dormente — auditar se deveria substituir o inline.*

---

## 8. CAMADA DE EXECUÇÃO FINANCEIRA *(tudo que move dinheiro — `src/executor/` + autotrader)*

- **8.1. `executor/gerenciador_ordens.py` — gateway de ordens Binance**
  - `criar_ordem_market` / `criar_ordem_limit` — *quádruplo-gate de conta real*: `if not testnet and not PERMITIR_CONTA_REAL: raise`.
  - **Idempotência ON por padrão (PSF-03 / DA-12):** todo `create_order` leva `newClientOrderId` determinístico.
  - **Conformidade de filtros de mercado:** `LOT_SIZE` (step_size, min_qty), `MIN_NOTIONAL`/`NOTIONAL` — ajuste por `Decimal`/`ROUND_DOWN`; *retry progressivo* em erro de precisão (`-1111`) e tradução de `FILTER FAILURE: NOTIONAL` → `NotionalTooSmall`.
  - **Auto-incremento de notional** limitado por `NOTIONAL_AUTO_INCREASE_MAX_FACTOR` (default 1.2) — *não estoura o pedido do usuário p/ atingir mínimo*.
  - **Custo round-trip** em `simular_ordem` (`NUMERO_DE_PERNAS=2`, BUG-03) — *informativo, não lido por decisão*.
- **8.2. `executor/idempotencia.py` — `gerar_client_order_id`**
  - SHA-256 da **intenção** (`usuario:simbolo:lado:notional:chave_intencao`), prefixo `orc`, ≤36 chars. *Mesma intenção ⇒ mesmo ID ⇒ Binance rejeita duplicado* (proteção grátis contra double-submit em retry/restart).
  - **⚠️ Achado:** quando `chave_intencao` é omitida, usa `int(time.time())` (segundo atual) — *idempotência só para retries no mesmo segundo*. Chamadores deveriam passar uma chave estável (ts do sinal / ordem_id).
- **8.3. `binance_api/cliente.py` — fachada read-only resiliente**
  - **Retry com backoff exponencial** (`2^(n-1)` capado em 8s), `asyncio.wait_for` (timeout 12s), **re-sincronização de timestamp** em erro `-1021`.
  - **Rotação opcional de chaves** (`BINANCE_API_KEYS` CSV, `API_ROTATE_ON_EACH_CALL`) — *throughput / rate-limit distribuído*.
  - `fechar()` encerra conexões — chamado em `finally` dos fluxos (evita *connection leak*).
- **8.4. `servicos/testnet_auto_trader.py` — GOD-FILE / núcleo autônomo (≈2480 LOC)**
  - **Loop principal** `_loop`: por ciclo → reset perda-diária-se-novo-dia → checa halt/circuit → `_executar_ciclo`. Recuperação de erro por ciclo (`consecutive_errors`, trip no limite); `CancelledError` propaga; `finally` fecha 3 clientes Binance.
  - **`_executar_ciclo` (≈833 LOC — método God):** pipeline dado→sinal→risco→**edge gate**→execução→persistência→monitoramento. *Não decomposto (exige caracterização supervisionada — F6).*
  - **Máquina de estados do ciclo:** `_novo_estado` → `_abrir_ciclo` (BUY) → monitoramento (`_avaliar_saida_ciclo`: trailing + stop + lucro-mínimo) → `_encerrar_ciclo` (SELL) → `_registrar_fechamento_ciclo`.
  - **Invariante anti-posição-fantasma (FLX-01):** `_ordem_foi_preenchida()` (status FILLED/PARTIALLY_FILLED **ou** executedQty>0) **guarda as 2 pernas** antes de mutar o ciclo. Reconciliação (`_sincronizar_ciclo`) é a rede; o guard é a prevenção.
  - **P2 (persistência de execução):** `_persistir_ordem_executada` grava cada fill em `ordens` (best-effort, falha não derruba ciclo) + seta `ciclo_ordem_id_*` ⇒ no fechamento, `registrar_resultado` anexa **lucro/regime/estratégia** à ordem (fecha loop de ML — FLX-02).
  - **Modo exploração (DA-18):** `AUTO_MODO_EXPLORACAO=true` relaxa pisos p/ micro-trading 1-15m operar — **TESTNET-ONLY por construção** (recusa engatar com conta real; `_usuario_virtual` força `permitir_ev_negativo=False` em real).
  - **Flags default-safe:** `AUTO_MAX_NOTIONAL_USDT` (teto), `AUTO_PERMITIR_STOP_COM_PREJUIZO` (default false).
  - **⚠️ Achado:** God-file de 2480 LOC com método de 833 LOC = *alta complexidade ciclomática, difícil de auditar e testar isoladamente; superfície de regressão financeira*. Decomposição é dívida técnica priorizada (F6).

---

## 9. GOVERNANÇA DE EDGE — FLUXO DE VALIDAÇÃO DE ASSERTIVIDADE E LUCRO *(isolado — pedido explícito)*

### 9.1. Backtester walk-forward (`backtester/walk_forward.py`)
- **Metodologia:** *out-of-sample honesto* — treino expande, testa no bloco futuro, **rola a janela** (sem lookahead/vazamento).
- **Modelo padrão:** `Pipeline(RobustScaler → HistGradientBoostingRegressor)`.
- **Contabilidade LÍQUIDA (a matemática do usuário):** *para sobrar X líquido, o trade precisa render `bruto = X + custo_round_trip`; o custo NÃO é lucro.* Custo via `EVCalculator` (fonte única — coerente com o caminho vivo).
- **Critério de entrada:** só entra se `|predição| ≥ alvo_líquido + custo`.
- **Veredito:** `tem_edge_liquido = n_trades≥20 ∧ net/trade>0 ∧ IC>0`.

### 9.2. Coletor contínuo (`tarefas/coletor_continuo.py`)
- `ATIVAR_COLETA_CONTINUA=true` → REST público (sem credencial), backoff, acumula `ohlcv_1m`/`features_1m` para pesquisa de edge.

### 9.3. Harness de pesquisa (`scripts/{pesquisa_edge,backtest_walkforward}.py`)
- Sensibilidade de fee, horizontes 5/15/30/60, seletividade. **Veredito atual: SEM edge líquido** (melhor bruto/trade 0,056% < fee mais barato BNB 0,15% ⇒ *fee não é o gargalo, o sinal bruto é fraco demais*).

### 9.4. Gate de edge para conta real (`risco/edge_config.py` — DA-19) — *crown jewel de segurança financeira*
- **Núcleo PURO** `avaliar_edge(config, agora_ms, validade_dias)` — determinístico, testável:
  - **DEFAULT-CLOSED:** símbolo desconhecido → `edge_inexistente` (negado).
  - **FRESCOR:** validado há > `EDGE_VALIDADE_DIAS` (7) → `edge_expirado` (*auto-expira sozinho = fail-safe*).
  - `ativo=False` → `edge_inativo`.
- **Registro durável** `RegistroEdge` (persistido em `RepositorioConfig` chave `edge_config`, sobrevive a restart).
- **`registrar_resultado_edge`** liga `ativo=True` **só** sob critério estrito: `tem_edge_liquido ∧ n_trades≥30 ∧ IC≥0.02 ∧ net/trade≥0`. *Nenhum caminho liga `ativo` à mão.*
- **Alimentação:** `scripts/backtest_walkforward.py` com `ATUALIZAR_EDGE=1` grava o registro ⇒ *rodar o backtest CONFIGURA o gate; sem edge, o registro fica fechado.*
- **Wiring (autotrader):** `_gate_edge_conta_real(simbolo)` na **abertura REAL** (`if not modo_testnet`), **FAIL-CLOSED** (erro ⇒ negado). **Só ENTRADA real passa**; SELL/exit nunca (travar venda prenderia capital). Testnet/exploração isentos.
- **API:** `GET /v1/edge` + incluído em `/v1/diagnostico`.
- **Estado hoje:** registro **vazio** ⇒ *entrada real bloqueada por desenho* (honesto: sem edge nos dados). Auto-ativa quando surgir edge real.

---

## 10. CAMADA DE MODELAGEM / MACHINE LEARNING

- **Dois aprendizes complementares:**
  - **Online (`modelagem/treinador_online.py`):** SGD incremental — aprende em runtime das velas.
  - **Batch (`modelagem/treinador_batch.py`):** `HistGradientBoostingRegressor` → `modelo_batch.joblib`.
- **Orquestração (`modelagem/gerenciador_modelo.py`):**
  - `status()` expõe `coef_norm` (norma L2 do vetor online), `min_amostras_online`, `gate_amostras_ok`, `online_em_uso`, `max_variacao_prevista`.
  - **Gate anti-divergência (P1):** `MIN_AMOSTRAS_ONLINE` (200) + guarda de saturação — *o online só entra em uso após amostra suficiente E sem divergência* (descoberto: online saturava em 18 amostras, `coef_norm≈71` → fallback heurístico).
  - **Cache de modelo por `mtime` de ARQUIVO** (PERF-01) — *evita `joblib.load` a cada ciclo*; invalida ao mudar o arquivo (não o diretório).
- **Feedback loop de ML:** `ordens` (com lucro/regime/estratégia) + `outcomes` + `predictions` → re-treino/recalibração.
- **⚠️ Achados de auditoria (ML):**
  - **`joblib.load` = unpickle** ⇒ *RCE se `MODEL_DIR`/arquivo for adulterado*. Tratar modelos como **input não-confiável**; assinar/verificar integridade.
  - **`fit`/`predict` inline no event-loop** ⇒ *bloqueio do loop async* (latência de toda a API durante treino). Considerar `run_in_executor`/processo separado.
  - **IC tem de ser de RETORNO, não de PREÇO** (bug corrigido: preço×preço dava IC espúrio ~0.97). *Auditar qualquer nova métrica para não correlacionar nível.*

---

## 11. INTEGRAÇÕES DE IA EXTERNA (Consultivas)

- **Provedor:** **OpenAI GPT-4o-mini** (`servicos/ai_advisor.py`, `llm_analista.py`, `noticias.py`). **Consultivo** — *NÃO treina nada local; é um conselheiro externo opcional.*
- **Controle de custo (`noticias.py::_llm_permitido`):** limite diário (20) + cooldown 60min após 5 falhas. *Circuit breaker de custo de IA.*
- **Fallback honesto (INC-02):** sem chave/erro → `heuristica_local` reportada como tal (não mente `gpt-4o-mini` na auditoria).
- **Parsing robusto (`_remover_cerca_markdown`):** `removeprefix/removesuffix` (corrige bug `lstrip("```json")` que removia conjunto de chars).
- **Saúde (`ai_advisor.saude_llm`):** chave presente, modo fallback, último insight, fonte.
- **Persistência:** tabela `ai_insights`.
- **⚠️ Achados de auditoria (IA):**
  - **Prompt injection** via conteúdo de notícias de terceiros que alimenta o LLM ⇒ *o output do LLM influencia `ai_boost`/decisão?* Verificar que o LLM é **estritamente consultivo** e **não** levanta gates de risco/edge (defesa: nenhum gate financeiro depende do LLM).
  - **Vazamento de chave GPT** — garantir que `GPT_API_KEY` nunca vai a log (logger JSON inclui `extra` arbitrário — auditar campos logados).
  - **Custo financeiro** — endpoints que disparam GPT precisam de autenticação + rate-limit.

---

## 12. CAMADA DE PERSISTÊNCIA (Data Layer)

### 12.1. Engine e Pragmas (`persistencia/conexao.py`)
- **SQLite** com **WAL** (`journal_mode=WAL`), `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000` — **aplicados por-conexão** (sync no bootstrap, async em `criar_conexao`).
- **Concorrência:** WAL permite *múltiplos leitores + 1 escritor*; `busy_timeout` evita `database is locked` sob contenção (loop + API + consumidor + coletor).
- **Context manager assíncrono** `get_conexao()` — *abre e fecha conexão por operação* (sem pool).

### 12.2. Schema (DDL + esquema evolutivo idempotente)
- **Tabelas de mercado:** `ohlcv_1m`, `ohlcv_15s`, `livro_topo`, `features_1m` (PK composta `(ts, simbolo)` + índices `(simbolo, ts DESC)`).
- **Tabelas de inferência:** `predictions` (+`regime,estrategia,capital_pct,ai_boost`), `outcomes` (+`regime,estrategia,confianca,capital_pct,lucro_usdt`).
- **Tabelas operacionais:** `config` (key-value tipado: BOOL/INT/FLOAT/JSON/STRING), `snapshot_estado` (com `versao` — RMW atômico INC-05), `usuarios` (FK alvo; `api_key_ref`/`api_key_secret_id`), `ordens` (FK→usuarios; +`lucro_usdt,lucro_pct,duracao_ms,capital_pct_usado,regime,estrategia`), `audit` (append-only), `fila_sinais` (`correlation_id`, `tentativas`, `disponivel_em`), `ai_insights`.
- **Migração:** `_garantir_schema_evolutivo` via `ALTER TABLE ADD COLUMN` idempotente (checa `PRAGMA table_info`).

### 12.3. Repositórios (Repository Pattern) + Concorrência
- ≈12 `repositorio_*.py`. **Padrão de referência:** `repositorio_fila_sinais.py` usa **`BEGIN IMMEDIATE`** (claim atômico — *evita double-processing*).
- `repositorio_snapshot.py::atualizar()` — RMW atômico (`BEGIN IMMEDIATE` + coluna `versao`, INC-05).
- `repositorio_config.py` — store tipado durável (usado por circuit_breaker, retomada, **edge_config**).
- `repositorio_ordens.py` — `obter`/`listar_recentes` retornam colunas de resultado (lucro/regime); `registrar_resultado` (UPDATE pós-fechamento).
- **`persistencia/uow.py` (Unit of Work) — IMPLEMENTADO, MORTO** (não-wireado; DA-04 quer ativá-lo envolvendo `criar_ordem + salvar_snapshot`). *Achado: operações multi-repositório hoje NÃO são transacionais ⇒ janela de inconsistência em crash.*
- **⚠️ Achados de auditoria (Persistência):**
  - **`f"PRAGMA table_info({tabela})"` e `f"ALTER TABLE {tabela}..."`** usam interpolação — *seguro hoje (nomes são constantes internas, não input do usuário)*, mas **anti-padrão**; qualquer reuso com dado externo vira **SQL injection**. Demais queries usam **placeholders parametrizados** (`?`) — bom.
  - **SQLite single-file** = *gargalo de escrita serializada (1 writer)* sob alta frequência de trades + *sem escala horizontal* + *ponto único de falha/corrupção* (sem réplica). Backup/PITR não evidenciado.
  - **Sem connection pool** — abre/fecha conexão por operação ⇒ *overhead de syscall sob throughput alto* (aceitável p/ escala atual; gargalo se crescer).
  - **Tabela `audit` append-only** mas *sem enforcement de imutabilidade* (regra de negócio "nenhum UPDATE/DELETE em auditoria" não é garantida pelo schema/trigger).

---

## 13. CICLO DE VIDA DOS DADOS E FLUXO DE TRANSAÇÕES FINANCEIRAS

### 13.1. Pipeline de dados (data lifecycle)
1. **Ingestão:** coletor contínuo / loop → Binance REST → `ohlcv_1m`, `livro_topo`.
2. **Transformação:** `gerador_features` → `features_1m` (+regime/vol_regime).
3. **Inferência:** modelo (online∥batch∥heurística) → `predictions`.
4. **Realização:** após horizonte → `outcomes` (y_true vs y_hat, err_rel, lucro_usdt).
5. **Aprendizado:** outcomes/ordens realimentam treino/calibração + métricas de qualidade (IC/Brier/drawdown).

### 13.2. Fluxo financeiro (state machine de capital) — *caminho crítico*
```
Sinal(acao) → risk_engine(14 gates) → filtro_ev(EV líquido) → profit_guard(margem)
   → [se conta REAL] edge_config.gate(default-closed, fresh, fail-closed)
   → gerenciador_ordens(quádruplo-gate real + idempotência + filtros LOT/NOTIONAL)
   → Binance create_order(MARKET) → _ordem_foi_preenchida?(guard 2 pernas)
   → _abrir_ciclo → persistir_ordem(EXECUTADA) → monitoramento(trailing/stop/lucro-min)
   → _encerrar_ciclo(SELL) → persistir_ordem + registrar_resultado(lucro/regime)
   → breaker perda-diária(halt persistido se estourar) → audit(correlation_id)
```
- **Idempotência transacional:** `clientOrderId` determinístico evita débito duplo em retry/restart.
- **Consistência:** *parcial* — execução + persistência **não** são uma transação única (UoW morto) ⇒ *janela: ordem na Binance sem registro local se crash entre os dois*.

---

## 14. MODELO DE AMEAÇAS E SEGURANÇA (AA+) — consolidado

- **Gates de conta real (defense-in-depth, ≥4 pontos independentes, default-FALSE):** `gerenciador_ordens.criar_ordem_*` (2×), endpoints `/v1/auto/*` e `/v1/trading/manual` (403), `validacao_config` (fail-fast), `_usuario_virtual` (força `permitir_ev_negativo=False`), `_aplicar_modo_exploracao` (recusa real), **edge gate** (nova camada). *Nunca reduzir a contagem.*
- **Segredos:** `core/segredos.py` — nunca persiste segredo no banco, só `secret_id` (nome de env var, regex `^[A-Z][A-Z0-9_]{1,127}$`) + resolução on-demand. Credencial bruta legada só com `ALLOW_LEGACY_RAW_USER_SECRETS`.
- **SEC-01 (creds em RAM):** mitigado (limpa logout/expiração; status sem segredo); *risco residual: dump de processo*.
- **Fail-fast:** `validacao_config.exigir_config_valida()` no boot.
- **Halt financeiro:** persistido, reset humano.
- **⚠️ Vetores priorizados para a IA auditora:**
  - *RCE:* `joblib.load` (modelo) — unpickle de artefato.
  - *Injeção:* SQL via f-string em PRAGMA/ALTER (hoje benigno); XSS em `/v1/noticias/frame` e `/v1/img/{filename}` (path traversal).
  - *Vazamento de memória/segredo:* dicts globais `_SESSOES`/`_CREDENCIAIS` (crescimento se limpeza falhar; exposição em dump). Estado do autotrader/cache de modelo — *checar caps (históricos capados em 20/50, OK)*.
  - *Custo/DoS:* endpoints LLM/export sem rate-limit.
  - *AuthZ:* CSRF ausente; `COOKIE_SECURE=false` default.

---

## 15. CONCORRÊNCIA, PERFORMANCE, LATÊNCIA E THROUGHPUT

- **Modelo:** *event-loop único asyncio* (cooperativo). I/O de rede (Binance/GPT) e DB são async — *bom para I/O-bound*.
- **⚠️ Gargalos (CPU-bound no loop):** `scikit-learn` `fit`/`predict`, feature engineering pesada, parsing — *bloqueiam o loop* (sem `ProcessPoolExecutor`/`run_in_executor`). *Latência de toda a API acoplada ao pior ciclo de ML.*
- **Throughput de escrita:** limitado pelo *single-writer* do SQLite (WAL mitiga leitura, não escrita concorrente).
- **Backpressure:** `fila_sinais` (status + `disponivel_em` + tentativas) provê *retry/backoff* e *claim atômico* — bom design de fila durável.
- **Sem cache distribuído** (Redis/memcached) — cache é in-process (modelo por mtime).

---

## 16. OBSERVABILIDADE

- **Logging estruturado JSON** (`observabilidade/logger.py`): `JsonFormatter`, stdout, `propagate=False`, nível INFO. *Campos `extra` arbitrários → **auditar para não logar segredo/PII**.*
- **Auditoria** (`observabilidade/audit.py` + tabela `audit`): eventos de decisão/execução, `componente`/`motivo`/`meta_json`.
- **Métricas** (`observabilidade/metricas.py` → `/v1/metrics`): Prometheus.
- **Qualidade de sinal** (`observabilidade/qualidade_sinal.py`): IC (Spearman de **retorno**), Brier, drawdown — *só numpy (sem scipy)*.
- **Correlação** (`observabilidade/correlacao.py`): `correlation_id` (rastreio fim-a-fim; presente em `fila_sinais`). *Pendência F7: wirear em todo log financeiro.*
- **Saúde de modelo/LLM/edge:** `/v1/modelos/treino`, `/v1/ai/saude`, `/v1/edge`, `/v1/diagnostico`.

---

## 17. INFRAESTRUTURA, CI/CD E QUALIDADE

- **CI (`.github/workflows/ci.yml`):** triggers em `push`/`PR` (main, develop); `concurrency` cancela runs antigos.
  - Ambiente: `DB_PATH=/tmp/ci_oraculo.sqlite`, `PERMITIR_CONTA_REAL=false` (*conta real sempre bloqueada na CI*).
  - **Gate BLOQUEANTE:** `validar_config()` (deve retornar `[]`) + **`pytest`**.
  - **Advisory (`continue-on-error`):** `ruff`, `black`, `isort`, `mypy` (DA-14 — código legado não nasceu sob eles; tornar bloqueante após 1º passe de formatação).
- **Build:** `setuptools`; runtime pinado em `requirements.txt` (fonte única); `[dev]` extras para qualidade.
- **Deploy:** *não evidenciado* (sem Dockerfile/IaC/k8s no escopo lido) — **execução local** (`uvicorn`, `start.sh`/`start.bat`). *Achado: lacuna de containerização/observabilidade de produção (logs centralizados, tracing, alerting).*
- **Pre-commit:** `.pre-commit-config.yaml` presente.

---

## 18. TOLERÂNCIA A FALHAS E RECUPERAÇÃO

- **Retry + backoff** (Binance), **timeout** por chamada, **re-sync de timestamp**.
- **Recuperação por ciclo** no autotrader (`consecutive_errors`, trip no limite; `finally` fecha clientes).
- **Halt persistido** sobrevive a restart; **retomada** relê estado no boot.
- **Idempotência** torna retry/restart seguros financeiramente.
- **Crescimento de estado controlado:** `historico_ciclos`≤20, `historico_execucoes_ts`≤50.
- **⚠️ Lacunas de resiliência:** single-node (sem failover), SQLite sem réplica/backup-PITR evidente, UoW desativado (atomicidade multi-repo ausente), sem handlers de SIGTERM/SIGINT dedicados, `fit` no loop (degradação sob carga).

---

## 19. 🎯 PONTOS DE AUDITORIA PRIORIZADOS (índice acionável para a IA)

- **[SEC-CRÍTICO]** `joblib.load` de modelo = unpickle (RCE). → §2, §10.
- **[SEC-ALTO]** XSS/`HTMLResponse` em `/v1/noticias/frame`; path traversal em `/v1/img/{filename}`. → §4, §5.3.
- **[SEC-ALTO]** Credenciais/segredos em dicts globais de processo (SEC-01); ausência de CSRF; `COOKIE_SECURE` default false; sem rate-limit em login/LLM/export. → §5.2, §14.
- **[SEC-MÉDIO]** SQL via f-string em PRAGMA/ALTER (benigno hoje, anti-padrão). → §12.4.
- **[PERF-ALTO]** `scikit-learn fit/predict` inline no event-loop (HOL blocking). → §10, §15.
- **[PERF-MÉDIO]** SQLite single-writer + sem pool de conexão (gargalo de escrita/throughput). → §12, §15.
- **[LÓGICA-ALTO]** UoW desativado ⇒ execução + persistência não-atômicas (inconsistência em crash). → §12.3, §13.2.
- **[LÓGICA-MÉDIO]** INC-01 limiares de consenso assimétricos (viés a abrir trade) — calibrar com dado. → §6.
- **[LÓGICA-MÉDIO]** Idempotência sem `chave_intencao` estável degrada para janela de 1s. → §8.2.
- **[ARQ-ALTO]** God-file `testnet_auto_trader.py` (2480 LOC) + método 833 LOC — complexidade/risco de regressão financeira. → §8.4.
- **[ARQ-MÉDIO]** Dois breakers (inline ativo + `circuit_breaker.py` dormente) — segunda-verdade potencial. → §7.6.
- **[ARQ/PROD]** Monólito single-node sem failover/HA/escala horizontal; sem Docker/IaC. → §1, §17, §18.
- **[FINANCEIRO]** Veredito honesto: **sem edge líquido** nos dados atuais; gate de edge **fechado por desenho** (seguro). Lucratividade depende de dado+edge, não de código. → §9.

---

## 20. GLOSSÁRIO DE RASTREIO (IDs internos)

- **DA-xx** — Decisões Arquiteturais (ex.: DA-02 fee round-trip; DA-16 halt único; DA-18 exploração testnet-only; **DA-19 gate de edge**; DA-20 SEC-01 status sem segredo).
- **BUG-xx** — bugs confirmados e corrigidos (BUG-02 fee EV; BUG-03 fee single-leg; BUG-06 overflow sigmoid; BUG-07 `if not False`).
- **INC-xx** — inconsistências (INC-01 consenso assimétrico; INC-04 profit_guard; INC-05 snapshot RMW; INC-07 slippage round-trip).
- **FLX-xx** — fluxo de execução (FLX-01 posição-fantasma; FLX-02 rótulo de ML por ordem).
- **PSF-xx** — segurança de produção (PSF-01 fail-fast; PSF-02 defense-in-depth; PSF-03 idempotência; PSF-04 halt persistido).
- **SEC-01** — credenciais em memória (mitigado).
- **P1/P2** — gate de amostras de ML / persistência de execução na tabela `ordens`.

> **Fontes de verdade do projeto:** `.claude/contexto.md` (estado vivo, bugs, decisões) · `.claude/skill.md` (lições/armadilhas) · `CLAUDE.md` (protocolo/ALVO). Este `mapa.md` é a **fotografia arquitetural REAL** para auditoria — gerado a partir de leitura direta do código em 2026-06-21.
