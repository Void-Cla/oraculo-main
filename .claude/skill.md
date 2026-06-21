# SKILL — LIÇÕES E ATALHOS DO ORACULO
> Conhecimento destilado do projeto. Carregue junto com `.claude/contexto.md` no início de cada sessão.
> Objetivo: **economizar tokens** — evitar re-descobrir o que já sabemos e não repetir erros já cometidos.
> Regra de ouro: se uma lição aqui evita reler um arquivo grande, ela já se pagou.

---

## 0. SEQUÊNCIA DE PARTIDA (faça nesta ordem, sempre)

```
1. Ler .claude/contexto.md   → estado atual + mapa REAL×ALVO + bugs
2. Ler .claude/skill.md      → este arquivo (armadilhas e atalhos)
3. Só então abrir código     → e SEMPRE pelo caminho REAL, nunca o do CLAUDE.md
```
Não releia o código inteiro para "entender o projeto" — o contexto.md + skill.md são a foto. Releia código só do arquivo que vai tocar.

---

## 1. A ARMADILHA Nº 1 — ESTRUTURA REAL ≠ ESTRUTURA DO CLAUDE.md

O CLAUDE.md descreve uma estrutura-**ALVO** (`src/dominio/`, `src/execucao/`, `src/autotrader/`, `src/sinais/probabilidade/`). **Ela não existe hoje.** Editar por esses caminhos = editar o vazio.

| Você quer… | NÃO está em… | Está REALMENTE em… |
|------------|--------------|--------------------|
| EV calculator | `src/dominio/` | `src/probabilidade/ev_calculator.py` |
| risk engine | `src/dominio/` | `src/risco/risk_engine.py` |
| profit guard | `src/dominio/` | `src/multiativo/profit_guard.py` |
| gerenciador de ordens | `src/execucao/` | `src/executor/gerenciador_ordens.py` |
| autotrader | `src/autotrader/` | `src/servicos/testnet_auto_trader.py` |
| regime detector | `src/sinais/regime/` | `src/meta_strategy/regime_detector.py` |
| circuit breaker / idempotência | `src/execucao/` | **NÃO EXISTEM** — criar na Fase 5 |

→ Tabela completa REAL×ALVO está no contexto.md. **Migração de pastas = só na Fase 6 (DA-06).** Não renomeie antes.

---

## 2. AMBIENTE — COMANDOS QUE FUNCIONAM AQUI (Windows + venv)

```bash
# Python correto: o do venv (Python 3.14). Em Git Bash:
.venv/Scripts/python.exe -m pytest -q --tb=no

# DB_PATH é obrigatório p/ rodar testes/app. Default do .env: ./dados/oraculo.sqlite
DB_PATH="./dados/oraculo.db" .venv/Scripts/python.exe -m pytest -q

# Maiores arquivos (NÃO usar `wc -l src/**/*.py` — glob recursivo falha no bash):
find src -name '*.py' -exec wc -l {} + | sort -rn | head -10
```

- **Deps** estão em `requirements.txt` (não no `pyproject.toml [project.dependencies]`).
- **mypy, ruff, black, isort, pytest-cov NÃO estão instalados.** O CLAUDE.md os promete, mas são da Fase 9. Não rode esses comandos esperando sucesso até instalá-los (`pip install -e ".[dev]"` após adicionar os extras).
- Caminho do projeto tem espaço e acento ("Área de Trabalho") — sempre entre aspas.

---

## 3. BASELINE — O NÚMERO QUE NÃO PODE REGREDIR

```
pytest: 82 passou / 10 falhou / 92 total   (NÃO são 95 testes)
```
As 10 falhas são **herdadas** (não foram introduzidas por nós). Mapeamento → bug raiz:
- `test_pipeline`, `test_fluxo_usuario_signal_queue` → BUG-01 (logger NameError) escondido atrás de onboarding
- `test_api_sessao_painel` (3) → BUG-04 (endpoint ignora notional) / auto bot
- `test_testnet_auto_trader` (5) → teto de notional, calibração testnet, stop por flag

