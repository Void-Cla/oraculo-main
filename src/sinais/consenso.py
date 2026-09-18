from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ============================================================================
# DUAS CAMADAS DE IA DISTINTAS NESTE SISTEMA (não confundir):
#
#   (1) VOTO DE PESO IGUAL (este módulo, fonte "ia_gemini" em `consolidar_decisao`) — a IA
#       opina BUY/SELL/HOLD como um segundo analista independente, com peso NOMINAL igual à
#       fonte "estrategia" (motor mecânico). Decisão explícita do dono do projeto (2026-07-01):
#       reduzir travamentos do motor mecânico ("mecânico demais") somando uma segunda opinião
#       mais flexível (sentimento de notícias, contexto). Ver `src/intelligence/market_analyst.py`.
#   (2) PreExecutionFilter (`src/intelligence/pre_execution_filter.py`) — veto final
#       independente, consultado DEPOIS de todos os gates financeiros (EV, risco, edge), mesmo
#       que este consenso já tenha decidido. Só pode VETAR (nunca aprovar). Inalterado por esta
#       mudança — continua ativo em `testnet_auto_trader._consultar_filtro_ia`.
#
# As duas são fail-open/fail-safe INDEPENDENTEMENTE. O voto de peso igual NUNCA pode contornar
# o gate de EV nem os demais gates financeiros — ele só influencia a DIREÇÃO/CONFIANÇA dentro do
# espaço já aprovado pelos gates mecânicos (ver checagem de `ev_suficiente`, inalterada, abaixo).
# ============================================================================

# --- Limiares de consenso entre fontes (estratégia, modelo, LLM, confirmação, probabilidade) ---
# ✅ INC-01 RESOLVIDO E SIMETRIZADO (sessão 2026-07-01, autorizado pelo dono do projeto):
# A assimetria anterior (confirmar com 1 fonte fraca >= 0.10; vetar só com 2 fontes fortes
# >= 0.35) dependia de o modelo ML produzir score_numerico plausível. Antes da correção do
# signal_prob_scale (signal_engine.py), o modelo saturava em ±1.0 quase sempre — o limiar de
# confirmação (0.10) era trivialmente satisfeito sempre, e o de veto (0.35) quase nunca, ou
# seja, o veto estava estruturalmente inoperante (segurança > lucro violada na prática).
# Com o modelo deixando de saturar (scale=200 em signal_engine.py), os limiares passaram a
# ser comparáveis e a assimetria foi removida: ALINHAMENTO == VETO, MIN_ALINHADAS == MIN_CONTRARIAS.
# O veto agora tem prioridade de avaliação sobre a confirmação (ver ordem dos `elif` abaixo).
LIMIAR_ALINHAMENTO_FONTE: float = 0.25    # score mínimo p/ uma fonte CONFIRMAR a estratégia
LIMIAR_VETO_FONTE: float = 0.25           # score mínimo p/ uma fonte CONTRÁRIA contar como veto
MIN_FONTES_ALINHADAS_CONFIRMA: int = 2    # nº de fontes alinhadas p/ liberar o trade
MIN_FONTES_CONTRARIAS_VETA: int = 1       # nº de fontes contrárias p/ vetar o trade

