# UP — GUIA MESTRE DO ORÁCULO: DO TESTNET AO CAPITAL REAL

> Gerado em 2026-07-10 pelo time completo de agentes (ORQ+GRD+QNT+SIN+EXE+PER+OBS+TST+REF+REV).
> Base: `contexto.md` 2026-07-04 · suíte **319 testes verdes** · veredito vigente: *pronto para produção TESTNET; conta real fechada por desenho até edge provado*.
> Este documento é o mapa único para: velocidade de decisão, resiliência sem IA de nuvem, LLM local, gaps de fluxo, e o plano real de entrada com 50–100 USDT.

---

## 0. RESUMO EXECUTIVO (leia isto se não ler mais nada)

1. **O bot NÃO é lento por defeito técnico.** O motor mecânico decide a **cada ciclo de 30s** sem esperar IA nenhuma (a IA tem throttle de 300s, cache e fail-open — ela nunca bloqueia uma decisão). O que parece "lentidão/oportunidade perdida" é, em ~90% dos casos, os **gates de qualidade dizendo NÃO** porque o EV líquido não cobre o custo — e isso é o comportamento correto de um sistema que protege capital.
2. **Se Gemini/GPT/Claude caírem, o bot JÁ continua comprando e vendendo.** Isso é garantia arquitetural desde DA-23: a camada de IA é consultiva, fail-open, e nenhum gate financeiro depende dela. LLM local (§5) é melhoria de *disponibilidade da opinião da IA*, não requisito de sobrevivência.
3. **A meta "100 USDT → 10 USDT/dia" é 10% ao dia.** Nenhum sistema sustentável do planeta entrega isso — nem mesas proprietárias de HFT. O edge real medido do Oráculo hoje é **+0,03% líquido/trade em 1 config de 72**. O caminho honesto até 10 USDT/dia existe, mas passa por **provar o edge → compor → escalar capital** (§10), não por afrouxar a segurança.
4. **O que realmente falta** (em ordem): validação de 7 dias do edge ETHUSDT h30 em testnet · alertas + backup · saída mais rápida via WebSocket · ML fora do event-loop · ordens maker (a MAIOR alavanca de "mais trades" segura) · LLM local como 4º provedor · Fase 6 (decomposição + UoW) antes de crescer capital.

---

## 1. A MATEMÁTICA HONESTA (QNT) — antes de qualquer promessa

### 1.1 O custo de cada trade (conta real, Binance spot)

| Componente | Valor | Round-trip |
|---|---|---|
| Taker fee | 0,10%/perna | **0,20%** |
| Taker + desconto BNB | 0,075%/perna | **0,15%** |
| Maker + BNB | ~0,056–0,075%/perna | **~0,11–0,15%** |
| Slippage + spread (1m, par líquido) | ~0,01–0,05% | somado ao acima |

**Todo trade nasce devendo ~0,15–0,24% do notional.** Com 100 USDT por trade, isso é 0,15–0,24 USDT de custo por ciclo compra+venda. O EV do bot já contabiliza isso corretamente (fee round-trip, DA-02 — invariante testado em 3 camadas).

### 1.2 O edge real medido (walk-forward no banco real, 34k velas, pós-fixes BUG-08..16)

```
Melhor config de 72 testadas: ETHUSDT h30 alvo 0,1%
  net LÍQUIDO/trade: +0,000295  (≈ +0,03%)
  IC: 0,086 · 821 trades · win rate 17,5% (perfil "corta perda rápido, deixa ganho correr")
  → É PISTA/QUASE-EDGE, não edge robusto. As outras 71 configs: net ≤ 0.
```

### 1.3 O que a meta pedida exigiria vs. o que existe