Após qualquer mudança: `passou ≥ 82`. Menos que isso = regressão = pare.

---

## 4. ARMADILHA Nº 2 — CÓDIGO MORTO POR SUBSTRING É MENTIRA (DA-07)

`grep "base"` retornou **22 falsos-positivos** (database, base classes…). Validar morto SÓ por import:
```bash
grep -rE "from [a-zA-Z0-9_.]*\bMOD\b import|import [a-zA-Z0-9_.]*\bMOD\b" src
```
- **Mortos confirmados (0 imports):** `coletor_noticias`, `coletor_velas_15s`, `coletor_velas_ws`.
- **`uow.py`:** morto hoje, mas ALVO o reativa (F4) → **mover para histórico, não deletar.**
- **`base.py`:** "morto" NÃO confirmado — verifique imports reais antes de remover.

---

## 5. ARMADILHA Nº 3 — A SEMÂNTICA DO FEE (não corrija no automático)

A regra é round-trip (2 pernas): `custo = notional * taxa * 2`. **MAS:**
- `gerenciador_ordens.py:107` → `custo_total = notional * taxa` = inequivocamente single-leg → ×2. (BUG-03)
- `ev_calculator.py` → modelo **fracional**: `EV = p_win*avg_win - p_loss*avg_loss - (fee+slippage+spread)`, `fee` default `0.0012`. **Antes de duplicar, decida:** esse 0.0012 já é round-trip ou não? O contexto.md (e a análise) descreviam `custos = notional * taxa` — **esse trecho NÃO existe nesse arquivo.** Confie no código que você lê, não na descrição. (BUG-02 — passar pela QNT)

Lição geral: **a análise (`analise-oraculo-main.md`) é excelente mas parcial (~47/124 arquivos lidos).** Trate-a como mapa de suspeitas confirmadas, não como verdade literal sobre cada linha. Sempre confirme no arquivo real.

> **Slippage também é round-trip (INC-07).** As 3 camadas de custo precisam concordar: `EVCalculator`
> faz `(fee+slippage)*2`, `profit_guard` reconstrói `taxa_rt + slippage*2`, e `filtro_ev` agora faz
> `taxa*2 + slippage*2`. Antes, `filtro_ev` aplicava slippage 1× → EV inflado no gate. Invariante
> travado por `test_custo_taxa_e_slippage_sao_round_trip`. **Convenção de unidade:** taxa em % (÷100),
> slippage em decimal — documentada em `filtro_ev`. Não misture (risco de erro de 100×).

---

## 5.1. INVARIANTE DE EXECUÇÃO — NUNCA MUTE O CICLO SEM CONFIRMAR O FILL (FLX-01)

Causa-raiz nº 2 do run 13-18h (posição-fantasma): o BUY abria ciclo com quantidade **teórica** mesmo
quando a ordem voltava `executedQty=0` / status `NEW/EXPIRED/REJECTED`. Resultado: `ciclo_ativo=True`
sem ativo real → trava em `limite_trades_abertos` e registra PnL inexistente.

- **Regra:** só `_abrir_ciclo`/`_encerrar_ciclo` se `_ordem_foi_preenchida(ordem)` (status FILLED/
  PARTIALLY_FILLED **ou** `executedQty>0`). Guard nas DUAS pernas (compra e venda).
- A reconciliação (`_sincronizar_ciclo`) é a REDE (cura no próximo loop a partir do saldo real), o
  guard é a PREVENÇÃO (na fonte). Precisa dos dois.
- Ao adicionar qualquer novo caminho que submeta ordem: verifique o fill ANTES de mexer no estado.

---

## 6. ORDEM DE ATAQUE AOS BUGS (menor risco → maior valor)

