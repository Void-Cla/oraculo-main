# Oráculo v3 — Plano de Implementação

## Resumo executivo
Bot autônomo de scalping na Binance spot, focado em maximizar lucro líquido (alvo: $0.01 a $1.00+ por ciclo) com capital configurável pelo usuário (10% a 100% do saldo USDT), priorizando pagamento de taxa em BNB e operando nos pares USDT/BNB.

---

## O que mudou vs versão anterior

### Removido
- Perfis "mini / ganancioso / diario" (lógica de capital fixo por perfil)
- Variáveis de ambiente para parâmetros de trading (todos hardcoded com autoajuste)
- Frontend de 3 abas com tabelas pesadas

### Adicionado
- **ControladorAdaptativo** — autoajusta cooldown, min_prob, min_score a cada 30s baseado em win rate e taxa de trades/min
- **AI Advisor** (`src/servicos/ai_advisor.py`) — lê últimas 20 predições + outcomes do DB, estado do mercado, chama GPT-4o-mini e retorna: direção, confiança, capital_pct_sugerido, reasoning, risco
- **Capital % dinâmico** — usuário seleciona 10% a 100% do saldo USDT; backend resolve para USDT real
- **DB: novas colunas** — sem remover existentes
- **Frontend minimalista** — 1 página, login, dashboard compacto, slider de capital%, AI panel, tabela de trades

---

## Arquitetura do fluxo principal

```
Login (API Key + Testnet toggle)
    │
    ▼
[Saldo USDT carregado] → Capital % selecionado → notional_usdt = saldo × pct%
    │
    ▼
Auto-Trading iniciado
    │
    ├── Cada 15s: orquestrador coletou snapshots (OHLCV + book topo)
    │       ├── gerador_features → features_1m (+ regime, vol_regime)
    │       ├── signal_engine → sinal (acao, tp/sl, confiança, probabilidades)
    │       ├── fee_optimizer → taxa_efetiva (com desconto BNB se saldo >= 0.01)
    │       └── ControladorAdaptativo.ajustar() → thresholds dinâmicos
    │
    ├── risk_engine → aprovado? (EV >= $0.01, lucro_liquido >= $0.01)
    │       ├── SE aprovado → gerenciador_ordens → MARKET order na Binance
    │       │       ├── registrar em `ordens` (+ lucro_usdt, lucro_pct, regime, estrategia)
    │       │       └── ControladorAdaptativo.registrar_ciclo(executado=True, lucro_usdt=X)
    │       └── SE rejeitado → ControladorAdaptativo.registrar_ciclo(aprovado=False, motivos=[...])
    │
    └── AI Advisor (sob demanda via GET /v1/ai/insight)
            ├── Lê 20 predições + 20 outcomes do DB
            ├── Lê features recentes + regime
            ├── Chama GPT-4o-mini com prompt estruturado
            └── Retorna: direcao, confianca, capital_pct_sugerido, reasoning, risco
                └── Persiste em `ai_insights`
```

---

## Seleção de estratégia (meta_controller)

| Regime detectado | Estratégia usada        | Características           |
|-----------------|-------------------------|---------------------------|
| TREND_UP        | momentum                | EMA cross + r_3m          |
| TREND_DOWN      | momentum                | Inverso                   |
| RANGE           | mean_reversion          | Reversão para média       |
| HIGH_VOL        | breakout                | Rompimento de range        |
| LOW_VOL         | volatility_scalping     | Spread + pressão de book  |

O ControladorAdaptativo **não troca** de estratégia — ele ajusta os **filtros de aprovação** (thresholds) para que apenas operações com EV real sejam aprovadas em qualquer regime.

---

## Controle de capital (10% a 100%)

```python
# Servidor resolve capital_pct → notional_usdt
pct = max(10, min(100, capital_pct))
notional_usdt = saldo_usdt_livre * pct / 100.0
```

Recomendações por perfil de risco:
| % Capital | Perfil      | Quando usar                              |
|-----------|-------------|------------------------------------------|
| 10–20%    | Conservador | Mercado volátil, poucos dados, início    |
| 30–50%    | Moderado    | Win rate > 60%, regime estável           |
| 60–80%    | Agressivo   | Win rate > 70%, AI confiança > 0.75      |
| 90–100%   | Máximo      | Somente com win rate > 80% comprovado    |

---

## Priorização BNB para taxa

