<!--
	README do diretório `src/` — Documentação detalhada do Oráculo.
	Objetivo: fornecer a qualquer leitor (ou AI) visão completa da
	arquitetura, responsabilidades, fluxos de dados e pontos de extensão.
-->

# Oráculo (src)

Este documento descreve o conteúdo do diretório `src/` do projeto Oráculo.
Ele foi escrito para ser um guia completo para desenvolvedores e para
agentes automáticos que precisam entender a arquitetura, responsabilidades
dos módulos, principais funções/contratos, variáveis de ambiente, esquema
de armazenamento e caminhos típicos de execução.

Sumário
- **Visão geral (Resumo rápido)**
- **Arquitetura e princípios**
- **Mapa de módulos e responsabilidades**
- **Fluxo de sinal (end-to-end)**
- **Banco de dados e schema**
- **Modelagem e predição**
- **Integração com Binance**
- **API pública e endpoints principais**
- **Observabilidade e métricas**
- **Variáveis de ambiente importantes**
- **Como executar / modo desenvolvedor**
- **Pontos de extensão e contribuições**

## Visão geral (Resumo rápido)

- O código em `src/` implementa um orquestrador de sinais de trading:
	coleta mercado, gera features, roda modelos (online e batch), calibra
	previsões, combina evidências (consenso), aplica regras de risco e
	envia ordens (ou simula/executa) por usuário.
- As responsabilidades são separadas por pacote: coleta (`binance_api`),
	cálculo de features (`calculos`), modelagem (`modelagem`), sinais
	e consenso (`sinais`, `meta_strategy`), risco (`risco`), execução
	(`executor`), persistência (`persistencia`) e operações/serviços
	(endpoints e fluxos) em `servicos` e `tarefas`.

## Arquitetura e princípios

- Separação de responsabilidades:
	- Coleta não decide trades;
	- Modelo não decide risco;
	- Motor de risco não executa ordens;
	- Executor é responsável por transformar plano em ordens.
- Modularidade: cada pacote implementa um contrato claro com funções
	assíncronas que podem ser utilizadas dentro de pipelines e testes.
- Persistência local: SQLite é utilizado como armazenamento principal
	(facilidade de deploy e testes locais).

## Mapa de módulos e responsabilidades (resumo)

- `main.py` — entrada da aplicação e definição dos endpoints HTTP.
- `api/` — adaptação/expôr `app` (FastAPI).
- `binance_api/` — cliente Binance (`ClienteBinance`) e coletores (REST/WS).
- `calculos/` — gerador de features (`gerador_features.py`).
- `calibracao/` — código de calibração (`bandit.py`).
- `contratos/` — contratos de domínio e helpers de trading.
- `core/` — configurações e gerenciamento de secrets (`settings.py`, `segredos.py`).
- `persistencia/` — camada de acesso a dados (repositórios e conexões).
- `modelagem/` — `GerenciadorModelo` (online), preditor end-to-end e treinadores.
- `meta_strategy/` — controller para combinar regras estratégicas e regimes.
- `sinais/` — engine de sinais, fila durável e consolidadores de decisão.
- `risco/` — engine de risco e sizing (validação de sinal por usuário).
- `executor/` — lógica para preparar e enviar ordens (paper/real).
- `servicos/` — orquestração de fluxos (painel, notícias, sessões, ajustes).
- `tarefas/` — background tasks e loops (previsão, consumidor de fila, coletor contínuo).
- `observabilidade/` — logger, métricas (Prometheus), qualidade de sinal (IC/Brier/drawdown),
	correlation_id e saúde de modelo/treino (`saude_modelo.py`).
- `multiativo/` — scanner, capital, arbitragem triangular, profit-guard e orquestrador.
- `backtester/` — backtester WALK-FORWARD com lucro líquido (`walk_forward.py`).
- `core/` — settings (`load_dotenv`), segredos e validação fail-fast de config.

### Estrutura de pastas (visão rápida)

- [src](src) — código-fonte principal
	- [api](src/api) — adaptador FastAPI
	- [binance_api](src/binance_api) — integração Binance
	- [calculos](src/calculos) — geração de features
	- [calibracao](src/calibracao) — calibração de previsões
	- [modelagem](src/modelagem) — modelos e gerenciador
	- [sinais](src/sinais) — signal engine, fila e consenso
	- [persistencia](src/persistencia) — repositórios e conexões
	- [servicos](src/servicos) — fluxos e APIs auxiliares
	- [executor](src/executor) — execução de ordens
	- [tarefas](src/tarefas) — workers/loops
	- [observabilidade](src/observabilidade) — logging/metrics

## Fluxo de sinal (end-to-end)

1. Coleta: `binance_api.coletor_velas_rest` obtém klines e livro e persiste
	 em `persistencia` (`RepositorioOhlcv`, `RepositorioLivroTopo`, `RepositorioFeatures`).
2. Features: `calculos.gerador_features.calcular_features_1m` produz dicionário
	 de features via candles + livro topo + sentimento de notícias.