```
1. BUG-01 logger (OBS)      → barato, destrava 2 testes, sem risco financeiro
2. BUG-04 notional endpoint → destrava testes de API, lógica clara
3. BUG-03 fee single-leg    → ×2 em gerenciador_ordens (QNT+GRD)
4. BUG-02 fee EV            → exige decisão de semântica primeiro (QNT)
5. BUG-05 ajustes_sinal None, BUG-06 exp overflow → guards defensivos
6. INC-01..06, SEC-01, PERF-01 → inconsistências de design (debater antes)
```
Sempre: teste vermelho ANTES da correção (TST) → corrige → verde. Tocou dinheiro → GRD.

---

## 7. PADRÕES BONS DO PROJETO (copie, não reinvente)

- `repositorio_fila_sinais.py` → `BEGIN IMMEDIATE` = claim atômico. **Padrão de referência** p/ concorrência.
- `core/segredos.py` → nunca guarda segredo no banco, só `secret_id` (env var) + regex. Mantenha.
- `risk_engine.py` → puro, determinístico, cada veto nomeado. Não introduza I/O aqui.
- 4+ gates `PERMITIR_CONTA_REAL` (defense in depth, default-false). Nunca reduza a contagem.
- `noticias.py` → `_llm_permitido()`: limite diário 20 + cooldown 60min após 5 falhas. Bom controle de custo.

---

## 8. ANTI-PADRÕES QUE JÁ APARECERAM (não reintroduzir)

