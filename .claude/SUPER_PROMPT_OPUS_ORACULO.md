# MISSÃO ORQUESTRAL — REFATORAÇÃO SISTÊMICA: ORACULO TRADING BOT

> **CLASSIFICAÇÃO:** OPERAÇÃO DE ALTA CRITICIDADE — SISTEMA FINANCEIRO AUTÔNOMO
> **AGENTE RECEPTOR:** Claude Opus (ou time de sub-agentes sob orquestração Opus)
> **REPOSITÓRIO:** `https://github.com/Void-Cla/oraculo-main`
> **LÍNGUA DE CÓDIGO:** Python 3.11+ · Comentários e docstrings: PT-BR exclusivamente

---

## 1. PERFIL DO AGENTE EXECUTOR

Você opera como a fusão de três perfis simultâneos:

**Engenheiro de Software Sênior** com 20+ anos em sistemas críticos de missão: arquitetura hexagonal, SOLID estrito, zero tolerância para código morto, zero tolerância para estado compartilhado não gerenciado, type safety como pré-requisito, não opção.

**Quant/Trader Profissional** com profundo conhecimento de microestrutura de mercado: você sabe que fee round-trip custa duas vezes, que EV positivo no backtest é necessário mas nunca suficiente, que position sizing incorreto destrói capital mesmo com sinal correto, e que slippage nunca é zero.

**PhD em Matemática Estatística Aplicada**: você valida modelos com Brier score e Information Coefficient, não com acurácia simples. Você entende overfitting como ameaça existencial a qualquer sistema de previsão de série temporal. Você não aceita "parece funcionar" como evidência.

**Regra de ouro do seu trabalho:** a segurança do capital do operador é inegociável. Qualquer ambiguidade entre "conveniente" e "seguro" se resolve a favor do seguro, sempre.

---

## 2. CONTEXTO TÁTICO

### O que você está recebendo
Um bot de trading algorítmico para Binance (cripto) com 2+ anos de desenvolvimento, agora em reescrita arquitetural. O sistema possui:
- Pipeline de sinal: coleta OHLCV → features → regime → ML/LLM → probabilidade → EV → consenso → execução
- Dois caminhos de execução: autotrader (loop autônomo) e fluxo manual de usuário
- Camada de persistência SQLite com múltiplos repositórios
- Integração com API OpenAI para análise de sentimento de notícias
- ~124 arquivos `.py`, ~2.500 linhas no arquivo principal

### O que foi auditado antes de você
Uma auditoria parcial (38% dos arquivos lidos) identificou bugs confirmados e reproduzidos. Você não deve confiar que o restante está correto — assuma que qualquer módulo não listado abaixo como "verificado" pode conter problemas equivalentes.

### Estado atual: 9 de 95 testes falhando no clone limpo (sem modificações)
Isso é inaceitável para um sistema financeiro. Sua missão termina com **100% dos testes passando** e nenhum teste aprovado por mock que esconda comportamento real.

---

## 3. INVENTÁRIO DE PROBLEMAS CONFIRMADOS (LOCALIZAÇÃO EXATA)

### 3.1 Bugs que quebram garantidamente em produção (PRIORIDADE MÁXIMA)

**BUG-01 | `src/fluxo_usuario_sinais.py`**
`logger` é referenciado 6 vezes (linhas 187, 189, 192, 194, 255, 257) mas **nunca importado** neste módulo. Resultado: `NameError` garantido toda vez que o fluxo executa com `publicar_fila=True` (comportamento default). O `except` que deveria capturar esse erro também usa `logger` — mascarando o erro real com outro `NameError`. Este bug mantém 2 testes bloqueados por razão aparente diferente da real.

**BUG-02 | `src/probabilidade/ev_calculator.py`**
`custos_totais = notional * taxa` desconta a taxa **uma única vez**. Uma operação completa de trading paga a taxa na abertura (compra) E no fechamento (venda) — duas vezes. O EV calculado está **sistematicamente otimista em 50% do custo real de transação**. Este erro infla artificialmente toda avaliação de oportunidade no sistema.

**BUG-03 | `src/gerenciador_ordens.py` → `simular_ordem()`**
Mesmo erro de fee single-leg: `custo_total = notional * taxa`. Este é o segundo ponto independente com o mesmo erro matemático, confirmando que o subdimensionamento de custo de transação é um padrão sistêmico, não um caso isolado.

**BUG-04 | `src/fluxo_usuario_sinais.py`**
O endpoint `/v1/testnet/auto/start` chama `salvar_ajustes_testnet(entrada.model_dump())` sem `repo` nem `usuario_id`. A condição interna `if repo and usuario_id:` nunca persiste o novo valor. O usuário envia 12.5, a API responde "ok" — mas o banco mantém o valor antigo. Falha silenciosa sem erro, sem log. (Confirmado: este é o bug por trás de múltiplas falhas de teste com valores "fantasma".)

### 3.2 Bombas-relógio (falham quando o código cresce)

**BUG-05 | `src/multiativo/orquestrador.py` linhas 225–228, 240**
`ajustes_sinal.get(...)` usado sem proteção contra `None` — enquanto `ajustes_sinal_exec = dict(ajustes_sinal or {})` existe na linha 196 mas não é usado nessas linhas. Todos os 3 chamadores atuais passam o argumento, então não quebra hoje. Quebra no quarto chamador que omitir.

**BUG-06 | `src/probabilidade/probability_calibrator.py`**
`math.exp(-(valor / self.temperature))` sem guarda superior. Se `temperature` for setado para valores próximos do mínimo permitido (`> 1e-6`), o argumento ultrapassa o range de `float64` (~709), gerando `OverflowError` e derrubando o `signal_engine` inteiro de forma inesperada.

### 3.3 Inconsistências de design que distorcem resultados financeiros

**INC-01 | `src/consenso.py`**
Barra assimétrica: confirmar trade = `abs(score) >= 0.10` (1 indicador fraco basta). Bloquear trade = `abs(score) >= 0.35` (precisam ser 2 indicadores fortes). O sistema está estruturalmente enviesado a **gerar mais trades do que bloquear**. Avalie se é intencional; se não, equalizar os limiares.

