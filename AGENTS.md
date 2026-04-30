# Agentes Autônomos — Oráculo de Trading

Este documento descreve um conjunto de agentes A.I. projetados para
construir, operar e evoluir um bot de trading autônomo baseado no projeto
presente em `src/`. Os agentes são organizados para delegar tarefas,
aplicar boas práticas de engenharia de software, administrar transações
e operar com expertise em `py-binance`, LLMs locais e regras de trading.

Objetivos principais
- Entregar autonomia operacional: todas as regras, pesos, limites e sinais
	devem ser gerenciáveis pelo próprio sistema (persistência em DB e UI/API),
	de forma que o arquivo `.env` contenha apenas credenciais sensíveis
	mínimas (ex.: chaves AI, `DB_PATH`).
- Garantir segurança: testes, gates para conta real, audit trail, reversão.
- Nomeclatura e documentação em PT-BR, coerência semântica e modularidade.

Como usar este arquivo
- `agente.md` contém responsabilidades, critérios e fluxos de cada agente.
- `agente.codex` (arquivo separado, gerado junto) contém um manifesto/JSON
	legível por máquinas com prompts e limites operacionais para cada agente.

Princípios transversais (regras que todo agente segue)
- Linguagem/Estilo: variáveis, funções e mensagens em PT-BR; nomes semânticos
	e consistentes (ex.: `gerar_previsao`, `repositorio_ohlcv`).
- Persistência de configuração: tudo que é parâmetro de operação (pesos,
	limiares, timeouts, filas) deve ser salvo em `config` via
	`RepositorioConfig` e exposto em endpoints `/v1/config` para monitoramento
	e ajuste dinâmico.
- Segurança: não executar ordens em contas reais sem `PERMITIR_CONTA_REAL=true`
	e aprovação explícita do operador; padrão `testnet=true` para novos usuários.
- Idempotência e retrys: operações externas (ordens, chamadas Binance) devem
	ser idempotentes, com retries exponenciais e registros de auditoria.
- Observabilidade: métricas, logs estruturados e auditoria de decisões.
- Testes automatizados: cada mudança gera/atualiza testes unitários e de
	integração relevantes.

Minimal .env desejável
- `DB_PATH` — caminho para SQLite
- `AI_API_KEY` ou `LOCAL_LLM_PATH` — credenciais/endpoint LLMs locais
- (opcional) `BINANCE_API_KEY` e `BINANCE_API_SECRET` apenas para testes

Nota: o agente de configuração deve migrar e materializar todos os limites
operacionais (signal thresholds, fees, slippage, queue params) para o DB
no primeiro boot.

Definição de agentes

1) Agente Coordenador (Coordinator)
- Papel: orquestrar os demais agentes; planejar sprints/automações; decidir
	quando aplicar mudanças de configuração em produção.
- Habilidades: leitura profunda do `src/README.md`, entendimento de CI/CD,
	versionamento de modelos e migrações DB.
- Entradas: issues, tarefas, estado atual do repositório, métricas.
- Saídas: tarefas delegadas, deploys seguros, checkpoints e auditorias.
- Regras de decisão: mudanças com impacto em ordens reais exigem
	validação por `QA` e aprovação manual ou por policy (ex.: consenso >= 2).

2) Agente de Coleta (DataCollector)
- Papel: manter coletores de mercado (REST/WS), validar completude dos dados
	e persistir OHLCV, livro topo e features.
- Habilidades: `py-binance`, robustez de rede, deduplicação, backfill.
- Contratos: garante que `RepositorioOhlcv` e `RepositorioLivroTopo` estejam
	atualizados; quando detectar lacunas aciona backfill e registra auditoria.

3) Agente de Features (FeatureEngine)
- Papel: encapsular `calculos.gerador_features.calcular_features_1m` e
	manter transformações consistentes (normalização, tratamento de nulos).
- Habilidades: tratamento numérico, geração de testes regressivos para
	features esperadas (conformidade com `FEATURE_ORDER`).

4) Agente de Modelagem (ModelTrainer)
- Papel: treinar modelos batch, manter versões, publicar artefatos em
	`MODEL_DIR` e fornecer critérios de promoção de modelos para produção.
- Habilidades: sklearn, joblib, validação cross-time, geração de
	conjuntos de validação e testes de performance (shap/feature-importance).
- Regras: só promover batch-model se métricas (ex.: MAPE, Sharp) melhorarem
	em relação ao baseline e não reduzirem robustez em cenários adversos.

5) Agente de Serviço de Modelos (ModelServer)
- Papel: manter `GerenciadorModelo` sincronizado — disponibilizar endpoint
	local para inferência offline/online e atualizar `RepositorioConfig` com
	meta-informações (versão ativa, amostras ajustadas).
- Habilidades: rollback, canary deploys, monitoramento de deriva de dados.

