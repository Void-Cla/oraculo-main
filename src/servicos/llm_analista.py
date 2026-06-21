from __future__ import annotations

import os
from typing import Any

from src.observabilidade.logger import get_logger

LOG = get_logger("llm_analista")

_TERMOS_POSITIVOS = {
    "etf",
    "inflow",
    "bullish",
    "alta",
    "compra",
    "adocao",
    "demanda",
    "expansao",
    "halving",
    "reserva",
}
_TERMOS_NEGATIVOS = {
    "guerra",
    "ataque",
    "banimento",
    "hack",
    "bearish",
    "queda",
    "venda",
    "liquidacao",
    "tarifa",
    "recessao",
}


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def _texto_noticia(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        partes = [item.get("titulo"), item.get("descricao"), item.get("resumo"), item.get("fonte")]
        return " ".join(str(parte) for parte in partes if parte)
    return str(item)


def _sentimento_noticias(noticias: list[Any] | None) -> tuple[float, list[str]]:
    if not noticias:
        return 0.0, []
    scores: list[float] = []
    tags: set[str] = set()
    for noticia in noticias:
        if isinstance(noticia, dict) and noticia.get("sentimento") is not None:
            score = _clamp(float(noticia["sentimento"]), -1.0, 1.0)
        else:
            texto = _texto_noticia(noticia).lower()
            positivos = sum(1 for termo in _TERMOS_POSITIVOS if termo in texto)
            negativos = sum(1 for termo in _TERMOS_NEGATIVOS if termo in texto)
            score = _clamp((positivos - negativos) / max(1, positivos + negativos), -1.0, 1.0)
            if "geopolit" in texto or "guerra" in texto or "tarifa" in texto:
                tags.add("macro_risco")
            if "etf" in texto or "bitcoin" in texto or "btc" in texto:
                tags.add("cripto")
        scores.append(score)
    return (sum(scores) / len(scores)), sorted(tags)


def analisar_contexto(
    historico_velas: list[Any],
    features: dict[str, Any],
    noticias: list[Any] | None = None,
    saldo: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sentimento_noticias, tags = _sentimento_noticias(noticias)
    vol = abs(float(features.get("vol5", 0.0) or 0.0))
    spread = abs(float(features.get("spread_rel", 0.0) or 0.0))
    pressao = float(features.get("pressao_rel", 0.0) or 0.0)
    micro = float(features.get("diff_close_micro_rel", 0.0) or 0.0)

    score_direcional = _clamp((sentimento_noticias * 0.55) + (pressao * 0.25) + (micro * 8.0), -1.0, 1.0)
    score_conf = _clamp(0.35 + (abs(sentimento_noticias) * 0.25) + (abs(pressao) * 0.15) - (vol * 6.0) - (spread * 10.0), 0.05, 0.95)

    direcao = "neutro"
    if score_direcional >= 0.15:
        direcao = "compra"
    elif score_direcional <= -0.15:
        direcao = "venda"

    exposicao = None
    if saldo:
        livre = float(saldo.get("saldo_livre", saldo.get("saldo_total", 0.0)) or 0.0)
        total = float(saldo.get("saldo_total", livre) or 0.0)
        exposicao = 0.0 if total <= 0 else 1.0 - (livre / total)
    if exposicao is not None and exposicao > 0.7:
        tags.append("exposicao_alta")
        score_conf = _clamp(score_conf - 0.1, 0.05, 0.95)

    insight = (
        f"Contexto {direcao}; sentimento_noticias={sentimento_noticias:.3f}; "
        f"pressao_livro={pressao:.3f}; volatilidade={vol:.5f}; spread={spread:.5f}"
    )
    fonte_analise = "heuristica_local"
    if any(isinstance(item, dict) and item.get("fonte_analise") == "openai_responses_api" for item in (noticias or [])):
        fonte_analise = "openai_responses_api"
    elif os.getenv("OPENAI_API_KEY") or os.getenv("GPT_API_KEY"):
        LOG.info("chave_llm_detectada_modo_local", extra={"modo_llm": "heuristica_local"})

    return {
        "insight": insight,
        "score_conf": score_conf,
        "score_direcional": score_direcional,
        "direcao": direcao,
        "sentimento_noticias": sentimento_noticias,
        "tags": sorted(set(tags)),
        "fonte": fonte_analise,
        # INC-02: coerente com `fonte` — só identifica o GPT quando a análise veio dele.
        "modelo_llm": "gpt-4o-mini" if fonte_analise == "openai_responses_api" else "heuristica_local",
    }
