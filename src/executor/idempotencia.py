"""Idempotência de ordens — PSF-03 / DA-05.

Gera um `clientOrderId` determinístico a partir da INTENÇÃO de trade. Mesma intenção
produz o mesmo ID; a Binance rejeita ordens com `clientOrderId` duplicado, o que
transforma retry/restart em proteção gratuita contra double-submission.
"""
from __future__ import annotations

import hashlib
import time

# A Binance aceita clientOrderId de até 36 caracteres; mantemos charset seguro [A-Za-z0-9].
_MAX_CLIENT_ORDER_ID: int = 36
_PREFIXO: str = "orc"


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
    Quando omitido, usa o segundo atual — o que dá idempotência apenas para retries
    imediatos (suficiente como rede de segurança, mas o chamador deveria passar a chave).
    """
    base = str(chave_intencao) if chave_intencao is not None else str(int(time.time()))
    intencao = f"{usuario_id}:{simbolo.upper()}:{lado.upper()}:{round(float(notional or 0.0), 8)}:{base}"
    digest = hashlib.sha256(intencao.encode("utf-8")).hexdigest()
    return f"{_PREFIXO}{digest}"[:_MAX_CLIENT_ORDER_ID]
