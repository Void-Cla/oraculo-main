# ANÁLISE DO RUN — 2026-06-20 (~13h–18h, testnet)

## Veredito em uma linha
Infra perfeita por 5h, **0 trades reais**. A "venda" vista no log era uma DECISÃO do modelo
(`decisao_emitida: SELL`), **não uma ordem executada** — `ordens` continua 0.

## Delta do banco (baseline 12:13 → 18:00)
| Tabela | Delta | Leitura |
|--------|-------|---------|
| predictions | +363 | loop de previsão rodou as 5h |
| outcomes | +363 | tracking previsão×realidade ok |
| ohlcv_1m / features_1m / livro_topo | +345 / +344 / +344 | coleta de mercado ok (~1/min) |
| audit | +1569 | 1203 `auto_trade` + 363 `previsao_hibrida` + 3 `noticias_fetch` |
| **ordens** | **+0** | **nenhuma ordem persistida** |
| ai_insights | +1 | — |

Nenhum erro/traceback/exception no log. Sem crash. Sem halt de circuit breaker.

## Causa-raiz (ordenada)
1. **MODELO NUMÉRICO SATURADO em ±1.000.** Em 100% dos ciclos `score_numerico` = -1.000
   (ou +1.000), nunca valores intermediários. `variacao_prevista` fixa em ~-0.6% a -1.2%.
   → sinal degenerado: o modelo "grita" direção máxima sempre. É o motivo nº 1 de não operar.
2. **POSIÇÃO FANTASMA.** Risk approval vetou com `limite_trades_abertos` mesmo com `ordens`=0
   → o estado em memória achava que tinha posição aberta (`ciclo_ativo=True`) sem ordem real.
   Travou: não abre nova (limite) e não fecha (SELL não permitido pela confirmação multi-TF).
3. **AUTOTRADER NÃO PERSISTE ORDENS.** Posição/ciclo só em memória; nada vai p/ `ordens`.
   Sem auditoria e estado perdido em restart. (Manual flow persiste; autotrader não.)
4. Conflito de consenso: modelo SELL vs `confirmacao_multi_timeframe.permitir_sell=False`
   (só permite BUY nos pares USDT) → resolve HOLD. Motivos do veto: `sinal_hold`,
   `limite_trades_abertos`, `lucro_liquido_abaixo_do_minimo`.

## O que funcionou (confirmado)
- Pipeline de coleta + previsão + aprendizado online rodou 5h sem falha.
- Segurança segurou: nenhum trade ruim foi aberto (HOLD por padrão).
- Fix INC-02 ATIVO: `modelo_llm`/`fonte` mostram `heuristica_local` (sem chave OpenAI) — honesto.
- Multiativo escaneando BTCUSDT/ETHUSDT/BNBUSDT/ETHBTC/BNBBTC.

## Plano de correção (ordem de impacto)
- **[P1] Modelo saturado** — investigar `dados/modelos/*` + normalização em `gerenciador_modelo`
  (`_normalizar_predicao_preco`, MAX_VARIACAO_PREVISTA, scaler). Provável: modelo online/batch
  ruim ou scaler degenerado gerando sempre extremo. Sem isso, o bot nunca terá sinal útil.
- **[P2] Posição fantasma / persistência de ordens** — autotrader deve PERSISTIR ordens em
  `ordens` e reconciliar `ciclo_ativo` com fills reais (evita deadlock de "limite_trades").
- **[P3] Revisar `permitir_sell`** da confirmação multi-TF (assimetria BUY-only).

## ⚖️ TESTE DE EDGE (experimento decisivo — sem deployar)
Treinei um HistGradientBoosting nos dados reais (split temporal 80/20, alvo = retorno 5m à frente, BTCUSDT):
- **IC (Spearman) = -0.029** (negativo = pior que aleatório; útil seria > 0.05).
- **Acurácia direcional = 48.5%** (< 50% = pior que cara/coroa).
- → **Não há edge estatístico** no modelo/features atuais.

Dados: OHLCV parece REAL (BTC 63k–80k, ETH ~2.3k — endpoints públicos retornam preço real mesmo em testnet),
mas é **fragmentado** (6520 candles de BTC em 52 dias = grandes lacunas; o bot só coletou quando ligado).

### CONCLUSÃO HONESTA
- **Seguro: ✅** (fix P1 impede trades em cima de modelo-lixo; bot fica em HOLD sem sinal real).
- **Lucrativo: ❌ não alcançável só com engenharia.** O gargalo é EDGE/estratégia, não código.
- **NÃO deployei** o modelo batch (IC negativo → deployar faria o bot operar num sinal perdedor).
- Caminho real p/ edge: (1) coleta CONTÍNUA de dado real (REST público, sem operar); (2) pesquisa de
  features/horizonte com validação out-of-sample rigorosa (IC>0 estável); (3) só então operar.
  Possibilidade real: micro-scalping 1–5m em cripto pode simplesmente não ter edge líquido de fee.

