# 🎯 ROADMAP DE REFATORAÇÃO — ORÁCULO TRADING BOT
## Auditoria Extrema Padrão AA+ Militar · Engenharia Quantitativa de HFT

> **Classificação:** MISSÃO CRÍTICA — CAPITAL EM JOGO  
> **Metodologia:** Pente-fino cirúrgico sobre `contexto.md` + `mapa.md` + `botai.md`  
> **Veredito herdado:** *Sem edge líquido nos dados atuais* (gate de conta real fechado por desenho — DA-19). **A lucratividade NÃO é problema de código; é problema de sinal/edge.** O código é estruturalmente seguro. A missão agora é: blindar contra regressão, decompor dívida técnica, e injetar a camada agêntica Gemini como **filtro de assimetria pré-execução** + **auditor pós-mortem**.

---

## 🩸 DIAGNÓSTICO ESTRATÉGICO INICIAL

O Oráculo é um **monólito modular assíncrono** (FastAPI + asyncio single-process) com persistência SQLite local, **stateful em memória de processo**, sem escala horizontal, sem failover, sem replicação. A tolerância a falhas é **intra-processo** (retry, breaker, halt persistido), não **inter-nó**. Para trading spot algorítmico em escala atual, isto é **aceitável**; para HFT real ou multi-conta, é **insuficiente**.

A suíte de 186 testes está verde, mas:
- **Cobertura não medida** (pytest-cov não instalado)
- **Mypy strict não medido** (mypy não instalado)
- **Ruff violations não medidos**
- **God-file `testnet_auto_trader.py` = 2371 LOC** com método `_executar_ciclo` de **833 LOC** (complexidade ciclomática catastrófica)
- **UoW implementado mas MORTO** (DA-04 pendente) — execução + persistência **não são atômicas**

A auditoria abaixo prioriza por **severidade financeira** (risco de ruína > risco de latência > risco de código sujo).

---

# 🩸 FASE 1 — TRIAGE CRÍTICA (O QUE VAI QUEBRAR O BOT HOJE)

## 1.1 🔴 FALHAS CRÍTICAS DE NEGOCIAÇÃO E LÓGICA FINANCEIRA

### CRIT-FIN-01: Não-Atomicidade Execução ↔ Persistência (UoW Desativado)
**Localização:** `src/persistencia/uow.py` (implementado, 0 callers) + `src/servicos/testnet_auto_trader.py` (pontos de submit L~2266/2277/2332/2382)  
**Severidade:** CATASTRÓFICA (risco de ruína por estado inconsistente)  
**Sintoma:** Se o processo crashear **entre** `gerenciador_ordens.criar_ordem_market()` (ordem FILLED na Binance) e `_persistir_ordem_executada()` (gravação em `ordens`), o bot:
1. Perde o registro da posição aberta
2. Reinicia sem saber que tem capital comprometido
3. Pode abrir posição duplicada (viola `limite_trades_abertos`)
4. `_sincronizar_ciclo` (rede de reconciliação) pode não capturar se o `ciclo_ativo` foi mutado antes do crash

**Vetor de falha real:** O `clientOrderId` determinístico (DA-05) protege contra double-submit, mas **NÃO** contra estado fantasma pós-crash. A reconciliação é *reativa* (rede), não *proativa* (transação).

**Fix cirúrgico:**
```python
# Ativar UoW envolvendo o bloco crítico:
async with UnitOfWork() as uow:
    resultado_ordem = await ger.criar_ordem_market(...)  # Binance
    await uow.repositorio_ordens.registrar(resultado_ordem)  # DB
    await uow.repositorio_snapshot.atualizar(ciclo_ativo)  # DB
    # COMMIT atômico — se falhar, a ordem JÁ foi para Binance,
    # mas o snapshot de reconciliação no próximo boot detecta a divergência
```

**Trade-off honesto:** A Binance é a **fonte da verdade** financeira. O UoW não garante atomicidade cross-system (Binance + SQLite); garante apenas que o **estado local** é internamente consistente. A reconciliação no boot (`_sincronizar_ciclo` via `get_account`) é a **verdadeira rede de segurança**.

---

### CRIT-FIN-02: Posição-Fantasma Residual (FLX-01 — Mitigado, Não Eliminado)
**Localização:** `src/servicos/testnet_auto_trader.py::_ordem_foi_preenchida`  
**Severidade:** ALTA (já corrigida na fonte, mas janela residual)  
**Estado:** FLX-01 corrigido — `_ordem_foi_preenchida()` guarda as **duas pernas** antes de mutar o ciclo. Mas a **reconciliação assume fill atrasado**, o que significa: se a Binance demorar >1 ciclo para reportar o fill, o bot pode **reabrir posição** no mesmo símbolo.

**Fix complementar:** Implementar **idempotência por símbolo** no autotrader:
```python
# Antes de _abrir_ciclo:
if await repo_ordens.existe_ordem_aberta_para_simbolo(simbolo, janela_segundos=300):
    log.warn("Símbolo com ordem recente submetida — aguardando confirmação")
    return "AGUARDANDO_FILL"
```

---

### CRIT-FIN-03: Idempotência Degrada sem `chave_intencao` Estável
**Localização:** `src/executor/idempotencia.py`  
**Severidade:** ALTA (double-submit em retry跨-janela)  
**Sintoma:** Quando `chave_intencao` é omitida, usa `int(time.time())` (segundo atual). Idempotência só vale para retries **no mesmo segundo**. Se o loop falhar e retomar no segundo seguinte, uma nova ordem é submetida para a mesma intenção.

**Fix:** Tornar `chave_intencao` **obrigatória** no autotrader, passando o `ts_sinal` (timestamp do sinal que gerou a decisão):
```python
client_order_id = gerar_client_order_id(
    usuario=usuario_id,
    simbolo=simbolo,
    lado="BUY",
    notional=notional,
    chave_intencao=str(ts_sinal_gerador)  # ESTÁVEL跨-retries
)
```

---

### CRIT-FIN-04: Floating-Point Error em Frações de Cripto
**Localização:** `src/executor/gerenciador_ordens.py` (ajuste `LOT_SIZE`)  
**Severidade:** MÉDIA-ALTA (rejeição de ordem → oportunidade perdida)  
**Estado:** Já usa `Decimal`/`ROUND_DOWN` para `LOT_SIZE` (step_size, min_qty). Mas o `notional` calculado no `risk_engine` usa `float` antes de chegar ao `gerenciador_ordens`. Se `notional = 15.000000001` e `MIN_NOTIONAL = 15.0`, a ordem é rejeitada.

**Fix:** Migrar **todo o pipeline de sizing** para `Decimal`:
```python
from decimal import Decimal, ROUND_DOWN, getcontext
getcontext().prec = 28  # Precisão bancária

# risk_engine:
notional = (Decimal(str(capital_risco)) / Decimal(str(stop_pct))).quantize(
    Decimal('0.00000001'), rounding=ROUND_DOWN
)
```

---

### CRIT-FIN-05: Slippage Assumido (Não Medido)
**Localização:** `src/probabilidade/ev_calculator.py` + `src/risco/filtro_ev.py`  
**Severidade:** MÉDIA (EV inflado se slippage real > assumido)  
**Estado:** Slippage é **parâmetro de config** (`slippage_decimal`), aplicado round-trip (DA-02, INC-07). Mas **não é medido empiricamente**. Se o slippage real em mercado volátil for 0.002 e o config assume 0.0005, o EV calculado é **4× mais otimista** que o real.

**Fix:** Implementar **slippage realizado** no `_registrar_fechamento_ciclo`:
```python
slippage_realizado = (preco_execucao_real - preco_sinal) / preco_sinal
await repo.metricas_slippado.registrar(simbolo, slippage_realizado, horizonte)
# Alimentar de volta no EVCalculator como prior dinâmica (EWMA)
```

---

### CRIT-FIN-06: Dessincronização de WebSocket (Não Aplicável Hoje, mas Risco Futuro)
**Estado atual:** O bot usa **REST polling** (`binance_api/cliente.py`), não WebSocket contínuo. Os coletores WS (`coletor_velas_ws.py`, `coletor_velas_15s.py`) foram **REMOVIDOS** (F1 — eram stubs com bug da flag `"x"`).  
**Risco:** Se WebSocket for reintroduzido para baixar latência, a dessincronização (gap detection, reconnection, gap fill) é **vetor crítico**. Hoje, o REST com `wait_for(timeout=12s)` + re-sync de timestamp (`-1021`) é **robusto mas lento**.

**Recomendação:** Manter REST até que a latência de polling se torne o gargalo de edge. Se migrar para WS, implementar:
1. Heartbeat watchdog (reconnect se sem mensagem >3× intervalo esperado)
2. Gap fill via REST após reconnect
3. Snapshot diffing (seq_num) para detectar perda de mensagem

---

## 1.2 🔴 ESTABILIDADE E TOLERÂNCIA A FALHAS

### CRIT-FT-01: `scikit-learn` `fit`/`predict` Inline no Event-Loop (Head-of-Line Blocking)
**Localização:** `src/modelagem/{preditor,gerenciador_modelo,treinador_online,treinador_batch}.py`  
**Severidade:** ALTA (latência de toda a API acoplada ao pior ciclo de ML)  
**Sintoma:** `HistGradientBoostingRegressor.fit()` em dataset de 10k amostras pode levar 200-800ms. Durante esse tempo, **todas as requisições da API** (health, status, trading manual) ficam **bloqueadas**. Em HFT, isto é **morte**.

**Fix arquitetural:**
```python
# Mover ML para ProcessPoolExecutor (não ThreadPool — GIL):
import concurrent.futures
_ml_executor = concurrent.futures.ProcessPoolExecutor(max_workers=2, mp_context=mp.get_context("spawn"))

async def prever_async(features):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_ml_executor, _prever_sync, features)

# Treino batch em processo separado (cron noturno, não no loop)
```

