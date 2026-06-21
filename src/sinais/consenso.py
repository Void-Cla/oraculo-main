from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --- Limiares de consenso entre fontes (estratégia, modelo, LLM, confirmação, probabilidade) ---
# ⚠️ ASSIMETRIA CONHECIDA E INTENCIONALMENTE EXPLÍCITA (INC-01):
# A configuração atual é enviesada a ABRIR trade — basta 1 fonte fracamente alinhada
# (score >= 0.10) para confirmar, mas exige 2 fontes FORTEMENTE contrárias (score >= 0.35)
# para vetar. Isso gera mais trades do que bloqueia.
# NÃO simetrizar sem dados: alterar limiares de risco sem backtest é, por si só, um risco.
# CALIBRAR com o backtester (Fase 8). Para remover o viés: igualar ALINHAMENTO == VETO
# e MIN_FONTES_ALINHADAS == MIN_FONTES_CONTRARIAS.
LIMIAR_ALINHAMENTO_FONTE: float = 0.10    # score mínimo p/ uma fonte CONFIRMAR a estratégia
LIMIAR_VETO_FONTE: float = 0.35           # score mínimo p/ uma fonte CONTRÁRIA contar como veto
MIN_FONTES_ALINHADAS_CONFIRMA: int = 1    # nº de fontes alinhadas p/ liberar o trade
MIN_FONTES_CONTRARIAS_VETA: int = 2       # nº de fontes contrárias p/ vetar o trade


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def normalizar_acao(acao: str | None) -> str:
    valor = str(acao or "HOLD").upper()
    if valor in {"BUY", "SELL"}:
        return valor
    return "HOLD"


def acao_para_sinal(acao: str | None) -> int:
    valor = normalizar_acao(acao)
    if valor == "BUY":
        return 1
    if valor == "SELL":
        return -1
    return 0


def score_para_acao(score: float, limiar: float = 0.12) -> str:
    if score >= limiar:
        return "BUY"
    if score <= -limiar:
        return "SELL"
    return "HOLD"


def score_da_acao(acao: str | None, intensidade: float) -> float:
    return acao_para_sinal(acao) * _clamp(abs(float(intensidade or 0.0)), 0.0, 1.0)


@dataclass(slots=True)
class FonteConsenso:
    nome: str
    acao: str
    score: float
    peso: float
    detalhe: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nome": self.nome,
            "acao": self.acao,
            "score": self.score,
            "peso": self.peso,
            "detalhe": self.detalhe,
        }


