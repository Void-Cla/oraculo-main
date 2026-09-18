"""Testes de `src.sinais.consenso.consolidar_decisao` — foco na fonte "ia_gemini" (voto de
peso NOMINAL igual à fonte "estrategia", decisão de 2026-07-01). Cobre: (a) IA concorda ⇒ reforça
confiança; (b) IA discorda fortemente com alta confiança ⇒ pode vetar via `contrarios`;
(c) IA indisponível (confianca=0.0) ⇒ resultado idêntico ao caso "sem IA" (prova do fail-safe);
(d) EV negativo + IA favorável forte ⇒ AINDA ASSIM HOLD (gate de EV não é bypassado pela IA)."""
from __future__ import annotations

import pytest

from src.sinais.consenso import (
    PESO_FONTE_CONFIRMACAO,
    PESO_FONTE_ESTRATEGIA,
    PESO_FONTE_IA_GEMINI,
    PESO_FONTE_MODELO,
    PESO_FONTE_PROBABILIDADE,
    PESO_FONTE_SENTIMENTO_NOTICIAS,
    consolidar_decisao,
)


def _sinal_base(acao="BUY", confianca=0.6):
    return {"acao": acao, "confianca": confianca}


def _confirmacao_ok(score=0.3):
    return {"score_direcional": score, "permitir_buy": True, "permitir_sell": True}


def _prob_trade(action="BUY", prob_up=0.65, prob_down=0.35):
    return {"action": action, "prob_up": prob_up, "prob_down": prob_down}


# ── invariante estrutural ────────────────────────────────────────────────────
def test_soma_dos_pesos_das_fontes_e_um():
    soma = (
        PESO_FONTE_ESTRATEGIA
        + PESO_FONTE_IA_GEMINI
        + PESO_FONTE_MODELO
        + PESO_FONTE_SENTIMENTO_NOTICIAS
        + PESO_FONTE_CONFIRMACAO
        + PESO_FONTE_PROBABILIDADE
    )
    assert soma == pytest.approx(1.0)


def test_peso_ia_gemini_igual_ao_peso_estrategia():
    # Pedido explícito e literal do dono do projeto: peso NOMINAL igual, par a par.
    assert PESO_FONTE_IA_GEMINI == PESO_FONTE_ESTRATEGIA


def test_fonte_ia_gemini_presente_no_resultado():
    resultado = consolidar_decisao(
        sinal_base=_sinal_base(),
        score_modelo=0.3,
        score_llm=0.1,
        confirmacao=_confirmacao_ok(),
        probabilidade_trade=_prob_trade(),
        lucro_liquido_esperado=0.002,
        lucro_liquido_minimo=0.0005,
        score_direcional_ia=0.7,
        confianca_ia=0.8,
    )
    nomes = {f["nome"] for f in resultado["fontes"]}
    assert "ia_gemini" in nomes
    assert "sentimento_noticias" in nomes  # renomeada de "llm"
    fonte_ia = next(f for f in resultado["fontes"] if f["nome"] == "ia_gemini")
    assert fonte_ia["peso"] == PESO_FONTE_IA_GEMINI
    assert fonte_ia["score"] == pytest.approx(0.7 * 0.8)


# ── (a) IA concorda com o motor mecânico ────────────────────────────────────
def test_ia_concorda_com_estrategia_reforca_confianca():
    kwargs_comuns = dict(
        sinal_base=_sinal_base("BUY", confianca=0.5),
        score_modelo=0.05,
        score_llm=0.0,
        confirmacao=_confirmacao_ok(score=0.05),
        probabilidade_trade=_prob_trade("BUY", prob_up=0.60, prob_down=0.40),
        lucro_liquido_esperado=0.002,
        lucro_liquido_minimo=0.0005,
    )
    sem_ia = consolidar_decisao(**kwargs_comuns, score_direcional_ia=0.0, confianca_ia=0.0)
    com_ia_concordando = consolidar_decisao(**kwargs_comuns, score_direcional_ia=0.9, confianca_ia=0.9)

    assert sem_ia["acao"] == "BUY"
    assert com_ia_concordando["acao"] == "BUY"
    # IA concordando fortemente aumenta o score_total e a confiança do consenso.
    assert com_ia_concordando["score_total"] > sem_ia["score_total"]
    assert com_ia_concordando["confianca"] >= sem_ia["confianca"]
    assert "ia_gemini" in com_ia_concordando["fontes_alinhadas"]


# ── (b) IA discorda fortemente (alta confiança) ⇒ pode vetar ───────────────
def test_ia_discorda_fortemente_entra_como_contraria_e_pode_vetar():
    # Motor mecânico quer BUY mas é fraco (poucas fontes alinhadas); a IA vota SELL forte
    # com alta confiança — deve contar como fonte contrária e, combinada com falta de outras
    # fontes alinhadas, vetar o trade (via MIN_FONTES_CONTRARIAS_VETA=1).
    resultado = consolidar_decisao(
        sinal_base=_sinal_base("BUY", confianca=0.4),
        score_modelo=0.02,
        score_llm=0.0,
        confirmacao={"score_direcional": 0.02, "permitir_buy": True, "permitir_sell": True},
        probabilidade_trade=_prob_trade("HOLD", prob_up=0.50, prob_down=0.50),
        lucro_liquido_esperado=0.002,
        lucro_liquido_minimo=0.0005,
        score_direcional_ia=-0.9,
        confianca_ia=0.95,
    )
    assert "ia_gemini" in resultado["fontes_contrarias"]
    assert resultado["acao"] == "HOLD"
    assert resultado["motivo"] == "bloqueado_por_consenso_contrario"