**Trade-off:** `ProcessPoolExecutor` tem overhead de serialização (pickle) — usar `shared_memory` para arrays grandes, ou persistir modelo em `joblib` e recarregar no worker.

---

### CRIT-FT-02: Dois Circuit Breakers (Segunda-Verdade Potencial)
**Localização:** `src/executor/circuit_breaker.py` (dormente) + halt inline no autotrader (ativo)  
**Severidade:** MÉDIA-ALTA (comportamento não-determinístico se ambos forem ativados)  
**Estado:** DA-16 decidiu NÃO wirear `circuit_breaker.py` para evitar redundância. Mas o código existe, testado, **pronto para ser ativado por engano** em uma refatoração descuidada.

**Fix:** **Deletar** `circuit_breaker.py` OU consolidar em uma única camada canônica:
```python
# Opção A (recomendada): Deletar o dormente
# rm src/executor/circuit_breaker.py
# Atualizar testes e imports

# Opção B: Consolidar — circuit_breaker.py vira o ÚNICO breaker,
# o inline é removido e o breaker é wireado no loop
```

**Parecer:** Opção A. O halt inline (perda diária USDT + `retomada_operacoes_bloqueadas` persistido) já é canônico, durável, e reset-humano (DA-03, DA-16, DA-17). Manter código dormente de segurança é **dívida técnica perigosa**.

---

### CRIT-FT-03: Sem Handlers SIGTERM/SIGINT Dedicados
**Localização:** `src/main.py::lifespan`  
**Severidade:** MÉDIA (perda de estado em deploy/restart de container)  
**Sintoma:** O `finally` do lifespan cancela tarefas via `.cancel()` + `asyncio.gather(..., return_exceptions=True)`, mas **não captura SIGTERM/SIGINT explicitamente**. Em container (Docker/k8s), o SIGTERM tem grace period de 10-30s antes do SIGKILL. Se o bot estiver no meio de um `_executar_ciclo`, a ordem pode ser submetida mas não persistida.

**Fix:**
```python
import signal
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    # ... bootstrap ...
    shutdown_event = asyncio.Event()
    
    def _signal_handler(signum, frame):
        log.warn(f"Sinal {signum} recebido — iniciando shutdown gracioso")
        shutdown_event.set()
    
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    
    # Tarefas em background checam shutdown_event
    app.state.shutdown_event = shutdown_event
    
    try:
        yield
    finally:
        shutdown_event.set()
        # Grace period de 15s para ciclo atual terminar
        await asyncio.wait_for(
            asyncio.gather(*app.state.tasks, return_exceptions=True),
            timeout=15.0
        )
```

---

### CRIT-FT-04: Race Condition em `snapshot_estado` (INC-05 — Mitigado)
**Localização:** `src/persistencia/repositorio_snapshot.py::atualizar`  
**Estado:** Corrigido — `BEGIN IMMEDIATE` + coluna `versao` (RMW atômico).  
**Risco residual:** `BEGIN IMMEDIATE` adquire write-lock imediatamente. Sob contenção (loop + API + consumidor + coletor), pode gerar `database is locked` se `busy_timeout=5000` não for suficiente. Em WAL, leitores não bloqueiam, mas escritores sim.

**Fix complementar:** Implementar **queue de escrita** serializada:
```python
_write_lock = asyncio.Lock()

async def atualizar_snapshot(estado):
    async with _write_lock:  # Serializa escritas no processo
        await repo.atualizar(estado)
```

---

### CRIT-FT-05: Vazamento de Memória em Loops Contínuos
**Localização:** `src/servicos/testnet_auto_trader.py` (historicos)  
**Estado:** **Controlado** — `historico_ciclos`≤20, `historico_execucoes_ts`≤50. Caches de modelo invalidam por `mtime` (PERF-01).  
**Risco residual:** `_SESSOES` e `_CREDENCIAIS` dicts globais crescem se `_limpar_expiradas_sem_lock` falhar silenciosamente. Em runs de 7+ dias, isso pode acumular.

**Fix:** Adicionar **cap duro** + métrica:
```python
_MAX_SESSOES = 1000

def _limpar_expiradas_sem_lock():
    # ... lógica existente ...
    if len(_SESSOES) > _MAX_SESSOES:
        # Evict por LRU (último acesso)
        sorted_sessions = sorted(_SESSOES.items(), key=lambda x: x[1].ultimo_acesso)
        for sid, _ in sorted_sessions[:len(_SESSOES) - _MAX_SESSOES]:
            del _SESSOES[sid]
        log.warn(f"Session store excedeu {_MAX_SESSOES} — evict LRU executado")
```

---

### CRIT-FT-06: Rate Limit da Binance (Parcialmente Mitigado)
**Localização:** `src/binance_api/cliente.py`  
**Estado:** Retry com backoff exponencial (`2^(n-1)` capado em 8s), timeout 12s, re-sync de timestamp. Rotação opcional de chaves (`BINANCE_API_KEYS` CSV).  
**Lacuna:** **Não há contador proativo de rate limit**. A Binance retorna headers `X-MBX-USED-WEIGHT-*` que indicam consumo. O bot reage (via retry) mas **não previne**.

**Fix:**
```python
# Parser de headers de rate limit
def _extrair_weight_usado(response):
    used = response.headers.get("X-MBX-USED-WEIGHT-1M")
    return int(used) if used else None

# Throttle proativo
if used_weight > 1000:  # Binance default: 1200/min
    await asyncio.sleep(60 * (used_weight / 1200))  # Proporcional
```

---

## 1.3 🔴 SEGURANÇA (NÍVEL MILITAR)

### CRIT-SEC-01: `joblib.load` = Unpickle = RCE (Remote Code Execution)
**Localização:** `src/modelagem/{preditor,gerenciador_modelo}.py`  
**Severidade:** CATASTRÓFICA (execução de código arbitrário)  
**Vetor:** Se `MODEL_DIR` for adulterado (path traversal, supply chain, insider), um `modelo_batch.joblib` malicioso executa código Python arbitrário no processo do bot — **acesso total a chaves de API, saldo, ordens**.

**Fix em camadas:**
1. **Assinatura HMAC-SHA256** do arquivo de modelo:
```python
import hmac, hashlib

def _verificar_assinatura(caminho_modelo, chave_hmac):
    with open(caminho_modelo, "rb") as f:
        dados = f.read()
    assinatura_esperada = hmac.new(chave_hmac, dados, hashlib.sha256).hexdigest()
    assinatura_arquivo = Path(f"{caminho_modelo}.sig").read_text().strip()
    if not hmac.compare_digest(assinatura_esperada, assinatura_arquivo):
        raise SecurityError("Assinatura do modelo inválida — abortando load")
```

2. **Sandbox de load** (processo separado com `seccomp`/`AppArmor`):
```python
# Em produção, o load de modelo roda em subprocess com capabilities reduzidas
# (sem network, filesystem read-only exceto MODEL_DIR)
```

3. **Pin de versão do sklearn** (anti-supply-chain): `scikit-learn==1.8.0` (não `>=1.8`).

---

### CRIT-SEC-02: Credenciais em Memória de Processo (SEC-01)
**Localização:** `src/servicos/sessoes.py::_CREDENCIAIS`  
**Severidade:** ALTA (dump de processo expõe api_key/secret)  
**Estado:** Mitigado — limpeza no logout/expiração; `/v1/sessao/status` não puxa segredo (DA-20). Mas durante sessão ativa, segredos estão em **texto puro em dict global**.

**Fix arquitetural (sem quebrar o loop autônomo):**
```python
# Padrão: secret_id + resolução on-demand (já existe em core/segredos.py)
# Mudança: NÃO armazenar credencial bruta em _CREDENCIAIS.
# Armazenar apenas secret_id (nome de env var).

_SESSOES: dict[str, Sessao] = {}  # SEM _CREDENCIAIS dict

class Sessao:
    secret_id_api_key: str  # ex: "BINANCE_API_KEY_USER_123"
    secret_id_api_secret: str  # ex: "BINANCE_API_SECRET_USER_123"
    
    def obter_credenciais(self) -> tuple[str, str]:
        # Resolve on-demand do ambiente (env var ou Vault)
        return (
            os.environ[self.secret_id_api_key],
            core.segredos.resolver(self.secret_id_api_secret)
        )
```

**Trade-off:** Cada ciclo do autotrader faz 2 lookups de env var (overhead mínimo). Ganho: **zero segredos em memória persistente**. Se o processo for dumpado, só se vê nomes de env vars, não valores.

---

### CRIT-SEC-03: XSS em `/v1/noticias/frame` + Path Traversal em `/v1/img/{filename}`
**Localização:** `src/main.py`  
**Severidade:** ALTA (execução de script no browser do admin → roubo de cookie de sessão)  

**Fix XSS em `/v1/noticias/frame`:**
```python
import html
from markupsafe import escape

@router.get("/v1/noticias/frame")
async def noticias_frame():
    noticias = await repo_noticias.listar_recentes()
    # ESCAPAR todo conteúdo de terceiros
    html_content = "<div>" + "".join(
        f"<p>{escape(n.titulo)} — {escape(n.fonte)}</p>" for n in noticias
    ) + "</div>"
    return HTMLResponse(content=html_content)
```

**Fix Path Traversal em `/v1/img/{filename}`:**
```python
from pathlib import Path
from fastapi import HTTPException

@router.get("/img/{filename}")
async def serve_image(filename: str):
    base_dir = Path("frontend/public/img").resolve()
    # Canonicalizar e verificar containment
    target = (base_dir / filename).resolve()
    if not str(target).startswith(str(base_dir)):
        raise HTTPException(403, "Path traversal detectado")
    if not target.exists() or not target.is_file():
        raise HTTPException(404)
    return FileResponse(target)
```