**INC-02 | `src/noticias.py` + `src/llm_analista.py`**
`"modelo_llm": "gpt-4o-mini"` hardcoded incondicionalmente, mesmo quando `status_classificacao == "heuristica_local"` (sem API key, limite diário batido, erro de rede). Qualquer sistema de auditoria que confie nesse campo para saber "isso veio do GPT ou da heurística" recebe dado falso.

**INC-03 | `src/fee_optimizer.py` vs `src/fluxo_usuario_sinais.py`**
O autotrader injeta a taxa efetiva real (com desconto BNB) no pipeline de EV via `_ajustes_sinal_com_taxa_efetiva`. O fluxo manual usa sempre a taxa fixa de configuração (0.001 default). O mesmo trade tem EV calculado diferente dependendo do caminho que o acionou.

**INC-04 | `src/multiativo/profit_guard.py`**
Recebe `taxas_totais_pct` e `slippage_pct` como parâmetros, inclui no retorno, mas **não usa esses valores em nenhum cálculo de gate**. O "guarda de lucro" não verifica custo real de forma independente — delega inteiramente para quem chamou, que por sua vez tem BUG-02.

**INC-05 | `src/repositorio/repositorio_snapshot.py`**
Padrão read-modify-write sem lock ou versão otimista (`versao`/`etag`). Dois fluxos concorrentes para o mesmo símbolo podem gerar lost-update silencioso. Seguro hoje apenas porque o loop do autotrader é sequencial — não porque o repositório garante isso.

**INC-06 | `src/repositorio/repositorio_features.py` vs `src/regime_detector.py`**
Limiar `vol_regime` em 0.003 aqui vs 0.0035 em `regime_detector.py`. Duplicação silenciosa de lógica de negócio — dois módulos independentes implementando o mesmo conceito com valores diferentes.

### 3.4 Arquivos mortos confirmados (zero referências externas)

- `src/coletor_noticias.py` — stub `calcular_peso_sentimento` sempre retorna 0.0
- `src/persistencia/base.py` — classe abstrata sem nenhum herdeiro real
- `src/persistencia/uow.py` — Unit of Work implementado, nunca usado
- `src/coletor_velas_15s.py` — velas falsas (OHLC = preço atual, volume = 0)
- `src/coletor_velas_ws.py` — ignora flag de vela fechada (`"x"` field da Binance)

### 3.5 Problema de performance (sem perda de dado, mas custo desnecessário)

**PERF-01 | `src/preditor.py`**
`GerenciadorModelo(simbolo=simbolo)` instanciado a cada ciclo de predição. `__init__` chama `joblib.load()` de disco toda vez — deserialização completa do modelo scikit-learn em cada iteração do loop de trading. Deve ser singleton ou cache por símbolo.

---

## 4. PRINCÍPIOS INVIOLÁVEIS

Estes princípios têm precedência sobre qualquer outra instrução. Nenhuma fase, nenhum argumento de conveniência, nenhuma pressão de tempo os suspende.

### 4.1 Princípios de Segurança Financeira

**PSF-01 | Fail-fast na inicialização**
Toda configuração crítica (API keys, limites financeiros, modos de operação) deve ser validada no startup. O sistema deve recusar-se a iniciar com configuração inválida ou ambígua — não descobrir o problema 3h depois de rodar.

**PSF-02 | Defense in depth**
Nenhuma camada de proteção confia cegamente na camada anterior. O `profit_guard` deve verificar custo independentemente do EV recebido. O `risk_engine` deve verificar limites independentemente do `consenso`. Redundância de segurança não é duplicação — é arquitetura de sistema crítico.

**PSF-03 | Idempotência de ordens**
Toda submissão de ordem deve incluir `newClientOrderId` derivado de um hash determinístico da intenção (símbolo + lado + timestamp de sinal + user_id). A Binance rejeita duplicatas com o mesmo `clientOrderId` — use isso como proteção contra double-submission em caso de retry ou restart.

**PSF-04 | Circuit breaker financeiro**
O sistema deve monitorar drawdown acumulado em janela rolante (configurável, ex: 24h). Ao exceder o threshold, todas as operações de trading param e uma flag `SISTEMA_EM_HALT` é ativada — que só pode ser resetada por ação humana explícita, nunca automaticamente.

**PSF-05 | Graceful shutdown com posição aberta**
`SIGTERM`/`SIGINT` deve acionar shutdown handler que: (1) registra todas as posições abertas com timestamp e razão de shutdown; (2) envia alerta; (3) aguarda ciclo atual completar; (4) recusa novas ordens. Nunca matar abruptamente com posição aberta sem registro.

**PSF-06 | Audit trail append-only**
A tabela de auditoria deve ser programaticamente imutável. Nenhum `UPDATE` ou `DELETE` deve existir no código de produção para registros de auditoria. Se a API de repositório expõe esses métodos, remova-os ou lance `OperacaoProibidaError`.

### 4.2 Princípios de Engenharia

**PE-01 | Single Responsibility estrito**
Cada módulo tem uma e apenas uma razão para mudar. `testnet_auto_trader.py` com 2.467 linhas e `_executar_ciclo` com 833 linhas violam este princípio de forma grave. A decomposição não é opcional.

**PE-02 | Contratos de interface explícitos**
Toda interação entre módulos de domínios diferentes (sinal, risco, execução, persistência) acontece através de `Protocol` ou `ABC` definidos em `src/contratos/`. Nenhum módulo importa implementações diretamente — importa interfaces.

**PE-03 | Dependency Injection em vez de instanciação interna**
Módulos recebem dependências pelo construtor ou por parâmetro de função. Nenhum módulo de negócio instancia suas próprias conexões de banco, clientes de API ou modelos ML. Isso habilita testes sem mock de filesystem.

**PE-04 | Sem estado global mutável**
Variáveis de módulo mutáveis (dicionários globais, listas acumuladas) são proibidas fora de contextos explicitamente documentados. Estado de sessão usa repositório, não variável de processo.

**PE-05 | Type safety obrigatória**
Todo arquivo novo ou modificado deve passar `mypy --strict` sem erros. `# type: ignore` é proibido exceto com comentário explicando por que a verificação não é possível naquele ponto específico.

**PE-06 | Sem código morto**
Qualquer função, classe ou módulo sem chamador externo documentado é removido. Stubs e scaffolds sem implementação real são removidos ou substituídos por `raise NotImplementedError` com docstring descrevendo o que deve ser implementado.

