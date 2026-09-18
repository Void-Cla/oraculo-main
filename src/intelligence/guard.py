"""Guardrails da camada agêntica — normaliza a decisão da IA garantindo os invariantes.

INVARIANTE: a IA só pode VETAR (ABORT). Qualquer outra coisa vira PROCEED (fail-open). Um
ABORT só é honrado se a confiança reportada atingir o piso (IA incerta NÃO bloqueia o bot).
Este módulo é PURO (sem I/O) — totalmente testável.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_ACOES_VALIDAS = {"PROCEED", "ABORT"}


@dataclass
class DecisaoIA:
    action: str            # "PROCEED" | "ABORT" — sempre normalizado
    rationale: str = ""
    confidence: float = 0.0
    source: str = "gemini"  # gemini | timeout | error | disabled
    pattern: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "source": self.source,
            "pattern": self.pattern,
        }

    @property
    def vetou(self) -> bool:
        return self.action == "ABORT"


def decisao_prosseguir(*, source: str, rationale: str = "") -> DecisaoIA:
    """Decisão segura padrão: PROCEED (não bloqueia o bot mecânico)."""
    return DecisaoIA(action="PROCEED", rationale=rationale, confidence=0.0, source=source)


def normalizar_decisao(
    bruto: dict[str, Any] | None,
    *,
    confianca_min_veto: float,
    source: str = "gemini",
) -> DecisaoIA:
    """Converte a resposta crua do LLM numa DecisaoIA segura.

    - resposta ausente/inválida → PROCEED
    - action != ABORT → PROCEED
    - ABORT com confiança < piso → PROCEED (IA incerta não bloqueia)
    - ABORT com confiança >= piso → ABORT (único caso que veta)
    """
    if not isinstance(bruto, dict):
        return decisao_prosseguir(source=source, rationale="resposta_ia_invalida")

    action = str(bruto.get("action", "PROCEED") or "PROCEED").strip().upper()
    if action not in _ACOES_VALIDAS:
        action = "PROCEED"
    try:
        confianca = float(bruto.get("confidence_score", bruto.get("confidence", 0.0)) or 0.0)
    except (TypeError, ValueError):
        confianca = 0.0
    confianca = max(0.0, min(1.0, confianca))
    rationale = str(bruto.get("rationale", "") or "")[:300]
    pattern = str(bruto.get("pattern_detected", bruto.get("pattern", "none")) or "none")

    if action == "ABORT" and confianca < float(confianca_min_veto):
        # IA incerta → não bloqueia (fail-open conservador a favor do fluxo mecânico).
        return DecisaoIA(
            action="PROCEED",
            rationale=f"ia_incerta(conf={confianca:.2f}<{confianca_min_veto:.2f}): {rationale}",
            confidence=confianca,
            source=source,
            pattern=pattern,
        )
    return DecisaoIA(action=action, rationale=rationale, confidence=confianca, source=source, pattern=pattern)