| Cenário | Retorno/dia | 100 USDT rendem/dia | Capital p/ 10 USDT/dia |
|---|---|---|---|
| Meta pedida | 10% | 10 USDT | 100 USDT |
| Trader de elite sustentado | ~1% | 1 USDT | ~1.000 USDT |
| Edge BOM provado (realista de mirar) | 0,3% | 0,30 USDT | **~3.300 USDT** |
| Edge medido HOJE (se sustentar) | ~0,03–0,1% | 0,03–0,10 USDT | ~10.000–33.000 USDT |

10%/dia composto = ×17 ao mês = ×~5.000 ao ano sobre o capital. Se existisse de forma estável, não haveria fundos — haveria só esse algoritmo. **Prometer isso seria mentir; o CLAUDE.md deste projeto proíbe agradar antes da verdade.**

### 1.4 A conclusão que reorganiza tudo

> **Velocidade não é o gargalo do lucro. Edge é.** Um bot 10× mais rápido com edge de +0,03% continua ganhando +0,03%/trade. Por isso este guia trata velocidade como *higiene* (§4) e edge como *missão* (§8, §10).

---

## 2. O QUE O BOT JÁ TEM (foto real — não refazer o que existe)

### 2.1 Pipeline de decisão (roda 100% local, a cada 30s, sem depender de nuvem)

```
Binance REST (klines 1m + book) → features normalizadas → regime detector
→ 4 estratégias → modelo ML (online+batch, cache mtime, gate anti-divergência)
→ calibração → EV líquido (fee round-trip) → consenso (simétrico 0.25/0.25 + voto IA peso igual)
→ risk_engine (14 vetos nomeados) → filtro_ev → profit_guard → [REAL: edge gate default-closed]
→ kill-switch → idempotência → ordem → guard de fill (2 pernas) → persistência → trailing/stop
→ breaker de perda diária (halt persistido, reset humano) → auditoria
```

### 2.2 Camadas de segurança já ativas (GRD — checklist 6/6 ✅ em 2026-07-04)

| Camada | Estado |
|---|---|
| Fee round-trip em TODO EV/simulação (DA-02) | ✅ 3 camadas concordam, invariante testado |
| PERMITIR_CONTA_REAL | ✅ 23 pontos em 9 arquivos, default-false |
| Edge gate conta real (DA-19) | ✅ default-closed, auto-expira, fail-closed — hoje FECHADO (honesto) |
| Kill-switch file-based (DA-21) | ✅ bloqueia toda ordem em segundos, fail-safe |
| Idempotência clientOrderId (DA-12) | ✅ ON em toda ordem, determinística cross-restart |
| Halt de perda diária persistido (DA-16/17) | ✅ sobrevive restart, reset só humano |
| Anti-posição-fantasma (FLX-01) | ✅ fill verificado nas 2 pernas + reconciliação |
| HMAC de modelo anti-RCE (DA-22) | ✅ opt-in via MODELO_HMAC_KEY |
| Fail-fast de config no boot (DA-15) | ✅ |
| Freios absolutos conta real | ✅ max_loss $0,20/trade, risk 0,5%, exposição 20% |

### 2.3 Camada de IA (já otimizada em 5 iterações — DA-23→32)

- **Consultiva e fail-open**: voto com peso igual ao mecânico (DA-24), mas `score×confiança` ⇒ IA indisponível contribui ~zero. Veto (`PreExecutionFilter`) coexiste. **A IA jamais aprova trade com EV negativo** (testado).
- **1 chamada de rede cobre todos os símbolos** (lote DA-29) · **só é consultada com EV acionável** (DA-30) · **falha também é cacheada** (DA-30.1) · **throttle 300s** + contagem de tentativas protege cota (DA-31) · **contexto -66%** (DA-32).
- **Multi-provider plugável** (DA-27): `AI_PROVIDER=gemini|gpt|claude` — trocar de IA = editar `.env`. Adicionar provedor = 1 subclasse.

### 2.4 Cadência atual (cadência ≠ qualidade — lição travada)

| | Testnet | Conta real |
|---|---|---|
| Trades/hora máx | 12 | 3 |
| Cooldown | ≥3 min | ≥10 min |
| Gates de qualidade (EV/lucro/consenso) | idênticos | idênticos |