---

### CRIT-SEC-04: Sem Rate-Limit Global / Brute-Force Protection
**Localização:** `src/main.py` (todos os endpoints)  
**Severidade:** ALTA (DoS de baixo esforço + amplificação de custo LLM)  

**Fix com `slowapi`:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/v1/sessao/entrar")
@limiter.limit("5/minute")  # Anti brute-force
async def login(request, payload):
    ...

@app.get("/v1/ai/insight")
@limiter.limit("10/hour")  # Anti amplificação de custo GPT
async def ai_insight(request):
    ...

@app.get("/v1/export/{tabela}")
@limiter.limit("3/minute")  # Anti exfiltração
async def export(request, tabela):
    ...
```

---

### CRIT-SEC-05: CSRF Ausente + `COOKIE_SECURE` Default `false`
**Localização:** `src/main.py` (middleware de sessão)  

**Fix:**
```python
# 1. Forçar COOKIE_SECURE=true em produção
if os.getenv("AMBIENTE") == "producao":
    assert COOKIE_SECURE is True, "COOKIE_SECURE deve ser True em produção"

# 2. CSRF token double-submit
@app.middleware("http")
async def csrf_middleware(request, call_next):
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        cookie_token = request.cookies.get("csrf_token")
        header_token = request.headers.get("X-CSRF-Token")
        if not cookie_token or cookie_token != header_token:
            return JSONResponse(403, {"detail": "CSRF token inválido"})
    response = await call_next(request)
    if not request.cookies.get("csrf_token"):
        response.set_cookie("csrf_token", secrets.token_urlsafe(32), httponly=False)
    return response
```

---

### CRIT-SEC-06: Dependências Não-Pinadas por Hash
**Localização:** `requirements.txt`  
**Severidade:** MÉDIA (dependency confusion / versão maliciosa)  

**Fix:**
```bash
pip install pip-tools
pip-compile --generate-hashes requirements.in
# Resultado: requirements.txt com hashes SHA256
# pip install --require-hashes -r requirements.txt
```

---

### CRIT-SEC-07: SQL via f-string em PRAGMA/ALTER
**Localização:** `src/persistencia/conexao.py`  
**Estado:** Benigno hoje (nomes são constantes internas), mas **anti-padrão**.  
**Fix:** Whitelist de tabelas permitidas:
```python
_TABELAS_PERMITIDAS = frozenset({
    "ohlcv_1m", "features_1m", "predictions", "outcomes",
    "ordens", "audit", "config", "usuarios", # ...
})

def _garantir_coluna(tabela: str, coluna: str, tipo: str):
    if tabela not in _TABELAS_PERMITIDAS:
        raise ValueError(f"Tabela {tabela} não permitida")
    # Agora seguro usar f-string (tabela é de whitelist)
```

---

## 1.4 🔴 COESÃO E SEMÂNTICA DO FLUXO DE DECISÃO

### CRIT-LOG-01: Limiares de Consenso Assimétricos (INC-01)
**Localização:** `src/sinais/consenso.py`  
**Severidade:** ALTA (viés sistemático a abrir trade)  
**Estado:** `confirmar ≥ 0.10` vs `vetar ≥ 0.35`. Confirmar é **3.5× mais fácil** que vetar. Isto cria viés de **abertura excessiva** — o bot abre trades que deveria abortar.  
**Parecer DA-09:** NÃO simetrizar sem backtest (alterar threshold de risco sem dado é risco).  
**Ação:** Executar backtest walk-forward com `confirmar=0.20, 0.25, 0.30` vs `vetar=0.35` e medir net/trade. **Só então** calibrar.

---

### CRIT-LOG-02: Falso Positivo — Comprar no Topo / Vender no Fundo
**Cenário de falha:** O pipeline `momentum → consenso → EV → risk_engine` pode gerar `BUY` no topo de um pump se:
1. `momentum.py` detecta rompimento de alta (mas é exaustão)
2. `consenso.py` confirma (limiar baixo de 0.10)
3. `ev_calculator.py` calcula EV positivo (mas avg_win é baseada em histórico que inclui o pump)
4. `risk_engine` aprova (saldo, drawdown, exposição OK)
5. `edge_config` aprova (se edge ativo — hoje está fechado)

**Defesa atual:** `regime_detector.py` detecta volatilidade extrema (`vol_regime > 0.0035`) e pode vetar. Mas o limiar é **estático**.

**Fix semântico (pré-Gemini):** Adicionar **filtro de exaustão de volume** no `signal_engine`:
```python
def _detectar_exaustao(features_recentes) -> bool:
    """Detecta spike de volume + RSI extremo + desvio padrão alto."""
    volume_spike = features_recentes.volume > features_recentes.volume_media_20 * 2.5
    rsi_extremo = features_recentes.rsi > 80 or features_recentes.rsi < 20
    std_alto = features_recentes.retorno_std > features_recentes.retorno_std_media * 2
    return volume_spike and rsi_extremo and std_alto

# No signal_engine:
if _detectar_exaustao(features):
    return Signal(acao="HOLD", motivo="exaustao_detectada")
```

---

### CRIT-LOG-03: IC Espúrio Preço×Preço (Já Corrigido)
**Estado:** ✅ Corrigido — `resumo_qualidade_recente` agora correlaciona **retorno×previsão de retorno** (não preço×preço). IC de retorno real: BTC 0.089, ETH -0.034, BNB 0.003.  
**Lição registrada:** Toda métrica de correlação deve ser de **retorno**, não de **nível**.

---

# 🧠 FASE 2 — REFATORAÇÃO SEMÂNTICA (FLUXO DE DECISÃO INQUEBRÁVEL)

## 2.1 Decomposição do God-File `testnet_auto_trader.py` (F6)

O arquivo de 2371 LOC com método `_executar_ciclo` de 833 LOC é a **maior dívida técnica** do projeto. Decompor em **4 módulos coesos**:

```
src/autotrader/
├── __init__.py              # Re-export público (compatibilidade)
├── configurador.py          # ✅ Já extraído
├── calculos.py              # ✅ Já extraído
├── ciclo_trading.py         # NOVO — máquina de estados do ciclo
├── gestor_estado.py         # NOVO — persistência + reconciliação
├── loop_principal.py        # NOVO — loop assíncrono + error handling
└── monitor_posicao.py       # NOVO — trailing/stop/lucro-mínimo
```

### 2.1.1 `ciclo_trading.py` — Máquina de Estados Pura
```python
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, Protocol

class EstadoCiclo(Enum):
    OCIOSO = auto()
    ABRINDO = auto()      # Ordem BUY submetida, aguardando fill
    MONITORANDO = auto()  # Posição aberta, avaliando saída
    FECHANDO = auto()     # Ordem SELL submetida, aguardando fill
    ENCERRADO = auto()

@dataclass
class ContextoCiclo:
    simbolo: str
    ts_sinal: int          # Para idempotência estável
    regime: str
    estrategia: str
    notional: Decimal
    preco_entrada: Optional[Decimal] = None
    ordem_id_entrada: Optional[str] = None
    ordem_id_saida: Optional[str] = None
    lucro_usdt: Optional[Decimal] = None

class MaquinaEstadosCiclo:
    """Máquina de estados pura — sem I/O, testável isoladamente."""
    
    def __init__(self):
        self._estado: EstadoCiclo = EstadoCiclo.OCIOSO
        self._contexto: Optional[ContextoCiclo] = None
    
    def pode_abrir(self) -> bool:
        return self._estado == EstadoCiclo.OCIOSO
    
    def abrir(self, ctx: ContextoCiclo) -> None:
        if not self.pode_abrir():
            raise RuntimeError(f"Não pode abrir no estado {self._estado}")
        self._contexto = ctx
        self._estado = EstadoCiclo.ABRINDO
    
    def confirmar_abertura(self, preco: Decimal, ordem_id: str) -> None:
        if self._estado != EstadoCiclo.ABRINDO:
            raise RuntimeError(f"Não pode confirmar abertura no estado {self._estado}")
        self._contexto.preco_entrada = preco
        self._contexto.ordem_id_entrada = ordem_id
        self._estado = EstadoCiclo.MONITORANDO
    
    def avaliar_saida(self, preco_atual: Decimal, config_saida) -> Optional[str]:
        """Retorna motivo de saída ou None se mantém."""
        if self._estado != EstadoCiclo.MONITORANDO:
            return None
        # ... trailing, stop, lucro-mínimo ...
    
    def confirmar_fechamento(self, preco: Decimal, ordem_id: str, lucro: Decimal) -> None:
        if self._estado != EstadoCiclo.FECHANDO:
            raise RuntimeError(f"Não pode confirmar fechamento no estado {self._estado}")
        self._contexto.preco_saida = preco
        self._contexto.ordem_id_saida = ordem_id
        self._contexto.lucro_usdt = lucro
        self._estado = EstadoCiclo.ENCERRADO
    
    def resetar(self) -> Optional[ContextoCiclo]:
        ctx = self._contexto
        self._contexto = None
        self._estado = EstadoCiclo.OCIOSO
        return ctx  # Para registro final
