"""Idempotência de ordens — PSF-03 / DA-05.

Gera um `clientOrderId` determinístico a partir da INTENÇÃO de trade. Mesma intenção
produz o mesmo ID; a Binance rejeita ordens com `clientOrderId` duplicado, o que
transforma retry/restart em proteção gratuita contra double-submission.
"""
from __future__ import annotations

import hashlib

# A Binance aceita clientOrderId de até 36 caracteres; mantemos charset seguro [A-Za-z0-9].
_MAX_CLIENT_ORDER_ID: int = 36
_PREFIXO: str = "orc"

# Fallback determinístico quando o chamador não passa `chave_intencao`. É uma string FIXA
# (não timestamp) — ver docstring de `gerar_client_order_id` para a justificativa completa.
_BASE_FALLBACK_SEM_CHAVE: str = "auto"


def gerar_client_order_id(
    *,
    simbolo: str,
    lado: str,
    notional: float,
    usuario_id: str = "auto",
    chave_intencao: str | int | None = None,
) -> str:
    """Retorna um clientOrderId determinístico de no máximo 36 chars.

    `chave_intencao` é o identificador estável da intenção (ex.: ts do sinal, ordem_id):
    o MESMO valor para a mesma intenção garante o mesmo ID em todas as tentativas.

    Quando omitido — hoje o caso de TODOS os callers em produção (`gerenciador_ordens.py`
    não passa `chave_intencao` em nenhuma chamada) — o fallback usa uma string CONSTANTE
    (`_BASE_FALLBACK_SEM_CHAVE`), não o relógio de parede. Isso é proposital: um fallback
    baseado em `time.time()` quebra idempotência entre tentativas espaçadas por >1s (ex.:
    retry após timeout, ou restart do processo) — cada chamada gera um clientOrderId novo,
    a Binance aceita como ordem NOVA em vez de rejeitar por ID duplicado, e o resultado é
    risco real de posição/débito duplicado. Com a base fixa, a MESMA intenção lógica
    (mesmo usuário+símbolo+lado+notional) sempre gera o MESMO ID, mesmo em segundos ou
    dias diferentes — o comportamento correto de idempotência quando não há uma chave de
    intenção mais granular.

    LIMITAÇÃO CONHECIDA: com o fallback, "comprar X USDT de BTCUSDT" é tratado como UMA
    ÚNICA intenção lógica até que os valores (símbolo/lado/notional) mudem — inclusive
    entre ciclos de negócio legítimos e distintos (não apenas retries). Callers que
    precisam reabrir a MESMA posição (mesmo símbolo/lado/notional) como operações
    distintas devem passar uma `chave_intencao` estável e granular (ex.: timestamp do
    sinal ou ID do ciclo) — isso é responsabilidade do CALLER, não deste módulo.
    """
    base = str(chave_intencao) if chave_intencao is not None else _BASE_FALLBACK_SEM_CHAVE
    intencao = f"{usuario_id}:{simbolo.upper()}:{lado.upper()}:{round(float(notional or 0.0), 8)}:{base}"
    digest = hashlib.sha256(intencao.encode("utf-8")).hexdigest()
    return f"{_PREFIXO}{digest}"[:_MAX_CLIENT_ORDER_ID]