---

## 3. DIAGNÓSTICO REAL DA "LENTIDÃO" (por que parece perder oportunidade)

Decomposição das fontes, da maior para a menor:

| # | Fonte | Peso | É defeito? | Ação |
|---|---|---|---|---|
| 1 | **Gates de qualidade rejeitando** (EV líquido < custo na maioria dos ciclos) | ~70% | ❌ É o sistema sendo honesto: sem edge, o certo é HOLD | Só se resolve com edge melhor (§8) e custo menor (maker, §4.V5) |
| 2 | **Cadência** (12/h testnet, 3/h real) | ~15% | ❌ Desenho anti-ruína | Já foi solta em testnet (DA-32). NÃO soltar em real antes de edge provado |
| 3 | **Janela de dados**: klines 1m via REST polling a cada 30s → reação a movimento pode atrasar até ~30s | ~10% | ⚠️ Custo real, afeta principalmente a **SAÍDA** (stop/trailing tardio = perda maior) | WebSocket (§4.V1) |
| 4 | **ML inline no event-loop** (predict/fit bloqueiam o loop 200–800ms nos piores ciclos) | ~5% | ⚠️ Latência de API + jitter de ciclo | ProcessPool (§4.V2) |
| 5 | IA de nuvem | ~0% | ✅ Já resolvido: nunca bloqueia (throttle+cache+fail-open) | Nada no hot path |

> **Tradução:** quando você olhar o bot "parado", olhe `/v1/diagnostico` e a auditoria — quase sempre ele está **recusando trades que perderiam dinheiro**. O dia em que ele "acelerar" sem edge, ele só vai perder mais rápido.

---

## 4. VELOCIDADE COM SEGURANÇA — o que mexer e o que é proibido

### V1 — WebSocket de mercado (maior ganho de reação, prioridade em SAÍDA) `[P1]`
Substituir/complementar o polling REST por stream WS de klines+bookTicker.
- **Ganho:** preço fresco em ~1–2s (vs até 30s) ⇒ stop/trailing dispara no preço certo → **perdas menores** (é ganho de segurança, não só de oportunidade).
- **Requisitos obrigatórios** (os coletores WS antigos foram removidos por serem stubs bugados — não repetir): respeitar flag `"x"` de vela fechada; watchdog de heartbeat (reconectar se silêncio > 3× intervalo); gap-fill via REST pós-reconexão; REST permanece como fallback canônico.
- **Agentes:** SIN desenha, EXE integra, GRD aprova (toca fluxo que decide dinheiro), TST cobre reconexão/gap.

### V2 — ML fora do event-loop `[P1]`
`predict` via `ProcessPoolExecutor` (spawn, 1–2 workers, modelo carregado no init do worker); `fit`/treino batch permanece out-of-band.
- **Ganho:** ciclo com duração estável; API nunca trava atrás de um `fit`.
- **Cuidado:** o cache global de gerenciador por símbolo é estado de processo — o worker precisa do próprio cache (invalidação por mtime já existe e serve).

### V3 — Rate-limit proativo da Binance `[P1, pequeno]`
Ler `X-MBX-USED-WEIGHT-1M` das respostas e frear ANTES do 429 (hoje o bot só reage com retry/backoff). Barato e elimina um modo de falha inteiro.

### V4 — Tirar cálculo display-only do ciclo quente `[P2, pequeno]`
Arbitragem triangular + reposição BNB são calculadas TODO ciclo e nunca executadas (GAP-FLX-02/03). Ou viram feature de verdade (decisão sua + testes), ou saem do hot loop para um intervalo lento (60–300s). CPU do ciclo é latência de decisão.