6) Agente de Calibração (CalibrationAgent)
- Papel: executar `calibracao.bandit` e `ewls`, atualizar parâmetros de
	calibração persistidos e manter histórico de mudanças.

7) Agente LLM Manager (LLMManager)
- Papel: gerenciar modelo LLM local (instalação, quantização, prompt tuning),
	indexação de fontes de notícias e orquestração de chamadas LLM.
- Habilidades: gerenciamento de runtimes locais (LLM), caching de prompts,
	failover para heurística caso LLM indisponível.

8) Agente de Sinal (SignalEngine Agent)
- Papel: implementar `sinais.signal_engine.gerar_sinal_orquestrado` em ciclos
	isolados, validar regras de confirmação multi-timeframe e gerar payloads
	para a fila (`RepositorioFilaSinais`).
- Regras: exporta motivo, nível de confiança e metadados para auditoria.

9) Agente de Probabilidade (ProbabilisticAgent)
- Papel: manter e rodar o `ProbabilisticTradeEngine`, gerar `ev_buy`,
	`ev_sell`, `prob_up`/`prob_down` e expor thresholds ajustáveis no DB.

10) Agente de Risco (RiskManager)
- Papel: aplicar `risco.risk_engine.avaliar_sinal_para_usuario`, calcular
	sizing, frações de capital, motivos de rejeição e controles anti-ruído.
- Regras administrativas: não autorizar execuções que violem limitações
	(stop loss máximos, exposição por usuário) e registrar sempre em `audit`.

11) Agente de Execução (Executor)
- Papel: preparar ordens via `executor.ExecutorIsoladoUsuario` e usar
	`GerenciadorOrdens` para envio; gerenciar confirmações e reenvios.
- Segurança: operações em conta real exigem `PERMITIR_CONTA_REAL=true`,
	`2FA` operacional ou aprovação manual; manter transações idempotentes.

12) Agente de Observabilidade (Observability)
- Papel: manter `observabilidade.metricas` e logs; criar dashboards para
	alertas de deriva, falhas de coleta e erros de execução.

13) Agente QA/Testes (QA Agent)
- Papel: gerar e executar baterias de testes unitários e integração após
	mudanças; validar contratos (repositórios, API, formatos de messages).

14) Agente DevOps (DevOps Agent)
- Papel: migrar DB (`inicializar_db()`), gerenciar releases, criar tags,
	manter CI/CD e rollbacks seguros.

Persistência e Autonomia de Configuração
- Todos os parâmetros operacionais (weights, thresholds, fees, slippage,
	filas, retry policies) devem ser persistidos em `config` via
	`RepositorioConfig.definir(chave, valor)` e expostos em `/v1/config`.
- No primeiro boot, o Agente Coordenador executa um script de bootstrap que
	insere valores default caso `config` esteja vazio.

Segurança e Governança de ordens reais
- Política: só executar ordens reais se:
	1) `PERMITIR_CONTA_REAL=true` no ambiente;
	2) usuário/operador aprovar via endpoint ou console;
	3) checks de risco passados (ex.: exposição, max drawdown diário);
	4) testes automatizados e integração contínua sem falhas.

Interfaces e APIs internas
- Use contratos Pydantic/typed (já presentes em `main.py`) para todos
	payloads entre agentes e endpoints. Logs e auditoria devem ser registros
	JSON com `tipo`, `ts`, `usuario` e `detalhe`.

Delegação e ciclo de trabalho dos agentes
- Tarefa de alto nível é quebrada pelo Coordenador em subtarefas (ex.:
	"treinar batch para BTCUSDT com último mês") que são enfileiradas no
	sistema de tarefas (`tarefas/` e fila de repositório). Cada agente explora
	o estado atual (DB, métricas) antes de executar e reporta resultado/erro.

Regras de engenharia de software (práticas obrigatórias)
- Testes: cobertura mínima para novo código >= 80% nas partes críticas.
- Tipagem estática e docstrings: funções públicas devem ter typing completo.
- Logging: eventos críticos e decisões de trading devem ser logados.
- Revisões e PRs: mudança de modelo/banco só após revisão e testes de
	performance comparativa.

Proposta de ciclo automático para ajustes de sinal
1. Monitorar métricas de outcomes vs predictions (outcomes/predictions).
2. Quando a performance cair abaixo do threshold, treinar novo modelo batch.
3. Validar performance offline; se aprovado, promover via canary (10% do tráfego).
4. Se canary ok, promover globalmente; caso contrário, rollback.

Considerações finais
- Esses agentes são papéis e recomendações. A implementação
	concretiza-os via scripts, jobs, endpoints e tarefas. Posso gerar agora:
	- `agente.codex` com prompts e políticas por agente (JSON);
	- scripts de bootstrap para persistir configurações iniciais;
	- um diagrama mermaid do pipeline para documentação visual.

Arquivo gerado pelo assistente — revise e diga qual arquivo quer primeiro: agente.codex, script de bootstrap, ou diagrama.