```

### 2.1.2 `loop_principal.py` — Loop Assíncrono com Error Handling
```python
class LoopPrincipal:
    def __init__(self, maquina: MaquinaEstadosCiclo, gestor: GestorEstado,
                 executor: GerenciadorOrdens, monitor: MonitorPosicao):
        self._maquina = maquina
        self._gestor = gestor
        self._executor = executor
        self._monitor = monitor
        self._consecutive_errors = 0
        self._max_errors = 5
    
    async def rodar(self, shutdown_event: asyncio.Event):
        while not shutdown_event.is_set():
            try:
                await self._ciclo()
                self._consecutive_errors = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._consecutive_errors += 1
                log.error(f"Erro no ciclo ({self._consecutive_errors}/{self._max_errors}): {e}")
                if self._consecutive_errors >= self._max_errors:
                    await self._gestor.halt("limite_erros_consecutivos")
                    return
            await asyncio.sleep(self._intervalo_ciclo)
    
    async def _ciclo(self):
        # Pipeline limpo: dado → sinal → risco → edge → exec → persist
        ...
```

---

## 2.2 Ativação do Unit of Work (DA-04)

```python
# src/persistencia/uow.py — reativar
class UnitOfWork:
    def __init__(self, conexao_factory):
        self._conexao_factory = conexao_factory
        self._conexao = None
        self.repositorio_ordens = None
        self.repositorio_snapshot = None
        self.repositorio_audit = None
    
    async def __aenter__(self):
        self._conexao = await self._conexao_factory()
        await self._conexao.execute("BEGIN IMMEDIATE")
        self.repositorio_ordens = RepositorioOrdens(self._conexao)
        self.repositorio_snapshot = RepositorioSnapshot(self._conexao)
        self.repositorio_audit = RepositorioAudit(self._conexao)
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                await self._conexao.commit()
            else:
                await self._conexao.rollback()
        finally:
            await self._conexao.close()
```

**Wiring no autotrader:**
```python
async def _abrir_ciclo(self, sinal):
    async with UnitOfWork(self._conexao_factory) as uow:
        resultado = await self._executor.criar_ordem_market(...)  # Binance
        if resultado.status == "FILLED":
            await uow.repositorio_ordens.registrar(resultado)
            await uow.repositorio_snapshot.atualizar(self._maquina.contexto)
            await uow.repositorio_audit.registrar("ciclo_aberto", ...)
        # COMMIT atômico
```

---

## 2.3 Migração de ML para ProcessPoolExecutor

```python
# src/modelagem/inferencia_async.py
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
import asyncio
import joblib

_executor: ProcessPoolExecutor = None
_modelos_cache: dict[str, object] = {}  # Por PID

def _init_worker(model_dir: str):
    """Inicializa modelos no worker (uma vez por processo)."""
    global _modelos_cache
    for modelo_path in Path(model_dir).glob("*.joblib"):
        _modelos_cache[modelo_path.stem] = joblib.load(modelo_path)

def _prefer_sync(nome_modelo: str, features_dict: dict) -> float:
    modelo = _modelos_cache[nome_modelo]
    return float(modelo.predict(pd.DataFrame([features_dict]))[0])

class InferenciaAsync:
    def __init__(self, model_dir: str, max_workers: int = 2):
        ctx = mp.get_context("spawn")  # Seguro, não fork
        self._executor = ProcessPoolExecutor(
            max_workers=max_workers,
            mp_context=ctx,
            initializer=_init_worker,
            initargs=(model_dir,)
        )
    
    async def prever(self, nome_modelo: str, features: dict) -> float:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, _prefer_sync, nome_modelo, features
        )
    
    def shutdown(self):
        self._executor.shutdown(wait=True)
```

---

## 2.4 Calibração de Limiares de Consenso (INC-01)

```python
# scripts/calibrar_consenso.py
"""Backtest sweep para calibrar limiares de consenso."""

import asyncio
from src.backtester.walk_forward import WalkForward
from src.persistencia.repositorios import RepositorioOHLCV

async def main():
    repo = RepositorioOHLCV()
    dados = await repo.listar_todos("BTCUSDT")
    
    resultados = []
    for confirmar in [0.10, 0.15, 0.20, 0.25, 0.30]:
        for vetar in [0.25, 0.30, 0.35, 0.40]:
            if confirmar >= vetar:
                continue
            wf = WalkForward(confirmar_threshold=confirmar, vetar_threshold=vetar)
            resultado = wf.run(dados)
            resultados.append({
                "confirmar": confirmar,
                "vetar": vetar,
                "net_per_trade": resultado.net_per_trade,
                "n_trades": resultado.n_trades,
                "ic": resultado.ic,
                "max_drawdown": resultado.max_drawdown
            })
    
    # Selecionar melhor config por Sharpe ratio
    melhor = max(resultados, key=lambda r: r["net_per_trade"] / max(r["max_drawdown"], 0.001))
    print(f"Melhor config: confirmar={melhor['confirmar']}, vetar={melhor['vetar']}")
    print(f"Net/trade: {melhor['net_per_trade']:.4f}, IC: {melhor['ic']:.4f}")
```

---

## 2.5 Slippage Realizado (Feedback Loop)

```python
# src/observabilidade/slippage_tracker.py
from collections import defaultdict
import numpy as np

class SlippageTracker:
    def __init__(self, janela_ewma: int = 100):
        self._amostras: dict[str, list[float]] = defaultdict(list)
        self._janela = janela_ewma
    
    def registrar(self, simbolo: str, preco_sinal: float, preco_execucao: float):
        slippage = (preco_execucao - preco_sinal) / preco_sinal
        self._amostras[simbolo].append(slippage)
        if len(self._amostras[simbolo]) > self._janela:
            self._amostras[simbolo].pop(0)
    
    def obter_estimativa(self, simbolo: str) -> float:
        amostras = self._amostras.get(simbolo, [])
        if len(amostras) < 10:
            return None  # Sem dados suficientes
        # EWMA com peso maior para amostras recentes
        pesos = np.exp(np.linspace(-3, 0, len(amostras)))
        pesos /= pesos.sum()
        return float(np.average(amostras, weights=pesos))
    
    def obter_percentil(self, simbolo: str, percentil: float = 0.95) -> float:
        """Slippage pessimista (p95) para uso conservador no EV."""
        amostras = self._amostras.get(simbolo, [])
        if len(amostras) < 10:
            return None
        return float(np.percentile(amostras, percentil * 100))
```

**Wiring no EVCalculator:**
```python
class EVCalculator:
    def __init__(self, slippage_tracker: SlippageTracker):
        self._tracker = slippage_tracker
    
    def calcular(self, simbolo, ...):
        slippage_empirico = self._tracker.obter_percentil(simbolo, 0.95)
        if slippage_empirico is not None:
            slippage = max(slippage_empirico, self._slippage_config)  # Pessimista
        else:
            slippage = self._slippage_config
        # ... cálculo EV com slippage round-trip ...
```

---

# 🛡️ FASE 3 — BLINDAGEM E DEPLOY (PRODUÇÃO REAL HOSTIL)

## 3.1 Containerização e IaC

### 3.1.1 Dockerfile Multi-Stage
```dockerfile
# Stage 1: Builder
FROM python:3.14-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime (mínimo, sem build tools)
FROM python:3.14-slim AS runtime
# Usuário não-root
RUN useradd -m -u 1000 oraculo
USER oraculo
WORKDIR /app
COPY --from=builder /install /usr/local/lib/python3.14/site-packages
COPY --chown=oraculo:oraculo src/ ./src/
COPY --chown=oraculo:oraculo frontend/ ./frontend/
COPY --chown=oraculo:oraculo scripts/ ./scripts/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/v1/health || exit 1

# Variáveis de ambiente seguras
ENV AMBIENTE=producao \
    COOKIE_SECURE=true \
    PERMITIR_CONTA_REAL=false \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

**Nota crítica:** `--workers 1` é **obrigatório** — o bot é stateful (sessões, estado do autotrader em memória). Multiple workers quebrariam o estado. Para escalar, usar **múltiplos containers com sharding por símbolo** (não multiple workers no mesmo container).

---

### 3.1.2 docker-compose.yml com Serviços de Suporte
```yaml
version: "3.9"

services:
  oraculo:
    build: .
    container_name: oraculo-bot
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"  # NUNCA expor direto — usar reverse proxy
    volumes:
      - ./dados:/app/dados        # SQLite persistente
      - ./modelos:/app/dados/modelos
    env_file:
      - .env.production
    networks:
      - oraculo-net
    depends_on:
      - prometheus
      - loki

  # Reverse proxy com TLS + WAF básico
  caddy:
    image: caddy:2
    container_name: oraculo-proxy
    restart: unless-stopped
    ports:
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    networks:
      - oraculo-net

  prometheus:
    image: prom/prometheus:latest
    container_name: oraculo-prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    networks:
      - oraculo-net

  alertmanager:
    image: prom/alertmanager:latest
    container_name: oraculo-alertmanager
    volumes:
      - ./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml
    networks:
      - oraculo-net

  loki:
    image: grafana/loki:latest
    container_name: oraculo-loki
    volumes:
      - loki_data:/loki
    networks:
      - oraculo-net

  grafana:
    image: grafana/grafana:latest
    container_name: oraculo-grafana
    ports:
      - "127.0.0.1:3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    networks:
      - oraculo-net

volumes:
  caddy_data:
  prometheus_data:
  loki_data:
  grafana_data:

networks:
  oraculo-net:
    driver: bridge
```

---

### 3.1.3 Caddyfile (Reverse Proxy + TLS Automático + WAF Básico)
```caddyfile
oraculo.seudominio.com {
    reverse_proxy oraculo:8000
    
    # TLS automático via Let's Encrypt
    encode gzip zstd
    
    # Headers de segurança
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
    
    # Rate limiting básico
    rate_limit {
        zone oraculo_login {
            key {remotehost}
            events 5
            window 1m
        }
    }
    
    # Bloquear paths sensíveis
    @blocked path /v1/export/* /docs /redoc /openapi.json
    respond @blocked 403
}
```

---