### V5 — Ordens MAKER (a alavanca que mais "destrava trade" com segurança) `[P2, exige GRD]`
Custo taker+BNB 0,15% → maker+BNB ~0,11%. **Baixar o custo baixa o piso do gate de EV ⇒ mais candidatos passam legitimamente** — é o único jeito de "ter mais trades" sem afrouxar critério.
- **Complexidade honesta:** LIMIT post-only pode não preencher — exige timeout de fill, reprecificação e cancelamento idempotente. É mudança de execução financeira: caracterizar em testnet primeiro, GRD veta qualquer atalho.

### 🚫 PROIBIDO em nome de "velocidade" (regras de ouro)
- Afrouxar gates de qualidade (EV, lucro mínimo, consenso, veto) — cadência e qualidade são coisas separadas por lei do projeto.
- Pôr IA (qualquer uma) no caminho síncrono da decisão.
- `uvicorn --workers >1` (o bot é stateful — quebraria sessões/estado).
- Reset automático de halt/breaker (DA-03: só humano).
- "Simetrizar"/recalibrar limiares de risco sem walk-forward (DA-09).

---

## 5. IA RESILIENTE: NUVEM OFFLINE + LLM LOCAL (o desenho certo)

### 5.1 O que JÁ está garantido (não refazer)
- Nuvem caiu/429/timeout/sem chave ⇒ voto vira confiança 0 (contribui zero), veto vira PROCEED, e **o motor mecânico segue operando a cada 30s**. Comprovado ao vivo (429 real tratado sem crash).
- Falha é cacheada (TTL 30s) — 1 falha nunca vira N tentativas (DA-30.1).

### 5.2 LLM local como 4º provedor — `ollama_client.py` `[P2]`
Graças ao DA-27, é **1 subclasse + 3 variáveis de env**, zero mudança nos consumidores:

```
src/intelligence/ollama_client.py
  class OllamaClient(ProvedorIABase):
      # _executar_chamada(system_prompt, user_context, temperature) via httpx
      # POST http://localhost:11434/api/chat  (format: "json", stream: false)

.env:
  AI_PROVIDER=ollama
  OLLAMA_URL=http://127.0.0.1:11434
  OLLAMA_MODEL=qwen2.5:7b-instruct    # ou llama3.1:8b — ambos seguram JSON estruturado
```

- **Herda de graça** da base: timeout duro, cooldown por falhas, redação anti-vazamento, wrapper fail-open. Cost-control vira no-op útil (sem cota, mas o teto interno protege o ciclo).
- **`disponivel()`**: ping em `/api/tags` no boot; Ollama parado ⇒ factory retorna None ⇒ camada desativada (mesmo fail-safe de sempre).
- **Segurança que MELHORA:** sem chave de API para vazar; dado de mercado não sai da máquina; mesmos sanitizadores de prompt-injection; e o invariante intocável continua: **IA nunca levanta gate financeiro** — vale para local igual a nuvem.
- **Hardware/latência honestos:** 7–8B quantizado ≈ 5–8GB RAM; 2–10s por resposta em CPU. Irrelevante para o bot (a IA está fora do hot path por desenho), mas não espere qualidade de análise igual a Gemini/GPT — o valor é disponibilidade 24/7 e custo zero.

### 5.3 Cadeia de fallback nuvem→local `[P2, opcional]`
`AI_PROVIDER_FALLBACK=ollama`: wrapper `ProvedorComFallback` que tenta o primário e, em falha/cooldown, usa o local. ~30 linhas na factory, mesmos testes de contrato. Resultado: **opinião de IA quase sempre presente, bot nunca dependente dela**.

---

## 6. GAPS DE LÓGICA E FLUXO — consolidado das auditorias

### 6.1 Já FECHADOS (não reabrir — referência no contexto.md)
Fee round-trip 3 camadas (BUG-02/03, INC-07) · posição-fantasma (FLX-01) · bypass de EV no consenso (BUG-08) · modelo saturado + confirmação decorativa (BUG-10) · calibrador aleatório dimensionando posição (GAP-FIN-01) · idempotência cross-restart (BUG-13) · breaker sem persistência (BUG-12) · features mal-normalizadas (BUG-16) · taxa maker errada (BUG-15) · cache de falha da IA (DA-30.1) · quota/thinking do Gemini (DA-30.2/31) · veracidade do front + sizing pelo slider (DA-31/32) · **auditoria fim-a-fim DA-28: 0 gate financeiro furado**.