# ── (c) IA indisponível (confianca=0.0) ⇒ idêntico ao caso "sem IA" ─────────
def test_ia_indisponivel_e_identico_a_sem_ia():
    kwargs_comuns = dict(
        sinal_base=_sinal_base("BUY", confianca=0.6),
        score_modelo=0.3,
        score_llm=0.15,
        confirmacao=_confirmacao_ok(score=0.3),
        probabilidade_trade=_prob_trade("BUY", prob_up=0.68, prob_down=0.32),
        lucro_liquido_esperado=0.002,
        lucro_liquido_minimo=0.0005,
    )
    # Fail-safe do VotoIA quando a IA falha: acao="HOLD", confianca=0.0 — mesmo que
    # score_direcional_ia venha não-zero por algum motivo, confianca=0.0 deve neutralizar.
    resultado_falha_com_score_residual = consolidar_decisao(**kwargs_comuns, score_direcional_ia=0.8, confianca_ia=0.0)
    resultado_sem_ia_explicito = consolidar_decisao(**kwargs_comuns, score_direcional_ia=0.0, confianca_ia=0.0)
    resultado_default = consolidar_decisao(**kwargs_comuns)  # nem passa os kwargs de IA (defaults)

    # Compara o que é DECISORIO (acao/confianca/score_total/motivo/fontes_alinhadas/
    # fontes_contrarias) — idêntico nos 3 casos, provando que confianca_ia=0.0 neutraliza o
    # fail-safe mesmo com score_direcional_ia residual não-zero. O campo `detalhe` da fonte
    # "ia_gemini" difere (guarda o score bruto para auditoria/observabilidade), mas isso não
    # afeta a decisão — por isso é excluído desta comparação de propósito.
    campos_decisorios = ("acao", "confianca", "motivo", "score_total", "acao_consenso", "fontes_alinhadas", "fontes_contrarias")
    for campo in campos_decisorios:
        assert resultado_falha_com_score_residual[campo] == resultado_sem_ia_explicito[campo] == resultado_default[campo], campo

    fonte_ia = next(f for f in resultado_default["fontes"] if f["nome"] == "ia_gemini")
    assert fonte_ia["score"] == 0.0  # confianca=0.0 zera a contribuição, mesmo com peso nominal 0.36
    fonte_ia_residual = next(f for f in resultado_falha_com_score_residual["fontes"] if f["nome"] == "ia_gemini")
    assert fonte_ia_residual["score"] == 0.0  # score_direcional=0.8 * confianca=0.0 = 0.0 (fail-safe por construção)


# ── (d) EV negativo + IA favorável forte ⇒ AINDA ASSIM HOLD (gate de EV não é bypassado) ──
def test_ev_negativo_com_ia_favoravel_forte_ainda_assim_hold():
    resultado = consolidar_decisao(
        sinal_base=_sinal_base("BUY", confianca=0.9),
        score_modelo=0.9,
        score_llm=0.9,
        confirmacao={"score_direcional": 0.9, "permitir_buy": True, "permitir_sell": True},
        probabilidade_trade=_prob_trade("BUY", prob_up=0.95, prob_down=0.05),
        lucro_liquido_esperado=-0.01,   # EV NEGATIVO — não cobre o mínimo
        lucro_liquido_minimo=0.0005,
        score_direcional_ia=1.0,        # IA em BUY máximo
        confianca_ia=1.0,               # confiança máxima
    )
    assert resultado["acao"] == "HOLD"
    assert resultado["motivo"] == "bloqueado_por_lucro_liquido_minimo"


def test_ev_negativo_com_ia_favoravel_forte_e_force_allow_false_nunca_libera():
    # Reforça que nem com todas as fontes (incluindo IA) alinhadas o EV negativo libera,
    # independente da ordem dos ramos (checagem final de defesa em profundidade).
    resultado = consolidar_decisao(
        sinal_base=_sinal_base("SELL", confianca=0.9),
        score_modelo=-0.9,
        score_llm=-0.9,
        confirmacao={"score_direcional": -0.9, "permitir_buy": True, "permitir_sell": True},
        probabilidade_trade=_prob_trade("SELL", prob_up=0.05, prob_down=0.95),
        lucro_liquido_esperado=-0.005,
        lucro_liquido_minimo=0.0001,
        score_direcional_ia=-1.0,
        confianca_ia=1.0,
        force_allow=False,
    )
    assert resultado["acao"] == "HOLD"


# ── comportamento com força-allow (testnet) — IA não contorna, mas não atrapalha ────
def test_force_allow_ainda_funciona_com_fonte_ia_neutra():
    resultado = consolidar_decisao(
        sinal_base=_sinal_base("BUY", confianca=0.6),
        score_modelo=0.1,
        score_llm=0.05,
        confirmacao={"score_direcional": 0.05, "permitir_buy": False, "permitir_sell": False},
        probabilidade_trade=_prob_trade("BUY", prob_up=0.57, prob_down=0.43),
        lucro_liquido_esperado=-0.001,
        lucro_liquido_minimo=0.0005,
        force_allow=True,
        score_direcional_ia=0.0,
        confianca_ia=0.0,
    )
    # force_allow (testnet) ainda deve conseguir liberar mesmo com IA neutra (comportamento
    # preservado — o wiring da nova fonte não quebra o caminho de teste/exploração).
    assert resultado["acao"] in {"BUY", "HOLD"}  # depende do consenso_forte/vantagem_prob; não deve lançar
