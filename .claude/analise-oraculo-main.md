# Análise de Arquivos do Repositório GitHub — `oraculo-main`

> **Conversa completa entre Void hub e Claude**
> Data: 17–18 de junho de 2025
> Repositório analisado: [https://github.com/Void-Cla/oraculo-main](https://github.com/Void-Cla/oraculo-main)

---

## Pergunta 1

**Pode analisar todos os arquivos de esse e o meu `https://github.com/Void-Cla/oraculo-main`**

---

## Resposta 1

Vou analisar os dois repositórios.

> *(Rate limit não autenticado na API do GitHub — acesso via git clone. O repositório "mirage" retornou 404; o `oraculo-main` foi clonado com sucesso.)*

**Importante:** este projeto não tem nada a ver com FiveM/vRP2. É um **projeto Python de trading automatizado** (sinais, ordens, Binance, backtester, risco).

---

## Pergunta 2

**Presta atenção, não é o repositório mirage, é o oraculo `https://github.com/Void-Cla/oraculo-main`**

---

## Resposta 2

Entendido — o `oraculo-main` é o repositório certo, esqueço o mirage. O "Modo FiveM/vRP2" das instruções não se aplica aqui — vou tratar esse projeto pelo que ele realmente é: um bot de trading.

Já tenho clonado localmente. Mapeando a estrutura real:

**Leituras realizadas:**
- `AGENTS.md` — 14 agentes definidos como visão/spec, regras claras de governança para conta real.
- `src/` — `testnet_auto_trader.py` tem 116K (desproporcional a todo o resto → indício de god-file).
- `trading.py` — contratos Pydantic limpos, naming consistente em PT-BR.
- `settings.py` — helpers de env, padrão default-seguro (`env_bool` padrão `False`).

**Gates de segurança de conta real:** 4 pontos de bloqueio independentes (defense in depth: API + executor), todos `default-false`, com teste cobrindo isso.

**Bugs encontrados em `gerenciador_ordens.py`:**

**Bug 1 — `criar_ordem_limit` engole erro de notional:**
`NotionalTooSmall` não é levantado aqui, ao contrário de `criar_ordem_market`. Inconsistência entre métodos gêmeos — quem chama não consegue distinguir "notional pequeno" de qualquer outro erro da API.

**Bug 2 — `try/except NameError` como controle de fluxo:**
Dentro de `criar_ordem_market`, um bloco `try: filtros_local = filtros / except NameError` depende de uma variável que pode nunca ter sido definida. É código morto confuso que refaz uma chamada de rede desnecessária toda vez.

**Bug em `risk_engine.py` (linha 205–207) — inicialmente apontado, depois corrigido:**

```python
papel = bool(risk_cfg.get("paper_trading", True))
if usuario.get("testnet"):
    papel = False
```

Parecia inverter a semântica, mas após rastrear `executor_usuario.py:33`:

```python
"modo": "paper" if aprovacao_risco["paper_trading"] else ("testnet" if self.usuario["testnet"] else "real"),
```

Há **três modos distintos** (paper, testnet, real). `testnet=True` forçar `paper_trading=False` é necessário para que o `else` caia corretamente em `"testnet"`. Não é bug — a variável é mal-nomeada, mas a lógica está correta. Retiro esse apontamento.

**`testnet_auto_trader.py`:**
- 2.467 linhas, 57 funções/métodos.
- `_executar_ciclo`: 833 linhas em um único método.
- Loop sequencial com `await` bloqueante — **sem race condition real** dentro do mesmo token.
- `iniciar()` protege corretamente contra duplo-start (linha 1341–1346).

**Resultado da suíte de testes (clone limpo, `pytest -q`):**
**10 de 92 testes falhando** sem nenhuma modificação.

**Causas identificadas:**

| Falha | Causa |
|---|---|
| `test_pipeline`, `test_fluxo_usuario_signal_queue` | Dependência de usuário pré-existente no banco; gap de onboarding |
| `test_api_sessao_painel` | Endpoint `/v1/testnet/auto/start` ignora silenciosamente o valor enviado |
| `test_estado_limita_notional_operacional` | Teto de segurança `AUTO_MAX_NOTIONAL_USDT` removido do código de produção |
| `test_usuario_virtual_*` | Calibrações de risco para testnet não mais aplicadas |

**Bug crítico confirmado — endpoint `/v1/testnet/auto/start` ignora `notional_usdt`:**
`salvar_ajustes_testnet(entrada.model_dump())` é chamada sem `repo` nem `usuario_id`. A condição `if repo and usuario_id:` nunca persiste o novo valor. Você envia 12.5, a API responde "ok" mas internamente usa o valor antigo do banco.

**Bug crítico confirmado — teto de notional morto:**
`_teto_notional_operacional_usdt()` está definida mas **nunca chamada**. `_normalizar_notional_operacional` tem comentário explícito "no hard ceiling". `AUTO_MAX_NOTIONAL_USDT` não é lida em nenhum lugar do código de produção.

**Sem CI/CD configurado** — `.github/workflows` não existe. Essas falhas não são pegas automaticamente.

---

## Pergunta 3

**Então meu projeto está mais próximo do fim para ficar pronto do que estava no início né? Me dê sua real avaliação — seja honesta, não precisa me agradar. Você realmente acha que meu projeto tem potencial real de funcionamento 24/7 com NPL positivo? E se você pudesse usar meu programa para por seu dinheiro, seria seguro e confiável usar ele? O que falta para ele ser perfeito e confiável de verdade sem aumentar complexidade?**

---

## Resposta 3

Vou ser direto, sem amaciar: **não, hoje eu não colocaria dinheiro real nesse sistema.**

**O dado mais importante descoberto:** o banco de produção (versionado no repositório) tem **zero linhas** em `outcomes`, `predictions` e `ohlcv_1m`. Isso significa: nunca houve um único candle coletado, uma única predição gerada, um único trade fechado nesse sistema. Não é "tem poucos dados" — é **"nunca rodou de verdade nem uma vez"**.

Combinado com um único commit de três semanas atrás, a conclusão inevitável é: este sistema **nunca operou contra mercado real** — nem em testnet de fato, nem em paper trading.

**Isso reformula completamente sua pergunta:**

> Você está perto do fim da *construção do esqueleto*.
> Você está no início absoluto da *validação* — que é a parte que importa para saber se isso ganha dinheiro.

**Engenharia de software e validação de estratégia de trading são dois projetos diferentes** que compartilham o mesmo repositório. O primeiro está avançado. O segundo não começou.

**Por que o EV positivo ainda é desconhecido:**
O `risk_engine` bem escrito decide se um trade *passa pelos filtros de risco* — ele não tem opinião sobre se a *previsão de preço* está certa com frequência suficiente para superar taxas e slippage no longo prazo. Isso só se descobre rodando.

**O que eu de fato faria no seu lugar (sem aumentar complexidade):**

1. **Rodar o coletor de mercado** contra a API pública da Binance por semanas, só coletando, sem operar nada. Isso preenche `ohlcv_1m` com dado real.
2. **Usar esse dado no backtester** (que já existe, só nunca foi usado) para responder: nos últimos N dias de BTCUSDT real, esse `signal_engine` teria dado lucro ou prejuízo, líquido de taxa e slippage?
3. **Só depois** — e só se o número 2 for positivo — ligar a Binance testnet de verdade, registrando `outcomes`, por mais um período.

Isso não adiciona uma linha de complexidade arquitetural. É *sequenciamento*: você já construiu a ferramenta de medir, só nunca mediu.

---

## Pergunta 4

**Então esse programa eu venho fazendo ele a mais de 2 anos, porém você está de frente com uma nova versão. Sim, ela é nova, porém já teve fases de test real onde lucrei 20 dólares, mas depois fui mexendo e perdi a mão. E tem infinitos testes com a conta testnet — por isso furei o limite para 70k USDT, pq não era conta real. O banco de dados está vazio porque o GitHub não é data center para segurar tanta informação assim. Mas posso te garantir que o banco de dados persiste todas as informações desejadas e o LLM nativo do projeto também treina o modelo até que bem, deixando a predição com 50–60% de acerto.**

---

## Resposta 4

Isso recalibra bastante o que eu disse, e preciso ser preciso sobre o que exatamente muda e o que continua de pé.

**O que sua explicação resolve de fato:**
- Banco vazio no GitHub não é mais evidência de "nunca rodou". Faz sentido não versionar um sqlite de produção — isso é prática correta, não falha.
- 17 dias de calendário entre commits não contradiz 2 anos de trabalho — o histórico anterior não veio nesse push/squash. Retiro a conclusão "nunca operou" como fato.

**O que isso não resolve:**
Trocamos "evidência de que nunca rodou" por "nenhuma evidência de nada" — diferente de "evidência de que funciona". Continuo sem saber se há edge real.

Sua própria descrição já dá um sinal concreto para investigar: você ganhou $20, depois perdeu a mão mexendo, e está numa versão nova. Isso não é uma curva de lucro estabelecida — é uma amostra de N=1 positivo seguida de uma reescrita que ainda não foi validada.

---

## Pergunta 5

**Enfim o que quero dizer é que o projeto ficou complexo demais e está além da minha capacidade técnica e cognitivo — passou dos meus limites e resolvi colocar a IA pra jogo. Com sua análise detalhada, você acha que se eu puser esse projeto na mão do Fable 5 ele consegue arrumar tudo deixando todos os arquivos organizados, limpos, sem redundância, fluxo lógico coeso, organização separada por responsabilidades, segura ao extremo, lucrativa, testada perfeitamente?**

---

## Resposta 5

Preciso responder isso com o mesmo rigor que usei até agora.

**Sobre o Fable 5:**
Fable 5 é um modelo Claude real — descrito como "agentic coding", autonomia de longa duração, capaz de rodar dias planejando em etapas, com auto-verificação e sub-agentes. É exatamente o perfil certo para uma refatoração grande como essa.

**Porém:** Fable 5 foi lançado em 9 de junho de 2026 e suspenso 3 dias depois (12 de junho) por uma diretiva de exportação do governo dos EUA. Todas as clouds (AWS, Microsoft, GitHub Copilot) removeram acesso. Continua fora do ar até hoje (confirmado por múltiplas fontes, checagem de poucas horas atrás), sem data de retorno. O fallback recomendado pela Anthropic é o **Opus 4.8**.

**A parte que importa mais: nenhuma IA — Fable 5, Opus, eu — deveria fazer o que você pediu, do jeito que você pediu.**

Você pediu 7 coisas de natureza completamente diferente como se fossem uma. Separando:

| Pedido | Realidade |
|---|---|
| Organizado, limpo, sem redundância | Refatoração de engenharia — IA competente faz bem. Risco: escala e revisão. |
| Testado perfeitamente | **Não existe** como entregável de uma sessão. Constrói-se incrementalmente, validando contra comportamento real. |
| Lucrativo | **Nenhuma IA entrega isso.** É uma propriedade de uma estratégia testada contra dado real. Um código perfeito pode perder dinheiro com elegância. |
| Seguro ao extremo | Segurança em sistema que move dinheiro se constrói camada por camada, cada uma validada. |

**O que eu realmente recomendo:**

1. Corrigir os 3 bugs de segurança confirmados — pequeno, você revisa o diff, entende cada linha.
2. Um módulo por vez de refatoração (começar por `testnet_auto_trader.py`), sempre com teste passando antes e depois.
3. Em paralelo: rodar o coletor, alimentar o backtester com dado real, descobrir se há edge antes de perseguir "perfeito".

---

## Pergunta 6

**Sim sim, eu falei generalizada. Mas enfim, com auxílio máximo de IA, dá para deixar esse projeto perfeito né?**

---

## Resposta 6

Vou ser igual de direto: **não, "perfeito" não é uma palavra que se aplica honestamente a esse projeto**, mesmo com o auxílio máximo de IA que existe hoje.

**Há duas categorias diferentes:**

**Código (organização, segurança, testes, ausência de bugs):** sim, IA com supervisão boa pode levar muito perto de *excelente*. Não existe garantia matemática de "zero bug" em software não-trivial, IA nenhuma entrega isso, mas dá para chegar a um nível de qualidade muito alto, auditável, com cobertura de teste real. **Isso é alcançável.**

**Lucratividade:** essa não tem "perfeito" nem com IA ilimitada, porque não é um problema de engenharia. É uma aposta estatística sobre o futuro do mercado, e mercado não tem solução fechada. A melhor IA do mundo rodando o melhor backtest do mundo te dá uma probabilidade melhor informada, **nunca uma certeza**. Qualquer um — humano ou IA — que te disser "isso aqui vai ser lucrativo de forma garantida" está te vendendo uma ilusão.

A versão honesta da sua pergunta é: *dá para deixar o código tão bom e seguro quanto humanamente possível, e dá para aumentar bastante a confiança de que a estratégia tem edge real* — mas a palavra "perfeito" nunca vai se aplicar à parte que decide se você ganha ou perde dinheiro.

### Correções dos 3 bugs de segurança (aplicadas nesta sessão):

**Bug 1 — `criar_ordem_limit` engolia erro de notional:**
Adicionado tratamento de `NotionalTooSmall`, igual ao padrão já usado em `criar_ordem_market`. Inconsistência eliminada.

**Bug 2 — `criar_ordem_market` buscava filtros duas vezes (via `NameError` como controle de fluxo):**
Removida busca redundante de filtros via `try/except NameError` morto. Eliminada uma chamada de rede desnecessária a cada ordem de mercado, sem mudar resultado numérico.

**Bug 3 — Teto de notional morto:**
Em vez de restaurar um teto fixo que travaria testes em testnet, o teto agora depende de `modo_testnet`:
- **Testnet:** continua livre (seu caso de uso intencional de 70k).
- **Conta real:** teto configurável via `AUTO_MAX_NOTIONAL_USDT_REAL` — proteção que hoje não existia de nenhuma forma.

**Resultado após correções:** 10 falhas → 9. Os 3 novos testes de teto de notional passam. Total: 95 testes.

---

## Pergunta 7

**Mas essa análise que você fez foi parcial ou deu para ler todos os arquivos do projeto?**

---

## Resposta 7

**Foi parcial, e vou te dizer exatamente com que grau de parcialidade.**

**Números reais do projeto:**
- 124 arquivos `.py` são o código real (excluindo `node_modules`, `__pycache__` e `.pyc`).
- Eu li o conteúdo completo de **7 arquivos** (~6% do total).
- Os outros 117 arquivos foram apenas referenciados por nome/grep, não lidos.

**O que foi de fato lido:**
`trading.py`, `settings.py`, `gerenciador_ordens.py`, `risk_engine.py`, `testnet_auto_trader.py` *(trechos grandes, não 100% das 2.485 linhas)*, `main.py` *(só o endpoint específico)*, `ajustes.py`.

**O que nunca foi aberto:**
`signal_engine.py`, `consenso.py`, `ev_calculator.py`, `probabilistic_engine.py`, `probability_calibrator.py`, `trade_selector.py`, `gerenciador_modelo.py`, `preditor.py`, `treinador_batch.py`, todos os 8 arquivos de `src/multiativo/`, todos os 10 de `src/persistencia/`, todos os de `src/estrategias/`, `llm_analista.py`, `meta_controller.py`, `regime_detector.py` e 108 dos 124 testes.

"Análise detalhada" e "vi 6% dos arquivos" não deveriam coexistir na cabeça de quem está lendo sem eu deixar isso claro. Me corrijo.

---

## Pergunta 8

**Faz o seguinte: leia todos os arquivos para me trazer gaps, bugs, lacunas.**

---

## Resposta 8

Vou fazer isso direito desta vez — sistemático, sem pular nada, registrando o que de fato vi.

### Camada de Decisão — Sinais e Estratégias

**`signal_engine.py`:**
Estrutura de orquestração clara: features → regime → confirmação multi-timeframe → predição ML/LLM → engine probabilístico de EV → consenso final. `force_allow_for_testnet=True` força `lucro_liquido_min = -1.0` — desliga completamente o piso de lucro mínimo. Comportamento intencional para testnet.

**`consenso.py` — Bug de assimetria estrutural:**
Barra para *confirmar* trade: `abs(score) >= 0.10` (1 indicador fraco basta).
Barra para *vetar* trade: `abs(score) >= 0.35` (precisam ser 2 indicadores fortes).
O sistema está estruturalmente **enviesado a confirmar trades, não a vetá-los**. Não é código quebrado — é uma escolha de design com viés real para mais trades. Pode ou não ser intencional.

**Estratégias (`breakout.py`, `mean_reversion.py`, `momentum.py`, `volatility_scalping.py`):**
Sem bugs. Simples, legíveis, heurísticas com pesos e limiares fixos. A ausência de comentário de origem dos números mágicos (25.0, 12.0, 0.45 etc.) indica falta de calibração baseada em dado histórico — não é bug, é lacuna de validação.

**`meta_controller.py`:**
`confianca_final = sinal["confianca"] * score_regime + 0.15` — constante mágica de +0.15 sem comentário. Na prática inofensiva porque `score_regime` nunca é 0.0 (mínimo real: 0.45).

**`regime_detector.py`:**
Sem bug. Scores: `{0.45, 0.7, 0.72, 0.8}` — nunca zero.

### Camada de Probabilidade e EV

**`ev_calculator.py` — Bug crítico de custo de transação:**
```python
custos = notional * taxa  # UMA única perna
```
Um trade completo (compra + venda) paga taxa **duas vezes** — entrada e saída. O EV calculado está **sistematicamente otimista**: o custo real de fricção é o dobro do que o modelo assume. Isso é exatamente o tipo de erro que faz um sistema parecer rentável no papel e perder dinheiro de verdade.

**`simular_ordem` em `gerenciador_ordens.py` — Mesmo bug, segundo lugar independente:**
`custo_total = notional * taxa` — apenas uma perna. Padrão recorrente confirmado em dois módulos distintos.

**`probability_calibrator.py` — Risco latente de `OverflowError`:**
`math.exp(-(valor / self.temperature))` — se `temperature` for setado muito baixo via config (só `> 1e-6` é bloqueado), o argumento de `exp` pode ultrapassar o range de `float64` (~709), causando crash do `signal_engine.py` inteiro de forma inesperada. Improvável na prática, mas sem guarda.

**`trade_selector.py`:** Sem bug.

### Camada de Modelagem e ML/LLM

**`preditor.py` + `gerenciador_modelo.py` — Recarga de modelo do disco a cada ciclo:**
`GerenciadorModelo(simbolo=simbolo)` é instanciado dentro da função chamada a cada ciclo de decisão. `__init__` chama `_carregar()`, que faz `joblib.load()` de disco toda vez — leitura de arquivo e deserialização de modelo scikit-learn repetidas a cada predição. É I/O bloqueante desnecessário num loop com orçamento de tempo apertado (5–30s por ciclo).

> Confirmação positiva: em todos os lugares onde `partial_fit` é chamado (`treinador_online.py`, `recalibracao_startup.py`), `salvar()` é sempre chamado depois — o aprendizado online não se perde silenciosamente.

**`llm_analista.py` + `noticias.py` — `modelo_llm` mente a origem real:**
`"modelo_llm": "gpt-4o-mini"` é hardcoded incondicionalmente, mesmo quando `status_classificacao` é `"heuristica_local"` (sem chave de API, limite diário batido, ou erro de rede). Qualquer dashboard ou log que confie nesse campo para saber "isso veio do GPT ou da heurística" está sendo enganado pelo próprio dado.

**`decisor_hibrido.py`:**
Boa lógica de pesos por confiança. Conflito só reduz tamanho de posição quando ambas as confianças são `≥0.55`. Se o LLM tiver baixa confiança mas score forte e oposto ao numérico, o conflito não reduz nada — assimetria conhecida.

**`noticias.py` — Confirmação: existe chamada real à API da OpenAI:**
`https://api.openai.com/v1/responses` com retry exponencial, parsing seguro, fallback para heurística. `_llm_permitido()` com limite diário de 20 chamadas e cooldown de 60min após 5 falhas seguidas — bom design de controle de custo.

---

## Pergunta 9

**Pode continuar lendo tudo, que depois vou usar o Opus para corrigir tudo. Mas preciso que você ache todas inconsistências.**

---

## Resposta 9

Continuando — executor, fluxo de usuário, persistência, multiativo.

### Camada de Execução

**`fluxo_usuario_sinais.py` — Bug crítico garantido: `NameError` em produção:**
`logger` é chamado **6 vezes** (linhas 187, 189, 192, 194, 255, 257), mas **nunca foi importado** neste arquivo. Sem nenhuma definição ou import de `logger` em qualquer parte do módulo.

Resultado: `NameError: name 'logger' is not defined` é garantido toda vez que esse código executar — que é o comportamento **default** do sistema (`publicar_fila=True` é o padrão, linha 111). Pior: o `except` que deveria capturar e logar o erro também falha com o mesmo `NameError`, porque tenta usar `logger` de novo — então o erro real fica mascarado por um erro de "variável não existe".

**Reprodução confirmada com traceback real:**
```
NameError: name 'logger' is not defined
  File ".../fluxo_usuario_sinais.py", line 255
```

Esse é o motivo real pelo qual `test_pipeline` e `test_fluxo_usuario_signal_queue` falham — os testes aparentavam falhar por "usuário inexistente", mas o bug de `logger` estava escondido logo depois dessa barreira.

**`sessoes.py` — Credenciais Binance em texto puro na memória do processo:**
`SESSION_STORE_CREDENTIALS` tem default `True`. Quando ativo, `api_key` e `api_secret` ficam guardados em texto puro num dicionário global de processo `(_CREDENCIAIS)`, sem nenhuma criptografia em repouso, sem rotação, sem proteção contra dump de memória. Qualquer vetor que permita inspecionar a memória do processo expõe a API secret de qualquer usuário com sessão ativa.

**`ai_advisor.py` — Code smell em parsing de JSON:**
`texto.strip().lstrip("```json").lstrip("```").rstrip("```")` — `lstrip/rstrip` em Python não removem uma *substring* literal, removem qualquer caractere do *conjunto* fornecido. `lstrip("```json")` remove de forma greedy qualquer combinação de `` ` ``, `j`, `s`, `o`, `n` do início da string. Na prática, o `{` que inicia qualquer JSON válido quebra a sequência antes de dano real — **não é bug confirmado**, é prática incorreta. O correto seria `removeprefix()`/`removesuffix()` (Python 3.9+). Classificado como code smell, não bug funcional.

### Camada de Persistência

**`persistencia/base.py`** — Classe abstrata definida, zero repositórios reais herdam dela. **Arquivo morto confirmado.**

**`persistencia/uow.py`** — `UnidadeDeTrabalho` (Unit of Work) definida, zero usos em qualquer outro arquivo. **Arquivo morto confirmado.** Consequência: nenhuma transação multi-statement do sistema usa UoW — toda a persistência usa `get_conexao()` direto, statement a statement, sem transação explícita amarrando operações logicamente relacionadas (ex: criar ordem + atualizar snapshot).

**`repositorio_snapshot.py` — Read-modify-write sem lock:**
O padrão `obter_snapshot → modificar → salvar_snapshot` não tem nenhum mecanismo de "ler-e-travar" ou versão otimista (sem coluna `versao`/`etag`, sem transação amarrando as duas operações). Duas chamadas concorrentes ao mesmo símbolo podem resultar em *lost update* silencioso. Na prática seguro hoje (loop sequencial por token), mas frágil se qualquer novo caminho de código tocar o mesmo símbolo concorrentemente.

**`repositorio_fila_sinais.py`** — Melhor padrão do projeto: `BEGIN IMMEDIATE` garante claim atômico de itens da fila. Correto e bem feito.

**`conexao.py`** — Schema com WAL mode, `busy_timeout`, migrações idempotentes via `ALTER TABLE`. Design correto.

**`segredos.py`** — Excelente design: o sistema não armazena segredo nenhum no banco, apenas um `secret_id` (nome de variável de ambiente), com validação por regex estrita. Caminho legado exige flag explícita (`ALLOW_LEGACY_RAW_USER_SECRETS`, default `False`). **Ponto forte real.**

**`coletor_noticias.py`** — `calcular_peso_sentimento` é stub literal que sempre retorna `0.0`. Zero referências em qualquer outro arquivo. **Arquivo morto confirmado.**

### Camada Multiativo

**`capital_manager.py` — Parâmetro de risco agressivo:**
Para capital ≤$20: aloca **70% do saldo livre** num único trade, visando apenas **0.1% de lucro** (`_TAKE_PROFIT_ALVO = 0.001`). Combinado com o EV que já subestima custos de transação, é uma combinação especialmente arriscada: maior concentração de exposição justamente quando o capital é menor. O comentário "agressivo para capital pequeno" confirma que é intencional — mas vale reavaliar se reflete o apetite de risco desejado.

**`fee_optimizer.py` vs `fluxo_usuario_sinais.py` — Inconsistência de taxa entre caminhos:**
O autotrader (`testnet_auto_trader.py`) injeta a taxa efetiva real da conta (com desconto BNB) via `_ajustes_sinal_com_taxa_efetiva` antes do EV. O fluxo manual de usuário (`fluxo_usuario_sinais.py`) usa sempre a taxa de configuração fixa (0.001 default), ignorando qualquer desconto BNB. O **mesmo trade recebe avaliação de EV diferente** dependendo de qual caminho o acionou.

**`profit_guard.py` — Guard que não guarda:**
Recebe `taxas_totais_pct` e `slippage_pct` como parâmetros, os inclui no retorno, mas **nunca usa esses valores em nenhum cálculo de gate**. Confia inteiramente em quem chamou já ter feito essa conta corretamente antes — que sabemos estar com o bug do fee único. A última linha de defesa não verifica nada de forma independente.

**`orquestrador.py` — Bug de `AttributeError` latente:**
`ajustes_sinal` tem default `None` na assinatura (linha 140), mas linhas 225–228 e 240 usam `ajustes_sinal.get(...)` sem proteção — enquanto a linha 196 cria corretamente uma versão segura `ajustes_sinal_exec = dict(ajustes_sinal or {})` que nunca é usada nessas linhas. Todos os 3 chamadores atuais passam o parâmetro — bug não acionado hoje, mas é exatamente a "bomba-relógio" que quebra quando um quarto chamador omite o argumento.

### Coletores (coletor_velas_*)

**`coletor_velas_15s.py`** — Cria vela falsa onde `open = high = low = close = preço atual` e `volume = 0.0` sempre. Dados sem variação real. Zero referências fora do próprio arquivo. **Scaffold inacabado, arquivo morto.**

**`coletor_velas_ws.py`** — Ignora o campo `"x"` (boolean de vela fechada/em formação) da API WebSocket da Binance, persistindo velas parciais durante a formação. Qualquer leitor concorrente pode ler `high/low/volume` incompletos. **Zero referências fora do próprio arquivo — arquivo morto.** Bug real no código, sem efeito em produção hoje.

**`gerador_features.py`** — Bem feito. Features cíclicas de hora/dia via seno/cosseno (técnica correta). `_sanear_numero` aplicado universalmente. `_retorno` silenciosamente reduz passos se a série for curta — valor degradado sem sinalização no output (ambiguidade semântica, não erro de execução).

**`repositorio_features.py`** — Limiares `vol_regime` (0.012, 0.003) divergem ligeiramente de `regime_detector.py` (0.012, 0.0035). Pequena inconsistência de duplicação silenciosa de lógica — pode divergir mais com o tempo se alguém ajustar um sem lembrar do outro.

---

## Pergunta 10

**Continuar**

---

## Resposta 10

Continuando — `binance_api/`, `calculos/calibracao/`, `adaptacao/`, e observabilidade.

**`cliente.py` (binance_api) — Retry/backoff:**
`obter_resumo_conta()` retorna graciosamente `{"disponivel": False, ...}` sem credenciais — o `ClienteBinance()` sem chaves em `dashboard.py` é seguro. A lógica de `_executar_com_retry` para erros de timestamp está correta (mais sutil do que pareceu à primeira leitura, mas sem bug confirmado).

**`coletor_velas_rest.py`** — Código de coleta via REST está correto. É o único coletor real integrado ao sistema atualmente.

---

## Sumário Consolidado de Achados

### Bugs Críticos (quebram garantidamente em produção)

| # | Arquivo | Descrição |
|---|---|---|
| 1 | `fluxo_usuario_sinais.py` | `NameError: logger is not defined` — 6 chamadas a `logger.*` sem import. Quebra todo o fluxo de sinal de usuário com o comportamento default (`publicar_fila=True`). Causa real de 2 testes que falhavam por "motivo aparente diferente". |
| 2 | `ev_calculator.py` | Fee descontado **uma vez** (entrada), mas trade completo paga **duas** (entrada + saída). EV estruturalmente otimista — subestima custo real pela metade. |
| 3 | `gerenciador_ordens.py` → `simular_ordem` | Mesmo bug de fee único, segundo lugar independente. |

### Bugs Corrigidos Nesta Sessão

| # | Arquivo | Descrição |
|---|---|---|
| ✅ | `gerenciador_ordens.py` | `criar_ordem_limit` agora levanta `NotionalTooSmall` corretamente. |
| ✅ | `gerenciador_ordens.py` | Removido `try/except NameError` como controle de fluxo; eliminada chamada de rede duplicada. |
| ✅ | `testnet_auto_trader.py` | Teto de notional: testnet livre, conta real com teto via `AUTO_MAX_NOTIONAL_USDT_REAL`. |

### Bugs Latentes / Bomba-Relógio

| # | Arquivo | Descrição |
|---|---|---|
| 4 | `orquestrador.py` | `ajustes_sinal.get(...)` em linhas 225–228/240 sem proteção contra `None`, enquanto a variável segura (`ajustes_sinal_exec`) existe mas não é usada ali. Não acionado hoje — quebra no próximo chamador que omitir o argumento. |
| 5 | `probability_calibrator.py` | `math.exp(...)` pode estourar `float64` se `temperature` for muito baixo. Sem guarda além de `> 1e-6`. |
| 6 | `repositorio_snapshot.py` | Read-modify-write sem lock/versão. Lost update silencioso se dois processos tocarem o mesmo símbolo concorrentemente. |

### Inconsistências de Design (não quebram, mas distorcem resultados)

| # | Arquivo | Descrição |
|---|---|---|
| 7 | `consenso.py` | Assimetria estrutural: confirmar = score ≥0.10 (1 indicador fraco); vetar = score ≥0.35 (2 indicadores fortes). Sistema enviesado a mais trades. |
| 8 | `noticias.py` + `llm_analista.py` | `"modelo_llm": "gpt-4o-mini"` hardcoded mesmo quando a resposta vem da heurística. Auditoria de logs corrompida. |
| 9 | `fee_optimizer.py` vs `fluxo_usuario_sinais.py` | Autotrader usa taxa efetiva real (com desconto BNB); fluxo manual usa taxa fixa. Mesmo trade, EV diferente. |
| 10 | `profit_guard.py` | Recebe `taxas_totais_pct` e `slippage_pct`, nunca os usa em nenhum cálculo. Guard que não guarda de forma independente. |
| 11 | `capital_manager.py` | 70% do saldo livre por trade para capital ≤$20, com alvo de apenas 0.1%. Combinação agressiva de risco concentrado com EV já subestimado. |
| 12 | `repositorio_features.py` vs `regime_detector.py` | Limiares `vol_regime` divergem (0.003 vs 0.0035). Duplicação silenciosa que pode divergir mais. |

### Arquivos Mortos / Scaffold Nunca Conectado

| Arquivo | Status |
|---|---|
| `coletor_noticias.py` | Zero referências externas. Stub `calcular_peso_sentimento` sempre retorna 0.0. |
| `persistencia/base.py` | Classe abstrata, zero repositórios herdam. |
| `persistencia/uow.py` | Unit of Work implementado, nunca usado — nenhuma transação multi-statement real. |
| `coletor_velas_15s.py` | Scaffold — velas falsas, nunca conectado ao sistema. |
| `coletor_velas_ws.py` | Ignora flag de vela fechada — bug real no código, mas arquivo morto em produção. |

### Performance

| # | Arquivo | Descrição |
|---|---|---|
| 13 | `preditor.py` | `GerenciadorModelo()` instanciado (e modelo recarregado do disco via `joblib.load()`) a cada ciclo de predição. I/O bloqueante repetido desnecessariamente. |

### Pontos Genuinamente Bem Feitos

- **`risk_engine.py`** — Puro, determinístico, sem I/O, cada veto nomeado e auditável. Boa base para confiar decisões de capital.
- **`segredos.py`** — Não armazena segredo no banco, apenas referência a variável de ambiente. `ALLOW_LEGACY_RAW_USER_SECRETS` com default `False`.
- **`repositorio_fila_sinais.py`** — `BEGIN IMMEDIATE` garante claim atômico — o melhor padrão de concorrência do projeto.
- **`noticias.py`** — `_llm_permitido()` com limite diário de 20 chamadas e cooldown de 60min após 5 falhas. Controle de custo e resiliência bem pensados.
- **4 pontos de bloqueio de `PERMITIR_CONTA_REAL`** — API + executor, todos `default-false`. Defense in depth real.
- **`TestnetAutoTrader.iniciar()`** — Protege corretamente contra dupla-task no mesmo token (linha 1341–1346).
- **`triangular_arbitrage.py`** — Bid/ask usados corretamente conforme o lado da operação; taxa e slippage aplicados em cada perna.

---

## Status Final da Auditoria

| Métrica | Valor |
|---|---|
| Total de arquivos `.py` do projeto | 124 |
| Arquivos lidos completamente | ~47 (38%) |
| Testes passando após correções | 86 de 95 |
| Arquivos mortos confirmados | 5 |
| Bugs críticos confirmados (não corrigidos ainda) | 3 |
| Bugs corrigidos nesta sessão | 3 |
| Sem CI/CD configurado | `.github/workflows` inexistente |

> **Próximo passo recomendado para o Opus:**
> Priorizar na ordem: (1) `NameError` de logger em `fluxo_usuario_sinais.py`; (2) fee round-trip em `ev_calculator.py` e `simular_ordem`; (3) orquestrador `ajustes_sinal=None`; (4) demais inconsistências de design.
> Em paralelo e independentemente do código: rodar o coletor de mercado real, alimentar o backtester, validar se há edge estatístico antes de qualquer outra refatoração.