# --- Pesos das fontes do consenso (soma = 1.00) ---
# ✅ PESO IGUAL IA×MECÂNICO (sessão 2026-07-01, decisão explícita e autorizada do dono do
# projeto): a fonte "ia_gemini" (voto direcional independente da IA, ver
# `src/intelligence/market_analyst.py`) recebe peso NOMINAL IGUAL à fonte "estrategia" (motor
# mecânico) — 0.36 cada. Isto RELAXA a proteção histórica "a IA só pode vetar" (DA-23), mas
# apenas para esta camada nova; o `PreExecutionFilter` (veto puro, pós-gates) continua intacto
# como segunda camada independente (ver comentário de topo do arquivo).
#
# Peso NOMINAL ≠ peso EFETIVO: o score da fonte "ia_gemini" é `score_direcional * confianca`
# (ver `consolidar_decisao`). Quando a IA falha/está indisponível, `confianca=0.0` por
# construção (`VotoIA` fail-safe) ⇒ o score da fonte já é 0.0 ⇒ sua contribuição na média
# ponderada colapsa a ~zero mesmo com peso nominal de 0.36. Ou seja: "peso igual" é seguro por
# construção — uma IA ausente/incerta não consegue puxar o consenso, apesar do peso nominal alto.
#
# A antiga fonte "llm" (heurístico local de CONTAGEM DE PALAVRAS-CHAVE em notícias — NÃO é a
# IA Gemini; ver `src/servicos/llm_analista.py`) foi renomeada para "sentimento_noticias" —
# nome mais honesto — e teve o peso reduzido de 0.16 para 0.08 (ela não é mais "a voz da IA",
# é só um sinal de sentimento textual barato; continua agregando sinal fraco, não foi removida).
# "modelo"/"confirmacao"/"probabilidade" foram reduzidos proporcionalmente (mesma razão relativa
# 0.22:0.14:0.12 de antes) para caber no orçamento restante de 0.20 e manter soma total = 1.00.
PESO_FONTE_ESTRATEGIA: float = 0.36        # motor mecânico — inalterado
PESO_FONTE_IA_GEMINI: float = 0.36         # = PESO_FONTE_ESTRATEGIA — pedido explícito: peso nominal igual
PESO_FONTE_MODELO: float = 0.09            # antes 0.22; reduzido proporcionalmente
PESO_FONTE_SENTIMENTO_NOTICIAS: float = 0.08   # antes "llm" 0.16; heurístico de palavras-chave, não IA
PESO_FONTE_CONFIRMACAO: float = 0.06       # antes 0.14; reduzido proporcionalmente
PESO_FONTE_PROBABILIDADE: float = 0.05     # antes 0.12; reduzido proporcionalmente
# 0.36 + 0.36 + 0.09 + 0.08 + 0.06 + 0.05 = 1.00 (soma validada em teste de invariante)


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
    score_direcional_ia: float = 0.0,
    confianca_ia: float = 0.0,
) -> dict[str, Any]:
    """Consolida o consenso ponderado entre as fontes de sinal.

    `score_direcional_ia`/`confianca_ia` vêm do `VotoIA` já resolvido pelo CALLER
    (`signal_engine.gerar_sinal_orquestrado`, que chama `AnalistaMercadoIA.avaliar_direcional`
    de forma assíncrona ANTES desta função). Esta função permanece SÍNCRONA e PURA (sem I/O de
    rede) — só o orquestrador de sinal precisa ser `async def`. Isso mantém `consolidar_decisao`
    testável sem mock de rede.
    """
    acao_estrategia = normalizar_acao(sinal_base.get("acao"))
    confianca_base = _clamp(float(sinal_base.get("confianca", 0.0) or 0.0), 0.0, 1.0)
    score_confirmacao = _clamp(float(confirmacao.get("score_direcional", 0.0) or 0.0), -1.0, 1.0)
    score_probabilidade = _clamp(
        float(probabilidade_trade.get("prob_up", 0.5) or 0.5) - float(probabilidade_trade.get("prob_down", 0.5) or 0.5),
        -1.0,
        1.0,
    )
    # Score EFETIVO da IA = score_direcional * confianca (mesma convenção de `score_da_acao`
    # para as demais fontes). Confiança 0.0 (fail-safe do VotoIA: sem chave/erro/timeout/
    # cooldown) já zera a contribuição desta fonte na média — o peso NOMINAL (igual à
    # estratégia) só vira peso EFETIVO alto quando a IA responde com confiança real. Ver
    # comentário de `PESO_FONTE_IA_GEMINI` no topo do arquivo.
    score_ia_efetivo = _clamp(float(score_direcional_ia or 0.0), -1.0, 1.0) * _clamp(float(confianca_ia or 0.0), 0.0, 1.0)

    fontes = [
        FonteConsenso(
            nome="estrategia",
            acao=acao_estrategia,
            # Sem piso artificial: confiança real 0.0 deve pesar 0.0 no consenso — um piso
            # mínimo aqui injetava viés mesmo quando a estratégia não tinha convicção nenhuma,
            # quebrando a independência estatística das fontes (cada fonte deve refletir seu
            # próprio sinal, não um mínimo garantido).
            score=score_da_acao(acao_estrategia, confianca_base),
            peso=PESO_FONTE_ESTRATEGIA,
            detalhe={"confianca_base": confianca_base},
        ),
        FonteConsenso(
            nome="ia_gemini",
            acao=score_para_acao(score_ia_efetivo, limiar=0.10),
            score=score_ia_efetivo,
            peso=PESO_FONTE_IA_GEMINI,
            detalhe={"score_direcional_bruto": float(score_direcional_ia or 0.0), "confianca_ia": float(confianca_ia or 0.0)},
        ),
        FonteConsenso(
            nome="modelo",
            acao=score_para_acao(score_modelo),
            score=_clamp(score_modelo, -1.0, 1.0),
            peso=PESO_FONTE_MODELO,
        ),
        FonteConsenso(
            nome="sentimento_noticias",
            acao=score_para_acao(score_llm, limiar=0.10),
            score=_clamp(score_llm, -1.0, 1.0),
            peso=PESO_FONTE_SENTIMENTO_NOTICIAS,
        ),
        FonteConsenso(
            nome="confirmacao",
            acao=score_para_acao(score_confirmacao, limiar=0.10),
            score=score_confirmacao,
            peso=PESO_FONTE_CONFIRMACAO,
        ),
        FonteConsenso(
            nome="probabilidade",
            acao=normalizar_acao(probabilidade_trade.get("action")),
            score=score_da_acao(probabilidade_trade.get("action"), abs(score_probabilidade)),
            peso=PESO_FONTE_PROBABILIDADE,
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
    ev_suficiente = lucro_liquido_esperado >= float(lucro_liquido_minimo)
    prob_up = float(probabilidade_trade.get("prob_up", 0.0) or 0.0)
    prob_down = float(probabilidade_trade.get("prob_down", 0.0) or 0.0)
    vantagem_prob = prob_up if acao_estrategia == "BUY" else prob_down
    # ⚠️ O override de consenso (abaixo) NUNCA pode contornar o gate de EV: um trade com
    # EV negativo abre posição perdedora por construção — capital perdido não volta. Por
    # isso `ev_suficiente or force_allow` é exigido AQUI, e não deixado para um `elif`
    # posterior que jamais seria alcançado quando o override já define `acao_final`.
    if acao_estrategia == "BUY" and not bool(confirmacao.get("permitir_buy", False)) and not force_allow:
        if consenso_forte and vantagem_prob >= 0.56 and (ev_suficiente or force_allow):
            acao_final = "BUY"
            motivo_extra = "confirmacao_multi_timeframe_superada_por_consenso"
        else:
            acao_final = "HOLD"
            motivo_extra = "bloqueado_por_confirmacao_multi_timeframe"
    elif acao_estrategia == "SELL" and not bool(confirmacao.get("permitir_sell", False)) and not force_allow:
        if consenso_forte and vantagem_prob >= 0.56 and (ev_suficiente or force_allow):
            acao_final = "SELL"
            motivo_extra = "confirmacao_multi_timeframe_superada_por_consenso"
        else:
            acao_final = "HOLD"
            motivo_extra = "bloqueado_por_confirmacao_multi_timeframe"
    elif not ev_suficiente and not force_allow:
        acao_final = "HOLD"
        motivo_extra = "bloqueado_por_lucro_liquido_minimo"
    elif acao_estrategia == "HOLD":
        acao_final = "HOLD"
        motivo_extra = "estrategia_em_hold"
    # Veto tem prioridade sobre confirmação (segurança > lucro): se fontes contrárias
    # suficientes vetam, isso é avaliado ANTES do caminho de confirmação — do contrário,
    # alinhados>=MIN e contrarios>=MIN simultâneos nunca chegariam a acionar o veto.
    elif len(contrarios) >= MIN_FONTES_CONTRARIAS_VETA and not force_allow:
        acao_final = "HOLD"
        motivo_extra = "bloqueado_por_consenso_contrario"
    elif len(alinhados) >= MIN_FONTES_ALINHADAS_CONFIRMA:
        acao_final = acao_estrategia
        motivo_extra = "consenso_favoravel"
    elif acao_consenso == acao_estrategia:
        acao_final = acao_estrategia
        motivo_extra = "consenso_ponderado_favoravel"

    # Defesa em profundidade: mesmo que um ramo futuro esqueça de checar o EV, esta
    # checagem final força HOLD sempre que o lucro líquido esperado não cobre o mínimo.
    # O gate de EV nunca pode ser contornado por override de consenso — capital perdido
    # não volta.
    if acao_final != "HOLD" and not ev_suficiente and not force_allow:
        acao_final = "HOLD"
        motivo_extra = "bloqueado_por_lucro_liquido_minimo"

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