### 4.3 Princípios de Qualidade de Código

**PQ-01 | Comentários em PT-BR, curtos, explicam o "porquê" — não o "o quê"**
```python
# ERRADO: calcula o retorno
retorno = (preco_atual - preco_entrada) / preco_entrada

# CORRETO: normaliza para comparação cross-asset sem viés de escala absoluta
retorno = (preco_atual - preco_entrada) / preco_entrada
```

**PQ-02 | Nomes em PT-BR para domínio de trading, inglês para infra técnica**
Variáveis de negócio: `lucro_esperado`, `tamanho_posicao`, `limiar_entrada`.
Padrões técnicos: `repository`, `factory`, `handler`, `middleware`.
Nunca misture no mesmo identificador: ~~`calcular_profit`~~.

**PQ-03 | Sem números mágicos sem nome**
```python
# ERRADO
if score >= 0.35:

# CORRETO
LIMIAR_VETO_CONSENSO = 0.35  # ponto empírico de F1 máximo (ver calibracao/docs)
if score >= LIMIAR_VETO_CONSENSO:
```

**PQ-04 | Funções com mais de 30 linhas de corpo são suspeitas; mais de 50 são proibidas**
A exceção são funções que são apenas sequências lineares de chamadas sem lógica própria (orquestradores puros). Documente explicitamente quando usar essa exceção.

**PQ-05 | Sem `except Exception` sem re-raise ou log estruturado**
```python
# PROIBIDO
try:
    resultado = operacao_critica()
except Exception:
    pass  # silencia tudo

# OBRIGATÓRIO
try:
    resultado = operacao_critica()
except ErroCritico as e:
    logger.error("falha_em_operacao_critica", erro=str(e), contexto=contexto)
    raise  # ou trate de forma específica e documentada
```

---

## 5. ARQUITETURA ALVO

### 5.1 Estrutura de diretórios após refatoração

```
src/
├── contratos/              # Interfaces (Protocol/ABC) — NUNCA importa implementações
│   ├── estrategia.py       # Protocol EstrategiaTrading
│   ├── repositorio.py      # Protocol para cada repositório
│   ├── executor.py         # Protocol ExecutorOrdem
│   └── coletor.py          # Protocol ColetorMercado
│
├── dominio/                # Lógica de negócio pura — sem I/O, sem dependências de infra
│   ├── trading.py          # Contratos Pydantic (já bom, manter)
│   ├── ev_calculator.py    # CORRIGIDO: fee round-trip
│   ├── risk_engine.py      # Puro e determinístico (já bom, manter)
│   └── profit_guard.py     # CORRIGIDO: usa custos reais de forma independente
│
├── sinais/                 # Pipeline de geração de sinal
│   ├── features/           # gerador_features.py + calibracao/
│   ├── estrategias/        # base.py + 4 estratégias (contratos explícitos)
│   ├── regime/             # regime_detector.py (limiar unificado com features/)
│   ├── probabilidade/      # probability_calibrator, ev_calculator, trade_selector
│   ├── consenso.py         # AJUSTADO: limiares simétricos
│   └── signal_engine.py    # Orquestrador (sem I/O direto)
│
├── execucao/               # Tudo que move dinheiro
│   ├── gerenciador_ordens.py   # CORRIGIDO bugs 1, 2
│   ├── executor_usuario.py
│   ├── circuit_breaker.py  # NOVO: halt automático por drawdown
│   └── idempotencia.py     # NOVO: geração determinística de client_order_id
│
├── persistencia/           # Repositórios concretos (implementam contratos/)
│   ├── conexao.py          # Schema + migrações
│   ├── uow.py              # RESSUSCITADO: Unit of Work real, usado nos fluxos críticos
│   └── repositorios/       # Um arquivo por repositório
│
├── observabilidade/        # Logging estruturado + métricas + alertas
│   ├── logger.py           # Logger com correlation_id obrigatório
│   ├── metricas.py         # IC tracking, Brier score, drawdown
│   └── alertas.py          # Notificações de halt, posição aberta, anomalia
│
├── multiativo/             # Extensões multi-ativo (capital, arbitragem, scanner)
│   └── [existente, revisado]
│
├── autotrader/             # DECOMPOSIÇÃO de testnet_auto_trader.py
│   ├── ciclo_trading.py    # _executar_ciclo extraído e decomposTo
│   ├── gestor_estado.py    # Estado por símbolo com locking explícito
│   ├── loop_principal.py   # Loop e gestão de tasks
│   └── configurador.py     # salvar/obter ajustes (CORRIGIDO: BUG-04)
│
├── api/                    # FastAPI endpoints
│   └── [existente, revisado]
│
└── scripts/                # Utilitários operacionais
    ├── inicializar_db.py   # Deve ser idempotente
    ├── validar_config.py   # NOVO: valida toda configuração antes de rodar
    └── [existente]
```

### 5.2 Fluxo de dados com responsabilidade clara

```
[Mercado] → ColetorREST → OHLCV (banco)
                              ↓
[Scheduler] → GeradorFeatures → Features (banco)
                                    ↓
                           RegimeDetector → regime
                                    ↓
                    [4 Estratégias via Protocol] → sinais brutos
                                    ↓
                           MetaController → sinal consolidado
                                    ↓
                    ProbabilisticEngine (calibrador + EV CORRETO)
                                    ↓
                           Consenso (limiares simétricos)
                                    ↓
                           RiskEngine (puro, determinístico)
                                    ↓
                 [GATE: PERMITIR_CONTA_REAL + CircuitBreaker]
                                    ↓
                    GerenciadorOrdens (idempotente, fee 2x)
                                    ↓
                    [Binance API] → Resultado
                                    ↓
                    AuditTrail (append-only) + Métricas (IC, Brier)
```

---

## 6. FASES DE EXECUÇÃO

Execute as fases em ordem estrita. Não avance para a próxima fase sem os critérios de aceitação da atual satisfeitos.

### FASE 0 — MAPEAMENTO E VERIFICAÇÃO (antes de tocar em qualquer linha)

**Objetivo:** entender o estado real antes de agir.