3. Predição: `modelagem.GerenciadorModelo.predict` combina modelo online,
	 modelo batch e fallback heurístico; `modelagem.preditor` calibra a saída.
4. Meta-strategy: `meta_strategy.meta_controller` aplica regras estratégicas
	 e regime detection para gerar sinal base (take profit, stop loss, etc.).
5. Probabilidade: `probabilidade.probabilistic_engine.ProbabilisticTradeEngine`
	 avalia expectativa, prob_up/prob_down e métricas de EV.
6. Consenso: `sinais.consenso.consolidar_decisao` agrega fontes (estratégia,
	 modelo, LLM, confirmação multi-timeframe, probabilidade) e define ação.
7. Risco: `risco.risk_engine.avaliar_sinal_para_usuario` valida sinal por usuário,
	 calcula fraction sizing e papel vs real.
8. Executor: `executor.ExecutorIsoladoUsuario` prepara plano e `GerenciadorOrdens`
	 envia ordens (ou simula). Filas (`sinais.fila_sinais`) suportam processamento
	 assíncrono e retrys.

## Banco de dados (SQLite) — esquema resumido

O esquema inicial criado em `persistencia.conexao.DDL_BASE` contém tabelas
principais (resumo):

- `ohlcv_1m`, `ohlcv_15s` — candles (ts, simbolo, open, high, low, close, volume)
- `livro_topo` — snapshot de topo de livro (bid/ask preço e qty)
- `features_1m` — features JSON por ts/símbolo
- `predictions` — previsões (y_hat, y_cal, p_conf, meta_json)
- `outcomes` — outcomes para avaliação de predições
- `config` — pares chave/valor para ajustes dinâmicos
- `usuarios` — usuários, secrets references, risk_config
- `ordens` — ordens registradas (status, modo, detalhe_json)
- `audit` — eventos de auditoria
- `fila_sinais` — fila durável de sinais para processamento assíncrono

As DDL e pragmas estão em `src/persistencia/conexao.py` e a inicialização
é feita por `inicializar_db()` (usada na inicialização do app em `main.py`).

## Modelagem e predição

- `modelagem.GerenciadorModelo`:
	- Mantém modelo online (`SGDRegressor` + `StandardScaler`).
	- Suporta `partial_fit` (ajuste online) e `salvar()` para persistência.
	- Carrega modelos batch quando presentes (`batch-*.joblib`).
	- `FEATURE_ORDER` lista as features esperadas.
- `modelagem.preditor.preditor_end_to_end`:
	- Orquestra gerenciador, calibrador (bandit) e decisor híbrido.
	- Retorna `y_hat`, `y_cal`, `p_conf`, `decisao` e metadados.
- Treinamento em batch: `treinador_batch.py` e treinamento online em `treinador_online.py`.

## Integração com Binance

- `binance_api.ClienteBinance` encapsula `binance.AsyncClient`.
	- Retry, sincronização de timestamp, rotação de chaves (opcional).
	- Métodos: `obter_klines`, `obter_order_book_top`, `obter_preco_atual`, `obter_conta_raw`, etc.
- Coletores:
	- `coletor_velas_rest.coletar_e_persistir` baixa klines (1m), salva OHLCV,
		livro topo e features (upsert idempotente).
	- `tarefas/coletor_continuo.loop_coleta_continua` — coleta CONTÍNUA (REST público,
		sem credenciais) em loop, ligada por `ATIVAR_COLETA_CONTINUA`. Acumula dado real
		para pesquisa de edge independente do trading.

## API pública (endpoints principais)

As rotas estão em `main.py` (FastAPI). Principais endpoints:

- `/` — raiz com versão e links.
- `/v1/health` — healthcheck + estado de loops.
- `/v1/metrics` — métricas Prometheus.
- `/v1/previsao` — gerar previsão (coleta opcional e persistência).
- `/v1/previsao/manual` — enviar payload manual com klines/livro/notícias.
- `/v1/sessao/entrar` `/v1/sessao/status` `/v1/sessao/sair` — sessão Binance (cookies).
- `/v1/auto/*` — iniciar/parar auto-trader (testnet/real) e status.
- `/v1/diagnostico` — visão consolidada (health + treino online + LLM).
- `/v1/modelos/treino` — saúde do treino online: gate de amostras, divergência (`coef_norm`),
	`online_em_uso` e IC de **retorno** recente (métrica de edge — não preço).
- `/v1/ai/saude` — vida do LLM (chave presente, modo fallback, último insight).
- `/v1/export/*` — exportar OHLCV, features, predicoes, outcomes, auditoria.
- `/v1/dashboard/resumo` — montar dashboard combinado via `servicos.dashboard`.

Veja `main.py` para validações, Pydantic models e regras (por exemplo, controle
de start em conta real via env `PERMITIR_CONTA_REAL`).

## Observabilidade e métricas

