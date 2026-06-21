# CONTEXTO DO PROJETO — ORACULO TRADING BOT
> Mantido pelo Agente Revisor (REV). Última atualização: 2026-06-21 (sessão de governança de EDGE + SEC-01)
> Leia este arquivo PRIMEIRO em toda sessão para evitar retrabalho e economizar tokens.
> Não edite manualmente — apenas o Revisor escreve aqui.
> Leia também `.claude/skill.md` (lições/atalhos do projeto) na mesma carga inicial.

---

## ESTADO ATUAL DA SESSÃO

```
Fase ativa:        F1+F2+F4+F5+F9 (✅) + lacunas INC-02/03/05+PERF-01 (✅) → próxima: F7 obs / F6 decomp
Último agente:     REV (após EXE, GRD, QNT, OBS, SIN, PER)
Último commit:     46f585b "cc" (mudanças desta sessão ainda não commitadas)
Testes:            186 passou / 0 falhou / 186 total   (DB_PATH=./dados/oraculo.db)
                   (168 anteriores + 18: governança de EDGE 14, SEC-01 sessões 4, +edge na API)
God-file:          testnet_auto_trader.py 2467 → 2371 linhas (2 clusters extraídos p/ autotrader/)
Mypy erros:        não medido (mypy não instalado — ver FASE 9)
Cobertura atual:   não medida (pytest-cov não instalado)
Python do venv:    3.14 (pyproject exige >=3.11 — OK)
```

> ✅ As 10 falhas herdadas foram TODAS eliminadas nesta sessão. Suíte 100% verde.
> Bugs BUG-01..06 corrigidos + bug de edição `if not False:` no auto-trader + 4 arquivos mortos removidos.

---

## ⚠️ DIVERGÊNCIA ESTRUTURA REAL vs ALVO (LER ANTES DE QUALQUER EDIÇÃO)

O `CLAUDE.md` descreve uma **estrutura-ALVO** (`src/dominio/`, `src/execucao/`, `src/autotrader/`, `src/sinais/probabilidade/`…) que **NÃO é a estrutura real de hoje**. Usar os caminhos do CLAUDE.md leva a editar arquivos inexistentes. Use SEMPRE os caminhos REAIS abaixo. A migração para o ALVO é a Fase 6 (decomposição) — não mova arquivos antes disso.

| Conceito | Caminho REAL (hoje) | Caminho ALVO (CLAUDE.md) |
|----------|---------------------|--------------------------|
| Contratos | `src/contratos/trading.py` | `src/contratos/` ✅ já alinhado |
| Risk engine | `src/risco/risk_engine.py` | `src/dominio/risk_engine.py` |
| Filtro EV | `src/risco/filtro_ev.py` | `src/dominio/` |
| EV calculator | `src/probabilidade/ev_calculator.py` | `src/sinais/probabilidade/ev_calculator.py` |
| Calibrador | `src/probabilidade/probability_calibrator.py` | `src/sinais/probabilidade/` |
| Trade selector | `src/probabilidade/trade_selector.py` | `src/sinais/probabilidade/` |
| Engine probabilístico | `src/probabilidade/probabilistic_engine.py` | `src/sinais/probabilidade/` |
| Estratégias | `src/estrategias/*.py` | `src/sinais/estrategias/` |
| Regime | `src/meta_strategy/regime_detector.py` | `src/sinais/regime/regime_detector.py` |
| Meta-controlador | `src/meta_strategy/meta_controller.py` | `src/sinais/` |
| Consenso / signal engine | `src/sinais/consenso.py`, `src/sinais/signal_engine.py` | `src/sinais/` ✅ |
| Gerenciador de ordens | `src/executor/gerenciador_ordens.py` | `src/execucao/gerenciador_ordens.py` |
| Executor usuário | `src/executor/executor_usuario.py` | `src/execucao/` |
| God-file autotrader | `src/servicos/testnet_auto_trader.py` | `src/autotrader/` (decompor em 4) |
| Profit guard | `src/multiativo/profit_guard.py` | `src/dominio/profit_guard.py` |
| Multiativo (resto) | `src/multiativo/*` | `src/multiativo/` ✅ |
| Circuit breaker | `src/executor/circuit_breaker.py` ✅ (criado F5; wiring no loop = F6) | `src/execucao/` |
| Idempotência | `src/executor/idempotencia.py` ✅ (criado F5, ON em toda ordem) | `src/execucao/` |
| Autotrader (decomp.) | `src/autotrader/{calculos,configurador}.py` ✅ (parcial F6) + `src/servicos/testnet_auto_trader.py` | `src/autotrader/` (completar) |
| Observabilidade qualidade | `src/observabilidade/{qualidade_sinal,correlacao}.py` ✅ (F7) | `src/observabilidade/` |
| Unit of Work | `src/persistencia/uow.py` (morto) | `src/persistencia/uow.py` — reativar F4 |
| Observabilidade | `src/observabilidade/{logger,audit,metricas}.py` | `src/observabilidade/` ✅ |
| API / endpoints | `src/api/app.py` + `src/main.py` (1176 linhas) | `src/api/main.py` |

