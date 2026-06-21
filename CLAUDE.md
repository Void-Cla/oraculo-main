# ORACULO — SISTEMA DE TRADING ALGORÍTMICO PARA BINANCE
> Sistema de orquestração multi-agente para Claude Code
> Leia `.claude/contexto.md` antes de qualquer ação — ele resume o estado atual e economiza tokens.

---

## PROTOCOLO DE INICIALIZAÇÃO OBRIGATÓRIO

```
1. Ler .claude/contexto.md (estado atual + mapa REAL×ALVO de caminhos)
2. Ler .claude/skill.md (lições, atalhos e armadilhas já aprendidas)
3. Ler .claude/00_orquestrador.md (quem você é)
4. Identificar o tipo de tarefa recebida
5. Delegar ao agente especialista correto
6. Acionar o guardião ANTES de qualquer mudança em código que move/avalia dinheiro
   (hoje: src/executor/, src/risco/, src/probabilidade/ev_calculator.py,
    src/multiativo/profit_guard.py, src/servicos/testnet_auto_trader.py, src/main.py)
7. Acionar o revisor APÓS cada mudança significativa
```

> ⚠️ Os agentes vivem em `.claude/*.md` (raiz), NÃO em `.claude/agentes/`.
> ⚠️ A "Estrutura de Diretórios Alvo" abaixo é a META (Fase 6), não a realidade de hoje.
> Para os caminhos REAIS de cada arquivo, consulte a tabela REAL×ALVO em `.claude/contexto.md`.

**NUNCA** comece a modificar código sem ler `contexto.md` primeiro.
**NUNCA** altere arquivos de execução financeira sem aprovação explícita do Guardião.
**NUNCA** marque uma fase como concluída sem o Revisor ter atualizado `contexto.md`.

---

## DIRETRIZ DE OPERAÇÃO — TRADUTOR E OTIMIZADOR INTERNO (sempre ativa)

Antes de responder a QUALQUER comando — especialmente os simples, pobres ou diretos
("pode continuar", "me explica", "testei X e deu erro") — **remasterize a intenção
internamente e de forma invisível** (não devolva o prompt reescrito; entregue o resultado):

1. **Padrão mental:** interprete o comando como se escrito pelo maior gênio visionário
   da história (QI 900), com domínio absoluto de todas as engenharias e arquiteturas relevantes.
2. **Padrão de execução:** opere (você e os agentes) no mais alto nível — **segurança
   nível militar (AA+)**, excelência semântica, fluxo lógico impecável e **arquitetura
   estritamente separada por responsabilidades**.
3. **Abordagem:** equipe de especialistas de elite (QI 600 cada), sempre pensando fora da caixa.
4. **Disciplina honesta (precede tudo):** alto nível ≠ over-engineering. Segurança de capital
   e verdade técnica vêm antes de agradar. Não simetrizar/alterar risco sem dado; não adicionar
   complexidade especulativa. Na dúvida entre conveniente e seguro → seguro.

> Esta diretriz é permanente e vale para todas as sessões. Resumo operacional em `.claude/skill.md`.

---

## PROJETO

**Nome:** Oraculo Trading Bot
**Stack:** Python 3.11+, FastAPI, SQLite (WAL), scikit-learn, Binance API, OpenAI API
**Ambiente:** venv em `.venv/` (Python 3.14). Deps em `requirements.txt`; `pip install -e ".[dev]"` para ferramentas de qualidade (extras `dev` definidos em `pyproject.toml`).
**Banco:** `$DB_PATH` (env var) — default `.env`: `./dados/oraculo.sqlite`. Nunca hardcode de path.
**Testes:** `pytest -q` — meta: 0 falhas. **Baseline atual: 82 passou / 10 falhou** (ver contexto.md).
**Tipos:** `mypy src/ --strict` — meta; mypy ainda não instalado (Fase 9).
**Lint:** `ruff check src/` + `black src/` + `isort src/` — meta; ainda não instalados (Fase 9).

### Estrutura de Diretórios Alvo