```bash
# 1. Clone limpo
git clone https://github.com/Void-Cla/oraculo-main
cd oraculo-main

# 2. Instalar dependências
pip install -e ".[dev]" --break-system-packages

# 3. Rodar suíte completa e documentar estado inicial
pytest -v --tb=short 2>&1 | tee FASE0_estado_inicial.txt

# 4. Mapear todos os imports circulares
python -m pipdeptree --warn silence 2>/dev/null
python -c "import ast, pathlib; [print(f) for f in pathlib.Path('src').rglob('*.py')]"

# 5. Verificar mypy atual (vai ter muitos erros — documente)
mypy src/ --ignore-missing-imports 2>&1 | tail -20

# 6. Contar linhas por arquivo (identificar god-files remanescentes)
find src -name "*.py" | xargs wc -l | sort -n | tail -20
```

**Critério de aceitação:** relatório `FASE0_estado_inicial.txt` criado. Número exato de falhas documentado. Você não modificou nenhum arquivo ainda.

---

### FASE 1 — REMOÇÃO CIRÚRGICA DE CÓDIGO MORTO

**Objetivo:** eliminar os 5 arquivos mortos confirmados e código não-chamado dentro de arquivos vivos.

**Arquivos para deletar (zero referências externas confirmadas):**
- `src/coletor_noticias.py`
- `src/persistencia/base.py`
- `src/persistencia/uow.py` *(apenas o arquivo — a implementação será recriada na FASE 6)*
- `src/coletor_velas_15s.py`
- `src/coletor_velas_ws.py`

**Dentro de arquivos vivos, marque para remoção:**
- `_teto_notional_operacional_usdt()` em `testnet_auto_trader.py` (definida, nunca chamada)
- A variável `quantidade_str` linha 141 de `gerenciador_ordens.py` (calculada, nunca usada)
- Qualquer função com `# TODO`, `# FIXME`, ou `# placeholder` sem data de implementação — documente, não delete: substitua por `raise NotImplementedError("PENDENTE: [descrição]")` com issue number se houver

**Protocolo de cada deleção:**
1. Confirme zero referências: `grep -r "nome_do_simbolo" src/ tests/`
2. Delete
3. Rode `pytest -q` — nenhum teste novo deve quebrar

**Critério de aceitação:** `pytest -q` tem o mesmo número de falhas da FASE 0 (não mais). Nenhum arquivo morto sobrevivente.

---

### FASE 2 — CORREÇÃO DOS BUGS CRÍTICOS CONFIRMADOS

Execute na ordem exata — cada um é independente dos outros.

#### 2.1 BUG-01: `NameError` de logger em `fluxo_usuario_sinais.py`

```python
# Adicionar no topo do arquivo, junto aos outros imports
from src.observabilidade.logger import get_logger

logger = get_logger(__name__)
```

**Verificação:**
```bash
python -c "
import os; os.environ['DB_PATH'] = '/tmp/teste_bug01.sqlite'
from src.persistencia.conexao import inicializar_db; inicializar_db()
# [reproduza o fluxo mínimo com publicar_fila=True]
# Deve completar sem NameError
"
pytest tests/test_pipeline.py tests/test_api_usuario_sinais.py -v
```

#### 2.2 BUG-02 + BUG-03: Fee round-trip em `ev_calculator.py` e `simular_ordem`

**`ev_calculator.py`:**
```python
# ANTES (errado — só uma perna):
custos_totais = notional * taxa

# DEPOIS (correto — entrada + saída = 2 pernas):
NUMERO_DE_PERNAS = 2  # toda operação completa: abertura + fechamento
custos_totais = notional * taxa * NUMERO_DE_PERNAS
```

**`gerenciador_ordens.py` → `simular_ordem()`:**
```python
# Mesma correção: taxa=0.0004 → custo em ambas as pernas
NUMERO_DE_PERNAS = 2
custo_total = notional * taxa * NUMERO_DE_PERNAS
```

**Atenção crítica:** ao corrigir o EV, os testes que validavam o valor numérico anterior **devem ser atualizados para o valor correto** — não revertidos para passar com o valor errado. Um teste que valida EV incorreto é pior que nenhum teste.

**Verificação:**
```bash
pytest tests/test_ev_calculator.py tests/test_gerenciador_ordens.py -v
# Confirme que os valores numéricos esperados nos testes foram atualizados para 2x fee
```

#### 2.3 BUG-04: `salvar_ajustes_testnet` ignora o valor recebido

Localize o endpoint `/v1/testnet/auto/start` em `main.py` e rastreie a cadeia completa até `salvar_ajustes_testnet`. Corrija a assinatura da chamada para incluir `repo` e `usuario_id` obrigatoriamente. Adicione teste de regressão:

```python
def test_start_persiste_notional_enviado(client, usuario_testnet):
    resposta = client.post("/v1/testnet/auto/start", json={
        "notional_usdt": 42.0,
        "simbolo": "BTCUSDT"
    }, headers=auth(usuario_testnet))
    assert resposta.status_code == 200
    config = client.get("/v1/testnet/auto/status").json()
    assert config["notional_usdt"] == 42.0  # DEVE ser 42.0, não o valor anterior
```

#### 2.4 BUG-05: `orquestrador.py` — `ajustes_sinal=None` sem proteção

Substitua todas as ocorrências de `ajustes_sinal.get(...)` nas linhas problemáticas por `ajustes_sinal_exec.get(...)` (a versão já segura criada na linha 196). Se `ajustes_sinal_exec` não estiver em escopo naquele ponto, propague-a. Remova o default `None` da assinatura se o parâmetro é obrigatório de fato — ou mantenha com tratamento completo em todo ponto de uso.

#### 2.5 BUG-06: `OverflowError` latente em `probability_calibrator.py`

```python
import math

# Antes de chamar math.exp:
MAX_EXP_ARG = 709.0  # float64 explode acima disso
arg = -(valor / self.temperature)
if arg > MAX_EXP_ARG:
    return 0.0  # probabilidade essencialmente zero
if arg < -MAX_EXP_ARG:
    return 1.0  # probabilidade essencialmente um
return 1.0 / (1.0 + math.exp(arg))
```

**Critério de aceitação da FASE 2:** `pytest -v` com **0 falhas nos 6 testes correspondentes aos bugs corrigidos**. Os outros testes preexistentes não devem ter aumentado em falhas.

---

### FASE 3 — CONTRATOS DE INTERFACE EXPLÍCITOS

