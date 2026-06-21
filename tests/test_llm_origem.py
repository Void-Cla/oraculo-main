"""INC-02 — `modelo_llm` reflete a ORIGEM real da análise (não mente na auditoria)."""
from __future__ import annotations

from src.servicos.llm_analista import analisar_contexto


def _features() -> dict[str, float]:
    return {"vol5": 0.001, "spread_rel": 0.0002, "pressao_rel": 0.1, "diff_close_micro_rel": 0.0}


def test_modelo_llm_e_heuristica_quando_sem_openai():
    out = analisar_contexto([], _features(), noticias=[{"titulo": "x", "sentimento": 0.2}])
    assert out["fonte"] == "heuristica_local"
    assert out["modelo_llm"] == "heuristica_local"


def test_modelo_llm_identifica_gpt_quando_veio_do_openai():
    noticias = [{"titulo": "x", "sentimento": 0.2, "fonte_analise": "openai_responses_api"}]
    out = analisar_contexto([], _features(), noticias=noticias)
    assert out["fonte"] == "openai_responses_api"
    assert out["modelo_llm"] == "gpt-4o-mini"
