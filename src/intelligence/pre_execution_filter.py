"""Filtro de pré-execução — interceptor consultivo ANTES de abrir posição.

PRINCÍPIO (defense in depth): a IA só pode VETAR (ABORT). Timeout/erro/cooldown/desligado
⇒ PROCEED (fail-open). A IA NUNCA aprova nem dimensiona; só pode barrar uma armadilha óbvia.
`avaliar()` NUNCA lança exceção.
"""
from __future__ import annotations

import asyncio

from src.core.settings import env_float
from src.intelligence.context_builder import construir_contexto_pre_execucao
from src.intelligence.guard import DecisaoIA, decisao_prosseguir, normalizar_decisao
from src.intelligence.provedor_ia import ProvedorIA
from src.intelligence.prompt_templates import PROMPT_PRE_EXECUCAO
from src.observabilidade.logger import get_logger

LOG = get_logger("pre_execution_filter")


class PreExecutionFilter:
    def __init__(
        self,
        gemini: ProvedorIA,
        *,
        habilitado: bool = True,
        timeout_s: float | None = None,
        confianca_min_veto: float | None = None,
    ) -> None:
        self._gemini = gemini
        self._habilitado = bool(habilitado)
        self._timeout = float(timeout_s) if timeout_s is not None else env_float(
            "AI_FILTER_TIMEOUT_SEGUNDOS", 12.0, minimo=1.0
        )
        self._confianca_min_veto = (
            float(confianca_min_veto)
            if confianca_min_veto is not None
            else env_float("AI_FILTER_MIN_CONFIDENCE_ABORT", 0.70, minimo=0.0)
        )

    async def avaliar(self, *, simbolo: str, sinal: dict, saldo: float) -> DecisaoIA:
        if not self._habilitado:
            return decisao_prosseguir(source="disabled", rationale="filtro_ia_desativado")
        try:
            contexto = await construir_contexto_pre_execucao(simbolo, sinal, saldo)
            bruto = await asyncio.wait_for(
                self._gemini.analisar(PROMPT_PRE_EXECUCAO, contexto, temperature=0.1),
                timeout=self._timeout,
            )
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            LOG.warning("filtro_ia_timeout", extra={"simbolo": simbolo})
            return decisao_prosseguir(source="timeout", rationale="timeout_ia")
        except Exception as exc:
            LOG.error("filtro_ia_erro", extra={"simbolo": simbolo, "erro": str(exc)})
            return decisao_prosseguir(source="error", rationale=str(exc))

        if bruto is None:
            return decisao_prosseguir(source="error", rationale="ia_indisponivel")
        decisao = normalizar_decisao(bruto, confianca_min_veto=self._confianca_min_veto)
        if decisao.vetou:
            LOG.warning(
                "ia_vetou_operacao",
                extra={
                    "simbolo": simbolo,
                    "rationale": decisao.rationale,
                    "confianca": decisao.confidence,
                    "pattern": decisao.pattern,
                },
            )
        return decisao