### 6.2 ABERTOS (o que resta, com prioridade e dono)

| # | Gap | Risco real | Prioridade | Agente |
|---|---|---|---|---|
| G1 | **Edge não validado ao vivo** — ETHUSDT h30 é 1 config fina, nunca rodou ≥7d em testnet | Entrar em real sem prova = doar dinheiro à Binance | **P0** | QNT |
| G2 | **Sem alertas push** (halt, drawdown, erro em loop) — bot autônomo que falha em silêncio às 3h da manhã | Perda descoberta horas depois | **P0** | OBS |
| G3 | **Sem backup do SQLite** (592MB de dado de pesquisa + estado) | Corrupção = perde a memória do bot | **P0** | PER |
| G4 | **Slippage assumido, não medido** — EV pode estar otimista em mercado rápido | EV inflado exatamente quando mais dói | **P1** | QNT |
| G5 | Janela de reação de saída até ~30s (REST polling) | Stop tardio = perda maior que o desenhado | **P1** | SIN/EXE |
| G6 | ML inline no event-loop | Jitter de ciclo, API trava em fit | **P1** | EXE |
| G7 | Sem freio proativo de rate-limit Binance | 429 em cascata em mercado agitado | **P1** | EXE |
| G8 | **UoW morto** — ordem na Binance + registro local não são atômicos (crash entre os dois = estado local cego até a reconciliação) | Janela pequena, rede de reconciliação existe | **P2 (F6)** | PER |
| G9 | God-file 2470 linhas / `_executar_ciclo` 833 linhas | Toda mudança futura carrega risco de regressão | **P2 (F6)** | REF |
| G10 | Sem signal handlers SIGTERM/SIGINT dedicados | Restart no meio de ciclo (mitigado por idempotência+reconciliação) | P2 (F6) | EXE |
| G11 | `circuit_breaker.py` dormente ao lado do halt inline (duas verdades em potencial) | Ativação acidental em refactor | P2 (F6): consolidar OU deletar | GRD |
| G12 | Métrica do voto da IA inexistente (não sabemos se DA-24 ajuda ou atrapalha) | Decisão às cegas sobre manter peso igual | P2 | OBS |
| G13 | SEC-01 residual (credenciais em RAM durante sessão ativa) | Dump de processo local | P3 (mitigado, requisito do loop) | GRD |
| G14 | mypy/ruff/cobertura não medidos localmente | Dívida invisível | P3 (F9) | TST |

---

## 7. O QUE O BOT **NÃO** DEVERIA TER (anti over-engineering — capital de 100 USDT não sustenta luxo)

- **NÃO** adicionar agora: Docker/k8s, PostgreSQL, Redis, n8n, MCP, microserviços, banco vetorial/RAG, dashboards Grafana — tudo já avaliado e adiado com parecer no contexto.md. Cada um é superfície de falha sem consumidor.
- **NÃO** manter cálculo morto no ciclo quente (arbitragem/BNB display-only → §4.V4).
- **NÃO** manter duas verdades de breaker para sempre (G11 — decidir na F6).
- **NÃO** criar segundo caminho de custo/EV/limiar — fonte única é lei (constantes_mercado, EVCalculator, aplicar_taxa_efetiva).
- **NÃO** adicionar provedores/chamadas de IA além do desenho atual (1 lote/throttle) — cota é recurso finito e o ganho marginal é zero.
- **NÃO** transformar o front em fonte de verdade: todo número exibido vem do backend (lição DA-32).

---

## 8. ROADMAP P0→P3 (com critério de aceite verificável)

