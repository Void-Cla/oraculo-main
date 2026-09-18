"""Alertas de eventos críticos (halt, drawdown, erros) — Telegram/webhook, fail-safe.

CONTEXTO (up.md P0 / gap G2): um bot autônomo que falha em silêncio às 3h da manhã é o gap
mais perigoso de um sistema sem supervisão humana constante. Este módulo NÃO decide nada — só
notifica eventos que JÁ aconteceram (halt disparado, erro consecutivo, etc.) depois que o
código financeiro (risk_engine/circuit breaker) já tomou a decisão. Mesmo princípio fail-open
da camada de IA (DA-23): qualquer falha de rede/config aqui NUNCA propaga para o chamador — o
loop de trading não pode travar porque o Telegram está fora do ar.

Canais suportados (ambos opcionais, podem coexistir):
  - Telegram: ALERTA_TELEGRAM_BOT_TOKEN + ALERTA_TELEGRAM_CHAT_ID
  - Webhook genérico (Slack/Discord/n8n/etc via POST JSON): ALERTA_WEBHOOK_URL

Sem nenhuma env configurada, o módulo é NO-OP silencioso — mesmo padrão fail-open do resto do
projeto (ausência de config = camada desativada, não erro).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from src.core.settings import env_float, env_str
from src.observabilidade.logger import get_logger

LOG = get_logger("alertas")

_TIMEOUT_PADRAO_S = 10.0
_COOLDOWN_PADRAO_S = 300.0  # não repetir o MESMO tipo de alerta antes disso (evita flood)

# Último disparo BEM-SUCEDIDO por "chave" de alerta (dedup/anti-flood em memória de processo).
_ULTIMO_DISPARO: dict[str, float] = {}


def _telegram_config() -> tuple[str, str]:
    return env_str("ALERTA_TELEGRAM_BOT_TOKEN", ""), env_str("ALERTA_TELEGRAM_CHAT_ID", "")


def _webhook_url() -> str:
    return env_str("ALERTA_WEBHOOK_URL", "")


def _configurado() -> bool:
    token, chat_id = _telegram_config()
    return bool(token and chat_id) or bool(_webhook_url())


def _cooldown_segundos() -> float:
    return env_float("ALERTA_COOLDOWN_SEGUNDOS", _COOLDOWN_PADRAO_S, minimo=0.0)


def _em_cooldown(chave: str) -> bool:
    cooldown = _cooldown_segundos()
    if cooldown <= 0:
        return False
    ultimo = _ULTIMO_DISPARO.get(chave)
    return ultimo is not None and (time.time() - ultimo) < cooldown


def _resetar_estado_teste() -> None:
    """Limpa o dedup em memória — uso exclusivo de testes (isolamento entre casos)."""
    _ULTIMO_DISPARO.clear()


async def _enviar_telegram(mensagem: str) -> bool:
    token, chat_id = _telegram_config()
    if not token or not chat_id:
        return False
    import httpx

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_PADRAO_S) as cliente:
            resposta = await cliente.post(url, json={"chat_id": chat_id, "text": mensagem})
            resposta.raise_for_status()
        return True
    except Exception as exc:
        LOG.warning("falha_enviar_alerta_telegram", extra={"erro": str(exc)})
        return False


async def _enviar_webhook(mensagem: str, contexto: dict[str, Any]) -> bool:
    url = _webhook_url()
    if not url:
        return False
    import httpx

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_PADRAO_S) as cliente:
            resposta = await cliente.post(url, json={"texto": mensagem, "contexto": contexto})
            resposta.raise_for_status()
        return True
    except Exception as exc:
        LOG.warning("falha_enviar_alerta_webhook", extra={"erro": str(exc)})
        return False


async def disparar_alerta(*, chave: str, titulo: str, severidade: str = "CRITICAL", **contexto: Any) -> None:
    """Envia um alerta (Telegram e/ou webhook). NUNCA lança — fail-safe por contrato.

    `chave` identifica o TIPO de alerta (ex.: "halt_perda_diaria") para dedup por cooldown —
    evita floodar o dono com o mesmo alerta a cada ciclo de 30s enquanto o bot está parado/preso
    num erro recorrente.
    """
    try:
        if not _configurado():
            return
        if _em_cooldown(chave):
            return
        mensagem = f"🚨 [{severidade}] ORACULO — {titulo}"
        if contexto:
            detalhes = " | ".join(f"{k}={v}" for k, v in contexto.items())
            mensagem = f"{mensagem}\n{detalhes}"
        enviado_telegram = await _enviar_telegram(mensagem)
        enviado_webhook = await _enviar_webhook(mensagem, contexto)
        if enviado_telegram or enviado_webhook:
            _ULTIMO_DISPARO[chave] = time.time()
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # fail-safe absoluto: alerta jamais derruba o caminho financeiro
        LOG.error("falha_inesperada_disparar_alerta", extra={"erro": str(exc), "chave": chave})


def disparar_alerta_background(*, chave: str, titulo: str, severidade: str = "CRITICAL", **contexto: Any) -> None:
    """Fire-and-forget: agenda o alerta como task e NUNCA bloqueia o chamador.

    Use nos pontos quentes do autotrader em vez de `await disparar_alerta(...)` — a latência de
    rede do Telegram/webhook (até `_TIMEOUT_PADRAO_S`) não pode atrasar o próximo ciclo de
    trading. `disparar_alerta` já é fail-safe (nunca lança), então a task nunca gera exceção
    "never retrieved".
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        LOG.warning("alerta_sem_loop_ativo_ignorado", extra={"chave": chave})
        return

    async def _tarefa() -> None:
        await disparar_alerta(chave=chave, titulo=titulo, severidade=severidade, **contexto)

    loop.create_task(_tarefa())