- `observabilidade.logger.get_logger` centraliza logs estruturados.
- `observabilidade.metricas` define métricas Prometheus usadas em `main.py`:
	latência de previsão, contadores de previsões/erros, confiança média, etc.

## Variáveis de ambiente importantes (não exaustivo)

- `DB_PATH` — caminho para o SQLite (padrao `./dados/oraculo.sqlite`).
- `MODEL_DIR` — diretório para modelos (padrao `./dados/modelos`).
- `ATIVAR_LOOP_PREVISAO` — roda loop de previsão automático se `true`.
- `ATIVAR_CONSUMIDOR_SINAIS` — ativa consumidor da fila de sinais (ativo por padrão).
- `ATIVAR_CARGA_TESTE` — ativa carga de teste.
- `COOKIE_SECURE` — cookie secure flag.
- `SESSION_TTL_HOURS` — duração TTL das sessões (cookies).
- `PERMITIR_CONTA_REAL` — habilita uso com conta real (safety gate).
- `BINANCE_API_KEYS`, `BINANCE_API_KEY`, `BINANCE_API_SECRET` — credenciais.
- `API_ROTATE_ON_EACH_CALL` — rotaciona chaves por chamada.
- `BINANCE_TESTNET`, `BINANCE_TIMEOUT_SECONDS`, `BINANCE_MAX_TENTATIVAS` — cliente Binance.
- `SIGNAL_*` — diversas flags/limiares usados por `signal_engine` (confirm, fees, slippage,
	min_ev, min_prob, temperature, scale, decision_window_minutes, etc.).
- `FORCE_ALLOW_RISKY_TRADES` — override para permitir trades arriscados (uso interno/testnet).

Para uma lista completa, grep por `os.getenv(` e `env_*` nas fontes.

## Como executar (modo rápido)

1. Criar virtualenv e instalar dependências (veja `requirements.txt`).
2. Ajustar variáveis de ambiente (ex.: `DB_PATH`, `BINANCE_API_KEY`, `BINANCE_API_SECRET`).
3. Iniciar (local):

```powershell
# ativar venv
& .\\.venv\\Scripts\\Activate.ps1
# entry point canônico: src.main:app (mesmo de start.sh/start.bat)
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

4. Para iniciar loops/background workers, setar `ATIVAR_LOOP_PREVISAO=true` antes de iniciar.
   O consumidor de sinais já é ativado por padrão.

Scripts utilitários estão em `scripts/` (migrar DB, criar usuários de teste, etc.).

## Testes

- Há testes em `tests/` cobrindo integração e unidades dos módulos principais.
- Use `pytest` no root do projeto. Alguns testes podem exigir DB ou variáveis
	de ambiente (veja `tests/conftest.py`).

## Pontos de extensão e contribuição rápida

- Adicionar nova estratégia/meta-strategy: implementar em `meta_strategy/`
	e registrar/usar em `sinais.signal_engine`.
- Troca de backend de persistência: abstrair repositórios em `persistencia/`
	e implementar adaptadores (ex.: Postgres) seguindo contratos atuais.
- Nova fonte de dados: criar coletor que persista em `persistencia` e
	forneça as features esperadas por `FEATURE_ORDER`.

## Dicas de leitura (ordem recomendada)

1. `src/main.py` — para ver como a aplicação é exposta e quais contratos HTTP existem.
2. `src/persistencia/conexao.py` — entender o schema e invariantes do DB.
3. `src/calculos/gerador_features.py` — ver as features esperadas.
4. `src/modelagem/gerenciador_modelo.py` e `src/modelagem/preditor.py` — predição e pesos.
5. `src/sinais/signal_engine.py` e `src/sinais/consenso.py` — como combinar sinais.
6. `src/risco/risk_engine.py` — regras por usuário e sizing.
7. `src/executor/` — concretização do envio de ordens.

## Segurança e estado de edge (fiel, 2026-06)

- **Segurança:** fail-fast de config no startup; conta real bloqueada por padrão; breaker de perda
	diária persistido (sobrevive a restart, reset humano); custo round-trip coeso em todas as camadas;
	só abre/encerra ciclo após confirmar o fill (anti-posição-fantasma); EV negativo proibido em conta real.
- **Modelo:** gate anti-divergência descarta modelo online sub-treinado/saturado (`coef_norm` alto) —
	visível em `/v1/modelos/treino`. Hoje o modelo está frio (poucas amostras, batch ausente) → o bot
	roda no fallback heurístico até acumular dado.
- **Edge:** pesquisa walk-forward com lucro LÍQUIDO mostra que **não há edge tradeável nos dados atuais**
	(retorno bruto < custo). Pré-requisito para operar com lucro: ligar `ATIVAR_COLETA_CONTINUA`, acumular
	dado por dias, re-rodar `scripts/backtest_walkforward.py` e só operar se `net/trade > 0` estável.

> Estado vivo do projeto: `.claude/contexto.md`. Lições/armadilhas: `.claude/skill.md`.