```
src/
├── contratos/          # Protocol/ABC — interfaces sem implementação
├── dominio/            # Lógica de negócio pura (sem I/O)
├── sinais/             # Pipeline: features → regime → estratégias → consenso → EV
│   ├── estrategias/    # 4 estratégias + base (Protocol)
│   ├── probabilidade/  # calibrador, ev_calculator, trade_selector
│   └── regime/         # regime_detector
├── execucao/           # Tudo que move dinheiro
│   ├── circuit_breaker.py
│   ├── idempotencia.py
│   └── gerenciador_ordens.py
├── persistencia/       # Repositórios concretos + UoW
│   ├── uow.py          # Unit of Work (DEVE estar ativo)
│   └── repositorios/
├── autotrader/         # Decomposição de testnet_auto_trader.py
│   ├── ciclo_trading.py
│   ├── gestor_estado.py
│   ├── loop_principal.py
│   └── configurador.py
├── observabilidade/    # Logger estruturado, IC, Brier, drawdown
├── multiativo/         # Capital, arbitragem, scanner, orquestrador
└── api/                # FastAPI endpoints

.claude/
├── contexto.md         # Estado vivo + mapa REAL×ALVO — atualizado pelo Revisor
├── skill.md            # Lições, atalhos e armadilhas do projeto (carregar com contexto.md)
├── 00_orquestrador.md  # ORQ
├── 01_revisor.md       # REV
├── 02_guardiao.md      # GRD
├── 03_sinais.md        # SIN
├── 04_quant.md         # QNT
├── 05_execucao.md      # EXE
├── 06_persistencia.md  # PER
├── 07_testes.md        # TST
├── 08_refatoracao.md   # REF
└── 09_observabilidade.md # OBS
```
> Os arquivos de agente ficam na RAIZ de `.claude/`, não numa subpasta `agentes/`.

---

## TIME DE AGENTES

| ID | Arquivo | Função | Aciona quando |
|----|---------|--------|---------------|
| `ORQ` | `00_orquestrador.md` | Coordena todos os agentes | Sempre — ponto de entrada |
| `REV` | `01_revisor.md` | Revisa e atualiza contexto.md | Após cada mudança significativa |
| `GRD` | `02_guardiao.md` | Segurança financeira e veto | Antes de qualquer mudança em execucao/ ou dominio/ |
| `SIN` | `03_sinais.md` | Pipeline de geração de sinal | Tarefas em sinais/, regime, features |
| `QNT` | `04_quant.md` | Matemática financeira e EV | Cálculos de fee, EV, Kelly, IC, Brier |
| `EXE` | `05_execucao.md` | Execução de ordens e segurança | Tarefas em execucao/, circuit breaker |
| `PER` | `06_persistencia.md` | Banco de dados e UoW | Tarefas em persistencia/, migrações |
| `TST` | `07_testes.md` | Testes e cobertura | Toda mudança que requer teste |
| `REF` | `08_refatoracao.md` | Decomposição e clean code | God-files, SOLID, extração de função |
| `OBS` | `09_observabilidade.md` | Logging e métricas de qualidade | Logging, IC, Brier, drawdown, alertas |

---

## REGRAS GLOBAIS (valem para TODOS os agentes)

### Código
- Comentários e docstrings **exclusivamente em PT-BR**
- Nomes de domínio em PT-BR (`lucro_esperado`, `tamanho_posicao`)
- Nomes de padrões técnicos em inglês (`repository`, `handler`, `factory`)
- Funções com **> 30 linhas de corpo são suspeitas**; **> 50 linhas são proibidas**
- **Sem números mágicos** — toda constante tem nome e comentário de origem
- **Sem `except Exception` silencioso** — sempre log estruturado + re-raise ou tratamento explícito
- **Sem `# type: ignore`** sem comentário explicando a exceção
- `mypy --strict` deve passar após cada mudança

### Financeiro
- **Fee sempre em round-trip (2 pernas)**: `custo = notional * taxa * 2`
- **Circuit breaker** deve estar ativo em toda execução real
- **Client order ID idempotente** em toda ordem submetida à Binance
- **Nenhum UPDATE/DELETE** em tabelas de auditoria
- **PERMITIR_CONTA_REAL** verificado em pelo menos 4 pontos independentes

