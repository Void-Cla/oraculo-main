Runbook: E2E Testnet (24–72h)

Objetivo
- Validar comportamento do `TestnetAutoTrader` em ambiente de Testnet/Simulado por um período configurável.

Requisitos
- Definir `TESTNET_API_KEY` e `TESTNET_API_SECRET` no ambiente (mantive `.env` como solicitado).
- Python virtualenv com dependências instaladas (veja `requirements.txt` / `pyproject.toml`).

Como executar
1. Ative o ambiente virtual:

```powershell
& .venv\Scripts\Activate.ps1
```

2. Execute o runner (por padrão 10 minutos). Ajuste duração via `E2E_DURATION_SECONDS`:

```powershell
$env:TESTNET_API_KEY = '...'
$env:TESTNET_API_SECRET = '...'
python scripts\run_testnet_e2e.py
```

3. Logs: saída no console e eventos de auditoria gravados em `repositorio_auditoria` (se disponível).

Configurações úteis (env vars)
- `E2E_DURATION_SECONDS` — duração do run (segundos).
- `E2E_SYMBOL` — símbolo monitorado, default `BTCUSDT`.
- `E2E_INTERVAL_SECONDS` — intervalo entre checks/status, default `30`.
- `E2E_NOTIONAL_USDT` — capital por ciclo, default `5.0`.

Práticas recomendadas
- Execute por 24–72 horas para observar comportamento de retenção, custo de chamadas LLM e estabilidade de execução.
- Monitore `dados/` e auditoria (`auditoria`) para eventos de trade e métricas.