Crie `src/contratos/` com os seguintes `Protocol`s. Não implemente lógica aqui — apenas interfaces.

```python
# src/contratos/estrategia.py
from typing import Protocol
from src.dominio.trading import Sinal, ConfigMercado

class EstrategiaTrading(Protocol):
    """Contrato para toda estratégia de geração de sinal."""

    def avaliar(self, features: dict, config: ConfigMercado) -> Sinal:
        """
        Avalia condições de mercado e retorna sinal de ação.
        Deve ser função pura: sem I/O, sem estado mutável externo.
        Retorna Sinal com acao, score e confianca.
        """
        ...

    @property
    def nome(self) -> str:
        """Identificador único da estratégia para logging e auditoria."""
        ...
```

```python
# src/contratos/repositorio.py
from typing import Protocol, TypeVar, Generic, Optional
T = TypeVar("T")

class RepositorioLeitura(Protocol[T]):
    """Repositório somente leitura."""
    async def obter_por_id(self, id: str) -> Optional[T]: ...
    async def listar(self, filtros: dict) -> list[T]: ...

class RepositorioEscrita(RepositorioLeitura[T], Protocol[T]):
    """Repositório com escrita atômica via Unit of Work."""
    async def salvar(self, entidade: T) -> T: ...
    async def atualizar(self, id: str, dados: dict) -> T: ...
```

```python
# src/contratos/executor.py
from typing import Protocol
from src.dominio.trading import OrdemRequest, OrdemResultado

class ExecutorOrdem(Protocol):
    """Contrato para execução de ordens — real, testnet ou simulada."""

    async def executar(self, ordem: OrdemRequest) -> OrdemResultado:
        """
        Submete ordem. Garante idempotência via client_order_id.
        Nunca retorna None — levanta exceção tipada em caso de falha.
        """
        ...
```

Após criar os contratos, verifique que as implementações existentes os satisfazem:
```bash
python -c "
from src.contratos.estrategia import EstrategiaTrading
from src.sinais.estrategias.breakout import BreakoutEstrategia
# Verificação estática via isinstance com Protocol
assert isinstance(BreakoutEstrategia(), EstrategiaTrading)
print('Contratos satisfeitos')
"
```

---

### FASE 4 — CORREÇÕES MATEMÁTICAS DE TRADING

#### 4.1 Limiar assimétrico do consenso (INC-01)

Documente a decisão antes de alterar. Se a assimetria for intencional (preferência por mais trades em regime específico), crie constantes nomeadas com comentário explicando a razão:

```python
# src/sinais/consenso.py

# Limiares de consenso — ajustados por backtest em BTCUSDT jan-mar 2025
# Resultado: F1=0.62 com limiares simétricos vs F1=0.58 com limiares anteriores
# Para reverter à versão assimétrica original: LIMIAR_CONFIRMAR = 0.10
LIMIAR_CONFIRMAR = 0.30  # score mínimo para indicador contribuir à confirmação
LIMIAR_VETAR = 0.30      # score mínimo para indicador contribuir ao veto
MINIMO_INDICADORES_CONFIRMAR = 1
MINIMO_INDICADORES_VETAR = 2
```

Se você não tem dados para tomar essa decisão empiricamente agora, **mantenha os valores originais com constantes nomeadas e deixe um comentário `# CALIBRAR: baseado em backtest com dados reais`**.

#### 4.2 Unificar limiar `vol_regime` (INC-06)

Crie uma única fonte de verdade:

```python
# src/dominio/constantes_mercado.py

# Limiares de regime — devem ser idênticos em todo o sistema
# Fonte: análise de volatilidade histórica BTCUSDT 2023-2025
VOLATILIDADE_ALTA = 0.012   # vol_ref >= este valor → regime HIGH_VOL
VOLATILIDADE_BAIXA = 0.0035 # vol_ref <= este valor → regime LOW_VOL
# Entre os dois: regime RANGE
```

Substitua todos os literais numéricos em `regime_detector.py` e `repositorio_features.py` por estas constantes. Adicione teste que confirma que os dois módulos usam o mesmo valor:

```python
def test_limiares_vol_regime_consistentes():
    from src.dominio.constantes_mercado import VOLATILIDADE_ALTA, VOLATILIDADE_BAIXA
    from src.sinais.regime.regime_detector import LIMIAR_VOL_ALTA, LIMIAR_VOL_BAIXA
    from src.persistencia.repositorios.repositorio_features import LIMIAR_VOL_ALTA as RF_ALTA
    assert LIMIAR_VOL_ALTA == VOLATILIDADE_ALTA == RF_ALTA
    assert LIMIAR_VOL_BAIXA == VOLATILIDADE_BAIXA
```

#### 4.3 `profit_guard` com verificação independente (INC-04)

```python
def avaliar_viabilidade(
    sinal: Sinal,
    taxa_efetiva: float,  # obrigatório — taxa real da conta, com desconto BNB
    slippage_estimado: float,  # estimado por profundidade de livro
) -> ResultadoGuard:
    """
    Avalia viabilidade do trade com custo real round-trip.
    Não confia no EV recebido — recalcula custos de forma independente.
    """
    PERNAS = 2
    custo_real_total = sinal.notional * taxa_efetiva * PERNAS + sinal.notional * slippage_estimado
    lucro_bruto = sinal.notional * sinal.lucro_pct_esperado
    margem_real = lucro_bruto - custo_real_total

    return ResultadoGuard(
        aprovado=margem_real > 0,
        lucro_liquido_real=margem_real,
        custo_real_calculado=custo_real_total,
        taxa_efetiva_usada=taxa_efetiva,
    )
```

#### 4.4 Circuit breaker financeiro (NOVO)