### Qualidade
- `pytest -q` com **0 falhas** após cada mudança — sem exceção
- Cobertura mínima: dominio/ ≥95%, execucao/ ≥90%, global ≥80%
- **Sem código morto** — arquivos sem caller externo são removidos ou marcados `NotImplementedError`
- **Sem estado global mutável** fora de contextos explicitamente documentados

---

## FASES DO PROJETO

> Consulte `.claude/contexto.md` para o estado atual de cada fase.

| Fase | Nome | Critério de conclusão |
|------|------|----------------------|
| 0 | Mapeamento | `FASE0_estado_inicial.txt` criado, 0 modificações |
| 1 | Remoção de código morto | 5 arquivos mortos deletados, pytest igual ao inicial |
| 2 | Bugs críticos | 0 falhas nos 6 bugs confirmados |
| 3 | Contratos de interface | `src/contratos/` criado, Protocol para cada domínio |
| 4 | Correções matemáticas | Fee round-trip, limiares simétricos, UoW ativo |
| 5 | Segurança financeira | Circuit breaker, idempotência, graceful shutdown, fail-fast |
| 6 | Decomposição god-file | testnet_auto_trader.py → 4 módulos, 0 função > 50 linhas |
| 7 | Observabilidade | IC, Brier score, correlation_id em todo log financeiro |
| 8 | Testes | 0 falhas, ≥80% cobertura, testes de propriedade nos críticos |
| 9 | CI/CD | `.github/workflows/ci.yml` verde, pre-commit configurado |

---

## COMANDOS RÁPIDOS

```bash
# Verificar estado atual
pytest -q && mypy src/ --ignore-missing-imports --no-error-summary | tail -3

# Rodar fase específica de verificação
pytest tests/test_ev_calculator.py tests/test_gerenciador_ordens.py -v

# Verificar god-files (Git Bash)
find src -name '*.py' -exec wc -l {} + | sort -rn | head -10

# Confirmar código morto — POR IMPORT, nunca por substring (ver DA-07 no contexto.md)
# Um módulo só é "morto" se nenhum outro arquivo o importa.
python -c "
import pathlib, re
arquivos = list(pathlib.Path('src').rglob('*.py'))
mortos = []
for f in arquivos:
    mod = f.stem
    if mod == '__init__': continue
    padrao = re.compile(rf'(from\s+[\w.]*\b{mod}\b\s+import|import\s+[\w.]*\b{mod}\b)')
    usado = any(padrao.search(g.read_text(encoding='utf-8')) for g in arquivos if g != f)
    if not usado: mortos.append(str(f))
print(chr(10).join(mortos) or 'nenhum modulo orfao por import')
"
```

---

## CONTATO DE EMERGÊNCIA

Se qualquer verificação abaixo falhar, **pare tudo e chame o Guardião:**

```python
# Verificação de segurança financeira mínima (caminhos REAIS de hoje)
from pathlib import Path

# Fee round-trip no cálculo de EV (Fase 4): hoje o custo é aplicado 1× — BUG-02 em aberto.
ev = Path("src/probabilidade/ev_calculator.py").read_text(encoding="utf-8")
assert "* 2" in ev or "NUMERO_DE_PERNAS = 2" in ev, "BUG-02 EM ABERTO: fee single-leg em ev_calculator.py"

# Circuit breaker (Fase 5): criado em src/executor/ (mesmo pacote de execução real).
assert Path("src/executor/circuit_breaker.py").exists(), "FALTA: circuit_breaker.py (Fase 5)"
assert Path("src/executor/idempotencia.py").exists(), "FALTA: idempotencia.py (Fase 5)"

# Gate de conta real presente na API
assert "PERMITIR_CONTA_REAL" in Path("src/main.py").read_text(encoding="utf-8"), "GATE de conta real ausente em main.py"
```

> Estas asserções descrevem o ESTADO-ALVO de segurança. Hoje BUG-02 e o circuit breaker
> ainda estão em aberto — elas falharão de propósito até as Fases 4 e 5 serem concluídas.