## 3.2 Kill-Switches (Botões de Pânico Multi-Camada)

### 3.2.1 Kill-Switch Financeiro (Hardware-Level)
```python
# src/executor/kill_switch.py
class KillSwitchFinanceiro:
    """Camada de kill-switch INDEPENDENTE do resto do sistema.
    Verifica UMA condição: se o arquivo /app/dados/KILL_SWITCH existe,
    NENHUMA ordem é submetida. Override de tudo."""
    
    KILL_FILE = Path("/app/dados/KILL_SWITCH")
    
    @classmethod
    def is_engatado(cls) -> bool:
        return cls.KILL_FILE.exists()
    
    @classmethod
    def engatar(cls, motivo: str):
        cls.KILL_FILE.write_text(f"{datetime.utcnow().isoformat()}: {motivo}\n")
        log.critical(f"KILL-SWITCH ENGATADO: {motivo}")
    
    @classmethod
    def destravar(cls):
        if cls.KILL_FILE.exists():
            cls.KILL_FILE.unlink()
            log.info("Kill-switch destravado por ação humana")

# No gerenciador_ordens, ANTES de qualquer create_order:
async def criar_ordem_market(...):
    if KillSwitchFinanceiro.is_engatado():
        raise KillSwitchEngatadoError("Ordem bloqueada por kill-switch financeiro")
    # ... continuar ...
```

**Operação:** Para parar o bot **imediatamente** sem restart:
```bash
touch /app/dados/KILL_SWITCH
# O próximo ciclo detecta e aborta. Para destravar:
rm /app/dados/KILL_SWITCH
```

### 3.2.2 Kill-Switch de API (Exchange-Level)
```python
# Revogar permissões de trading via API da Binance
async def revogar_permissoes_trading():
    """Chama endpoint da Binance para desabilitar trading da API key."""
    # POST /sapi/v1/account/apiRestrictions
    # setIsolatedMarginTrade=false, setSpotTrading=false
    # Isso é DESTRUTIVO — requer reativação manual no painel da Binance
```

### 3.2.3 Kill-Switch de Processo (OS-Level)
```bash
# Parada graciosa com timeout
docker exec oraculo-bot kill -SIGTERM 1
# Se não responder em 15s:
docker stop oraculo-bot
```

---

## 3.3 Monitoramento Automatizado

### 3.3.1 Alertas Prometheus (alertmanager.yml)
```yaml
groups:
  - name: oraculo-financeiro
    rules:
      - alert: HaltFinanceiroAtivo
        expr: oraculo_halt_ativo == 1
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "HALT financeiro ativo — intervenção humana necessária"
      
      - alert: DrawdownDiarioExcedido
        expr: oraculo_drawdown_diario_percent > 2.5
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Drawdown diário em {{ $value }}% (limite 3%)"
      
      - alert: ErrosConsecutivosLoop
        expr: oraculo_erros_consecutivos > 3
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "{{ $value }} erros consecutivos no loop autônomo"
      
      - alert: LatenciaCicloAlta
        expr: histogram_quantile(0.95, rate(oraculo_ciclo_duracao_seconds_bucket[5m])) > 30
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "P95 de duração de ciclo > 30s — possível HOL blocking"
      
      - alert: SQLiteDatabaseLocked
        expr: rate(oraculo_db_locked_total[5m]) > 0.1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "SQLite database is locked — contenção de escrita"
      
      - alert: SemTradesExecutados24h
        expr: increase(oraculo_ordens_executadas_total[24h]) == 0
        for: 1h
        labels:
          severity: info
        annotations:
          summary: "Nenhuma ordem executada em 24h — verificar gates"
```

### 3.3.2 Webhook Telegram para Alertas Críticos
```python
# src/observabilidade/alertas.py
import httpx
import hmac
import hashlib

class AlertaTelegram:
    def __init__(self, bot_token: str, chat_id: str, secret: str):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._secret = secret
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    async def enviar(self, mensagem: str, severidade: str = "CRITICAL"):
        # Assinatura HMAC para validar origem no receptor
        assinatura = hmac.new(
            self._secret.encode(), mensagem.encode(), hashlib.sha256
        ).hexdigest()
        
        payload = {
            "chat_id": self._chat_id,
            "text": f"🚨 [{severidade}] ORÁCULO\n\n{mensagem}",
            "parse_mode": "Markdown"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(self._url, json=payload)
                resp.raise_for_status()
            except Exception as e:
                log.error(f"Falha ao enviar alerta Telegram: {e}")
                # Fallback: log estruturado (alertmanager captura)
```

---

## 3.4 Redundância e Backup

### 3.4.1 Backup SQLite (PITR-like)
```bash
#!/bin/bash
# scripts/backup_sqlite.sh
# Roda a cada hora via cron

DB_PATH="/app/dados/oraculo.db"
BACKUP_DIR="/backups/sqlite"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Backup online (sem lock) via .backup() do SQLite
sqlite3 "$DB_PATH" "VACUUM INTO '$BACKUP_DIR/oraculo_${TIMESTAMP}.db'"

# Rotação: manter 24h horário + 7d diário + 30d semanal
find "$BACKUP_DIR" -name "oraculo_*.db" -mmin +1440 -delete  # >24h horário
find "$BACKUP_DIR" -name "oraculo_*.db" -mtime +7 -delete     # >7d diário
find "$BACKUP_DIR" -name "oraculo_*.db" -mtime +30 -delete    # >30d semanal

# Upload para S3 (opcional)
aws s3 cp "$BACKUP_DIR/oraculo_${TIMESTAMP}.db" \
    "s3://oraculo-backups/sqlite/$(date +%Y/%m/%d)/"
```

### 3.4.2 Schema de Replicação Futura (Liquibase + PostgreSQL)
Para escala horizontal futura, migrar SQLite → PostgreSQL com:
- **Read replicas** para queries de API/dashboard
- **Write master** para ordens/snapshots
- **Partitioning** por símbolo em `ohlcv_1m` (alta cardinalidade)

---

## 3.5 Graceful Shutdown Completo

```python
# src/main.py — lifespan refinado
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Fail-fast
    exigir_config_valida()
    
    # 2. Bootstrap
    await inicializar_db()
    await garantir_ajustes_padrao()
    
    # 3. Recuperar halt persistido
    await _inicializar_retomada(app)
    
    # 4. Signal handlers
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_event.set)
    
    app.state.shutdown_event = shutdown_event
    
    # 5. Iniciar workers em background
    tasks = []
    if os.getenv("ATIVAR_LOOP_PREVISAO"):
        tasks.append(asyncio.create_task(loop_previsao(shutdown_event)))
    if os.getenv("ATIVAR_CONSUMIDOR_SINAIS"):
        tasks.append(asyncio.create_task(loop_consumidor_sinais(shutdown_event)))
    # ... outros workers ...
    
    app.state.tasks = tasks
    
    try:
        yield
    finally:
        # 6. Graceful shutdown com timeout
        log.info("Shutdown iniciado — aguardando tarefas em andamento")
        shutdown_event.set()
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=15.0
            )
        except asyncio.TimeoutError:
            log.error("Timeout no shutdown — forçando cancelamento")
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # 7. Fechar conexões de modelo (ProcessPool)
        if hasattr(app.state, 'inferencia'):
            app.state.inferencia.shutdown()
        
        log.info("Shutdown completo")
```

---

# 🧬 INTEGRAÇÃO DA CAMADA AGÊNTICA GEMINI (botai.md)

## 4.1 Arquitetura Híbrida — O Cérebro Sobre o Músculo

O Oráculo atual é o **músculo** (execução determinística, stops rígidos, persistência). A camada Gemini será o **cérebro consultivo** — **NUNCA** com poder direto de execução. A IA atua como:

1. **Filtro de Pré-Execução (Interceptor):** Antes do `_abrir_ciclo`, consulta Gemini com contexto de mercado + histórico de performance. Se a IA disser `ABORT`, a ordem é cancelada.
2. **Auditor Pós-Trade (Cron 2h):** A cada 2 horas, a IA lê os trades recentes do banco e identifica padrões que o código rígido não enxerga.
3. **Detector de Regime Macro:** A IA avalia mudanças de regime que os indicadores técnicos demoram a capturar.

### Princípio Fundamental: DEFENSE-IN-DEPTH
**Nenhum gate financeiro (risk_engine, profit_guard, edge_config) pode ser overridden pela IA.** A IA é um **filtro adicional** que só pode **VETAR**, nunca **APROVAR**. Se a IA falhar, alucinar, ou demorar, o bot mecânico continua operando normalmente (timeout → ignora IA).

---

## 4.2 Estrutura de Diretórios da Camada Agêntica

```
src/
└── intelligence/                    # NOVO — camada agêntica isolada
    ├── __init__.py
    ├── gemini_client.py             # Cliente Gemini API (async, com retry/cost-control)
    ├── context_builder.py           # Transforma dados do DB em contexto estruturado para LLM
    ├── pre_execution_filter.py      # Hook interceptor antes de _abrir_ciclo
    ├── post_trade_auditor.py        # Cron 2h — análise pós-mortem de trades
    ├── regime_analyzer.py           # Detector de regime macro via IA
    ├── prompt_templates.py          # Templates de prompt versionados
    ├── response_sanitizer.py        # Parse + validação de JSON retornado pela IA
    └── guard.py                     # Guardrails independentes da IA
```

---

## 4.3 `gemini_client.py` — Cliente Resiliente com Cost-Control