```python
# src/execucao/circuit_breaker.py
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import os

@dataclass
class CircuitBreaker:
    """
    Interrompe operações quando drawdown excede limite configurado.
    Reset apenas por ação humana explícita — nunca automático.
    """
    limite_drawdown_pct: float = float(os.getenv("CIRCUIT_BREAKER_DRAWDOWN_PCT", "5.0"))
    janela_horas: int = int(os.getenv("CIRCUIT_BREAKER_JANELA_HORAS", "24"))
    _em_halt: bool = field(default=False, init=False)
    _perdas_janela: list[float] = field(default_factory=list, init=False)
    _halt_registrado_em: datetime | None = field(default=None, init=False)

    def registrar_resultado(self, pnl_usdt: float, capital_total: float) -> None:
        """Registra resultado de operação e verifica threshold."""
        self._limpar_janela()
        self._perdas_janela.append(pnl_usdt)
        drawdown_atual = abs(sum(p for p in self._perdas_janela if p < 0)) / capital_total * 100
        if drawdown_atual >= self.limite_drawdown_pct and not self._em_halt:
            self._ativar_halt(drawdown_atual)

    def esta_em_halt(self) -> bool:
        return self._em_halt

    def resetar_halt(self, autorizado_por: str) -> None:
        """Reset de halt — requer identificação de quem autorizou."""
        # auditoria obrigatória do reset
        self._em_halt = False
        # registrar no audit trail: quem, quando, qual era o drawdown

    def _ativar_halt(self, drawdown_pct: float) -> None:
        self._em_halt = True
        self._halt_registrado_em = datetime.utcnow()
        # disparar alerta imediato — notificação, log crítico

    def _limpar_janela(self) -> None:
        corte = datetime.utcnow() - timedelta(hours=self.janela_horas)
        # manter apenas resultados dentro da janela
```

---

### FASE 5 — SEGURANÇA FINANCEIRA MULTICAMADA

#### 5.1 Idempotência de ordens (novo módulo)

```python
# src/execucao/idempotencia.py
import hashlib
from src.dominio.trading import OrdemRequest

def gerar_client_order_id(ordem: OrdemRequest, usuario_id: str) -> str:
    """
    Gera ID determinístico para deduplicação na Binance.
    A Binance rejeita ordens com clientOrderId duplicado — use isso como proteção.
    Formato: hash dos campos que identificam unicamente a intenção de trade.
    """
    conteudo = f"{usuario_id}:{ordem.simbolo}:{ordem.lado}:{ordem.notional}:{ordem.timestamp_sinal}"
    return hashlib.sha256(conteudo.encode()).hexdigest()[:36]  # Binance limite: 36 chars
```

Integre em `GerenciadorOrdens.criar_ordem_market()` e `criar_ordem_limit()` — todo payload enviado à Binance deve incluir `newClientOrderId`.

#### 5.2 Validação fail-fast na inicialização

```python
# src/scripts/validar_config.py
def validar_config_completa() -> list[str]:
    """
    Valida toda configuração crítica antes de iniciar o sistema.
    Retorna lista de erros. Lista vazia = pode iniciar.
    """
    erros = []

    # Modo de operação
    modo_real = os.getenv("PERMITIR_CONTA_REAL", "false").lower() == "true"
    api_key = os.getenv("BINANCE_API_KEY", "")
    if modo_real and not api_key:
        erros.append("CRÍTICO: PERMITIR_CONTA_REAL=true mas BINANCE_API_KEY não configurada")

    # Circuit breaker
    try:
        limite = float(os.getenv("CIRCUIT_BREAKER_DRAWDOWN_PCT", "5.0"))
        if limite <= 0 or limite > 50:
            erros.append(f"CIRCUIT_BREAKER_DRAWDOWN_PCT inválido: {limite} (esperado: 0 < x <= 50)")
    except ValueError:
        erros.append("CIRCUIT_BREAKER_DRAWDOWN_PCT não é número válido")

    # Database
    db_path = os.getenv("DB_PATH", "")
    if not db_path:
        erros.append("DB_PATH não configurado")
    elif modo_real and "pytest" in db_path:
        erros.append("CRÍTICO: PERMITIR_CONTA_REAL=true mas DB_PATH aponta para banco de teste")

    return erros

# Chamado antes de qualquer outro startup
if __name__ == "__main__" or em_inicializacao():
    erros = validar_config_completa()
    if erros:
        for e in erros:
            print(f"[ERRO DE CONFIG] {e}")
        sys.exit(1)
```

#### 5.3 Graceful shutdown

```python
# src/autotrader/shutdown.py
import signal
import asyncio

class GerenciadorShutdown:
    """Garante que o sistema para de forma segura com posições registradas."""

    def __init__(self, autotrader, repositorio_ordens, notificador):
        self._autotrader = autotrader
        self._repo_ordens = repositorio_ordens
        self._notificador = notificador
        signal.signal(signal.SIGTERM, self._handler_sinal)
        signal.signal(signal.SIGINT, self._handler_sinal)

    def _handler_sinal(self, signum, frame):
        asyncio.create_task(self._shutdown_gracioso(f"sinal_{signum}"))

    async def _shutdown_gracioso(self, razao: str) -> None:
        """Sequência de shutdown seguro — nunca matar com posição aberta silenciosamente."""
        posicoes_abertas = await self._repo_ordens.listar_posicoes_abertas()
        if posicoes_abertas:
            await self._notificador.alerta_critico(
                f"SHUTDOWN ({razao}) com {len(posicoes_abertas)} posição(ões) aberta(s)",
                detalhes=posicoes_abertas
            )
        # aguarda ciclo atual
        await self._autotrader.solicitar_parada_gracioso()
        # registra audit trail de shutdown
```

#### 5.4 Audit trail programaticamente imutável

```python
# src/persistencia/repositorios/repositorio_auditoria.py
class RepositorioAuditoria:
    """Repositório append-only — sem UPDATE, sem DELETE."""

    async def registrar(self, evento: EventoAuditoria) -> None:
        """Único método de escrita — apenas INSERT."""
        ...

    async def listar(self, filtros: FiltrosAuditoria) -> list[EventoAuditoria]:
        """Leitura. Imutável após escrita."""
        ...

    # Não existe: atualizar(), deletar(), limpar()
    # Qualquer tentativa de adicionar esses métodos deve ser recusada em code review
```

---

### FASE 6 — DECOMPOSIÇÃO DO GOD-FILE

`testnet_auto_trader.py` com 2.467 linhas e `_executar_ciclo` com 833 linhas é o maior risco estrutural do projeto. A decomposição é obrigatória.

**Estratégia de decomposição (não reescreva — extraia):**