## HARNESS DE EDGE (scripts/pesquisa_edge.py) — varredura 6 símbolos × 4 horizontes
- **Retorno por trade NEGATIVO em TODAS as 24 configs** — o fee round-trip (0,24%) > qualquer sinal.
- BTCUSDT (par líquido real): IC≈0, acerto <50% → sem edge.
- Pares cruzados (BNBBTC/BNBETH/ETHBTC): IC "alto" (0,27) mas acerto 23–37% = **artefato de dado
  ilíquido/parado**, não edge. Melhor acerto real ~54,6% (BNBUSDT h15), ainda assim perde após fee.
- **Conclusão estrutural:** minitrading em massa neste fee/timeframe **perde por matemática**, não por bug.
  Meta de 60% de acerto é inalcançável com features/dados atuais.
- **Caminhos reais p/ ter chance de lucro:** (a) horizonte maior (15m+ onde o move >> fee);
  (b) fee menor (ordem MAKER/limit + desconto BNB → ~0,075%); (c) features melhores + dado contínuo;
  (d) aceitar que pode não haver edge. Sem isso, NÃO operar (perde saldo, mesmo fictício).

## SENSIBILIDADE DE FEE + SELETIVIDADE (2026-06-21) — fecha o caminho "MAKER"
Harness ampliado (6 horizontes 1–60m, fee bruto vs 3 cenários: taker 0,24% / taker 0,20% / BNB 0,15%):
- **Melhor retorno BRUTO/trade entre 36 configs = 0,056% (ETHBTC h60).** O fee mais barato (BNB 0,15%)
  é ~3× maior. **Fee NÃO é o gargalo decisivo — o sinal bruto é fraco demais** (ordem de grandeza < custo).
- BTCUSDT (par real): bruto NEGATIVO em todo horizonte, IC≈0. Sem poder preditivo no par principal.
- Correlação feature×retorno futuro (BTCUSDT h15): melhor |IC| ~0,08 (vol10 −0,09, r_15m −0,08) =
  estrutura FRACA de reversão à média; magnitude exploitável ~0,07% < fee.
- **Trade SELETIVO por convicção (|pred|):** único quase-viável = **BNBUSDT h60**: top 25% (188 trades)
  bruto 0,145% → líq. BNB ≈ −0,005% (break-even), acerto 79,8%; top 2% (15 trades) líq. +0,001%.
  → break-even, amostra minúscula, split único. **Pista, não edge confiável.**
- **VEREDITO REFORÇADO:** a premissa "minitrading em massa 1-15m" perde por matemática. Se houver edge,
  vive no OPOSTO: horizonte longo (1h+) + alta seletividade + BNBUSDT + fee BNB — e mesmo assim só
  break-even hoje. Profit exige: mais/melhor dado, features novas, e **validação walk-forward** ANTES de operar.

## BACKTESTER WALK-FORWARD (2026-06-21) — veredito rigoroso com lucro LÍQUIDO
`scripts/backtest_walkforward.py` + `src/backtester/walk_forward.py`. Matemática do alvo
líquido (pedido do usuário): BRUTO necessário = alvo_líquido + custo_round_trip; só entra
trade cujo bruto previsto cobre alvo+custo; contabiliza SEMPRE líquido. Custo via EVCalculator
(fonte única, sem desync). Walk-forward expandindo, 5 folds, out-of-sample.
- **Net líquido/trade NEGATIVO em TODAS as configs** (≈ −0,2% a −0,3% = custo sem edge bruto).
- Gross-up funciona: subir o alvo (0→0,1%→0,2%) derruba nº de trades, mas os sobreviventes
  ainda perdem → o filtro de entrada não fabrica edge de um modelo sem edge.
- IC walk-forward positivo em alguns (ETHUSDT h30=0,20; BNBUSDT h60=0,29) mas net < 0 →
  ranking ≠ lucro após custo. Único net>0: ETHBTC h60 alvo 0,2% = +0,01% com 4 trades (ruído).
- **VEREDITO walk-forward: SEM edge líquido. Não operar para lucro com os dados atuais.**
- **Caminho restante:** `coletor_continuo.py` (ATIVAR_COLETA_CONTINUA) acumula dado real
  contínuo; re-rodar o walk-forward periodicamente; só operar se net/trade>0 ESTÁVEL aparecer.

## CORREÇÃO DE SAÍDA (alinhada a "sair antes de prejuízo")
`_avaliar_saida_ciclo`: stop-loss agora **ATIVO por padrão** (corta perda). O default antigo segurava
o perdedor indefinidamente (causa do travamento no run). Segurar no prejuízo só com
`AUTO_SEGURAR_NO_PREJUIZO=true` (opt-in desaconselhado). ⚠️ Ressalva honesta: stop apertado + fee alto
= sangria; o stop protege contra perda grande, mas NÃO cria lucro — o gargalo segue sendo o fee/edge.