```python
try: x = filtros          # ❌ try/except NameError como controle de fluxo (já removido 1×)
except NameError: ...
texto.lstrip("```json")    # ❌ lstrip remove CONJUNTO de chars, não substring → use removeprefix
custo = notional * taxa    # ❌ single-leg (falta * 2)
"modelo_llm": "gpt-4o-mini"# ❌ hardcoded mesmo em fallback heurístico → mente na auditoria
self._em_halt = False      # ❌ reset automático de halt (só humano pode — DA-03)
logger.info(...)           # ❌ usar logger sem importar (BUG-01)
```

---

## 9. REGRAS DE PROCESSO (economia de token + segurança)

1. **Não releia código que o contexto.md já resume.** Releia só o arquivo-alvo.
2. **Toda mudança financeira passa pelo GRD** (executor/, risco/, ev_calculator, profit_guard, autotrader, main.py).
3. **REV atualiza contexto.md após cada mudança significativa** — senão a próxima sessão re-descobre tudo.
4. **Confirme no arquivo real** antes de citar caminho/linha — docs e análise podem estar desatualizados.
5. **Um commit faz uma coisa:** ou organiza, ou corrige bug, ou refatora — nunca os três juntos.
6. **Na dúvida entre velocidade e segurança financeira: segurança.** Capital perdido não volta.

---

## 10.5. AUTO-TRADER (god-file): FLAGS E CALIBRAÇÕES — mapa rápido

`src/servicos/testnet_auto_trader.py` é o maior arquivo (2467 linhas). Pontos que já custaram tempo:

**Flags de ambiente (default-seguro):**
- `AUTO_MAX_NOTIONAL_USDT` — teto de notional por operação. Ausente/≤0 = sem teto (permite testnet alto). Lido por `_teto_notional_operacional_usdt()` → aplicado em `_normalizar_notional_operacional` → `_novo_estado`.
- `AUTO_PERMITIR_STOP_COM_PREJUIZO` — `true` libera fechar posição no vermelho (`stop_protecao_acionado`). Default `false` = bloqueia (`prejuizo_liquido_bloqueado`).

**Calibração testnet (micro-trading) — quem mexer aqui, mantenha os valores:**
- `_usuario_virtual(..., modo_testnet=True)`: freios SEMPRE conservadores (max_trades_abertos→1, por_hora→3, cooldown→≥10, flip-flop on, exposição≤0.20, risk_per_trade≤0.005, max_loss≤0.20). Testnet rebaixa pisos: lucro_liquido_minimo=0.0002, lucro_liquido_minimo_usdt=0.001, filtro_ev_minimo_usdt=0.001. Conta real mantém hard floors ($0.01).
- `_ajustes_microtrading_auto`: `limiar_variacao_numerica` recebe ×1.2; testnet capa overrides altos (lucro_min_usdt→0.001, signal_min_ev→0.0008, signal_min_prob→0.62). Caps só "mordem" overrides altos — defaults passam intactos (por isso integração não quebra).

**Armadilha de edição:** `if not False:` na L947 era placeholder de uma flag (BUG-07). Sempre suspeite de `if not False:`, `if True:`, `if 1:` — são edições pela metade.

**`custo_estimado` de `simular_ordem` NÃO é lido por ninguém** — é informativo. Corrigir o fee ali (round-trip) é seguro mas não muda decisão.

## 10.6. SEGURANÇA (FASE 5) E DIRETRIZ DE OPERAÇÃO

**Diretriz permanente** (CLAUDE.md → "Tradutor e Otimizador Interno"): remasterize internamente
todo comando simples como se fosse de um gênio QI 900; entregue no nível AA+ (segurança militar,
semântica, fluxo lógico, arquitetura por responsabilidade); equipe QI 600; honestidade > agradar;
nada de over-engineering. É invisível — não devolva o prompt reescrito.

**Módulos de segurança (em `src/executor/` + `src/core/`):**
- `executor/idempotencia.py` → `gerar_client_order_id(...)`: hash SHA-256 da intenção, ≤36 chars. ON por padrão em `criar_ordem_market/limit` (PSF-03/DA-12).
- `executor/circuit_breaker.py` → `CircuitBreaker`: halt por drawdown%; reset SÓ humano. **NÃO está wireado e NÃO deve ser (DA-16):** o halt financeiro canônico já existe inline (breaker de perda diária) + persiste em `retomada_operacoes_bloqueadas`. Dois breakers = redundância/segunda-verdade. Reservado p/ consolidação supervisionada futura.
- `core/validacao_config.py` → `validar_config()/exigir_config_valida()`: fail-fast no startup. **Wireado no `lifespan` do main.py (DA-15).** Pega conta real sem chave, DB de teste em modo real, drawdown fora de faixa (PSF-01).

## 10.7. RUN-LONGO — O QUE MATA UM RUN DE HORAS/DIAS (não aparece em 1 ciclo)

Checklist verificado (2026-06-21) — tudo OK, mas RE-CONFIRME se mexer:
- **Halt financeiro sobrevive a restart?** SIM — `retomada_operacoes_bloqueadas` (RepositorioConfig) é relido em `_inicializar_retomada` no startup; `iniciar` recusa operar; API responde 423. Reset = humano.
- **`daily_loss_usdt` reseta no virar do dia?** SIM (DA-17) — `_resetar_perda_diaria_se_novo_dia` no `_loop`. Senão "perda diária" vira cumulativa e trava cedo. NÃO destrava `circuit_tripped` (dia ruim ainda exige revisão).
- **SQLite concorrente (loop+API+consumidor)?** OK — `criar_conexao()` aplica WAL + `busy_timeout=5000` + `foreign_keys=ON` em TODA conexão. busy_timeout/foreign_keys são por-conexão (não esquecer em conexões novas).
- **Recuperação de erro no loop?** OK — exceção por ciclo é capturada, conta `consecutive_errors` (reset no sucesso), trip no limite; `CancelledError` propaga; `finally` fecha os 3 clientes Binance.
- **Crescimento de estado?** OK — `historico_ciclos` capado em 20, `historico_execucoes_ts` em 50, `pares_estado`/cache de modelo limitados por nº de símbolos.
- **Posição-fantasma em run longo?** Coberto (FLX-01): fill verificado nas 2 pernas antes de abrir/encerrar ciclo + reconciliação.

**CI (FASE 9):** `.github/workflows/ci.yml` — testes + `validar_config` são bloqueantes; ruff/black/isort/mypy são **advisory** (`continue-on-error`) porque o código legado não nasceu sob eles (DA-14). Tornar bloqueante após o 1º passe de formatação. `pre-commit install` para rodar local.

## 11. PADRÃO DE FIX DE BUG (validado nesta sessão)

1. Ler o teste que falha ANTES de tocar o código — ele revela o comportamento esperado exato.
2. Conferir no arquivo real (a análise/contexto podem estar desatualizados — ex.: BUG-02 não era `notional*taxa`).
3. Corrigir com constante nomeada + comentário de origem; nada de número mágico.
4. Rodar o cluster do teste, depois a suíte inteira. `passou` nunca pode cair.
5. Bug financeiro → teste de propriedade (ex.: `test_ev_calculator`: aumentar fee nunca aumenta EV).
6. Atualizar contexto.md (status do bug) + skill.md (lição) — senão a próxima sessão re-descobre.

## 10. ATUALIZE ESTE ARQUIVO

Aprendeu algo novo que evitaria reler um arquivo grande ou repetir um erro? Adicione aqui (1 linha densa).
Este arquivo é o segundo cérebro do projeto, junto com contexto.md. Mantê-lo enxuto e verdadeiro é o que economiza tokens.

| Lição | Data |
|-------|------|
| Estrutura REAL ≠ ALVO; sempre usar caminho real | 2026-06-19 |
| Código morto só por import, nunca substring (22 falsos-positivos com "base") | 2026-06-19 |
| ev_calculator usa modelo fracional, não `notional*taxa` — confirmar no arquivo | 2026-06-19 |
| Slippage também é round-trip (×2): EVCalculator/profit_guard/filtro_ev TÊM de concordar (INC-07) | 2026-06-20 |
| Nunca mutar o ciclo sem confirmar o fill da ordem (FLX-01) — `_ordem_foi_preenchida` nas 2 pernas | 2026-06-20 |
| `lstrip(substr)` remove CONJUNTO de chars, não prefixo — use `removeprefix`/`removesuffix` | 2026-06-20 |
| Run-longo: perda "diária" tem de resetar no dia; halt financeiro tem de persistir restart (DA-15/16/17) | 2026-06-21 |
| EDGE: fee NÃO é o gargalo — melhor sinal bruto (0,056%) < fee mais barato (BNB 0,15%). Minitrading 1-15m perde por matemática | 2026-06-21 |
| Validação testnet OK ao vivo: login, pipeline 5 ciclos HOLD, round-trip real BUY+SELL FILLED, FLX-01/idempotência confirmados na API real | 2026-06-21 |
| Pista de edge (não confirmada): BNBUSDT h60 seletivo (top 25%) ~break-even após BNB, acerto 80% — exige walk-forward + mais dado antes de operar | 2026-06-21 |
| Modo exploração (`AUTO_MODO_EXPLORACAO`) liga o micro-trading 1-15m — TESTNET-ONLY (DA-18); conta real força `permitir_ev_negativo=False`. Bot opera mas segura racionalmente no prejuízo líquido (no-edge) | 2026-06-21 |
| Saídas de API: `/v1/modelos/treino` (gate/coef_norm/IC), `/v1/ai/saude` (vida LLM), `/v1/diagnostico` (consolidado). Saída inteligente (trailing+stop+lucro-mín) já existe em `_avaliar_saida_ciclo` | 2026-06-21 |
| Gotcha: `valor or default` trata `0.0` como ausente → use `if-else` quando 0 é válido (bug do piso de saída em exploração) | 2026-06-21 |
| Lucro LÍQUIDO = bruto − TODAS as taxas (round-trip). P/ X líquido, mire bruto = X + custo; o custo NÃO é lucro. `walk_forward.bruto_necessario_para_liquido_*` (custo via EVCalculator, fonte única) | 2026-06-21 |
| Coletor contínuo: `ATIVAR_COLETA_CONTINUA=true` (REST público, sem credencial) acumula dado real p/ pesquisa de edge. Backtester walk-forward: `scripts/backtest_walkforward.py`. Veredito atual: sem edge líquido | 2026-06-21 |
| GATE DE EDGE (DA-19): conta real só ABRE posição se `src/risco/edge_config.edge_aprovado_conta_real(simbolo)` aprovar (default-closed, frescor, fail-closed). Liga-se SOZINHO quando o walk-forward grava edge (`ATUALIZAR_EDGE=1`). SELL/testnet NÃO passam pelo gate. Ver `/v1/edge`. Hoje vazio ⇒ real bloqueado (honesto) | 2026-06-21 |
| SEC-01 (DA-20): credenciais JÁ são limpas no logout/expiração; caminhos que não usam segredo devem ler `obter_sessao(..., incluir_credenciais=False)`. NÃO flipar o default global (loop autônomo precisa das credenciais) | 2026-06-21 |
| Baseline 82/92 → 101/101 após FASE 1+2 (9 testes novos) | 2026-06-19 |
| `if not False:` = edição pela metade (BUG-07 no auto-trader) | 2026-06-19 |
| Flags auto-trader: AUTO_MAX_NOTIONAL_USDT, AUTO_PERMITIR_STOP_COM_PREJUIZO (default-safe) | 2026-06-19 |
| test_signal_engine quase todo mocka o engine — só 1 usa EVCalculator real (sem assert de EV) | 2026-06-19 |
| BUG-04: fix reflete notional em memória; persistência entre restarts ainda pendente | 2026-06-19 |
| Limiares de regime: fonte única em `src/core/constantes_mercado.py` (INC-06) | 2026-06-19 |
| Convenção de custo round-trip: `(fee+slippage)*2 + spread` (ev_calculator, _custos_ciclo_pct, profit_guard) | 2026-06-19 |
| Não simetrizar consenso (INC-01) sem backtest — só nomear+documentar (DA-09) | 2026-06-19 |
| Banco vetorial: adiar até ter dado real + caso de retrieval (não é pré-requisito) | 2026-06-19 |
| Cache de modelo invalida por mtime de ARQUIVO (não de diretório — mkdir muda o do dir) | 2026-06-20 |
| RMW de snapshot: usar `atualizar_snapshot(simbolo, mutador)` (BEGIN IMMEDIATE), não obter+salvar | 2026-06-20 |
| Taxa efetiva (desconto BNB): fonte única `fee_optimizer.aplicar_taxa_efetiva` (autotrader + manual) | 2026-06-20 |
| `modelo_llm`/`fonte_analise` devem refletir origem real (heuristica_local vs gpt) — INC-02 | 2026-06-20 |
| Métricas de qualidade em `observabilidade/qualidade_sinal.py` (IC/Brier/drawdown, só numpy); correlation_id em `observabilidade/correlacao.py` | 2026-06-20 |
| Não fazer cirurgia no god-file `testnet_auto_trader.py` sem supervisão; breaker wiring é F6 | 2026-06-20 |
| MCP/n8n: ADIAR (sem consumidor hoje); pareceres em contexto.md "PARECERES DE EXPANSÃO" | 2026-06-20 |
| F6: extração segura = mover p/ `autotrader/` + import no topo do god-file (re-export automático), testes intactos | 2026-06-20 |
| JÁ EXISTE breaker de perda diária no god-file (`_registrar_fechamento_ciclo` L~1580): pausa+persiste bloqueio. NÃO duplicar | 2026-06-20 |
| `_executar_ciclo` (833 linhas) = split só com caracterização supervisionada; não fazer às cegas | 2026-06-20 |
| Modelo online divergia (18 amostras, coef 71); gate `MIN_AMOSTRAS_ONLINE`=200 + guarda de saturação | 2026-06-20 |
| EDGE: harness `scripts/pesquisa_edge.py`. Resultado: ret/trade NEGATIVO em 24/24 configs (fee 0,24% > sinal) | 2026-06-20 |
| Minitrading 1-15m perde por MATEMÁTICA (fee>edge), não por bug. 60% acerto inalcançável c/ dados atuais | 2026-06-20 |
| Stop-loss agora ATIVO por padrão (corta perda); segurar perdedor só com AUTO_SEGURAR_NO_PREJUIZO=true | 2026-06-20 |
| Caminho p/ lucro: horizonte maior + ordem MAKER (fee ~0,075%) + features melhores + dado contínuo | 2026-06-20 |