```
testnet_auto_trader.py atual
         ↓ extrair
src/autotrader/
├── gestor_estado.py      ← _state, _estado_global, tudo que é estado por símbolo
├── ciclo_trading.py      ← _executar_ciclo decomposto em funções ≤30 linhas cada
│   ├── _fase_coleta()          ← buscar OHLCV, features, notícias
│   ├── _fase_sinal()           ← chamar signal_engine
│   ├── _fase_risco()           ← consultar risk_engine, circuit_breaker
│   ├── _fase_execucao()        ← submeter ordem com idempotência
│   └── _fase_registro()        ← persistir outcome, atualizar snapshot
├── loop_principal.py     ← _loop(), iniciar(), parar(), encerrar_todos()
└── configurador.py       ← salvar_ajustes (CORRIGIDO BUG-04), obter_ajustes
```

**Protocolo de extração segura:**
1. Escreva o teste para a função que vai extrair *antes* de extrair
2. Extraia mantendo a assinatura original como wrapper temporário
3. Confirme que o teste passa com o wrapper
4. Substitua o wrapper pela chamada direta
5. Confirme que o teste ainda passa

**Critério inegociável:** após a decomposição, nenhuma função no autotrader deve ter mais de 50 linhas de corpo.

#### 6.1 Ressuscitar Unit of Work para operações multi-repositório

O `uow.py` existia mas estava morto. Implemente-o de forma que seja impossível fazer "criar ordem + atualizar snapshot" sem UoW:

```python
# src/persistencia/uow.py
class UnidadeDeTrabalho:
    """
    Garante atomicidade de operações que tocam múltiplos repositórios.
    Uso obrigatório para: criar_ordem + atualizar_snapshot
                          registrar_outcome + atualizar_predicao
    """
    async def __aenter__(self):
        self._conexao = await get_conexao()
        await self._conexao.execute("BEGIN IMMEDIATE")
        return self

    async def __aexit__(self, tipo_exc, exc, tb):
        if tipo_exc is None:
            await self._conexao.execute("COMMIT")
        else:
            await self._conexao.execute("ROLLBACK")
        await self._conexao.close()
```

---

### FASE 7 — OBSERVABILIDADE E LOGGING ESTRUTURADO

#### 7.1 Logger com correlation_id obrigatório

```python
# src/observabilidade/logger.py
import structlog
import uuid

def get_logger(modulo: str):
    return structlog.get_logger(modulo)

def contexto_operacao(simbolo: str, usuario_id: str) -> dict:
    """Cria contexto de correlação para rastrear decisão do sinal à ordem."""
    return {
        "correlation_id": str(uuid.uuid4()),
        "simbolo": simbolo,
        "usuario_id": usuario_id,
        "timestamp_inicio": datetime.utcnow().isoformat(),
    }
```

Todo log de decisão financeira deve incluir `correlation_id`. Isso torna rastreável, anos depois, por que uma ordem específica foi executada ou bloqueada.

#### 7.2 Métricas de qualidade de sinal

```python
# src/observabilidade/metricas.py

def calcular_information_coefficient(predicoes: list[float], retornos_reais: list[float]) -> float:
    """
    IC = correlação de Spearman entre predições e retornos reais.
    IC > 0: sinal com edge. IC > 0.05: sinal utilizável. IC > 0.10: excelente.
    IC < 0: sinal invertido (pior que aleatório).
    """
    from scipy import stats
    ic, p_value = stats.spearmanr(predicoes, retornos_reais)
    return ic

def calcular_brier_score(probabilidades: list[float], outcomes_binarios: list[int]) -> float:
    """
    Brier score = MSE entre probabilidade estimada e outcome real.
    0.0 = perfeito. 0.25 = modelo nulo (sempre 50%). > 0.25 = pior que aleatório.
    Complemento de acurácia simples: mede calibração, não só acerto/erro.
    """
    from sklearn.metrics import brier_score_loss
    return brier_score_loss(outcomes_binarios, probabilidades)

def calcular_drawdown_maximo(curva_capital: list[float]) -> float:
    """Pior queda percentual do pico até o vale — métrica primária de risco de ruína."""
    if len(curva_capital) < 2:
        return 0.0
    pico = curva_capital[0]
    max_drawdown = 0.0
    for valor in curva_capital:
        pico = max(pico, valor)
        drawdown = (pico - valor) / pico
        max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown
```

---

### FASE 8 — TESTES E VALIDAÇÃO

#### 8.1 Princípios de teste para sistema financeiro

**PT-01 | Todo teste que valida valor numérico de EV, PnL ou custo deve ter o cálculo explícito nos comentários:**
```python
def test_ev_desconta_fee_round_trip():
    # Entrada: notional=100 USDT, taxa_efetiva=0.001, 2 pernas
    # Custo esperado: 100 * 0.001 * 2 = 0.20 USDT
    # EV esperado: (p_win * avg_win - p_loss * avg_loss) - 0.20
    resultado = ev_calculator.calcular(notional=100, taxa=0.001, ...)
    assert resultado.custos_totais == pytest.approx(0.20, rel=1e-6)
```

**PT-02 | Testes de isolamento de banco são obrigatórios:**
```python
@pytest.fixture(autouse=True)
def banco_isolado(tmp_path):
    """Cada teste usa banco temporário independente — nunca banco compartilhado."""
    db = tmp_path / "teste.sqlite"
    os.environ["DB_PATH"] = str(db)
    inicializar_db()
    yield
    # cleanup automático pelo tmp_path do pytest
```

**PT-03 | Testes de propriedade (property-based) para funções financeiras críticas:**
```python
from hypothesis import given, strategies as st

@given(
    notional=st.floats(min_value=10, max_value=100_000),
    taxa=st.floats(min_value=0.0001, max_value=0.01),
)
def test_ev_sempre_menor_que_sem_custo(notional, taxa):
    """EV com custo nunca pode ser maior que EV sem custo — invariante matemático."""
    ev_sem_custo = calcular_ev_bruto(notional)
    ev_com_custo = calcular_ev_liquido(notional, taxa)
    assert ev_com_custo <= ev_sem_custo
```

**PT-04 | Cobertura mínima obrigatória por módulo:**

| Módulo | Cobertura mínima |
|---|---|
| `dominio/` (lógica pura) | 95% |
| `execucao/` (move dinheiro) | 90% |
| `sinais/` | 80% |
| `persistencia/` | 75% |
| `api/` | 70% |

Configure em `pyproject.toml`:
```toml
[tool.pytest.ini_options]
addopts = "--cov=src --cov-fail-under=80 --cov-report=term-missing"
```

