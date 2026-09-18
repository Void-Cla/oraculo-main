"""Auditor pós-trade — cron consultivo que lê os trades recentes e registra padrões.

Roda em background (intervalo configurável, default 2h). É puramente OBSERVACIONAL: persiste
a análise na tabela `audit` para consulta humana/IA. NUNCA altera gates nem decisões.
"""
from __future__ import annotations

import asyncio

from src.core.settings import env_int
from src.intelligence.context_builder import construir_contexto_auditoria
from src.intelligence.prompt_templates import PROMPT_AUDITORIA_POS_TRADE
from src.intelligence.provedor_ia import ProvedorIA
from src.observabilidade.logger import get_logger
from src.persistencia.repositorio_auditoria import RepositorioAuditoria

LOG = get_logger("post_trade_auditor")


class PostTradeAuditor:
    def __init__(self, gemini: ProvedorIA, *, intervalo_horas: int | None = None) -> None:
        self._gemini = gemini
        self._intervalo_s = max(1, (intervalo_horas if intervalo_horas is not None
                                    else env_int("AI_AUDITOR_INTERVALO_HORAS", 2, minimo=1))) * 3600

    async def executar_ciclo(self) -> dict | None:
        """Roda uma auditoria e persiste o resultado. Retorna o dict da IA ou None."""
        contexto = await construir_contexto_auditoria()
        resultado = await self._gemini.analisar(
            PROMPT_AUDITORIA_POS_TRADE, contexto, temperature=0.3
        )
        if resultado is None:
            LOG.info("auditoria_ia_indisponivel_pulando_ciclo")
            return None
        try:
            await RepositorioAuditoria.registrar_enriquecido(
                evento="auditoria_2h",
                componente="post_trade_auditor",
                motivo=str(resultado.get("recommendation", ""))[:300],
                meta=resultado,
            )
        except Exception as exc:  # persistência best-effort
            LOG.warning("falha_persistir_auditoria", extra={"erro": str(exc)})
        padroes = resultado.get("patterns_loss") or []
        if isinstance(padroes, list) and len(padroes) >= 2:
            LOG.warning("auditoria_padroes_de_perda", extra={"padroes": padroes})
        return resultado

    async def run_loop(self, shutdown_event: asyncio.Event) -> None:
        LOG.info("post_trade_auditor_iniciado", extra={"intervalo_s": self._intervalo_s})
        # DA-31: ESPERA um intervalo ANTES da primeira auditoria. Antes, `executar_ciclo`
        # rodava no T+0 do boot — era o PRIMEIRO 429 que o dono via "logo após o boot", com a
        # quota do Gemini já drenada de runs anteriores. No boot também não há trade novo desde
        # a última sessão para auditar, então a chamada imediata só gasta quota à toa. Agora a
        # primeira auditoria só ocorre após `_intervalo_s` (default 2h) — e o loop encerra na
        # hora se o shutdown for sinalizado durante a espera.
        while not shutdown_event.is_set():
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=self._intervalo_s)
                return  # shutdown sinalizado durante a espera
            except asyncio.TimeoutError:
                pass  # passou o intervalo — hora de auditar
            try:
                await self.executar_ciclo()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOG.error("erro_ciclo_auditoria", extra={"erro": str(exc)})