---

## PROGRESSO POR FASE

| Fase | Status | Concluída em | Agentes usados |
|------|--------|-------------|----------------|
| 0 - Mapeamento | ✅ Concluída | 2026-06-19 | ORQ, REV |
| 1 - Código morto | ✅ Concluída (4 arquivos removidos; uow.py mantido p/ F4) | 2026-06-19 | REF, TST |
| 2 - Bugs críticos | ✅ Concluída (BUG-01..06 + bug `if not False`) | 2026-06-19 | OBS, EXE, QNT, TST |
| 3 - Contratos | 🔄 Parcial (`src/contratos/trading.py` existe) | — | — |
| 4 - Matemática | ⬜ Pendente | — | — |
| 5 - Segurança | ✅ Concluída (circuit_breaker, idempotência, fail-fast) | 2026-06-19 | EXE, GRD, TST |
| 6 - Decomposição | 🔄 Foundation + 2 clusters extraídos (`autotrader/{calculos,configurador}`; god-file 2467→2371). Falta: split de `_executar_ciclo` (833 linhas — exige caracterização supervisionada) + UoW | 2026-06-20 | REF, TST |
| 7 - Observabilidade | 🔄 Quase (IC/Brier/drawdown + correlation_id prontos e testados; falta só wirear nos logs financeiros) | 2026-06-20 | OBS, TST |
| 8 - Testes | ✅ 0 falhas / 115 verde (cobertura ainda não medida) | 2026-06-19 | TST |
| 9 - CI/CD | ✅ `.github/workflows/ci.yml` + `.pre-commit-config.yaml` + `[dev]` extras | 2026-06-19 | ORQ |

> Legenda: ⬜ Pendente · 🔄 Em andamento · ✅ Concluída · ❌ Bloqueada

---

## BUGS CONFIRMADOS — RASTREIO (caminhos REAIS)