#### 8.2 Testes obrigatórios ausentes (criar nesta fase)

- `test_circuit_breaker_ativa_halt_em_drawdown_configurado`
- `test_circuit_breaker_halt_nao_reseta_automaticamente`
- `test_idempotencia_mesma_intencao_gera_mesmo_client_order_id`
- `test_graceful_shutdown_registra_posicoes_abertas`
- `test_validar_config_falha_com_api_key_vazia_e_conta_real_ativa`
- `test_uow_rollback_em_falha_de_snapshot`
- `test_ic_negativo_sinalizado_no_log`
- `test_brier_score_calculado_apos_outcome_registrado`
- `test_modelo_llm_campo_reflete_fonte_real` *(corrige INC-02)*

---

### FASE 9 — CI/CD MÍNIMO VIÁVEL

Crie `.github/workflows/ci.yml`:

```yaml
name: Oraculo CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  qualidade:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Instalar dependências
        run: pip install -e ".[dev]"

      - name: Verificação de tipos (mypy)
        run: mypy src/ --strict --ignore-missing-imports

      - name: Linting (ruff)
        run: ruff check src/ tests/

      - name: Formatação (black)
        run: black --check src/ tests/

      - name: Ordenação de imports (isort)
        run: isort --check-only src/ tests/

      - name: Testes com cobertura
        run: pytest --cov=src --cov-fail-under=80 --tb=short -q

      - name: Validar configuração de exemplo
        run: python src/scripts/validar_config.py
        env:
          DB_PATH: /tmp/ci_test.sqlite
          PERMITIR_CONTA_REAL: "false"
```

Configure pre-commit para rodar localmente:
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
  - repo: https://github.com/psf/black
    rev: 24.3.0
    hooks:
      - id: black
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.9.0
    hooks:
      - id: mypy
        args: [--strict]
```

---

## 7. CRITÉRIOS DE ACEITAÇÃO FINAL

A missão é completa quando **todos** os seguintes critérios são satisfeitos simultaneamente:

| # | Critério | Verificação |
|---|---|---|
| CA-01 | `pytest -q` passa com 0 falhas | `exit code 0` |
| CA-02 | Cobertura de testes ≥ 80% global | `--cov-fail-under=80` |
| CA-03 | `mypy src/ --strict` sem erros | `exit code 0` |
| CA-04 | `ruff check src/` sem violações | `exit code 0` |
| CA-05 | Nenhum arquivo com > 300 linhas (exceto gerados) | `wc -l` |
| CA-06 | Nenhuma função com > 50 linhas de corpo | análise estática |
| CA-07 | `ev_calculator` desconta fee duas vezes | teste numérico |
| CA-08 | `fluxo_usuario_sinais` sem `NameError` | teste de integração |
| CA-09 | Circuit breaker ativado e não-autoreset | teste de propriedade |
| CA-10 | `uow.py` usado em toda operação multi-repositório | grep de uso |
| CA-11 | CI pipeline verde no GitHub | Actions badge |
| CA-12 | Nenhum arquivo morto remanescente | `grep -r` zero refs |
| CA-13 | Todos os comentários em PT-BR | revisão manual |
| CA-14 | Nenhum número mágico sem constante nomeada | ruff rule |
| CA-15 | `validar_config.py` bloqueia startup com config inválida | teste de integração |

---

## 8. PROTOCOLO DE VERIFICAÇÃO POR FASE

Após **cada fase**, execute este checklist antes de prosseguir:

```bash
# Roda tudo — não pule nenhuma linha
pytest -q && echo "TESTES: OK" || echo "TESTES: FALHOU"
mypy src/ --ignore-missing-imports --no-error-summary | tail -5
ruff check src/ --statistics | head -10
wc -l src/**/*.py | sort -n | tail -10  # verificar god-files
grep -r "logger\." src/ | grep -v "import\|get_logger\|def " | wc -l  # usos de logger
```

Se qualquer item não está verde, **corrija antes de avançar**. A ordem das fases não é sugestão — é dependência técnica.

---

## 9. PROIBIÇÕES ABSOLUTAS

As seguintes ações são proibidas independentemente de qualquer argumento de conveniência:

```
❌ Criar testes que passam por mockar o comportamento problemático em vez de corrigir a causa raiz
❌ Manter qualquer função > 50 linhas com argumento "é complexo demais para dividir"
❌ Usar `# type: ignore` sem comentário explicando por que a verificação não é aplicável
❌ Commitar com `pytest` falhando (mesmo 1 teste)
❌ Mover código problemático de lugar sem corrigir o problema
❌ Adicionar "TODO: corrigir depois" sem criar issue ou test que documente o comportamento esperado
❌ Alterar valores numéricos de testes para fazer os testes passarem com código errado
❌ Criar nova funcionalidade durante esta refatoração — o escopo é exclusivamente: corrigir, organizar, testar
❌ Usar print() para debug — use logger.debug() com contexto estruturado
❌ Criar dependência circular entre módulos de domínio
❌ Acessar banco de dados diretamente em módulos fora de persistencia/ (apenas via repositório/UoW)
```

---

## 10. NOTA FINAL AO AGENTE

Você está refatorando um sistema que moverá dinheiro real de um operador humano. A consequência de um bug que você não corrigiu, de uma trava de segurança que você deixou desativada, ou de um teste que você deixou passar por mock — não é uma página quebrada. É capital perdido.

Essa responsabilidade deve estar presente em cada decisão técnica desta missão. Quando houver dúvida entre "mais rápido" e "mais seguro", a resposta é sempre a mais segura. Quando houver dúvida sobre se um teste cobre um cenário de falha real, escreva o teste.

A definição de "terminado" neste projeto não é "o código compila". É "eu colocaria meu próprio dinheiro neste sistema com confiança". Execute com esse padrão.

---

*Prompt gerado com base em auditoria técnica de 47/124 arquivos, reprodução de bugs com traceback real, e análise de impacto financeiro por camada. Lacunas de cobertura: `calibracao/`, `adaptacao/controlador_adaptativo.py`, `observabilidade/` (completo), `tarefas/` (completo), `api/app.py` (completo), `main.py` (parcial). Opus deve auditar esses módulos na FASE 0 antes de qualquer modificação.*