### P0 — ANTES de qualquer USDT real (1–2 semanas de relógio, pouco código)
| Item | Critério de aceite |
|---|---|
| Rodar testnet 7+ dias focado em ETHUSDT h30 (cadência atual) | `/v1/dashboard`: net líquido ≥ 0 no período; sem halt; sem posição-fantasma |
| Re-rodar walk-forward semanal (`DB_PATH=./dados/oraculo.sqlite`!) | Edge ETHUSDT h30 se sustenta em novos folds (IC>0, net>0) |
| `observabilidade/alertas.py` (Telegram/webhook: halt, drawdown, N erros, 0 trades/24h) | Alerta de teste chega no celular |
| Backup horário (`VACUUM INTO` + rotação) | Restore testado 1× |
| Drill de kill-switch | `touch` bloqueia ordem em <1 ciclo; `rm` libera; auditado |
| **Suíte 319 verde permanece o piso** | `pytest -q` = 0 falhas após cada item |

### P1 — Velocidade/robustez segura (§4.V1–V3 + G4)
WS com watchdog+gap-fill · ML em ProcessPool · rate-limit proativo · slippage realizado (EWMA por símbolo alimentando EVCalculator com percentil pessimista).
**Aceite:** p95 de duração de ciclo < 2s; saída reage < 5s; slippage do EV = max(medido_p95, config).

### P2 — Resiliência de IA + custo (§5 + §4.V4–V5)
Ollama como 4º provedor + fallback chain · maker orders caracterizadas em testnet · arbitragem fora do hot loop ou executada de verdade (decisão do dono) · endpoint de métricas do voto IA (G12).
**Aceite:** derrubar a internet da IA de nuvem e o bot mantém votos (local) e trading (mecânico); custo round-trip efetivo medido < 0,15%.

### P3 — Estrutura para crescer (Fase 6 + 9 do CLAUDE.md)
Decomposição do god-file (máquina de estados) → wiring/consolidação do breaker → UoW ativo → signal handlers → mypy/ruff bloqueantes.
**Aceite:** nenhuma função >50 linhas em código de execução; suíte verde; contexto.md atualizado pelo REV.

---

## 9. CHECKLIST DE ENTRADA COM 50–100 USDT REAIS (GRD — inegociável)

**Pré-requisitos (todos, sem exceção):**
- [ ] P0 completo, incluindo 7+ dias testnet net-positivo na config do edge
- [ ] Walk-forward re-confirmou o edge ⇒ só então `ATUALIZAR_EDGE=1` (arma o gate para ETHUSDT)
- [ ] Alertas funcionando + backup rodando + drill de kill-switch feito
- [ ] Você aceitou por escrito (para si mesmo) a expectativa da §1.3 — **décimos de USDT/dia no início**

**Configuração sugerida para o primeiro mês real (100 USDT):**
```
PERMITIR_CONTA_REAL=true          # só após tudo acima
AUTO_MAX_NOTIONAL_USDT=25         # 25% do capital por operação, teto duro
max_daily_loss_usdt ≈ 2.00        # 2% do capital/dia e o bot PARA (halt persistido)
Cadência real: manter 3/h, cooldown 10min (defaults — NÃO soltar)
Freios absolutos: manter (max_loss $0,20/trade ⇒ 10 perdas seguidas custam $2)
KILL_SWITCH_PATH definido e testado · MODELO_HMAC_KEY definida
AI_PROVIDER=<sua escolha> (com throttle ≥300s) — opcional, o bot não depende
```
> Nota do QNT: com 100 USDT, os freios absolutos da conta real produzem trades de ~5–15 USDT e risco de ~0,2%/trade — **isso está corretamente dimensionado** para esse capital; não é "trade pequeno demais", é sobrevivência.

**Rotina diária do dono (5 min):** `/v1/diagnostico` + PnL do dia + auditoria de vetos. **Critérios de aborto imediato (kill-switch):** halt disparou 2 dias seguidos · qualquer posição-fantasma · divergência entre saldo Binance e estado do bot · edge expirado no `/v1/edge`.

---