def consolidar_decisao(
    *,
    sinal_base: dict[str, Any],
    score_modelo: float,
    score_llm: float,
    confirmacao: dict[str, Any],
    probabilidade_trade: dict[str, Any],
    lucro_liquido_esperado: float,
    lucro_liquido_minimo: float,
    force_allow: bool = False,
) -> dict[str, Any]:
    acao_estrategia = normalizar_acao(sinal_base.get("acao"))
    confianca_base = _clamp(float(sinal_base.get("confianca", 0.0) or 0.0), 0.0, 1.0)
    score_confirmacao = _clamp(float(confirmacao.get("score_direcional", 0.0) or 0.0), -1.0, 1.0)
    score_probabilidade = _clamp(
        float(probabilidade_trade.get("prob_up", 0.5) or 0.5) - float(probabilidade_trade.get("prob_down", 0.5) or 0.5),
        -1.0,
        1.0,
    )

    fontes = [
        FonteConsenso(
            nome="estrategia",
            acao=acao_estrategia,
            score=score_da_acao(acao_estrategia, max(confianca_base, 0.15 if acao_estrategia != "HOLD" else 0.0)),
            peso=0.36,
            detalhe={"confianca_base": confianca_base},
        ),
        FonteConsenso(
            nome="modelo",
            acao=score_para_acao(score_modelo),
            score=_clamp(score_modelo, -1.0, 1.0),
            peso=0.22,
        ),
        FonteConsenso(
            nome="llm",
            acao=score_para_acao(score_llm, limiar=0.10),
            score=_clamp(score_llm, -1.0, 1.0),
            peso=0.16,
        ),
        FonteConsenso(
            nome="confirmacao",
            acao=score_para_acao(score_confirmacao, limiar=0.10),
            score=score_confirmacao,
            peso=0.14,
        ),
        FonteConsenso(
            nome="probabilidade",
            acao=normalizar_acao(probabilidade_trade.get("action")),
            score=score_da_acao(probabilidade_trade.get("action"), abs(score_probabilidade)),
            peso=0.12,
            detalhe={
                "prob_up": float(probabilidade_trade.get("prob_up", 0.0) or 0.0),
                "prob_down": float(probabilidade_trade.get("prob_down", 0.0) or 0.0),
            },
        ),
    ]

    soma_pesos = sum(float(item.peso) for item in fontes) or 1.0
    score_total = sum(float(item.score) * float(item.peso) for item in fontes) / soma_pesos
    acao_consenso = score_para_acao(score_total, limiar=0.08)
    alinhados = [
        item.nome
        for item in fontes
        if item.nome != "estrategia" and acao_estrategia != "HOLD" and item.acao == acao_estrategia and abs(item.score) >= LIMIAR_ALINHAMENTO_FONTE
    ]
    contrarios = [
        item.nome
        for item in fontes
        if item.nome != "estrategia" and acao_estrategia != "HOLD" and item.acao not in {"HOLD", acao_estrategia} and abs(item.score) >= LIMIAR_VETO_FONTE
    ]

    motivo_extra = "consenso_neutro"
    acao_final = acao_estrategia
    consenso_forte = acao_consenso == acao_estrategia and abs(float(score_total or 0.0)) >= 0.12
    prob_up = float(probabilidade_trade.get("prob_up", 0.0) or 0.0)
    prob_down = float(probabilidade_trade.get("prob_down", 0.0) or 0.0)
    vantagem_prob = prob_up if acao_estrategia == "BUY" else prob_down
    if acao_estrategia == "BUY" and not bool(confirmacao.get("permitir_buy", False)) and not force_allow:
        if consenso_forte and vantagem_prob >= 0.56:
            acao_final = "BUY"
            motivo_extra = "confirmacao_multi_timeframe_superada_por_consenso"
        else:
            acao_final = "HOLD"
            motivo_extra = "bloqueado_por_confirmacao_multi_timeframe"
    elif acao_estrategia == "SELL" and not bool(confirmacao.get("permitir_sell", False)) and not force_allow:
        if consenso_forte and vantagem_prob >= 0.56:
            acao_final = "SELL"
            motivo_extra = "confirmacao_multi_timeframe_superada_por_consenso"
        else:
            acao_final = "HOLD"
            motivo_extra = "bloqueado_por_confirmacao_multi_timeframe"
    elif lucro_liquido_esperado < float(lucro_liquido_minimo) and not force_allow:
        acao_final = "HOLD"
        motivo_extra = "bloqueado_por_lucro_liquido_minimo"
    elif acao_estrategia == "HOLD":
        acao_final = "HOLD"
        motivo_extra = "estrategia_em_hold"
    elif len(alinhados) >= MIN_FONTES_ALINHADAS_CONFIRMA:
        acao_final = acao_estrategia
        motivo_extra = "consenso_favoravel"
    elif acao_consenso == acao_estrategia:
        acao_final = acao_estrategia
        motivo_extra = "consenso_ponderado_favoravel"
    elif len(contrarios) >= MIN_FONTES_CONTRARIAS_VETA and not force_allow:
        acao_final = "HOLD"
        motivo_extra = "bloqueado_por_consenso_contrario"

    confianca_consenso = _clamp(
        confianca_base + (score_total * acao_para_sinal(acao_final) * 0.18) + (len(alinhados) * 0.04) - (len(contrarios) * 0.05),
        0.05,
        0.99,
    )

    return {
        "acao": acao_final,
        "confianca": confianca_consenso if acao_final != "HOLD" else _clamp(confianca_base, 0.05, 0.99),
        "motivo": motivo_extra,
        "score_total": _clamp(score_total, -1.0, 1.0),
        "acao_consenso": acao_consenso,
        "fontes_alinhadas": alinhados,
        "fontes_contrarias": contrarios,
        "fontes": [item.to_dict() for item in fontes],
    }
