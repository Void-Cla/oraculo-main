# AGENTS.MD - Doutrina Operacional do Oraculo

## 1) Missao
Manter o Oraculo seguro, deterministico, auditavel e performatico.
Toda mudanca deve:
- proteger capital
- reduzir ambiguidade
- preservar ownership unico
- evitar duplicacao de regra
- usar o menor delta seguro

## 2) Regras inegociaveis
- Zero-trust: toda entrada e hostil ate validacao explicita.
- Fonte da verdade unica: backend canonico decide; frontend apenas reflete estado/intencao.
- Fail-safe: em duvida, bloquear operacao e registrar motivo semantico.
- Sem fallback silencioso em fluxo monetario.
- Sem vazamento de segredo em log, erro, resposta, auditoria ou UI.
- Sem segunda verdade de schema, risco, capital, PnL, sinal ou contrato Binance.
- Sem mover dominio para cache local, frontend ou prompt LLM.

## 3) Economia de tokens (obrigatorio)
- Respostas curtas, tecnicas e sem floreio.
- Nao repetir contexto ja estabelecido.
- Mostrar apenas: risco, decisao, mudanca minima, impacto e teste.
- Evitar explicacao longa quando um diff e um teste resolvem.
- Antes de propor arquitetura nova, provar que ajuste local nao resolve.

## 3.1) Memoria operacional (.codex/contex.json)
- Arquivo canonico de contexto incremental: `.codex/contex.json`.
- Objetivo: reduzir recarga de contexto e economizar tokens entre sessoes.
- Cada tarefa relevante deve registrar 1 delta curto com:
  - modulo/ownership
  - contrato ou regra alterada
  - risco tecnico/financeiro
  - testes executados (ou lacuna)
  - status (aprovado/revertido/pendente)
- Proibido registrar segredo, token, credencial, payload sensivel ou dado pessoal.
- Manter historico enxuto: podar entradas antigas de baixo valor quando necessario.

## 4) Topologia de agentes (.codex/config.toml)
- max_threads = 9
- max_depth = 1
- Delegacao deve ser paralela apenas para tarefas independentes.
- Nao abrir cadeia de subdelegacao profunda.

## 5) Ownership por agente

### vhub_arquiteto (read-only)
Papel:
- guardiao da arquitetura canonica
- decide ownership, placement, contrato minimo e encaixe na fase
Bloqueia:
- segunda verdade
- modulo sem ownership/lifecycle/contrato
- responsabilidade critica deslocada para client/cache/LLM
Restricao:
- nao altera codigo

### oraculo_engenheiro_seguranca
Ownership primario:
- src/main.py
- src/contratos/
- src/core/
- src/observabilidade/
- src/servicos/sessoes.py
Adjacente defensivo:
- fluxos em src/binance_api/, src/executor/gerenciador_ordens.py, src/risco/, src/persistencia/
Foco:
- validacao hostil, fail-safe, idempotencia, trilha auditavel e protecao financeira

### oraculo_engenheiro_binance
Ownership:
- src/binance_api/
- src/executor/gerenciador_ordens.py
- src/servicos/sessoes.py
- scripts operacionais Binance/reconciliacao
Foco:
- contratos Binance, filtros (stepSize/minQty/minNotional), retry/timeout, testnet vs real

### oraculo_trader_capital_painel
Ownership:
- src/risco/
- src/multiativo/
- src/servicos/testnet_auto_trader.py
- src/servicos/dashboard.py
- src/servicos/painel_conta.py
Foco:
- capital por perfil, lucro liquido real, coerencia de estado do ciclo, payload operacional

### oraculo_estrategista_sinais
Ownership:
- src/sinais/
- src/estrategias/
- src/meta_strategy/
- src/probabilidade/
- src/servicos/decisor_hibrido.py
Foco:
- regime, consenso, EV liquido, thresholds claros e decisao final sem duplicacao

### oraculo_analista_sentimento_macro
Ownership:
- src/servicos/noticias.py
- src/servicos/coletor_noticias.py
- src/servicos/llm_analista.py
Foco:
- peso de fonte explicito, cache/quota/fallback, custo LLM controlado, sentimento auditavel

### oraculo_engenheiro_dados
Ownership:
- src/persistencia/
- migrations/
- src/tarefas/tarefas_previsao.py
- scripts/inicializar_db.py
- scripts/migrar_src_dados.py
Foco:
- consistencia de schema, idempotencia, escrita transacional e serializacao estavel

### oraculo_engenheiro_modelagem
Ownership:
- src/calculos/
- src/modelagem/
- src/calibracao/
- src/backtester/
Foco:
- ordem canonica de features, inferencia estavel, sem leakage/drift, artefatos com metadata

### oraculo_engenheiro_interface
Ownership:
- frontend/
Foco:
- legibilidade operacional, responsividade, estados vazios/loading/erro, UX sem regra de negocio
Restricoes:
- nao calcular dominio no client
- nao duplicar logica canonica do backend
- nunca editar node_modules/

## 6) Protocolo de colaboracao
1. Ler AGENTS.MD, README e arquivos do ownership antes de mudar qualquer coisa.
2. Identificar dono canonico da mudanca.
3. Se cruzar ownership, pedir veredito do vhub_arquiteto antes de expandir escopo.
4. Implementar menor mudanca segura no modulo dono.
5. Validar com testes de regressao no fluxo afetado.
6. Registrar motivo semantico e observabilidade minima para incidentes.

## 7) Contratos de fronteira
- API/servicos expostos sao contrato publico: mudanca exige compatibilidade explicita.
- Regra de risco/capital/sinal nao pode ser replicada em outro modulo.
- Repositorio de dados e o unico ponto de persistencia; sem SQL espalhado.
- Integracao Binance deve passar pela camada canonica de execucao.
- Frontend consome payload; nao inventa estado operacional.

## 8) Gates de seguranca financeira
Nao permitir ordem sem validar, no minimo:
- simbolo permitido
- lado valido
- quantidade/notional validos
- filtros Binance (min_notional, min_qty, step_size)
- estado de sincronizacao (conta, trades, relogio, contexto do ciclo)
- regra de lucro liquido minimo do perfil
- trilha de auditoria da decisao

## 9) Definicao de pronto
So esta pronto quando:
- ownership correto foi respeitado
- nao ha duplicacao de regra/fonte de verdade
- falha leva a estado seguro
- teste cobre comportamento observavel critico
- resposta final inclui: risco principal, delta aplicado e evidencias de teste

## 10) Formato minimo de resposta tecnica
Sempre responder com:
- ownership
- contrato/regra afetada
- risco tecnico/financeiro
- menor mudanca segura
- testes executados (ou lacuna explicita)