```python
# src/intelligence/gemini_client.py
import asyncio
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from typing import Optional
import json
import logging
from datetime import datetime, date

log = logging.getLogger(__name__)

class GeminiClient:
    """Cliente Gemini com circuit breaker de custo, retry, e timeout."""
    
    # Cost-control
    MAX_CALLS_PER_DAY = 50
    MAX_CALLS_PER_HOUR = 10
    COOLDOWN_AFTER_FAILURES = 5
    COOLDOWN_MINUTES = 60
    
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            model_name,
            safety_settings={
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            }
        )
        self._api_key = api_key
        self._calls_today = 0
        self._calls_this_hour = 0
        self._consecutive_failures = 0
        self._cooldown_until: Optional[datetime] = None
        self._last_reset_day = date.today()
        self._last_reset_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
    
    def _check_limits(self) -> bool:
        """Verifica limites de custo. Retorna False se em cooldown/limite."""
        now = datetime.now()
        
        # Reset diário
        if now.date() != self._last_reset_day:
            self._calls_today = 0
            self._last_reset_day = now.date()
        
        # Reset horário
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        if current_hour != self._last_reset_hour:
            self._calls_this_hour = 0
            self._last_reset_hour = current_hour
        
        # Cooldown por falhas
        if self._cooldown_until and now < self._cooldown_until:
            return False
        
        # Limites
        if self._calls_today >= self.MAX_CALLS_PER_DAY:
            log.warning("Limite diário de Gemini atingido")
            return False
        if self._calls_this_hour >= self.MAX_CALLS_PER_HOUR:
            log.warning("Limite horário de Gemini atingido")
            return False
        
        return True
    
    async def analyze(self, system_prompt: str, user_context: str, 
                      temperature: float = 0.2) -> Optional[dict]:
        """
        Envia análise para Gemini. Retorna dict parseado ou None em falha.
        NUNCA lança exceção — falha silenciosa com log (bot continua operando).
        """
        if not self._check_limits():
            log.info("Gemini em cooldown/limite — usando fallback heurístico")
            return None
        
        try:
            # Gemini não tem system_prompt nativo como OpenAI;
            # concatenar no prompt
            full_prompt = f"{system_prompt}\n\n---\n\n{user_context}"
            
            # Timeout agressivo — bot não pode esperar IA
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self._model.generate_content,
                    full_prompt,
                    generation_config={
                        "temperature": temperature,
                        "max_output_tokens": 1024,
                        "response_mime_type": "application/json",
                    }
                ),
                timeout=15.0  # 15s hard limit
            )
            
            self._calls_today += 1
            self._calls_this_hour += 1
            self._consecutive_failures = 0
            self._cooldown_until = None
            
            # Parse JSON
            content = response.text.strip()
            return json.loads(content)
            
        except asyncio.TimeoutError:
            log.warning("Gemini timeout (15s) — fallback heurístico")
            self._consecutive_failures += 1
        except json.JSONDecodeError as e:
            log.warning(f"Gemini retornou JSON inválido: {e}")
            self._consecutive_failures += 1
        except Exception as e:
            log.error(f"Erro Gemini: {type(e).__name__}: {e}")
            self._consecutive_failures += 1
        
        # Circuit breaker de falhas
        if self._consecutive_failures >= self.COOLDOWN_AFTER_FAILURES:
            self._cooldown_until = datetime.now() + timedelta(minutes=self.COOLDOWN_MINUTES)
            log.error(f"Gemini em cooldown por {self.COOLDOWN_MINUTES}min após "
                      f"{self._consecutive_failures} falhas consecutivas")
        
        return None
    
    def health(self) -> dict:
        return {
            "disponivel": self._check_limits(),
            "calls_today": self._calls_today,
            "calls_this_hour": self._calls_this_hour,
            "consecutive_failures": self._consecutive_failures,
            "cooldown_until": self._cooldown_until.isoformat() if self._cooldown_until else None,
            "model": self._model.model_name,
        }
```

---

## 4.4 `context_builder.py` — Transformando DB em Contexto para IA

```python
# src/intelligence/context_builder.py
import json
from typing import Dict, Any, List
from src.persistencia.repositorios import (
    RepositorioOrdens, RepositorioOHLCV, RepositorioFeatures
)

class ContextBuilder:
    """Constrói contexto estruturado para o Gemini a partir do banco do Oráculo."""
    
    def __init__(self, repo_ordens: RepositorioOrdens, 
                 repo_ohlcv: RepositorioOHLCV,
                 repo_features: RepositorioFeatures):
        self._repo_ordens = repo_ordens
        self._repo_ohlcv = repo_ohlcv
        self._repo_features = repo_features
    
    async def build_pre_execution_context(
        self, simbolo: str, sinal: dict, saldo: float
    ) -> str:
        """Contexto para o filtro de pré-execução."""
        
        # Últimos 10 trades (win/loss) para a IA ver padrões
        trades_recentes = await self._repo_ordens.listar_recentes(
            simbolo=simbolo, limite=10
        )
        
        # Features atuais (RSI, volume, volatilidade)
        features_atuais = await self._repo_features.obter_ultima(simbolo)
        
        # Velas recentes (últimas 20 de 15m = 5h de contexto)
        velas_recentes = await self._repo_ohlcv.listar_recentes(
            simbolo=simbolo, intervalo="15m", limite=20
        )
        
        contexto = {
            "simbolo": simbolo,
            "sinal_mecanico": {
                "acao": sinal.get("acao"),
                "confianca": sinal.get("confianca"),
                "estrategia": sinal.get("estrategia"),
                "regime": sinal.get("regime"),
                "ev_liquido_usdt": sinal.get("ev_liquido_usdt"),
            },
            "saldo_disponivel_usdt": saldo,
            "features_atuais": {
                "rsi_14": features_atuais.rsi if features_atuais else None,
                "volume_atual": features_atuais.volume if features_atuais else None,
                "volume_media_20": features_atuais.volume_media_20 if features_atuais else None,
                "volatilidade": features_atuais.vol_regime if features_atuais else None,
                "desvio_padrao_retorno": features_atuais.retorno_std if features_atuais else None,
            },
            "velas_recentes_15m": [
                {
                    "ts": v.ts.isoformat(),
                    "open": v.open, "high": v.high,
                    "low": v.low, "close": v.close,
                    "volume": v.volume
                }
                for v in velas_recentes
            ],
            "historico_performance": [
                {
                    "resultado": "WIN" if t.lucro_usdt and t.lucro_usdt > 0 else "LOSS",
                    "estrategia": t.estrategia,
                    "regime": t.regime,
                    "lucro_usdt": t.lucro_usdt,
                    "duracao_min": (t.duracao_ms / 60000) if t.duracao_ms else None,
                }
                for t in trades_recentes
            ],
        }
        
        return json.dumps(contexto, indent=2, ensure_ascii=False)
    
    async def build_post_trade_audit_context(self) -> str:
        """Contexto para auditoria pós-trade (cron 2h)."""
        ultimas_24h = await self._repo_ordens.listar_recentes(limite=50, horas=24)
        
        wins = [t for t in ultimas_24h if t.lucro_usdt and t.lucro_usdt > 0]
        losses = [t for t in ultimas_24h if t.lucro_usdt and t.lucro_usdt <= 0]
        
        contexto = {
            "periodo": "24h",
            "total_trades": len(ultimas_24h),
            "wins": len(wins),
            "losses": len(losses),
            "taxa_acerto": len(wins) / max(len(ultimas_24h), 1),
            "lucro_total_usdt": sum(t.lucro_usdt or 0 for t in ultimas_24h),
            "trades_detalhados": [
                {
                    "simbolo": t.simbolo,
                    "estrategia": t.estrategia,
                    "regime": t.regime,
                    "resultado": "WIN" if t.lucro_usdt and t.lucro_usdt > 0 else "LOSS",
                    "lucro_usdt": t.lucro_usdt,
                    "duracao_min": (t.duracao_ms / 60000) if t.duracao_ms else None,
                }
                for t in ultimas_24h
            ],
        }
        
        return json.dumps(contexto, indent=2, ensure_ascii=False)
```

---

## 4.5 `pre_execution_filter.py` — O Interceptor Crítico

```python
# src/intelligence/pre_execution_filter.py
import asyncio
import logging
from typing import Optional, Dict, Any
from .gemini_client import GeminiClient
from .context_builder import ContextBuilder
from .prompt_templates import PRE_EXECUTION_SYSTEM_PROMPT

log = logging.getLogger(__name__)

class PreExecutionFilter:
    """
    Hook interceptor ANTES de _abrir_ciclo.
    
    PRINCÍPIO: A IA só pode VETAR. Nunca aprovar.
    Se a IA falhar/timeout → bot continua (fallback mecânico).
    Se a IA disser ABORT → ordem cancelada.
    Se a IA disser PROCEED → ordem continua (IA não aprova, apenas não veta).
    """
    
    TIMEOUT_SECONDS = 12.0  # Hard limit — bot não espera IA
    
    def __init__(self, gemini: GeminiClient, context_builder: ContextBuilder,
                 enabled: bool = True):
        self._gemini = gemini
        self._context_builder = context_builder
        self._enabled = enabled
    
    async def evaluate(self, simbolo: str, sinal: dict, saldo: float) -> Dict[str, Any]:
        """
        Retorna:
        {
            "action": "PROCEED" | "ABORT",
            "rationale": str,
            "source": "gemini" | "timeout" | "disabled" | "error",
            "confidence": float
        }
        """
        if not self._enabled:
            return {"action": "PROCEED", "rationale": "Filtro IA desativado",
                    "source": "disabled", "confidence": 0.0}
        
        try:
            # Construir contexto a partir do banco
            user_context = await self._context_builder.build_pre_execution_context(
                simbolo, sinal, saldo
            )
            
            # Consultar Gemini com timeout
            resultado = await asyncio.wait_for(
                self._gemini.analyze(
                    system_prompt=PRE_EXECUTION_SYSTEM_PROMPT,
                    user_context=user_context,
                    temperature=0.1  # Baixa temperatura = decisões consistentes
                ),
                timeout=self.TIMEOUT_SECONDS
            )
            
            if resultado is None:
                # IA em cooldown/limite/erro → não bloqueia operação
                return {
                    "action": "PROCEED",
                    "rationale": "IA indisponível — prosseguindo com análise mecânica",
                    "source": "error",
                    "confidence": 0.0
                }
            
            action = resultado.get("action", "PROCEED").upper()
            rationale = resultado.get("rationale", "")
            confidence = float(resultado.get("confidence_score", 0.0))
            
            # SANITIZAÇÃO: IA só pode retornar PROCEED ou ABORT
            if action not in ("PROCEED", "ABORT"):
                action = "PROCEED"  # Default seguro
            
            # Se ABORT com baixa confiança, ignorar (IA incerta não deve bloquear)
            if action == "ABORT" and confidence < 0.70:
                log.info(f"Gemini sugeriu ABORT mas confiança {confidence} < 0.70 — ignorando")
                return {
                    "action": "PROCEED",
                    "rationale": f"IA incerta (conf={confidence}): {rationale}",
                    "source": "gemini",
                    "confidence": confidence
                }
            
            return {
                "action": action,
                "rationale": rationale,
                "source": "gemini",
                "confidence": confidence
            }
            
        except asyncio.TimeoutError:
            log.warning(f"Gemini timeout no filtro pré-execução para {simbolo}")
            return {
                "action": "PROCEED",
                "rationale": "Timeout IA — prosseguindo com análise mecânica",
                "source": "timeout",
                "confidence": 0.0
            }
        except Exception as e:
            log.error(f"Erro no filtro pré-execução: {e}")
            return {
                "action": "PROCEED",
                "rationale": f"Erro IA: {e}",
                "source": "error",
                "confidence": 0.0
            }
```

