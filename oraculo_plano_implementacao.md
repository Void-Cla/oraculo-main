# Oráculo — Plano de Implementação Completo
> Documento gerado para execução autônoma por agente de IA.  
> Linguagem do projeto: **Python (PT-BR)** — manter toda nomenclatura, semântica e comentários em português brasileiro.  
> Princípios: código **enxuto**, **resiliente**, **seguro**, separação clara de responsabilidades.

---

## Índice

1. [Contexto e arquitetura atual](#1-contexto-e-arquitetura-atual)
2. [Princípios obrigatórios](#2-princípios-obrigatórios)
3. [Melhoria 1 — Retomada autônoma após pausa](#3-melhoria-1--retomada-autônoma-após-pausa)
4. [Melhoria 2 — Filtro de EV mínimo líquido](#4-melhoria-2--filtro-de-ev-mínimo-líquido)
5. [Melhoria 3 — Calibração contínua ao religar](#5-melhoria-3--calibração-contínua-ao-religar)
6. [Melhoria 4 — Snapshot de estado persistido](#6-melhoria-4--snapshot-de-estado-persistido)
7. [Melhoria 5 — Detector de drift pós-pausa](#7-melhoria-5--detector-de-drift-pós-pausa)
8. [Melhoria 6 — Audit trail enriquecido](#8-melhoria-6--audit-trail-enriquecido)
9. [Integração entre melhorias — fluxo de inicialização](#9-integração-entre-melhorias--fluxo-de-inicialização)
10. [Variáveis de ambiente novas](#10-variáveis-de-ambiente-novas)
11. [Schema SQL — alterações necessárias](#11-schema-sql--alterações-necessárias)
12. [Testes obrigatórios](#12-testes-obrigatórios)
13. [Checklist de execução por ordem](#13-checklist-de-execução-por-ordem)

---

## 1. Contexto e arquitetura atual

O Oráculo é um orquestrador de sinais de trading que coleta dados da Binance, gera features, roda modelos (online SGDRegressor + batch joblib), calibra previsões via bandit/EWLS, combina consenso de múltiplas fontes e executa ordens por usuário.

### Estrutura relevante para este plano

```
src/
├── binance_api/          # coleta REST/WS — NÃO decide trades
├── calculos/             # gerador_features.py
├── calibracao/           # bandit.py, ewls.py
├── modelagem/            # gerenciador_modelo.py, preditor.py
├── sinais/               # signal_engine.py, consenso.py, fila_sinais.py
├── risco/                # risk_engine.py
├── executor/             # executor_isolado_usuario.py, gerenciador_ordens.py
├── persistencia/         # conexao.py (DDL_BASE), repositórios
├── tarefas/              # loops de background
├── servicos/             # dashboard, sessoes, noticias
├── observabilidade/      # logger.py, metricas.py
└── main.py               # FastAPI + inicialização
```

### Banco de dados (SQLite) — tabelas existentes relevantes

| Tabela | Uso |
|---|---|
| `ordens` | histórico de ordens (status, modo, detalhe_json) |
| `predictions` | previsões com y_hat, y_cal, p_conf, meta_json |
| `outcomes` | resultado real das previsões |
| `config` | pares chave/valor dinâmicos |
| `audit` | eventos de auditoria |
| `fila_sinais` | fila durável de sinais |
| `ohlcv_1m` | candles de 1 minuto |
| `features_1m` | features calculadas |

---

## 2. Princípios obrigatórios

Toda IA que implementar este plano **deve** seguir:

- [ ] **PT-BR obrigatório**: nomes de variáveis, funções, classes, comentários, logs e mensagens de erro em português brasileiro. Exemplo: `avaliar_retomada`, não `evaluate_resume`.
- [ ] **Código enxuto**: sem over-engineering. Se cabe em 20 linhas, não escreva 80.
- [ ] **Sem prejuízo automático**: nenhuma ação que possa causar perda financeira deve ser tomada sem checagem prévia de contexto de mercado.
- [ ] **Separação de responsabilidades**: cada módulo novo deve ter escopo único, sem acoplar coleta + decisão + execução no mesmo arquivo.
- [ ] **Falha segura**: em caso de exceção não tratada, o bot deve parar de operar e registrar no audit, nunca silenciar o erro e continuar enviando ordens.
- [ ] **Idempotência**: religar o bot duas vezes seguidas deve produzir o mesmo resultado que ligar uma vez.
- [ ] **Sem dependências novas desnecessárias**: usar apenas o que já está em `requirements.txt` a menos que seja absolutamente necessário.

---

## 3. Melhoria 1 — Retomada autônoma após pausa

### Objetivo

Quando o bot religar após qualquer pausa (minutos, horas ou dias), ele deve:
1. Detectar automaticamente o tempo parado
2. Avaliar quanto o mercado se moveu nesse período
3. Decidir o modo de retomada correto (observação, calibração, operação normal)
4. Nunca abrir posição sem entender o estado atual do mercado

### Arquivo a criar

**`src/tarefas/retomada.py`**

```python
"""
Módulo de retomada autônoma do Oráculo.
Avalia contexto de pausa e decide modo de inicialização segura.
"""
import asyncio
from datetime import datetime, timezone
from typing import Literal

from src.observabilidade.logger import get_logger
from src.persistencia.conexao import obter_conexao

log = get_logger(__name__)

ModoRetomada = Literal["normal", "observacao", "recalibracao_forcada"]

# Limiares configuráveis via env (ver seção 10)
import os
PAUSA_MEDIA_HORAS    = float(os.getenv("RETOMADA_PAUSA_MEDIA_H", "4"))
PAUSA_LONGA_HORAS    = float(os.getenv("RETOMADA_PAUSA_LONGA_H", "24"))
VARIACAO_RELEVANTE_PCT = float(os.getenv("RETOMADA_VARIACAO_PCT", "3.0"))


async def avaliar_retomada(simbolo: str) -> dict:
    """
    Avalia o estado do bot após pausa e retorna contexto de retomada.

    Retorna dict com:
        modo: ModoRetomada
        horas_parado: float
        variacao_pct: float | None
        preco_ultima_ordem: float | None
        preco_atual: float | None
        mensagem: str
    """
    ultima = await _obter_ultima_ordem(simbolo)
    agora = datetime.now(timezone.utc)

    if ultima is None:
        return _resultado("normal", 0.0, None, None, None,
                          "Sem histórico — inicialização limpa.")

    horas_parado = (agora - ultima["ts"]).total_seconds() / 3600
    preco_anterior = ultima.get("preco_execucao")
    preco_atual = await _obter_preco_atual(simbolo)

    variacao_pct = None
    if preco_anterior and preco_atual:
        variacao_pct = abs((preco_atual - preco_anterior) / preco_anterior) * 100

    modo = _determinar_modo(horas_parado, variacao_pct)

    msg = (
        f"Parado {horas_parado:.1f}h | "
        f"variação {variacao_pct:.2f}% | "
        f"modo={modo}"
    ) if variacao_pct is not None else f"Parado {horas_parado:.1f}h | modo={modo}"

    log.info("retomada_avaliada", extra={"modo": modo, "horas": horas_parado,
                                          "variacao_pct": variacao_pct})
    return _resultado(modo, horas_parado, variacao_pct,
                      preco_anterior, preco_atual, msg)


def _determinar_modo(horas: float, variacao_pct: float | None) -> ModoRetomada:
    """Regra de decisão do modo de retomada — pura, sem side-effects."""
    if horas >= PAUSA_LONGA_HORAS:
        return "recalibracao_forcada"
    if horas >= PAUSA_MEDIA_HORAS:
        return "observacao"
    if variacao_pct is not None and variacao_pct >= VARIACAO_RELEVANTE_PCT:
        return "observacao"
    return "normal"


def _resultado(modo, horas, variacao, preco_ant, preco_atual, msg) -> dict:
    return {
        "modo": modo,
        "horas_parado": horas,
        "variacao_pct": variacao,
        "preco_ultima_ordem": preco_ant,
        "preco_atual": preco_atual,
        "mensagem": msg,
    }


async def _obter_ultima_ordem(simbolo: str) -> dict | None:
    """Lê a última ordem executada do SQLite para o símbolo dado."""
    async with obter_conexao() as conn:
        row = await conn.fetchone(
            """
            SELECT criado_em, detalhe_json
            FROM ordens
            WHERE simbolo = ? AND status = 'executada'
            ORDER BY criado_em DESC LIMIT 1
            """,
            (simbolo,),
        )
    if row is None:
        return None
    import json
    detalhe = json.loads(row["detalhe_json"] or "{}")
    return {
        "ts": datetime.fromisoformat(row["criado_em"]).replace(tzinfo=timezone.utc),
        "preco_execucao": detalhe.get("preco_execucao"),
    }


async def _obter_preco_atual(simbolo: str) -> float | None:
    """Tenta obter preço atual da Binance. Retorna None em caso de falha."""
    try:
        from src.binance_api.cliente import ClienteBinance
        cliente = ClienteBinance()
        return await cliente.obter_preco_atual(simbolo)
    except Exception as exc:
        log.warning("preco_atual_indisponivel", extra={"erro": str(exc)})
        return None
```

### Arquivo a criar

**`src/tarefas/observacao.py`**

```python
"""
Loop de observação: bot aguarda N candles antes de operar após retomada.
"""
import asyncio
import os
from src.observabilidade.logger import get_logger

log = get_logger(__name__)
CANDLES_OBSERVACAO = int(os.getenv("RETOMADA_CANDLES_OBSERVACAO", "5"))


async def aguardar_observacao(simbolo: str, intervalo_segundos: int = 60) -> None:
    """
    Bloqueia operações por CANDLES_OBSERVACAO candles após retomada em modo observação.
    Registra progresso em log.
    """
    log.info("observacao_iniciada", extra={"candles": CANDLES_OBSERVACAO, "simbolo": simbolo})
    for i in range(1, CANDLES_OBSERVACAO + 1):
        await asyncio.sleep(intervalo_segundos)
        log.info("observacao_progresso", extra={"candle": i, "total": CANDLES_OBSERVACAO})
    log.info("observacao_concluida", extra={"simbolo": simbolo})
```

### Onde integrar

**`src/main.py`** — no evento `startup` do FastAPI, após `inicializar_db()`:

```python
# Trecho a ADICIONAR em main.py dentro do @app.on_event("startup")
from src.tarefas.retomada import avaliar_retomada
from src.tarefas.observacao import aguardar_observacao
from src.observabilidade.logger import get_logger

log = get_logger(__name__)

simbolo_principal = os.getenv("SIMBOLO_PRINCIPAL", "BTCUSDT")
ctx_retomada = await avaliar_retomada(simbolo_principal)
log.info("contexto_retomada", extra=ctx_retomada)

if ctx_retomada["modo"] == "recalibracao_forcada":
    # Aciona calibração antes de qualquer operação (ver Melhoria 3)
    from src.tarefas.recalibracao_startup import recalibrar_ao_religar
    await recalibrar_ao_religar(simbolo_principal)

elif ctx_retomada["modo"] == "observacao":
    # Agenda observação em background sem bloquear startup
    asyncio.create_task(aguardar_observacao(simbolo_principal))

# Persiste contexto no config para outros módulos consultarem
from src.persistencia.repositorio_config import salvar_config
await salvar_config("retomada_modo", ctx_retomada["modo"])
await salvar_config("retomada_horas_parado", str(ctx_retomada["horas_parado"]))
```

### Checklist desta melhoria

- [ ] Criar `src/tarefas/retomada.py` conforme código acima
- [ ] Criar `src/tarefas/observacao.py` conforme código acima
- [ ] Verificar se `obter_conexao()` em `persistencia/conexao.py` suporta `async with` — se não, adaptar `_obter_ultima_ordem` para o padrão existente do projeto
- [ ] Verificar se `ClienteBinance` tem método `obter_preco_atual` — se o nome for diferente, ajustar em `_obter_preco_atual`
- [ ] Verificar se a tabela `ordens` tem coluna `simbolo` — se não tiver, usar `detalhe_json` com `json_extract(detalhe_json, '$.simbolo')`
- [ ] Adicionar integração no `startup` do `main.py`
- [ ] Adicionar variáveis de ambiente (seção 10) ao `.env.example`
- [ ] Escrever teste `tests/test_retomada.py` (seção 12)

---

## 4. Melhoria 2 — Filtro de EV mínimo líquido

### Objetivo

Nenhuma ordem deve ser aprovada com expected value líquido (após taxas da Binance + slippage estimado) menor que **1,00 USDT**. Este filtro deve ser aplicado **antes** de qualquer ordem chegar ao executor.

### Conceito

```
EV_liquido = (prob_up × ganho_bruto) - (prob_down × perda_bruta) - taxa_total - slippage
taxa_total  = valor_ordem × (taxa_maker + taxa_taker)  # normalmente 0.075% + 0.075%
slippage    = valor_ordem × slippage_estimado_pct       # ex: 0.05%
```

### Arquivo a criar

**`src/risco/filtro_ev.py`**

```python
"""
Filtro de expected value líquido mínimo.
Rejeita operações cujo EV líquido seja inferior ao limiar configurado.
"""
import os
from src.observabilidade.logger import get_logger

log = get_logger(__name__)

EV_MINIMO_USDT   = float(os.getenv("FILTRO_EV_MINIMO_USDT", "1.0"))
TAXA_MAKER_PCT   = float(os.getenv("BINANCE_TAXA_MAKER_PCT", "0.075")) / 100
TAXA_TAKER_PCT   = float(os.getenv("BINANCE_TAXA_TAKER_PCT", "0.075")) / 100
SLIPPAGE_PCT     = float(os.getenv("SIGNAL_slippage", "0.05")) / 100


def calcular_ev_liquido(
    prob_up: float,
    prob_down: float,
    ganho_bruto_usdt: float,
    perda_bruta_usdt: float,
    valor_ordem_usdt: float,
    usar_taker: bool = True,
) -> float:
    """
    Calcula EV líquido de uma operação em USDT.

    Args:
        prob_up: probabilidade de subida (0.0 a 1.0)
        prob_down: probabilidade de queda (0.0 a 1.0)
        ganho_bruto_usdt: ganho em USDT se direção correta
        perda_bruta_usdt: perda em USDT se direção errada (valor positivo)
        valor_ordem_usdt: valor total da ordem em USDT
        usar_taker: se True usa taxa taker, senão maker

    Returns:
        EV líquido em USDT (negativo = operação desfavorável)
    """
    taxa = TAXA_TAKER_PCT if usar_taker else TAXA_MAKER_PCT
    custo_taxa = valor_ordem_usdt * taxa * 2  # entrada + saída
    custo_slippage = valor_ordem_usdt * SLIPPAGE_PCT
    ev_bruto = (prob_up * ganho_bruto_usdt) - (prob_down * perda_bruta_usdt)
    return ev_bruto - custo_taxa - custo_slippage


def sinal_passa_filtro_ev(
    prob_up: float,
    prob_down: float,
    ganho_bruto_usdt: float,
    perda_bruta_usdt: float,
    valor_ordem_usdt: float,
    usar_taker: bool = True,
) -> tuple[bool, float]:
    """
    Verifica se sinal passa pelo filtro de EV mínimo.

    Returns:
        (passou, ev_liquido_usdt)
    """
    ev = calcular_ev_liquido(
        prob_up, prob_down, ganho_bruto_usdt,
        perda_bruta_usdt, valor_ordem_usdt, usar_taker
    )
    passou = ev >= EV_MINIMO_USDT
    if not passou:
        log.info(
            "sinal_rejeitado_ev_insuficiente",
            extra={"ev_calculado": round(ev, 4), "ev_minimo": EV_MINIMO_USDT},
        )
    return passou, ev
```

### Onde integrar

**`src/risco/risk_engine.py`** — dentro de `avaliar_sinal_para_usuario`, antes de retornar aprovado:

```python
# ADICIONAR no risk_engine.py, após calcular sizing e antes de retornar aprovado
from src.risco.filtro_ev import sinal_passa_filtro_ev

passou_ev, ev_liquido = sinal_passa_filtro_ev(
    prob_up=sinal.get("prob_up", 0.5),
    prob_down=sinal.get("prob_down", 0.5),
    ganho_bruto_usdt=sinal.get("take_profit_usdt", 0.0),
    perda_bruta_usdt=sinal.get("stop_loss_usdt", 0.0),
    valor_ordem_usdt=sizing.get("valor_usdt", 0.0),
)
if not passou_ev:
    return {"aprovado": False, "motivo": f"ev_insuficiente({ev_liquido:.3f}usdt)"}

# Enriquecer sinal com EV calculado para audit
sinal["ev_liquido_usdt"] = ev_liquido
```

> **Atenção**: adaptar os nomes dos campos (`prob_up`, `take_profit_usdt`, etc.) conforme os contratos reais em `src/contratos/`. Se os campos tiverem nomes diferentes, mapear corretamente sem renomear os contratos existentes.

### Checklist desta melhoria

- [ ] Criar `src/risco/filtro_ev.py` conforme código acima
- [ ] Localizar `avaliar_sinal_para_usuario` em `src/risco/risk_engine.py`
- [ ] Verificar os campos reais do dicionário `sinal` em `risk_engine.py` e mapear corretamente para `filtro_ev`
- [ ] Adicionar chamada ao `filtro_ev` após cálculo de sizing, antes do retorno positivo
- [ ] Garantir que `ev_liquido_usdt` seja salvo no `detalhe_json` da ordem em `ordens`
- [ ] Garantir que `motivo` de rejeição seja salvo no `audit` (ver Melhoria 6)
- [ ] Adicionar variáveis `FILTRO_EV_MINIMO_USDT`, `BINANCE_TAXA_MAKER_PCT`, `BINANCE_TAXA_TAKER_PCT` ao `.env.example`
- [ ] Escrever teste `tests/test_filtro_ev.py` (seção 12)

---

## 5. Melhoria 3 — Calibração contínua ao religar

### Objetivo

Ao religar o bot após pausa longa (`modo == "recalibracao_forcada"`), executar `partial_fit` no modelo online com os últimos N candles persistidos no banco, antes de qualquer operação. Isso garante que o modelo não opere com distribuição defasada.

### Arquivo a criar

**`src/tarefas/recalibracao_startup.py`**

```python
"""
Recalibração do modelo online ao religar após pausa longa.
Usa dados históricos do banco para atualizar distribuição do SGDRegressor.
"""
import os
import json
from src.observabilidade.logger import get_logger
from src.persistencia.conexao import obter_conexao
from src.modelagem.gerenciador_modelo import GerenciadorModelo

log = get_logger(__name__)
CANDLES_RECALIBRACAO = int(os.getenv("RECALIBRACAO_CANDLES", "60"))


async def recalibrar_ao_religar(simbolo: str) -> dict:
    """
    Faz partial_fit com últimos CANDLES_RECALIBRACAO registros de features+outcomes.

    Returns:
        dict com quantidade de amostras usadas e status.
    """
    amostras = await _carregar_amostras_recentes(simbolo)
    if not amostras:
        log.warning("recalibracao_sem_amostras", extra={"simbolo": simbolo})
        return {"status": "sem_dados", "amostras": 0}

    gerenciador = GerenciadorModelo()
    atualizados = 0
    for feat, y_real in amostras:
        try:
            gerenciador.partial_fit(feat, y_real)
            atualizados += 1
        except Exception as exc:
            log.warning("partial_fit_erro", extra={"erro": str(exc)})

    gerenciador.salvar()
    log.info("recalibracao_concluida", extra={"amostras": atualizados, "simbolo": simbolo})
    return {"status": "ok", "amostras": atualizados}


async def _carregar_amostras_recentes(simbolo: str) -> list[tuple[dict, float]]:
    """
    Carrega últimos N pares (features, y_real) do banco.
    y_real vem de outcomes linkados às predictions.
    """
    async with obter_conexao() as conn:
        rows = await conn.fetchall(
            """
            SELECT f.features_json, o.y_real
            FROM features_1m f
            JOIN predictions p ON p.ts = f.ts AND p.simbolo = f.simbolo
            JOIN outcomes o ON o.prediction_id = p.id
            WHERE f.simbolo = ?
            ORDER BY f.ts DESC
            LIMIT ?
            """,
            (simbolo, CANDLES_RECALIBRACAO),
        )
    return [
        (json.loads(r["features_json"]), float(r["y_real"]))
        for r in rows
        if r["features_json"] and r["y_real"] is not None
    ]
```

> **Atenção**: verificar nomes reais das colunas nas tabelas `features_1m`, `predictions` e `outcomes`. Adaptar a query sem alterar o schema — se os nomes diferirem, ajustar apenas os aliases na query.

### Checklist desta melhoria

- [ ] Criar `src/tarefas/recalibracao_startup.py` conforme código acima
- [ ] Verificar assinatura de `GerenciadorModelo.partial_fit` — se recebe array numpy, converter o dicionário de features para array respeitando a ordem de `FEATURE_ORDER`
- [ ] Verificar nomes reais das colunas: `features_1m.features_json`, `predictions.ts`, `outcomes.y_real`, `outcomes.prediction_id`
- [ ] Confirmar que `GerenciadorModelo.salvar()` persiste em `MODEL_DIR` sem efeitos colaterais
- [ ] Integrar chamada em `main.py` (já indicado na Melhoria 1 — `startup`)
- [ ] Adicionar variável `RECALIBRACAO_CANDLES` ao `.env.example`
- [ ] Escrever teste `tests/test_recalibracao_startup.py` (seção 12)

---

## 6. Melhoria 4 — Snapshot de estado persistido

### Objetivo

A cada operação relevante (ordem enviada, sinal rejeitado, modo de operação alterado), persistir um snapshot do estado atual do bot numa tabela dedicada. Isso permite que ao religar, o bot tenha contexto completo sem depender de memória em processo.

### Alteração no schema (ver seção 11)

Nova tabela: `snapshot_estado`

### Arquivo a criar

**`src/persistencia/repositorio_snapshot.py`**

```python
"""
Repositório de snapshots de estado do bot.
Persiste e recupera o último estado conhecido de forma atômica.
"""
import json
from datetime import datetime, timezone
from src.persistencia.conexao import obter_conexao


async def salvar_snapshot(simbolo: str, estado: dict) -> None:
    """
    Upsert do snapshot de estado para o símbolo.
    Substitui o anterior — mantém apenas o mais recente por símbolo.
    """
    agora = datetime.now(timezone.utc).isoformat()
    async with obter_conexao() as conn:
        await conn.execute(
            """
            INSERT INTO snapshot_estado (simbolo, estado_json, atualizado_em)
            VALUES (?, ?, ?)
            ON CONFLICT(simbolo) DO UPDATE SET
                estado_json = excluded.estado_json,
                atualizado_em = excluded.atualizado_em
            """,
            (simbolo, json.dumps(estado, ensure_ascii=False), agora),
        )


async def obter_snapshot(simbolo: str) -> dict | None:
    """Retorna o último snapshot do símbolo ou None."""
    async with obter_conexao() as conn:
        row = await conn.fetchone(
            "SELECT estado_json FROM snapshot_estado WHERE simbolo = ?",
            (simbolo,),
        )
    return json.loads(row["estado_json"]) if row else None
```

### O que salvar no snapshot

O estado deve conter, no mínimo:

```python
estado = {
    "modo_operacao": "normal" | "observacao" | "recalibracao_forcada" | "pausado",
    "ultima_ordem": {
        "id": str,
        "lado": "COMPRA" | "VENDA",
        "preco_execucao": float,
        "quantidade": float,
        "ts": str,  # ISO 8601
    },
    "posicao_aberta": bool,
    "lado_posicao": "LONG" | "SHORT" | None,
    "p_conf_ultimo": float,  # confiança da última previsão
    "ev_liquido_ultimo": float,
}
```

### Onde integrar

Em `src/executor/executor_isolado_usuario.py`, após confirmação de ordem executada:

```python
# ADICIONAR após ordem executada com sucesso
from src.persistencia.repositorio_snapshot import salvar_snapshot

await salvar_snapshot(simbolo, {
    "modo_operacao": modo_atual,
    "ultima_ordem": {
        "id": ordem_id,
        "lado": lado,
        "preco_execucao": preco,
        "quantidade": quantidade,
        "ts": datetime.now(timezone.utc).isoformat(),
    },
    "posicao_aberta": True,
    "lado_posicao": lado_posicao,
    "p_conf_ultimo": p_conf,
    "ev_liquido_ultimo": ev_liquido,
})
```

### Checklist desta melhoria

- [ ] Adicionar tabela `snapshot_estado` ao DDL em `persistencia/conexao.py` (seção 11)
- [ ] Criar `src/persistencia/repositorio_snapshot.py` conforme código acima
- [ ] Localizar onde a ordem é confirmada em `executor_isolado_usuario.py` e adicionar `salvar_snapshot`
- [ ] Mapear campos reais disponíveis no executor e adaptar o dicionário de estado
- [ ] Usar `obter_snapshot` na Melhoria 1 (`retomada.py`) para enriquecer o contexto de retomada
- [ ] Escrever teste `tests/test_repositorio_snapshot.py` (seção 12)

---

## 7. Melhoria 5 — Detector de drift pós-pausa

### Objetivo

Após pausa longa, comparar as estatísticas de mercado atuais (volatilidade, spread, volume) com as do período anterior ao pause. Se houver drift significativo, forçar modo observação independente do tempo parado.

### Arquivo a criar

**`src/sinais/detector_drift.py`**

```python
"""
Detector de drift de mercado pós-pausa.
Compara distribuição de features pré e pós pausa para detectar mudança de regime.
"""
import os
import json
import math
from src.observabilidade.logger import get_logger
from src.persistencia.conexao import obter_conexao

log = get_logger(__name__)
DRIFT_VOLATILIDADE_THRESHOLD = float(os.getenv("DRIFT_VOLATILIDADE_THRESHOLD", "2.0"))
JANELA_PRE_PAUSA_CANDLES = int(os.getenv("DRIFT_JANELA_CANDLES", "30"))


async def detectar_drift(simbolo: str, ts_pausa_inicio: str) -> dict:
    """
    Compara volatilidade antes e depois da pausa.

    Args:
        simbolo: par de trading
        ts_pausa_inicio: timestamp ISO do início da pausa

    Returns:
        dict com: drift_detectado (bool), razao_volatilidade (float), mensagem (str)
    """
    vol_pre  = await _calcular_volatilidade(simbolo, antes_de=ts_pausa_inicio)
    vol_pos  = await _calcular_volatilidade_recente(simbolo, n=JANELA_PRE_PAUSA_CANDLES)

    if vol_pre is None or vol_pos is None or vol_pre == 0:
        return {"drift_detectado": False, "razao_volatilidade": None,
                "mensagem": "dados insuficientes para detectar drift"}

    razao = vol_pos / vol_pre
    drift = razao >= DRIFT_VOLATILIDADE_THRESHOLD or razao <= (1 / DRIFT_VOLATILIDADE_THRESHOLD)

    log.info("drift_avaliado", extra={
        "simbolo": simbolo, "vol_pre": round(vol_pre, 6),
        "vol_pos": round(vol_pos, 6), "razao": round(razao, 3), "drift": drift,
    })
    return {
        "drift_detectado": drift,
        "razao_volatilidade": round(razao, 3),
        "mensagem": f"vol_pre={vol_pre:.6f} vol_pos={vol_pos:.6f} razao={razao:.2f}",
    }


async def _calcular_volatilidade(simbolo: str, antes_de: str) -> float | None:
    """Desvio padrão de close nos N candles antes do ts_pausa_inicio."""
    async with obter_conexao() as conn:
        rows = await conn.fetchall(
            """
            SELECT close FROM ohlcv_1m
            WHERE simbolo = ? AND ts < ?
            ORDER BY ts DESC LIMIT ?
            """,
            (simbolo, antes_de, JANELA_PRE_PAUSA_CANDLES),
        )
    return _desvio_padrao([r["close"] for r in rows])


async def _calcular_volatilidade_recente(simbolo: str, n: int) -> float | None:
    """Desvio padrão de close nos últimos N candles."""
    async with obter_conexao() as conn:
        rows = await conn.fetchall(
            "SELECT close FROM ohlcv_1m WHERE simbolo = ? ORDER BY ts DESC LIMIT ?",
            (simbolo, n),
        )
    return _desvio_padrao([r["close"] for r in rows])


def _desvio_padrao(valores: list[float]) -> float | None:
    """Desvio padrão amostral. Retorna None se menos de 2 valores."""
    if len(valores) < 2:
        return None
    media = sum(valores) / len(valores)
    variancia = sum((v - media) ** 2 for v in valores) / (len(valores) - 1)
    return math.sqrt(variancia)
```

### Onde integrar

Em `src/tarefas/retomada.py`, na função `avaliar_retomada`:

```python
# ADICIONAR em avaliar_retomada, após calcular horas_parado
from src.sinais.detector_drift import detectar_drift

if ultima is not None:
    resultado_drift = await detectar_drift(simbolo, ultima["ts"].isoformat())
    if resultado_drift["drift_detectado"] and modo == "normal":
        modo = "observacao"  # drift força observação mesmo em pausa curta
        log.info("modo_elevado_por_drift", extra=resultado_drift)
```

### Checklist desta melhoria

- [ ] Criar `src/sinais/detector_drift.py` conforme código acima
- [ ] Verificar nome da coluna `close` em `ohlcv_1m` — pode ser `preco_fechamento` ou similar
- [ ] Integrar em `retomada.py` conforme indicado
- [ ] Adicionar variáveis `DRIFT_VOLATILIDADE_THRESHOLD`, `DRIFT_JANELA_CANDLES` ao `.env.example`
- [ ] Escrever teste `tests/test_detector_drift.py` (seção 12)

---

## 8. Melhoria 6 — Audit trail enriquecido

### Objetivo

Cada entrada na tabela `audit` deve incluir: motivo da decisão, valores relevantes (EV, prob_up, modo, etc.) e qual componente gerou o evento. Isso permite rastrear completamente por que cada ordem foi aprovada ou rejeitada.

### Alteração na tabela `audit` (ver seção 11)

Adicionar colunas: `componente`, `motivo`, `meta_json`.

### Arquivo a criar

**`src/observabilidade/audit.py`**

```python
"""
Helper de auditoria enriquecida.
Centraliza escrita na tabela audit com contexto completo.
"""
import json
from datetime import datetime, timezone
from src.persistencia.conexao import obter_conexao
from src.observabilidade.logger import get_logger

log = get_logger(__name__)

EventoAudit = str  # ex: "sinal_aprovado", "sinal_rejeitado", "retomada_iniciada"


async def registrar_audit(
    evento: EventoAudit,
    componente: str,
    motivo: str,
    usuario_id: str | None = None,
    simbolo: str | None = None,
    meta: dict | None = None,
) -> None:
    """
    Persiste evento de auditoria com contexto completo.

    Args:
        evento: nome do evento (snake_case)
        componente: módulo/classe que gerou o evento (ex: "risk_engine", "filtro_ev")
        motivo: descrição legível da decisão
        usuario_id: id do usuário se aplicável
        simbolo: par de trading se aplicável
        meta: dados adicionais (EV, prob, modo, etc.)
    """
    agora = datetime.now(timezone.utc).isoformat()
    meta_str = json.dumps(meta or {}, ensure_ascii=False)
    try:
        async with obter_conexao() as conn:
            await conn.execute(
                """
                INSERT INTO audit
                    (ts, evento, componente, motivo, usuario_id, simbolo, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (agora, evento, componente, motivo, usuario_id, simbolo, meta_str),
            )
    except Exception as exc:
        # Audit nunca deve quebrar o fluxo principal
        log.error("audit_falhou", extra={"erro": str(exc), "evento": evento})
```

### Padrão de uso nos módulos existentes

```python
# Em risk_engine.py — sinal rejeitado por EV
await registrar_audit(
    evento="sinal_rejeitado",
    componente="risk_engine",
    motivo=f"ev_insuficiente({ev_liquido:.3f}usdt)",
    usuario_id=usuario_id,
    simbolo=simbolo,
    meta={"ev_liquido": ev_liquido, "ev_minimo": EV_MINIMO_USDT,
          "prob_up": prob_up, "valor_ordem": valor_ordem},
)

# Em retomada.py — modo de retomada definido
await registrar_audit(
    evento="retomada_iniciada",
    componente="retomada",
    motivo=ctx_retomada["mensagem"],
    simbolo=simbolo,
    meta=ctx_retomada,
)

# Em executor — ordem executada
await registrar_audit(
    evento="ordem_executada",
    componente="executor",
    motivo=f"ordem {ordem_id} lado={lado} preco={preco}",
    usuario_id=usuario_id,
    simbolo=simbolo,
    meta={"ordem_id": ordem_id, "ev_liquido": ev_liquido, "p_conf": p_conf},
)
```

### Checklist desta melhoria

- [ ] Verificar schema atual da tabela `audit` em `persistencia/conexao.py`
- [ ] Adicionar colunas `componente`, `motivo`, `meta_json` se não existirem (migration — seção 11)
- [ ] Criar `src/observabilidade/audit.py` conforme código acima
- [ ] Substituir chamadas diretas ao banco para auditoria pelo helper `registrar_audit`
- [ ] Integrar `registrar_audit` em: `risk_engine.py`, `retomada.py`, `executor_isolado_usuario.py`, `consenso.py`
- [ ] Garantir que `registrar_audit` nunca levante exceção para o chamador (já tratado com try/except)
- [ ] Escrever teste `tests/test_audit.py` (seção 12)

---

## 9. Integração entre melhorias — fluxo de inicialização

O fluxo completo de startup após todas as melhorias implementadas deve ser:

```
main.py @startup
    │
    ├─ inicializar_db()                          # existente
    │
    ├─ avaliar_retomada(simbolo)                 # NOVO — Melhoria 1
    │       │
    │       ├─ detectar_drift(...)               # NOVO — Melhoria 5
    │       └─ obter_snapshot(simbolo)           # NOVO — Melhoria 4 (enriquece contexto)
    │
    ├─ registrar_audit("retomada_iniciada", ...) # NOVO — Melhoria 6
    │
    ├─ [se recalibracao_forcada]
    │       └─ recalibrar_ao_religar(simbolo)    # NOVO — Melhoria 3
    │
    ├─ [se observacao]
    │       └─ asyncio.create_task(aguardar_observacao(...))  # NOVO — Melhoria 1
    │
    └─ iniciar loops existentes                  # existente
            (ATIVAR_LOOP_PREVISAO, ATIVAR_CONSUMIDOR_SINAIS)
```

O fluxo de avaliação de sinal após as melhorias:

```
signal_engine → consenso → risk_engine
                                │
                                ├─ filtro_ev (NOVO — Melhoria 2)
                                │       ├─ [reprovado] → registrar_audit + return
                                │       └─ [aprovado] → continua
                                │
                                └─ executor_isolado_usuario
                                        │
                                        ├─ salvar_snapshot (NOVO — Melhoria 4)
                                        └─ registrar_audit (NOVO — Melhoria 6)
```

---

## 10. Variáveis de ambiente novas

Adicionar ao `.env.example` e documentar no README principal:

```dotenv
# --- Retomada autônoma ---
SIMBOLO_PRINCIPAL=BTCUSDT
RETOMADA_PAUSA_MEDIA_H=4          # horas: pausa media → modo observação
RETOMADA_PAUSA_LONGA_H=24         # horas: pausa longa → recalibração forçada
RETOMADA_VARIACAO_PCT=3.0         # % variação de preço que força observação
RETOMADA_CANDLES_OBSERVACAO=5     # candles aguardados antes de operar após observação

# --- Filtro EV mínimo ---
FILTRO_EV_MINIMO_USDT=1.0         # EV líquido mínimo por operação em USDT
BINANCE_TAXA_MAKER_PCT=0.075      # taxa maker em % (0.075 = 0.075%)
BINANCE_TAXA_TAKER_PCT=0.075      # taxa taker em %

# --- Recalibração ---
RECALIBRACAO_CANDLES=60           # candles usados para partial_fit ao religar

# --- Detector de drift ---
DRIFT_VOLATILIDADE_THRESHOLD=2.0  # razão vol_pos/vol_pre que indica drift
DRIFT_JANELA_CANDLES=30           # candles usados para calcular volatilidade
```

---

## 11. Schema SQL — alterações necessárias

### Nova tabela `snapshot_estado`

Adicionar ao `DDL_BASE` em `src/persistencia/conexao.py`:

```sql
CREATE TABLE IF NOT EXISTS snapshot_estado (
    simbolo       TEXT PRIMARY KEY,
    estado_json   TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
```

### Migração da tabela `audit`

Verificar se as colunas já existem antes de adicionar. Executar como migration em `scripts/migrar_audit.py`:

```python
"""
Migration: adiciona colunas enriquecidas à tabela audit.
Seguro para rodar múltiplas vezes (IF NOT EXISTS equivalente via ALTER TABLE).
"""
import sqlite3, os

DB_PATH = os.getenv("DB_PATH", "./dados/oraculo.sqlite")

novas_colunas = [
    ("componente", "TEXT"),
    ("motivo",     "TEXT"),
    ("meta_json",  "TEXT"),
]

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
colunas_existentes = {r[1] for r in cur.execute("PRAGMA table_info(audit)")}

for nome, tipo in novas_colunas:
    if nome not in colunas_existentes:
        cur.execute(f"ALTER TABLE audit ADD COLUMN {nome} {tipo}")
        print(f"Coluna audit.{nome} adicionada.")
    else:
        print(f"Coluna audit.{nome} já existe — ignorado.")

conn.commit()
conn.close()
print("Migration concluída.")
```

### Como executar a migration

```bash
python scripts/migrar_audit.py
```

Executar **antes** de subir o app com as melhorias. Pode rodar em produção sem downtime.

---

## 12. Testes obrigatórios

Cada melhoria deve ter seu arquivo de teste. Estrutura mínima:

### `tests/test_retomada.py`

```python
import pytest
from unittest.mock import AsyncMock, patch
from src.tarefas.retomada import avaliar_retomada, _determinar_modo


def test_determinar_modo_normal():
    assert _determinar_modo(1.0, 1.0) == "normal"

def test_determinar_modo_observacao_tempo():
    assert _determinar_modo(5.0, 1.0) == "observacao"

def test_determinar_modo_observacao_variacao():
    assert _determinar_modo(1.0, 5.0) == "observacao"

def test_determinar_modo_recalibracao():
    assert _determinar_modo(25.0, 1.0) == "recalibracao_forcada"

@pytest.mark.asyncio
async def test_avaliar_retomada_sem_historico():
    with patch("src.tarefas.retomada._obter_ultima_ordem", new_callable=AsyncMock) as mock:
        mock.return_value = None
        resultado = await avaliar_retomada("BTCUSDT")
    assert resultado["modo"] == "normal"
    assert resultado["horas_parado"] == 0.0
```

### `tests/test_filtro_ev.py`

```python
from src.risco.filtro_ev import calcular_ev_liquido, sinal_passa_filtro_ev


def test_ev_positivo_aprovado():
    passou, ev = sinal_passa_filtro_ev(
        prob_up=0.6, prob_down=0.4,
        ganho_bruto_usdt=10.0, perda_bruta_usdt=5.0,
        valor_ordem_usdt=100.0
    )
    assert passou is True
    assert ev > 1.0

def test_ev_negativo_rejeitado():
    passou, ev = sinal_passa_filtro_ev(
        prob_up=0.4, prob_down=0.6,
        ganho_bruto_usdt=2.0, perda_bruta_usdt=8.0,
        valor_ordem_usdt=100.0
    )
    assert passou is False

def test_custos_embutidos_corretamente():
    # Sem custo e EV bruto exato no limiar deve falhar (taxas consomem)
    ev = calcular_ev_liquido(
        prob_up=0.5, prob_down=0.5,
        ganho_bruto_usdt=1.0, perda_bruta_usdt=1.0,
        valor_ordem_usdt=100.0
    )
    assert ev < 0  # taxas tornam EV negativo mesmo com prob 50/50 e ganho=perda
```

### `tests/test_detector_drift.py`

```python
from src.sinais.detector_drift import _desvio_padrao


def test_desvio_padrao_constante():
    assert _desvio_padrao([10.0, 10.0, 10.0]) == 0.0

def test_desvio_padrao_insuficiente():
    assert _desvio_padrao([10.0]) is None

def test_desvio_padrao_calculado():
    dp = _desvio_padrao([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    assert round(dp, 4) == 2.0
```

### `tests/test_repositorio_snapshot.py`

```python
import pytest
from src.persistencia.repositorio_snapshot import salvar_snapshot, obter_snapshot

@pytest.mark.asyncio
async def test_salvar_e_recuperar_snapshot(db_teste):
    estado = {"modo_operacao": "normal", "posicao_aberta": False}
    await salvar_snapshot("BTCUSDT", estado)
    recuperado = await obter_snapshot("BTCUSDT")
    assert recuperado["modo_operacao"] == "normal"

@pytest.mark.asyncio
async def test_snapshot_inexistente_retorna_none(db_teste):
    resultado = await obter_snapshot("XYZUSDT")
    assert resultado is None
```

> Usar o fixture `db_teste` já existente em `tests/conftest.py` que cria um SQLite em memória.

---

## 13. Checklist de execução por ordem

Execute nesta sequência exata para evitar dependências quebradas:

### Fase 1 — Schema e base

- [ ] **1.1** Executar `python scripts/migrar_audit.py` para adicionar colunas à tabela `audit`
- [ ] **1.2** Adicionar tabela `snapshot_estado` ao `DDL_BASE` em `src/persistencia/conexao.py`
- [ ] **1.3** Confirmar que `inicializar_db()` cria a nova tabela — testar em ambiente local
- [ ] **1.4** Adicionar todas as variáveis novas ao `.env.example` (seção 10)

### Fase 2 — Módulos independentes (sem integração ainda)

- [ ] **2.1** Criar `src/risco/filtro_ev.py` (Melhoria 2)
- [ ] **2.2** Criar `src/persistencia/repositorio_snapshot.py` (Melhoria 4)
- [ ] **2.3** Criar `src/sinais/detector_drift.py` (Melhoria 5)
- [ ] **2.4** Criar `src/observabilidade/audit.py` (Melhoria 6)
- [ ] **2.5** Rodar testes unitários: `pytest tests/test_filtro_ev.py tests/test_detector_drift.py -v`

### Fase 3 — Módulos de retomada

- [ ] **3.1** Criar `src/tarefas/recalibracao_startup.py` (Melhoria 3)
- [ ] **3.2** Criar `src/tarefas/observacao.py` (Melhoria 1)
- [ ] **3.3** Criar `src/tarefas/retomada.py` (Melhoria 1) — **depende de 2.3 e 2.4**
- [ ] **3.4** Rodar testes: `pytest tests/test_retomada.py tests/test_recalibracao_startup.py -v`

### Fase 4 — Integrações nos módulos existentes

- [ ] **4.1** Integrar `filtro_ev` em `src/risco/risk_engine.py` (Melhoria 2)
- [ ] **4.2** Integrar `salvar_snapshot` em `src/executor/executor_isolado_usuario.py` (Melhoria 4)
- [ ] **4.3** Integrar `registrar_audit` em `risk_engine.py`, `executor_isolado_usuario.py`, `consenso.py` (Melhoria 6)
- [ ] **4.4** Rodar testes de integração: `pytest tests/ -v --ignore=tests/test_binance_api.py`

### Fase 5 — Startup

- [ ] **5.1** Integrar fluxo de retomada no `@app.on_event("startup")` de `src/main.py` (conforme seção 9)
- [ ] **5.2** Testar startup local com banco existente: `uvicorn src.api.app:app --reload`
- [ ] **5.3** Verificar logs: deve aparecer `contexto_retomada` e `retomada_avaliada`
- [ ] **5.4** Verificar tabela `audit`: deve ter registro `retomada_iniciada` após startup

### Fase 6 — Validação final

- [ ] **6.1** Rodar suite completa: `pytest tests/ -v`
- [ ] **6.2** Simular pausa longa: inserir ordem antiga no banco (`criado_em` = 3 dias atrás) e religar — deve entrar em `recalibracao_forcada`
- [ ] **6.3** Simular sinal com EV < 1 USDT — deve aparecer `sinal_rejeitado` no audit
- [ ] **6.4** Verificar `/v1/health` — deve retornar campo `retomada_modo` no estado dos loops
- [ ] **6.5** Verificar `/v1/export/auditoria` — deve retornar registros com `componente`, `motivo`, `meta_json`

---

## Notas finais para a IA executora

1. **Nunca renomear** contratos, funções ou campos existentes. Apenas adicionar/estender.
2. **Sempre verificar** o código existente antes de integrar. Os trechos de código neste documento são guias — os nomes reais de variáveis, métodos e campos do projeto podem diferir ligeiramente.
3. **Comentários em PT-BR**: todos os docstrings e comentários inline devem ser em português brasileiro.
4. **Falha segura primeiro**: se qualquer nova integração levantar exceção, ela deve ser capturada, logada e o fluxo deve continuar sem comprometer a operação do bot — exceto nos casos onde a falha é de segurança (ex: impossível calcular EV → não executar ordem).
5. **EV mínimo é inegociável**: a variável `FILTRO_EV_MINIMO_USDT` deve ser respeitada em todo fluxo de aprovação de sinal, sem exceções, mesmo em modo testnet.

---

*Documento gerado em 2026-04-29. Atualizar conforme evolução do código.*