- `fee_optimizer.py`: se `saldo_bnb >= 0.01`, aplica desconto de 25%
- Desconto: taker 0.1% → 0.075%, maker 0.1% → 0.09%
- Economiza ~$0.005 por trade de $10 → ~$0.10/dia em 20 trades

---

## DB: novas colunas (não remove existentes)

```sql
-- ordens
ALTER TABLE ordens ADD COLUMN lucro_usdt REAL;
ALTER TABLE ordens ADD COLUMN lucro_pct REAL;
ALTER TABLE ordens ADD COLUMN duracao_ms INTEGER;
ALTER TABLE ordens ADD COLUMN capital_pct_usado REAL;
ALTER TABLE ordens ADD COLUMN regime TEXT;
ALTER TABLE ordens ADD COLUMN estrategia TEXT;

-- outcomes (para ML)
ALTER TABLE outcomes ADD COLUMN regime TEXT;
ALTER TABLE outcomes ADD COLUMN estrategia TEXT;
ALTER TABLE outcomes ADD COLUMN confianca REAL;
ALTER TABLE outcomes ADD COLUMN capital_pct REAL;
ALTER TABLE outcomes ADD COLUMN lucro_usdt REAL;

-- predictions
ALTER TABLE predictions ADD COLUMN regime TEXT;
ALTER TABLE predictions ADD COLUMN estrategia TEXT;
ALTER TABLE predictions ADD COLUMN capital_pct REAL;
ALTER TABLE predictions ADD COLUMN ai_boost REAL;

-- features_1m
ALTER TABLE features_1m ADD COLUMN regime TEXT;
ALTER TABLE features_1m ADD COLUMN vol_regime TEXT;

-- NOVA: ai_insights
CREATE TABLE IF NOT EXISTS ai_insights (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_ts INTEGER NOT NULL,
  simbolo TEXT NOT NULL,
  modelo TEXT NOT NULL,
  direcao TEXT NOT NULL,
  confianca REAL,
  capital_pct_sugerido REAL,
  reasoning TEXT,
  risco TEXT,
  dados_entrada_json TEXT,
  executado INTEGER NOT NULL DEFAULT 0
);
```

Todas aplicadas via `_garantir_schema_evolutivo()` — safe em DB existente.

---

## AI Advisor — fluxo detalhado

1. **Entrada**: 20 predições recentes, 20 outcomes, features atuais, regime, saldo USDT
2. **Prompt**: direcionado para trader quantitativo — inclui acurácia recente, spread, momentum, regime
3. **Saída GPT**: `{direcao, confianca, capital_pct_sugerido, reasoning, risco}`
4. **Fallback** (sem GPT key): heurística local por regime + acurácia
5. **Segurança**: `capital_pct_sugerido` máximo 80% se confiança < 0.80
6. **Persistência**: salvo em `ai_insights` para análise futura

**Integração com bot**: O AI Advisor é consultado **sob demanda** (botão no frontend) e não bloqueia o ciclo automático. Futuramente pode ser integrado como boost de confiança no signal_engine.

---

## Endpoints novos/modificados

| Endpoint              | Método | Mudança                                      |
|-----------------------|--------|----------------------------------------------|
| `/v1/auto/start`      | POST   | Aceita `capital_pct` (10-100) além de notional |
| `/v1/ai/insight`      | GET    | NOVO — consulta AI Advisor                   |
| `/v1/auto/config`     | PUT    | Aceita `capital_pct` além de notional        |

---

## Performance esperada vs outros bots

| Bot          | Freq/hora | Capital min | AI Market | BNB prio | Adaptive |
|--------------|-----------|-------------|-----------|----------|---------|
| 3Commas DCA  | ~2-5      | $10         | ✗         | ✗        | ✗       |
| Pionex Grid  | ~10-30    | $5          | ✗         | ✗        | ✗       |
| freqtrade ML | ~5-20     | $50         | ✗         | ✗        | parcial |
| **Oráculo v3** | **~10-40** | **$5**     | **✓**     | **✓**    | **✓**   |

---

## Checklist de instalação

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Configurar .env (apenas credenciais)
cp .env.example .env
# Preencher: BINANCE_API_KEY, BINANCE_API_SECRET, GPT_API_KEY

# 3. Inicializar DB (cria novas colunas automaticamente)
python -c "from src.persistencia.conexao import inicializar_db; inicializar_db()"

# 4. Rodar
uvicorn src.main:app --host 0.0.0.0 --port 8000

# 5. Acessar frontend
http://localhost:8000
```