## 10. O CAMINHO REAL ATÉ 10 USDT/DIA

Não existe atalho; existe sequência:

1. **Provar** (P0): edge sustentado em testnet + walk-forward. Sem isso, real fica fechado — o próprio bot te protege de você.
2. **Sobreviver** (mês 1–2 real, 100 USDT): meta = **net ≥ 0 após custos**. Isso já coloca o bot à frente da maioria esmagadora dos bots de varejo.
3. **Medir e melhorar o edge** (contínuo): mais dado (coletor contínuo ON), horizontes maiores (h30/h60 — o 1–15m perde por matemática, já provado), maker orders (corta custo ~30–50%), features melhores. Cada +0,05% de edge líquido/trade vale mais que qualquer otimização de latência.
4. **Escalar capital, não risco**: com edge provado de 0,2–0,3%/dia, 10 USDT/dia exige ~3.000–5.000 USDT. O caminho é aporte + capitalização composta com os MESMOS freios percentuais — nunca aumentar % de risco para compensar capital pequeno.

| Se o dia render (líquido) | 100 USDT | 500 | 1.000 | 3.300 |
|---|---|---|---|---|
| 0,1% | 0,10 | 0,50 | 1,00 | 3,30 |
| 0,3% | 0,30 | 1,50 | 3,00 | **10,00** |
| 1,0% (excepcional) | 1,00 | 5,00 | 10,00 | 33,00 |

---

## 11. PARECERES DO TIME DE AGENTES (síntese)

- **ORQ:** velocidade é higiene, edge é missão; sequência P0→P3 acima, nada em paralelo com dinheiro real.
- **GRD (veto ativo):** conta real permanece fechada até P0 completo. Maker orders e WS tocam execução ⇒ passam por mim antes do merge. Nenhuma linha deste guia autoriza afrouxar gate.
- **QNT:** confie no walk-forward, não no olho; 100% win em ~24 micro-trades de testnet NÃO é prova estatística (n pequeno). Slippage medido (G4) antes de escalar.
- **SIN:** WS com flag de vela fechada + gap-fill, senão é regressão dos coletores removidos. O gate de EV antes da IA (DA-30) é o desenho certo — manter.
- **EXE:** ProcessPool para predict; rate-limit proativo; fill-timeout obrigatório se maker entrar.
- **PER:** backup horário é trivial e inegociável; UoW na F6, não antes (cirurgia no god-file sem decompor = risco).
- **OBS:** alerta que não chega no celular não é alerta; medir voto da IA (G12) antes de discutir o peso dela.
- **TST:** 319 verdes é o piso eterno; toda feature nova deste guia nasce com teste de falha (WS desconecta, Ollama fora, maker não preenche).
- **REF:** god-file só com caracterização supervisionada; extração segura já tem receita validada (F6 parcial).
- **REV:** este up.md substitui qualquer plano anterior solto; contexto.md continua sendo o estado vivo — consultá-lo antes de cada sessão.

---

## 12. AS 10 REGRAS DE OURO (colar na parede)

1. Capital perdido não volta — na dúvida, HOLD.
2. Cadência ≠ qualidade: mexa na primeira, nunca na segunda.
3. A IA opina; o mecânico decide; os gates mandam. Nenhuma exceção, nem para IA local.
4. Todo custo é round-trip (×2). Sempre.
5. Edge se prova out-of-sample (walk-forward + testnet ≥7d), nunca no gráfico de ontem.
6. Fill confirmado antes de mutar estado (2 pernas).
7. Halt/breaker só destravam por mão humana.
8. `pytest -q` verde após CADA mudança; mudou dinheiro ⇒ GRD antes, REV depois.
9. Front exibe o que o backend calcula — nunca o contrário.
10. Escale capital com edge provado; nunca escale risco para compensar capital.

---

*Fim do guia. Estado vivo em `.claude/contexto.md`; lições em `.claude/skill.md`. Próxima ação concreta: iniciar P0 (run de 7 dias + alertas + backup).*