---

## 4.6 `prompt_templates.py` — Engenharia de Prompt Versionada

```python
# src/intelligence/prompt_templates.py

PRE_EXECUTION_SYSTEM_PROMPT = """Você é um analista de trading quantitativo de elite, especializado em criptomoedas spot na Binance.

Sua função é atuar como FILTRO DE SEGURANÇA sobre os sinais gerados por um bot mecânico (Oráculo). Você NÃO decide abrir trades — você apenas pode VETAR operações que identificar como armadilhas.

PRINCÍPIOS INVARIANTES:
1. Você só pode retornar "PROCEED" ou "ABORT". Nunca "BUY" ou "SELL".
2. Se houver DÚVIDA, retorne "PROCEED" (o bot mecânico já passou por 14 gates de risco).
3. Só retorne "ABORT" se identificar com ALTA CONFIANÇA (≥0.70) um dos seguintes padrões:
   - BULL TRAP: Rompimento falso com volume decrescente (divergência bearish)
   - BEAR TRAP: Queda de exaustão com volume climax (divergência bullish)
   - MUDANÇA DE REGIME: Mercado em transição de tendência para consolidação (ou vice-versa)
   - CORRELAÇÃO MACRO: Ativo movendo-se contra o mercado mais amplo (armadilha de liquidez)
   - REPETIÇÃO DE PADRÃO DE PERDA: O histórico mostra que este setup específico perdeu nas últimas 3+ tentativas

4. Analise o histórico de performance fornecido. Se o bot perdeu 3+ trades seguidos com a mesma estratégia no mesmo regime, considere ABORT.

5. Você deve retornar ESTRITAMENTE um JSON válido:
{
  "action": "PROCEED" | "ABORT",
  "rationale": "Breve explicação técnica (máx 200 chars)",
  "confidence_score": 0.0 a 1.0,
  "pattern_detected": "bull_trap" | "bear_trap" | "regime_change" | "loss_pattern" | "none"
}

NÃO adicione texto fora do JSON. NÃO sugira tamanhos de posição. NÃO sugira stops."""

POST_TRADE_AUDIT_PROMPT = """Você é um auditor de performance de trading algorítmico.

Analise o histórico de trades das últimas 24h do bot Oráculo e identifique:

1. PADRÕES DE PERDA: Existe alguma combinação de (estratégia, regime, horário, símbolo) que está perdendo consistentemente?
2. PADRÕES DE GANHO: Qual configuração está performando melhor? (para potencialmente priorizar)
3. DURAÇÃO ÓTIMA: Trades que duram mais ou menos tendem a ganhar mais?
4. RECOMENDAÇÃO DE AJUSTE: Uma única recomendação acionável (ex: "desativar momentum em regime de consolidação")

Retorne ESTRITAMENTE:
{
  "patterns_loss": ["descrição do padrão 1", "descrição do padrão 2"],
  "patterns_win": ["descrição do padrão de ganho"],
  "optimal_duration_min": número,
  "recommendation": "uma recomendação acionável",
  "confidence": 0.0 a 1.0
}"""

REGIME_ANALYSIS_PROMPT = """Você é um analista de macro-estrutura de mercado cripto.

Com base nos dados de velas e features fornecidos, determine:

1. REGIME ATUAL: trending_up | trending_down | ranging | volatile_expansion | volatile_contraction
2. CONFIANÇA: 0.0 a 1.0
3. TRANSIÇÃO IMINENTE: true/false (o regime está mudando?)
4. RECOMENDAÇÃO DE AGRESSIVIDADE: 0.0 (conservador) a 1.0 (agressivo) — quanto o bot deveria operar neste regime

Retorne ESTRITAMENTE:
{
  "regime": "trending_up|trending_down|ranging|volatile_expansion|volatile_contraction",
  "confidence": 0.0 a 1.0,
  "transition_imminent": true|false,
  "aggressiveness_factor": 0.0 a 1.0,
  "rationale": "breve explicação"
}"""
```

---

## 4.7 `post_trade_auditor.py` — Cron de Auditoria 2h

```python
# src/intelligence/post_trade_auditor.py
import asyncio
import logging
from datetime import datetime
from .gemini_client import GeminiClient
from .context_builder import ContextBuilder
from .prompt_templates import POST_TRADE_AUDIT_PROMPT
from src.persistencia.repositorios import RepositorioAudit

log = logging.getLogger(__name__)

class PostTradeAuditor:
    """Cron de auditoria pós-trade a cada 2 horas."""
    
    INTERVAL_HOURS = 2
    
    def __init__(self, gemini: GeminiClient, context_builder: ContextBuilder,
                 repo_audit: RepositorioAudit):
        self._gemini = gemini
        self._context_builder = context_builder
        self._repo_audit = repo_audit
    
    async def run_loop(self, shutdown_event: asyncio.Event):
        log.info("PostTradeAuditor iniciado — intervalo 2h")
        while not shutdown_event.is_set():
            try:
                await self._audit_cycle()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error(f"Erro no ciclo de auditoria: {e}")
            
            # Sleep com checagem de shutdown
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(),
                    timeout=self.INTERVAL_HOURS * 3600
                )
            except asyncio.TimeoutError:
                continue  # Intervalo completo
    
    async def _audit_cycle(self):
        log.info("Iniciando auditoria pós-trade com Gemini")
        
        user_context = await self._context_builder.build_post_trade_audit_context()
        
        resultado = await self._gemini.analyze(
            system_prompt=POST_TRADE_AUDIT_PROMPT,
            user_context=user_context,
            temperature=0.3  # Mais criativo para análise de padrões
        )
        
        if resultado is None:
            log.info("Auditoria IA indisponível — pulando ciclo")
            return
        
        # Persistir auditoria no banco (para histórico e consulta futura)
        await self._repo_audit.registrar(
            componente="post_trade_auditor",
            evento="auditoria_2h",
            motivo=resultado.get("recommendation", ""),
            meta_json=resultado
        )
        
        log.info(f"Auditoria concluída: {resultado.get('recommendation', 'sem recomendação')}")
        
        # Se detectou padrão de perda crítico, alertar
        patterns_loss = resultado.get("patterns_loss", [])
        if patterns_loss and len(patterns_loss) >= 2:
            log.warning(f"⚠️ Padrões de perda detectados: {patterns_loss}")
            # Aqui poderia engatilhar alerta Telegram
```

---

## 4.8 Wiring da Camada Agêntica no Autotrader

```python
# src/servicos/testnet_auto_trader.py — modificação cirúrgica no _abrir_ciclo

class TestnetAutoTrader:
    def __init__(self, ... , pre_execution_filter: Optional[PreExecutionFilter] = None):
        # ... init existente ...
        self._ai_filter = pre_execution_filter  # None = desativado
    
    async def _abrir_ciclo(self, sinal, saldo):
        # ... gates mecânicos existentes (risk_engine, profit_guard, edge_config) ...
        
        # === CAMADA AGÊNTICA (Interceptor) ===
        if self._ai_filter is not None:
            ai_decision = await self._ai_filter.evaluate(
                simbolo=sinal.simbolo,
                sinal=sinal.to_dict(),
                saldo=saldo
            )
            
            if ai_decision["action"] == "ABORT":
                log.info(
                    f"🧠 IA VETOU operação {sinal.simbolo} — "
                    f"Motivo: {ai_decision['rationale']} "
                    f"(conf={ai_decision['confidence']}, source={ai_decision['source']})"
                )
                # Persistir veto no banco para análise
                await self._repo_audit.registrar(
                    componente="ai_pre_execution_filter",
                    evento="operacao_vetada",
                    motivo=ai_decision["rationale"],
                    meta_json={
                        "simbolo": sinal.simbolo,
                        "confidence": ai_decision["confidence"],
                        "source": ai_decision["source"],
                        "sinal_original": sinal.to_dict(),
                    }
                )
                return "VETADO_POR_IA"
        
        # === EXECUÇÃO MECÂNICA (se IA não vetou) ===
        async with UnitOfWork(self._conexao_factory) as uow:
            resultado = await self._executor.criar_ordem_market(...)
            # ... persistência atômica ...
```