| ID | Arquivo REAL | Descrição curta | Status | Corrigido por |
|----|--------------|-----------------|--------|---------------|
| BUG-01 | `src/servicos/fluxo_usuario_sinais.py` | `logger` sem import — `NameError` no fluxo default | ✅ Corrigido (`get_logger(__name__)` + test_pipeline reescrito) | OBS |
| BUG-02 | `src/probabilidade/ev_calculator.py` | Custo aplicado 1×; agora round-trip `(fee+slippage)*2 + spread` | ✅ Corrigido (`NUMERO_DE_PERNAS=2` + test_ev_calculator) | QNT |
| BUG-03 | `src/executor/gerenciador_ordens.py:107` | `custo_total = notional*taxa` single-leg | ✅ Corrigido (×`NUMERO_DE_PERNAS`; campo não era lido) | QNT |
| BUG-04 | `src/main.py` + `src/servicos/ajustes.py` | `salvar_ajustes_testnet` descartava `notional_usdt` enviado | ✅ Corrigido (reflete `filtrado` no `aplicado`) | EXE |
| BUG-05 | `src/multiativo/orquestrador.py:225-228,240` | `ajustes_sinal.get()` sem guard `None` | ✅ Corrigido (→ `ajustes_sinal_exec.get`) | EXE |
| BUG-06 | `src/probabilidade/probability_calibrator.py` | `math.exp()` `OverflowError` | ✅ Corrigido (sigmoid estável, clamp `_MAX_EXP_ARG`) | QNT |
| BUG-07 | `src/servicos/testnet_auto_trader.py:947` | `if not False:` (edição pela metade) ignorava flag de stop — bug NOVO | ✅ Corrigido (`AUTO_PERMITIR_STOP_COM_PREJUIZO`) | EXE |
| INC-01 | `src/sinais/consenso.py` | Limiares assimétricos confirmar ≥0.10 vs vetar ≥0.35 (viés a abrir trade) | 🟡 Mitigado: constantes nomeadas + viés documentado; VALOR a calibrar com backtester (F8). NÃO simetrizado sem dados (alterar risco sem backtest é risco) | QNT/GRD |
| INC-02 | `noticias.py` + `llm_analista.py` | `modelo_llm` hardcoded mesmo em fallback heurístico | ✅ Corrigido: reporta `heuristica_local` quando não veio do GPT (3 pontos) | OBS |
| INC-03 | `fee_optimizer.py` + `fluxo_usuario_sinais.py` | Taxa efetiva só no autotrader | ✅ Fonte única `aplicar_taxa_efetiva`; fluxo manual aplica via `perfil_taxas` no payload | QNT |
| INC-04 | `src/multiativo/profit_guard.py` | Recebe taxas/slippage e não os usava em gate | ✅ Corrigido: reconstrói custo round-trip + gate `margem_insuficiente_sobre_custo` (10% do custo) | QNT/GRD |
| INC-05 | `src/persistencia/repositorio_snapshot.py` | Read-modify-write sem lock/versão | ✅ `atualizar()` atômico (`BEGIN IMMEDIATE` + `versao`); 2 call sites migrados | PER |
| INC-06 | `regime_detector.py` vs `repositorio_features.py` | Limiar `vol_regime` divergente (0.003 vs 0.0035) | ✅ Corrigido: fonte única `src/core/constantes_mercado.py` (0.0035 canônico) | SIN/PER |
| PERF-01 | `src/modelagem/preditor.py` + `gerenciador_modelo.py` | `joblib.load` a cada ciclo | ✅ `obter_gerenciador_modelo` cacheado por símbolo (invalida por mtime; preserva online) | EXE/QNT |
| SEC-01 | `src/servicos/sessoes.py` | `SESSION_STORE_CREDENTIALS=True` guarda api_key/secret em texto puro em dict global | 🟡 Mitigado: credenciais JÁ são limpas no logout (`encerrar_sessao`) e na expiração (`_limpar_expiradas_sem_lock`); `/v1/sessao/status` passou a ler `incluir_credenciais=False` (segredo não sai do store). Invariante travado por 4 testes. O armazenamento em memória durante a sessão ativa é REQUISITO do loop autônomo (parecer: não flipar default sem supervisão) | GRD/EXE |
| EDGE | `src/risco/edge_config.py` (novo) + `testnet_auto_trader.py` (BUY real) | Não havia gate de LUCRATIVIDADE: conta real poderia abrir posição sem edge validado | ✅ Implementado: gate default-closed + frescor (auto-expira) + fail-closed; só abertura REAL passa (SELL/exit nunca); alimentado pelo walk-forward (`ATUALIZAR_EDGE=1`); API `/v1/edge` + `/v1/diagnostico`. Hoje registro VAZIO ⇒ entrada real bloqueada por desenho (honesto: sem edge nos dados). +14 testes | GRD/QNT/EXE/TST |
| INC-07 | `src/risco/filtro_ev.py:56-57` | Slippage aplicado 1× (single-leg) enquanto EVCalculator/profit_guard usam round-trip → EV inflado no gate de risco | ✅ Corrigido: `custo_slippage = valor_ordem * slippage * 2` (DA-02) + teste de invariante `test_custo_taxa_e_slippage_sao_round_trip` | QNT |
| FLX-01 | `src/servicos/testnet_auto_trader.py` (BUY ~2214 / SELL ~2257) | **Posição-fantasma na FONTE**: ordem não preenchida (status NEW/EXPIRED/REJECTED, executedQty=0) abria/encerrava ciclo com qtd teórica → `ciclo_ativo` sem ativo real → trava `limite_trades_abertos` + PnL falso. (causa-raiz #2 do run 13-18h) | ✅ Corrigido: `_ordem_foi_preenchida()` guarda as DUAS pernas antes de mutar o ciclo; reconciliação assume fill atrasado. +2 testes | EXE/GRD |
| FLX-02 | `src/servicos/testnet_auto_trader.py:_registrar_fechamento_ciclo` | `regime/estrategia` lidos de `ultimo_sinal` (que é STRING) → `AttributeError` silenciado por `except: pass` → resultado da ordem ficaria sem rótulo de ML. Bug latente (bloco antes inalcançável: `ciclo_ordem_id_*` nunca era setado) | ✅ Corrigido: captura `ciclo_regime`/`ciclo_estrategia` na entrada + log no lugar do swallow. **P2 agora seta `ciclo_ordem_id_*`** → bloco ativo | EXE/OBS |
| P2 | `src/servicos/testnet_auto_trader.py` (BUY/SELL exec) | Auto-trader executava ordens mas NÃO persistia em `ordens` → UI mostrava 0 e ML sem feedback por-ordem | ✅ Corrigido: `_persistir_ordem_executada` grava cada fill em `ordens` (EXECUTADA) + seta `ciclo_ordem_id_*`; `RepositorioOrdens.obter/listar` agora retornam colunas de resultado (lucro/regime). +3 testes | PER/EXE/TST |

---

## ARQUIVOS MORTOS — STATUS (verificar por IMPORT, não por substring)

| Arquivo REAL | Razão | Refs externas | Status |
|--------------|-------|---------------|--------|
| `src/servicos/coletor_noticias.py` | Stub `calcular_peso_sentimento` → 0.0 | 0 ✅ | ✅ REMOVIDO |
| `src/binance_api/coletor_velas_15s.py` | Scaffold, velas falsas | 0 ✅ | ✅ REMOVIDO |
| `src/binance_api/coletor_velas_ws.py` | Ignora flag `"x"` de vela fechada | 0 ✅ | ✅ REMOVIDO |
| `src/persistencia/base.py` | ABC sem herdeiros (verificado por import: 0; os 4 hits de "base" eram `estrategias/base.py`, vivo) | 0 ✅ | ✅ REMOVIDO |
| `src/persistencia/uow.py` | UoW implementado, nunca usado | 0 ✅ | ⏸️ MANTIDO — infraestrutura planejada p/ F4 (reativar, não recriar) |
| `src/backtester/simple_backtester.py` | Backtester pandas básico, substituído pelo walk_forward | 0 ✅ | ✅ REMOVIDO (limpeza estrutural 2026-06-21) |
| `src/calibracao/ewls.py` | Stub no-op `CalibradorEWLS` (placeholder, nunca implementado) | 0 ✅ | ✅ REMOVIDO (limpeza estrutural) |
| `src/modelagem/treinador_batch.py` | `treinar_batch` real (produz modelo_batch.joblib que o preditor carrega) | 0 (out-of-band) | ⏸️ MANTIDO — infra de treino batch (útil p/ pesquisa de edge) |

---

## DECISÕES ARQUITETURAIS REGISTRADAS

| ID | Decisão | Razão | Data |
|----|---------|-------|------|
| DA-01 | Limiares de vol_regime centralizados (fonte única) | Dois módulos divergem (0.003 vs 0.0035) | 2026-06-19 |
| DA-02 | Fee round-trip = 2× em todo EV e simulação | Binance cobra entrada E saída | 2026-06-19 |
| DA-03 | Circuit breaker reset só por ação humana | Halt automático reversível = risco de ruína em loop | 2026-06-19 |
| DA-04 | UoW obrigatório para operações multi-repositório | Sem transação → estado inconsistente em crash | 2026-06-19 |
| DA-05 | Client order ID determinístico via hash de intenção | Binance rejeita clientOrderId duplicado = idempotência grátis | 2026-06-19 |
| DA-06 | NÃO mover arquivos para a estrutura-ALVO antes da Fase 6 | Renomear em massa quebra imports e mistura "organizar" com "refatorar" | 2026-06-19 |
| DA-07 | Validação de código morto SEMPRE por import (`from x import`/`import x`), nunca por substring grep | `grep "base"` deu 22 falsos-positivos | 2026-06-19 |
| DA-08 | Limiares de regime centralizados em `src/core/constantes_mercado.py` (ALVO: `dominio/`, mover na F6) | Fonte única elimina INC-06; `core/` é leaf sem ciclo de import | 2026-06-19 |
| DA-09 | NÃO simetrizar limiares de consenso (INC-01) sem backtest — só nomear+documentar+calibrar na F8 | Alterar threshold de risco sem dado empírico é, por si, um risco financeiro | 2026-06-19 |
| DA-10 | profit_guard valida custo de forma independente (defense in depth) — gate de margem 10% do custo round-trip | PSF-02: nenhuma camada confia cegamente na anterior | 2026-06-19 |
| DA-11 | Módulos de segurança em `src/executor/` (não `execucao/`) — circuit_breaker.py, idempotencia.py | Mantém todo o pacote de execução real coeso; evita split-brain executor/execucao | 2026-06-19 |
| DA-12 | Idempotência ON por padrão: `criar_ordem_*` geram `newClientOrderId` se o chamador não passar | PSF-03: nenhuma ordem sai sem proteção contra double-submit | 2026-06-19 |
| DA-13 | Circuit breaker persiste estado em `RepositorioConfig` (chave `circuit_breaker_estado`); reset só humano | PSF-04/DA-03: halt sobrevive a restart; reset automático = risco de ruína | 2026-06-19 |
| DA-14 | CI: lint/format/mypy são advisory (continue-on-error); testes + validar_config são o gate bloqueante | Código legado não nasceu sob ruff/black; reformatar tudo numa sessão = diff gigante/arriscado | 2026-06-19 |
| DA-15 | `exigir_config_valida()` é chamado no `lifespan` (startup) — fail-fast real (PSF-01) | Config insegura (real sem chave, DB de teste em real, drawdown inválido) deve impedir o boot, não ser descoberta horas depois | 2026-06-21 |
| DA-16 | Halt financeiro canônico = breaker de perda diária inline + `retomada_operacoes_bloqueadas` persistido. `circuit_breaker.py` (drawdown%) NÃO é wireado — fica reservado p/ consolidação supervisionada futura | Dois breakers em paralelo = segunda-verdade/redundância; o inline já é durável (sobrevive restart) e reset-humano. Na dúvida → não duplicar caminho financeiro | 2026-06-21 |
| DA-17 | `daily_loss_usdt` reseta no virar do dia operacional (`daily_loss_data`), mas NÃO destrava `circuit_tripped` | "Perda diária" tem de ser diária (senão vira cumulativa e trava cedo em run multi-dia); já o halt de um dia ruim continua exigindo revisão humana (DA-03) | 2026-06-21 |
| DA-18 | Modo exploração (`AUTO_MODO_EXPLORACAO=true`) torna o micro-trading 1-15m operacional relaxando pisos de lucro/EV, mas é TESTNET-ONLY por construção (recusa engatar se conta real ligada; `_usuario_virtual` força `permitir_ev_negativo=False` em conta real) | Atende ao pedido de operar 1-15m sem jamais arriscar dinheiro real em EV negativo (dado prova EV<0). Dupla trava + log alto. Validado ao vivo: bot opera, mas racionalmente segura posição (não vende no prejuízo líquido) — confirma no-edge | 2026-06-21 |
| DA-19 | Gate de EDGE para conta real (`src/risco/edge_config.py`): abertura REAL exige edge líquido validado (walk-forward) E fresco. Default-CLOSED, auto-expira por frescor, fail-closed no erro. Só ENTRADA real passa; SAÍDA (SELL) nunca. Alimentado pelo runner do walk-forward (`ATUALIZAR_EDGE=1`); persiste em `RepositorioConfig` (chave `edge_config`) | "Esperto, rápido, seguro, lucrativo e principalmente seguro": o bot só arrisca capital quando há lucratividade PROVADA out-of-sample, e auto-ativa quando ela surge. Camada INDEPENDENTE (defense in depth), além de PERMITIR_CONTA_REAL. Hoje registro vazio ⇒ real bloqueado (honesto: sem edge) | 2026-06-21 |
| DA-20 | `/v1/sessao/status` lê sessão com `incluir_credenciais=False` (segredo não sai do store em caminho que não o usa). NÃO flipar o default global de `incluir_credenciais` (autotrader precisa de credenciais no loop) | SEC-01 mitigação segura: reduz superfície de vazamento sem quebrar o trading autônomo. Limpeza de credenciais no logout/expiração já existia; agora travada por testes | 2026-06-21 |

---

## DESCOBERTAS PENDENTES DE INVESTIGAÇÃO

| Suspeita | Módulo | Investigar com |
|----------|--------|----------------|
| ~~`ai_advisor.py` usa `lstrip("```json")`~~ | `src/servicos/ai_advisor.py` | ✅ RESOLVIDO: `_remover_cerca_markdown` com removeprefix/suffix + 4 testes (caminho ativa só com chave OpenAI) |
| ~~`dashboard.py` instancia `ClienteBinance()` sem credenciais~~ | `src/servicos/dashboard.py` | ✅ FECHADO: seguro (retorna `{disponivel: False}`) |
| ~~`capital_manager.py` aloca 70% em capital ≤$20 com alvo 0.1%~~ | `src/multiativo/capital_manager.py` | ✅ VERIFICADO COERENTE: `_TAKE_PROFIT_ALVO` é heurística de SIZING (sem custo), não vaza p/ gate de saída; gate de custo real é profit_guard+risk_engine (round-trip). Não alterar |
| ~~`ev_calculator.py`: `fee=0.0012` round-trip?~~ | `src/probabilidade/ev_calculator.py` | ✅ RESOLVIDO (BUG-02): `(fee+slippage)*NUMERO_DE_PERNAS` round-trip |
| ~~`base.py` morto?~~ | `src/persistencia/base.py` | ✅ RESOLVIDO na F1 (removido, 0 imports) |
| Triangular arbitrage: custo por perna correto? | `src/multiativo/triangular_arbitrage.py` | ✅ VERIFICADO: aplica taxa+slippage POR PERNA no loop (3×, modelo correto p/ 3-leg) |

---

## MÉTRICAS DE QUALIDADE

```
Data da medição:     2026-06-19 (após F1+F2+F4 parcial+F5+F9)
Testes:              115 passou / 0 falhou / 115 total / 0 skipped
Cobertura global:    não medida (instalar pytest-cov)
Mypy erros (strict): não medido (instalar mypy)
Ruff violations:     não medido (instalar ruff)
Maior arquivo (LOC): src/servicos/testnet_auto_trader.py — 2467 linhas
2º maior:            src/main.py — 1176 linhas
3º maior:            src/servicos/noticias.py — 773 linhas
Total src/:          13.321 linhas em ~70 módulos .py
IC médio:            n/d (banco de produção não versionado)
Brier score:         n/d
```

---

## PRÓXIMOS PASSOS

```
[1] PRÓXIMA AÇÃO: FASE 6 — decompor god-file `testnet_auto_trader.py` (2467 linhas) em
                  autotrader/{ciclo_trading,gestor_estado,loop_principal,configurador} e, junto,
                  ativar UoW (DA-04) envolvendo criar_ordem + salvar_snapshot. WIRING do circuit
                  breaker no loop (consultar esta_em_halt antes de submeter) acontece aqui.
[2] BLOQUEADOR:   Nenhum para F6. mypy/ruff/cov rodam na CI (advisory); instalar local p/ medir cobertura.
[3] AGENTE:       REF (extração) + EXE/GRD (wiring do breaker) → TST → REV
[4] CRITÉRIO:     pytest segue 115 verde; nenhuma função > 50 linhas no autotrader pós-decomposição
[5] PENDÊNCIAS:   F5 graceful shutdown (signal handlers — adiado, melhor com loop decomposto);
                  INC-02 (modelo_llm origem), INC-03 (taxa efetiva fluxo manual), INC-05 (snapshot R-M-W),
                  SEC-01 (credenciais texto puro), PERF-01 (joblib.load), durabilidade ajustes_testnet.
[6] BANCO VETORIAL: adiar até dado real + caso de retrieval (RAG p/ Gemini). sqlite-vec/Chroma local
                  atrás de contratos/RepositorioVetorial. Não é pré-requisito hoje.
```

---

## PARECERES DE EXPANSÃO E WIRING PENDENTE (decisões para revisão humana)

### Wiring do circuit breaker (DEFERIDO p/ F6 — segurança)
Módulo `src/executor/circuit_breaker.py` está pronto, persistido e testado. NÃO foi wireado no
loop porque `testnet_auto_trader.py` tem 4 pontos de submit espalhados (L~2266/2277/2332/2382) e
o registro de PnL em outro ponto — cirurgia no god-file sem supervisão poderia quebrar o próprio
mecanismo de segurança. **Plano F6 (após decompor o loop):**
- `_fase_execucao`: `if breaker.esta_em_halt(): return "HALT"` ANTES de `ger.criar_ordem_*`.
- `_fase_registro`: `breaker.registrar_resultado(pnl_liquido, capital_total); await breaker.salvar()`.
- `iniciar()`/startup: `await breaker.carregar()` (recupera halt persistido).
- Instância única no `__init__` do trader.

### MCP (Model Context Protocol) — parecer: ADIAR (não agora)
Benefício real é expor o bot a um agente externo (Claude/Gemini) como ferramentas (ex.: "status do
bot", "métricas", "halt"). É valioso para OPERAÇÃO assistida por IA — exatamente a fase futura do
usuário. Mas hoje não há consumidor; adicionar um servidor MCP agora é superfície sem uso.
**Gatilho:** quando a integração com IA começar. **Forma enxuta:** 1 servidor MCP fino expondo
funções já existentes (status/métricas/validar_config/halt) — sem nova lógica de negócio.

### n8n — parecer: ADIAR (provável overkill)
n8n é orquestração visual de workflows/integrações (alertas, webhooks, cron). O projeto já tem
FastAPI + tarefas internas + (futuro) circuit breaker. Introduzir n8n adiciona um serviço externo
para coordenar — contra "manter compacto". **Alternativa enxuta:** alertas (halt, drawdown) via um
`observabilidade/alertas.py` simples (webhook/Telegram) quando necessário, sem orquestrador externo.
**Gatilho p/ n8n:** se surgirem muitas integrações externas heterogêneas que valham UI de workflow.

### Bibliotecas — parecer: manter mínimo
Stack atual cobre o necessário. Só adicionar com benefício claro: `sqlite-vec`/`chromadb` (vetorial,
quando a Gemini entrar), `structlog` (se quiser logging estruturado mais rico que o atual). Evitar
deps transitivas como API (ex.: scipy via sklearn) — métricas de qualidade usam só numpy de propósito.

### SEC-01 (credenciais em texto puro em memória) — parecer: NÃO mexer sem supervisão
`sessoes.py` com `SESSION_STORE_CREDENTIALS=True` mantém api_key/secret em dict global. O autotrader
PRECISA das credenciais persistidas em memória para o loop em background — flipar o default p/ False
quebraria o trading autônomo. Mitigação real não é "cifrar em memória" (não protege contra dump do
processo). **Recomendações (revisar com humano):** (1) limpar credenciais no logout/expiração de
sessão; (2) reduzir TTL de sessão; (3) garantir que segredos nunca vão a log/serialização (já ok via
`core/segredos.py`); (4) avaliar manter só `secret_id` + buscar do ambiente on-demand no loop.

---

## LOG DE SESSÕES

| Data | Fase | O que foi feito | Agentes | Testes antes/depois |
|------|------|-----------------|---------|---------------------|
| 2026-06-19 | 0 | Contexto inicial criado | ORQ, REV | —/— |
| 2026-06-19 | 0 | Mapeamento real: baseline 82/92, reconciliação estrutura REAL×ALVO, correção de caminhos de bugs, criação do time completo de agentes + skill.md + ambiente | ORQ, REV | —/82-passou |
| 2026-06-19 | 1+2 | BUG-01..07 corrigidos + 4 arquivos mortos removidos + 9 testes novos (EV, calibrador). Auto-trader: restauradas calibrações testnet e teto de notional via env | OBS, EXE, QNT, REF, TST, REV | 82/92 → 101/101 |
| 2026-06-19 | 4 (parcial) | INC-06 fonte única `core/constantes_mercado.py`; INC-01 limiares nomeados+documentados (não simetrizado sem dado); INC-04 profit_guard com gate de custo independente. +4 testes | QNT, SIN, PER, GRD, TST, REV | 101/101 → 105/105 |
| 2026-06-19 | 5+9 | F5: idempotencia.py (newClientOrderId em toda ordem), circuit_breaker.py (halt persistido, reset humano), validacao_config.py (fail-fast). F9: ci.yml + pre-commit + [dev] extras. Diretriz "Tradutor/Otimizador" no CLAUDE.md. +10 testes | EXE, GRD, TST, ORQ, REV | 105/105 → 115/115 |
| 2026-06-20 | lacunas | PERF-01 (cache modelo por mtime), INC-02 (modelo_llm honesto), INC-05 (snapshot RMW atômico), INC-03 (fonte única taxa efetiva). +6 testes. Trabalho autônomo em ciclos | EXE, OBS, PER, QNT, TST, REV | 115/115 → 121/121 |
| 2026-06-20 | 7 | Observabilidade: `qualidade_sinal.py` (IC/Brier/drawdown, só numpy) + `correlacao.py` (correlation_id). +5 testes. Pareceres MCP/n8n/SEC-01 + plano de wiring do breaker registrados | OBS, TST, REV | 121/121 → 126/126 |
| 2026-06-20 | 6 (parcial) | Pacote `src/autotrader/` + extração segura de `calculos` e `configurador` (re-export, testes intactos). God-file 2467→2371. Descoberto breaker de perda diária JÁ existente (não duplicar). +2 testes | REF, TST, REV | 126/126 → 128/128 |
| 2026-06-20 | run+P1 | Analisado run 13-18h (0 trades; modelo online saturado em 18 amostras/coef 71). FIX P1: gate de amostras mínimas + guarda de divergência (`MIN_AMOSTRAS_ONLINE`). Teste de EDGE: IC=-0.03, acc 48.5% → SEM edge. Não deployei modelo batch. Segredos destrackados do git. +1 teste | EXE, QNT, OBS, TST, REV | 128/128 → 129/129 |
| — | VEREDITO | Engenharia sólida e SEGURA; LUCRATIVIDADE não é problema de código (sem edge nos dados atuais). Próximo gargalo = coleta contínua de dado real + pesquisa de edge. Ver `.claude/run_analise_2026-06-20.md` | — | — |
| 2026-06-20 | edge+saida | Harness `scripts/pesquisa_edge.py`: 24/24 configs com ret/trade NEGATIVO (fee 0,24% > sinal) → minitrading 1-15m perde por matemática. Stop-loss invertido p/ ATIVO por padrão (sair antes de prejuízo). +2 testes de saída | QNT, EXE, TST, REV | 129/129 |
| 2026-06-20 | sincronização | Auditoria de fluxo/custo. FLX-01: posição-fantasma corrigida NA FONTE (`_ordem_foi_preenchida` gate as 2 pernas antes de abrir/encerrar ciclo). INC-07: slippage round-trip em `filtro_ev` (alinhado a EVCalculator/profit_guard, DA-02). +3 testes. Verificado: fee round-trip coeso nas 3 camadas; daily-loss breaker correto (abs só em perda); convenção de unidades taxa%/slippage-decimal documentada e consistente | EXE, GRD, QNT, TST, REV | 129 → 132 |
| 2026-06-20 | sincronização-2 | Varredura multiativo+IA. ai_advisor: `lstrip("```json")`→`_remover_cerca_markdown` (removeprefix) +4 testes. Verificado COERENTE (sem alterar): capital_manager (TP alvo é só sizing, não vaza p/ gate), opportunity_scanner (taxa×2 pré-dobrada + profit_guard dobra slippage), triangular_arbitrage (custo por perna 3×), orquestrador (fluxo sinal→scanner→exec). 5 pendências de investigação FECHADAS | SIN, QNT, OBS, TST, REV | 132 → 136 |
| 2026-06-21 | edge-governanca+SEC-01 | **Gate de EDGE (DA-19):** `src/risco/edge_config.py` — núcleo PURO `avaliar_edge` (default-closed, frescor/auto-expira) + `RegistroEdge` durável (RepositorioConfig) + `registrar_resultado_edge` (veredito do walk-forward → `ativo`, critério estrito: tem_edge ∧ n_trades≥30 ∧ IC≥0.02 ∧ net≥0). Wireado na abertura REAL do autotrader (`_gate_edge_conta_real`, fail-closed; SELL/testnet isentos). Runner do walk-forward grava o registro (`ATUALIZAR_EDGE=1`). API `/v1/edge` + edge em `/v1/diagnostico`. **SEC-01 (DA-20):** `/v1/sessao/status` agora `incluir_credenciais=False`; invariante de limpeza no logout/expiração travado. +18 testes. Hoje registro de edge VAZIO ⇒ entrada real bloqueada por desenho (sem edge nos dados — honesto) | GRD, QNT, EXE, OBS, TST, REV | 168 → 186 |
| 2026-06-21 | P2-persistencia | Caminho A produção: P2 COMPLETO. `_persistir_ordem_executada` grava cada execução (BUY/SELL) na tabela `ordens` + seta `ciclo_ordem_id_*` (ativa o registro de lucro/regime por ordem, FLX-02). `ciclo_ordem_id_*` init/reset em _novo_estado/_abrir_ciclo/_encerrar_ciclo. `RepositorioOrdens.obter/listar_recentes` retornam colunas de resultado. Best-effort (falha não derruba ciclo). +3 testes. Diagnóstico 5h: bot executou 2 SELLs reais mas invisíveis na UI (gap fechado agora) | PER, EXE, GRD, TST, REV | 165 → 168 |
| 2026-06-21 | log+ic-join | Verificado log.txt do restart: SEM erro real (38 linhas, todas INFO; os "401" iniciais são polls pré-login, viram 200 após /v1/sessao/entrar). Coletor contínuo confirmado rodando (3/3). Fix follow-up: o join do IC-de-retorno exigia ts exato, mas `ts_previsao` é meio-de-minuto → 0 matches; corrigido p/ floor-ao-minuto (18595 matches). IC de retorno real agora: BTC 0.089, ETH -0.034, BNB 0.003. +ajuste de 2 testes. Pendente: restart p/ o fix do IC ir ao vivo (servidor roda versão anterior; só observabilidade) | OBS, QNT, TST, REV | 165 |
| 2026-06-21 | espiada-online+fix | Espiei o servidor online (/v1/diagnostico). Confirmado: gate anti-divergência funcionando AO VIVO (online coef_norm=70.88 saturado, 18 amostras → online_em_uso=false; batch ausente → bot no fallback heurístico). **FALHA achada+corrigida:** `resumo_qualidade_recente` correlacionava PREÇO×PREÇO (IC espúrio 0.97 = falso sinal); reescrito p/ IC de RETORNO (join ohlcv ref) +2 testes. READMEs (raiz+src) reescritos fiéis ao estado atual. `.env`/`.env.example`: ATIVAR_COLETA_CONTINUA ligado | OBS, QNT, REF, REV | 164 → 165 |
| 2026-06-21 | limpeza-estrutural | Varredura completa. REMOVIDOS: `mec.txt` (⚠️ segredos em texto puro — ROTACIONAR), `log.txt` (78KB stale), `oraculo.egg-info/` (artefato build, +gitignore), `migrations/schema_mysql.sql` (schema MySQL divergente não-usado), `simple_backtester.py` (substituído por walk_forward), `calibracao/ewls.py` (stub no-op), planos defasados (`oraculo_plano_implementacao.md`, `PLANO_IMPLEMENTACAO_V3.md`), agent spec duplicado (`AGENTS.md`, `agente.codex` — canônico = CLAUDE.md + .claude/). MANTIDOS: uow.py, treinador_batch.py (infra útil). Docs ressincronizados (READMEs). Suíte intacta | REF, REV | 164 (sem mudança) |
| 2026-06-21 | edge-infra | Coletor contínuo (`tarefas/coletor_continuo.py`, env ATIVAR_COLETA_CONTINUA, reusa coletar_e_persistir, wirado no lifespan) + backtester WALK-FORWARD (`backtester/walk_forward.py` + script) com matemática de lucro LÍQUIDO correta (bruto = alvo + custo round-trip via EVCalculator). +11 testes. Veredito walk-forward: SEM edge líquido (net/trade<0 em todas configs). Pré-requisitos honestos p/ perseguir edge entregues | QNT, OBS, TST, REV | 153 → 164 |
| 2026-06-21 | api+operacional | Caminho A: micro-trading 1-15m OPERACIONAL + saídas de API. F7 wirado: `/v1/modelos/treino` (gate online, coef_norm/divergência, IC recente do banco), `/v1/ai/saude` (vida do LLM, fallback), `/v1/diagnostico` (consolidado). Módulos: `observabilidade/saude_modelo.py`, `ai_advisor.saude_llm`, status() enriquecido. Modo exploração (DA-18) testnet-only. +15 testes. Validado ao vivo: bot opera (assume/monitora posição) mas segura racionalmente no prejuízo líquido → no-edge reconfirmado. Saída inteligente (trailing+stop+lucro-mínimo) já existia e está ativa | OBS, EXE, GRD, QNT, TST, REV | 138 → 153 |
| 2026-06-21 | edge-fee | Harness ampliado (fee-sensitivity + seletividade). Melhor bruto/trade=0,056% (ETHBTC h60) < fee BNB 0,15% → FEE NÃO É O GARGALO, sinal bruto fraco demais. BTCUSDT IC≈0. Único quase-viável: BNBUSDT h60 seletivo (top 25%, acerto 79,8%, break-even após BNB) — pista, não edge (amostra minúscula, split único). Minitrading 1-15m morto por matemática. Detalhes em run_analise | QNT, REV | 138 |
| 2026-06-21 | validação-testnet | Validação ao vivo com credenciais reais (testnet, autorizado). Login OK (USDT~74k). Run de 5 ciclos: pipeline dado→sinal→decisão→auditoria→shutdown sem erro; BTCUSDT HOLD, 0 ordens (gates de custo seguraram). Round-trip real BUY+SELL $15: ambos FILLED, `_ordem_foi_preenchida`=True (FLX-01 validado contra API real), clientOrderId idempotente setado. P&L round-trip ≈0 bruto / negativo após fee = prova viva do veredito de edge. Nota: símbolos não-foco têm score_num saturado (±1.0) — não perigoso (gates usam lucro líquido), nota p/ edge | EXE, GRD, QNT, REV | 138 (sem mudança de código) |
| 2026-06-21 | run-longo | Hardening p/ runs longos. DA-15: `exigir_config_valida()` wireado no lifespan (fail-fast). DA-17: reset de `daily_loss_usdt` no virar do dia (+2 testes). DA-16: confirmado que halt financeiro persiste via `retomada_operacoes_bloqueadas` (sobrevive restart) → NÃO wirar circuit_breaker.py redundante. FLX-02: bug latente regime/estrategia (`ultimo_sinal` string) + swallow silencioso corrigidos. Verificado: SQLite WAL+busy_timeout+foreign_keys por conexão; loop com recuperação de erro + finally fecha clientes; sem crescimento de estado (históricos capados) | EXE, GRD, OBS, TST, REV | 136 → 138 |
