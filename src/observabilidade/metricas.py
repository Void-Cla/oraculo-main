from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

previsoes_total = Counter(
    "oraculo_previsoes_total",
    "Total de previsoes geradas pelo Oraculo",
    ["simbolo", "origem"],
)
previsoes_erro_total = Counter(
    "oraculo_previsoes_erro_total",
    "Total de falhas ao gerar previsoes",
    ["simbolo", "origem"],
)
decisoes_total = Counter(
    "oraculo_decisoes_total",
    "Total de decisoes hibridas emitidas",
    ["simbolo", "acao"],
)
latencia_previsao_segundos = Histogram(
    "oraculo_latencia_previsao_segundos",
    "Latencia da previsao em segundos",
    ["simbolo", "origem"],
)
confianca_previsao = Gauge(
    "oraculo_confianca_previsao",
    "Confianca mais recente da previsao",
    ["simbolo"],
)

# Métricas do AutoTrader / Execução
auto_trader_consecutive_errors = Gauge(
    "oraculo_auto_trader_consecutive_errors",
    "Erros consecutivos atuais por token",
    ["token", "simbolo"],
)
auto_trader_circuit_tripped = Gauge(
    "oraculo_auto_trader_circuit_tripped",
    "Circuit breaker (1=tripped, 0=ok)",
    ["token", "simbolo"],
)
auto_trader_daily_loss_usdt = Gauge(
    "oraculo_auto_trader_daily_loss_usdt",
    "Perda diaria estimada (USDT)",
    ["token", "simbolo"],
)
orders_success_total = Counter(
    "oraculo_orders_success_total",
    "Total de ordens executadas com sucesso",
    ["simbolo"],
)
orders_failed_total = Counter(
    "oraculo_orders_failed_total",
    "Total de ordens que falharam",
    ["simbolo"],
)
orders_latency_seconds = Histogram(
    "oraculo_orders_latency_seconds",
    "Latencia das operacoes de ordem em segundos",
    ["simbolo"],
)


def exportar_metricas() -> bytes:
    return generate_latest()


__all__ = [
    "CONTENT_TYPE_LATEST",
    "confianca_previsao",
    "decisoes_total",
    "exportar_metricas",
    "latencia_previsao_segundos",
    "previsoes_erro_total",
    "previsoes_total",
    "auto_trader_consecutive_errors",
    "auto_trader_circuit_tripped",
    "auto_trader_daily_loss_usdt",
    "orders_success_total",
    "orders_failed_total",
    "orders_latency_seconds",
]