---

## 4.9 Wiring no Lifespan (Startup)

```python
# src/main.py — adicionar no lifespan

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... bootstrap existente ...
    
    # === INICIALIZAR CAMADA AGÊNTICA GEMINI ===
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if gemini_api_key:
        from src.intelligence.gemini_client import GeminiClient
        from src.intelligence.context_builder import ContextBuilder
        from src.intelligence.pre_execution_filter import PreExecutionFilter
        from src.intelligence.post_trade_auditor import PostTradeAuditor
        
        gemini_client = GeminiClient(api_key=gemini_api_key)
        context_builder = ContextBuilder(
            repo_ordens=RepositorioOrdens(db),
            repo_ohlcv=RepositorioOHLCV(db),
            repo_features=RepositorioFeatures(db)
        )
        
        # Filtro de pré-execução (interceptor no autotrader)
        ai_filter = PreExecutionFilter(
            gemini=gemini_client,
            context_builder=context_builder,
            enabled=os.getenv("AI_FILTER_ENABLED", "true").lower() == "true"
        )
        app.state.ai_filter = ai_filter
        
        # Auditor pós-trade (cron 2h)
        auditor = PostTradeAuditor(
            gemini=gemini_client,
            context_builder=context_builder,
            repo_audit=RepositorioAudit(db)
        )
        app.state.tasks.append(
            asyncio.create_task(auditor.run_loop(shutdown_event))
        )
        
        log.info("✅ Camada agêntica Gemini inicializada")
    else:
        log.warning("⚠️ GEMINI_API_KEY não configurada — camada agêntica desativada")
        app.state.ai_filter = None
    
    # ... restante do lifespan ...
```

---

## 4.10 API Endpoints para a Camada Agêntica

```python
# Adicionar em src/main.py

@router.get("/v1/ai/saude")
async def ai_saude(request: Request):
    """Status da camada agêntica Gemini."""
    gemini = getattr(request.app.state, "gemini_client", None)
    if gemini is None:
        return {"disponivel": False, "motivo": "GEMINI_API_KEY não configurada"}
    return gemini.health()

@router.get("/v1/ai/auditorias")
async def ai_auditorias_recentes(limit: int = 10):
    """Últimas auditorias pós-trade da IA."""
    repo = RepositorioAudit(db)
    auditorias = await repo.listar_por_componente(
        componente="post_trade_auditor", limite=limit
    )
    return {"auditorias": auditorias}

@router.get("/v1/ai/vetos")
async def ai_vetos_recentes(limit: int = 20):
    """Operações vetadas pela IA (para análise de eficácia)."""
    repo = RepositorioAudit(db)
    vetos = await repo.listar_por_componente(
        componente="ai_pre_execution_filter", limite=limit
    )
    return {"vetos": vetos}

@router.post("/v1/ai/regime")
async def ai_analisar_regime(simbolo: str):
    """Análise de regime macro via IA (sob demanda)."""
    gemini = request.app.state.gemini_client
    context_builder = request.app.state.context_builder
    
    contexto = await context_builder.build_regime_context(simbolo)
    resultado = await gemini.analyze(
        system_prompt=REGIME_ANALYSIS_PROMPT,
        user_context=contexto,
        temperature=0.2
    )
    return resultado or {"erro": "IA indisponível"}
```

---

## 4.11 Configuração `.env` para Gemini

```bash
# .env.production — adicionar

# === CAMADA AGÊNTICA GEMINI ===
GEMINI_API_KEY=sua_chave_aqui
AI_FILTER_ENABLED=true                    # Filtro de pré-execução
AI_AUDITOR_ENABLED=true                   # Cron de auditoria 2h
AI_FILTER_TIMEOUT_SECONDS=12              # Hard limit
AI_FILTER_MIN_CONFIDENCE_ABORT=0.70       # Confiança mínima para veto
AI_MAX_CALLS_PER_DAY=50                   # Cost-control
AI_MAX_CALLS_PER_HOUR=10
AI_COOLDOWN_AFTER_FAILURES=5
AI_COOLDOWN_MINUTES=60
```

---

## 4.12 Métricas de Eficácia da Camada Agêntica

Para validar se a IA está **realmente agregando valor** (e não apenas bloqueando trades bons):

```python
# src/observabilidade/metricas_ai.py
from prometheus_client import Counter, Histogram, Gauge

# Contadores
AI_VETOS_TOTAL = Counter("oraculo_ai_vetos_total", "Operações vetadas pela IA",
                         ["simbolo", "estrategia", "source"])
AI_PROCEEDS_TOTAL = Counter("oraculo_ai_proceeds_total", "Operações aprovadas pela IA",
                            ["simbolo", "estrategia"])
AI_TIMEOUTS_TOTAL = Counter("oraculo_ai_timeouts_total", "Timeouts da IA no filtro")
AI_FAILURES_TOTAL = Counter("oraculo_ai_failures_total", "Falhas da IA", ["error_type"])

# Histogramas
AI_LATENCY_SECONDS = Histogram("oraculo_ai_latency_seconds",
                                "Latência da chamada Gemini",
                                buckets=[0.5, 1, 2, 5, 10, 15])
AI_CONFIDENCE = Histogram("oraculo_ai_confidence",
                          "Confiança reportada pela IA",
                          buckets=[0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 1.0])

# Gauges
AI_AVAILABLE = Gauge("oraculo_ai_available", "IA disponível (1) ou em cooldown (0)")
AI_CALLS_TODAY = Gauge("oraculo_ai_calls_today", "Chamadas Gemini hoje")
```

**Dashboard Grafana para validar eficácia:**
- Painel 1: Trades vetados pela IA vs. resultado real (se o trade fosse executado, teria ganho ou perdido?) — precisa de shadow testing
- Painel 2: Win rate com IA vs. sem IA (comparar períodos)
- Painel 3: Latência da IA (P95 deve ser < 10s)
- Painel 4: Custo da IA (chamadas/dia × custo por chamada)

---

# 📋 RESUMO EXECUTIVO — ORDEM DE EXECUÇÃO

| Prioridade | Tarefa | Fase | Esforço | Impacto |
|-----------|--------|------|---------|---------|
| P0 | Ativar UoW (atomicidade exec+persist) | F2 | 4h | CATASTRÓFICO → mitigado |
| P0 | `chave_intencao` obrigatória no autotrader | F1 | 1h | ALTO → mitigado |
| P0 | Assinar modelos HMAC (anti-RCE) | F3 | 3h | CATASTRÓFICO → mitigado |
| P0 | Rate-limit nos endpoints (slowapi) | F3 | 2h | ALTO → mitigado |
| P0 | XSS escape em `/v1/noticias/frame` | F3 | 1h | ALTO → mitigado |
| P0 | Path traversal em `/v1/img/{filename}` | F3 | 1h | ALTO → mitigado |
| P1 | Mover ML para ProcessPoolExecutor | F2 | 8h | ALTO (latência) → mitigado |
| P1 | Decompor god-file `testnet_auto_trader.py` | F2 | 16h | ALTO (dívida técnica) |
| P1 | Kill-switch financeiro (file-based) | F3 | 2h | CATASTRÓFICO → mitigado |
| P1 | Signal handlers SIGTERM/SIGINT | F3 | 2h | MÉDIO → mitigado |
| P1 | Dockerfile + docker-compose | F3 | 4h | Deploy production-ready |
| P1 | Backup SQLite automatizado | F3 | 2h | ALTO → mitigado |
| P2 | Calibrar INC-01 (consenso) com backtest | F2 | 4h | MÉDIO (requer dados) |
| P2 | Slippage realizado (feedback loop) | F2 | 6h | MÉDIO |
| P2 | Pin de dependências por hash | F3 | 2h | MÉDIO → mitigado |
| P2 | CSRF + COOKIE_SECURE=true | F3 | 2h | MÉDIO → mitigado |
| P2 | Deletar `circuit_breaker.py` dormente | F2 | 1h | MÉDIO (clareza) |
| P3 | **Integração Gemini (camada agêntica)** | F4 | 24h | **Filtro de assimetria + auditor** |
| P3 | Prometheus + AlertManager + Grafana | F3 | 8h | Monitoramento production |
| P3 | Webhook Telegram para alertas | F3 | 2h | Notificação crítica |
| P3 | Caddy reverse proxy + TLS + headers | F3 | 2h | Hardening network |

---

## 🏁 VEREDITO FINAL

O Oráculo é **engenharia sólida e segura**. Os 186 testes verdes, os 10 bugs herdados eliminados, os 20 decisões arquiteturais documentadas, e o gate de edge **honestamente fechado** (sem edge nos dados) demonstram maturidade técnica rara.

**A lucratividade não é problema de código** — é problema de **sinal/edge**. A camada Gemini não vai *criar* edge onde não existe; vai **filtrar falsos positivos** e **identificar padrões de perda** que o código rígido não enxerga, reduzindo o drawdown e preservando capital para quando o edge surgir.

**A missão agora é:**
1. Fechar as 6 lacunas críticas de P0 (atomicidade, RCE, XSS, rate-limit)
2. Decompor o god-file (dívida técnica que impede evolução)
3. Containerizar para deploy reproducível
4. Integrar Gemini como **cérebro consultivo** sobre o músculo mecânico
5. Coletar dados contínuos e perseguir edge empiricamente

**A falha não é uma opção. O capital perdido não volta. Na dúvida, NÃO opera.**

> *"Esperto, rápido, seguro, lucrativo e principalmente seguro."* — Diretriz do projeto, honrada em cada linha de código.