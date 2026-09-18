"""Constrói contexto estruturado (JSON) para a IA a partir do banco REAL do Oráculo.

Lê os repositórios concretos (métodos estáticos) de forma DEFENSIVA — nenhum campo ausente
pode quebrar a montagem do contexto (a IA é consultiva; falha aqui não derruba o bot).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from src.observabilidade.logger import get_logger
from src.persistencia.repositorio_features import RepositorioFeatures
from src.persistencia.repositorio_ohlcv import RepositorioOhlcv
from src.persistencia.repositorio_ordens import RepositorioOrdens

LOG = get_logger("context_builder")


def _resultado_trade(ordem: dict[str, Any]) -> str:
    lucro = ordem.get("lucro_usdt")
    if lucro is None:
        return "ABERTO"
    return "WIN" if float(lucro) > 0 else "LOSS"


# ── Compactação de contexto (DA-32) ─────────────────────────────────────────
# O free tier do Gemini limita também TOKENS/minuto, e payload menor = resposta mais rápida.
# A IA não precisa de floats com 12 casas nem de 20 velas verbosas para formar um voto
# direcional — precisa do DESENHO do mercado. Compactar corta ~60% dos tokens do contexto
# sem perder informação de decisão.

# Janela de velas enviada à IA: 12 cobre ~12min de 1m (o horizonte do micro-trading 1-15m).
_VELAS_IA = 12
# Histórico de trades: 5 últimos bastam para a IA ver o padrão recente (win/loss/lado).
_TRADES_IA = 5
# Notícias: 5 manchetes com sentimento — mais que isso vira ruído no prompt.
_NOTICIAS_IA = 5
# Título de notícia truncado — a manchete inteira raramente muda o sentimento já calculado.
_TITULO_MAX = 90


def _r(valor: Any, casas: int = 6) -> Any:
    """Arredonda floats para poucas casas (token-friendly); passa outros tipos intactos."""
    try:
        return round(float(valor), casas)
    except (TypeError, ValueError):
        return valor


def _velas_compactas(velas: list[dict[str, Any]], limite: int = _VELAS_IA) -> list[list[Any]]:
    """Velas como arrays [ts, abre, max, min, fecha, volume] — sem repetir chaves por vela."""
    return [
        [int(v.get("ts", 0) or 0), _r(v.get("open")), _r(v.get("high")), _r(v.get("low")), _r(v.get("close")), _r(v.get("volume"), 3)]
        for v in velas[-limite:]
    ]


def _features_compactas(features: dict[str, Any]) -> dict[str, Any]:
    """Mesmas chaves, floats arredondados — a IA não distingue 0.001234567891011 de 0.001235."""
    return {k: _r(v) for k, v in features.items() if v is not None}


def _historico_compacto(trades: list[dict[str, Any]], limite: int = _TRADES_IA) -> list[dict[str, Any]]:
    """Só o que informa o voto: resultado, lado, lucro e regime — sem estratégia/duração."""
    return [
        {
            "resultado": _resultado_trade(t),
            "lado": t.get("lado"),
            "lucro_usdt": _r(t.get("lucro_usdt"), 4),
            "regime": t.get("regime"),
        }
        for t in trades[:limite]
    ]


def _noticias_compactas(noticias: list[Any] | None, limite: int = _NOTICIAS_IA) -> list[dict[str, Any]]:
    return [
        {"titulo": str(item.get("titulo") or "")[:_TITULO_MAX], "sentimento": _r(item.get("sentimento"), 3)}
        for item in (noticias or [])
        if isinstance(item, dict)
    ][:limite]


async def construir_contexto_pre_execucao(simbolo: str, sinal: dict[str, Any], saldo: float) -> str:
    """Contexto para o filtro de pré-execução (sinal mecânico + features + histórico)."""
    try:
        trades = await RepositorioOrdens.listar_recentes(simbolo=simbolo, limite=_TRADES_IA)
    except Exception as exc:  # repositório indisponível não pode travar a IA
        LOG.warning("falha_contexto_trades", extra={"erro": str(exc)})
        trades = []
    try:
        features_rows = await RepositorioFeatures.listar_ultimas(simbolo, limite=1)
        features = (features_rows[0].get("features") if features_rows else {}) or {}
    except Exception as exc:
        LOG.warning("falha_contexto_features", extra={"erro": str(exc)})
        features = {}
    try:
        velas = await RepositorioOhlcv.obter_ultimas(simbolo, limite=_VELAS_IA)
    except Exception as exc:
        LOG.warning("falha_contexto_velas", extra={"erro": str(exc)})
        velas = []

    contexto = {
        "simbolo": simbolo,
        "sinal_mecanico": {
            "acao": sinal.get("acao"),
            "confianca": _r(sinal.get("confianca"), 4),
            "estrategia": sinal.get("estrategia") or (sinal.get("detalhe") or {}).get("estrategia"),
            "regime": sinal.get("regime") or (sinal.get("detalhe") or {}).get("regime"),
            "ev_liquido_usdt": _r(sinal.get("ev_liquido_usdt"), 6),
            "lucro_liquido_esperado_pct": _r(sinal.get("lucro_liquido_esperado_pct"), 6),
        },
        "saldo_disponivel_usdt": round(float(saldo or 0.0), 2),
        "features_atuais": _features_compactas(features),
        "formato_velas": "[ts, abre, maxima, minima, fecha, volume]",
        "velas_recentes": _velas_compactas(velas),
        "historico_performance": _historico_compacto(trades),
    }
    return json.dumps(contexto, ensure_ascii=False, default=str)


async def construir_contexto_analise_direcional(simbolo: str, saldo: float, noticias: list[Any] | None = None) -> str:
    """Contexto para o voto DIRECIONAL de peso igual (`AnalistaMercadoIA`).

    Deliberadamente OMITE o campo `sinal_mecanico` (presente em `construir_contexto_pre_execucao`)
    — a IA deve formar sua própria opinião sem saber o que o motor mecânico decidiu, para não
    ancorar/enviesar a resposta na decisão que ela mesma vai ajudar a ponderar no consenso.
    """
    try:
        trades = await RepositorioOrdens.listar_recentes(simbolo=simbolo, limite=_TRADES_IA)
    except Exception as exc:  # repositório indisponível não pode travar a IA
        LOG.warning("falha_contexto_direcional_trades", extra={"erro": str(exc)})
        trades = []
    try:
        features_rows = await RepositorioFeatures.listar_ultimas(simbolo, limite=1)
        features = (features_rows[0].get("features") if features_rows else {}) or {}
    except Exception as exc:
        LOG.warning("falha_contexto_direcional_features", extra={"erro": str(exc)})
        features = {}
    try:
        velas = await RepositorioOhlcv.obter_ultimas(simbolo, limite=_VELAS_IA)
    except Exception as exc:
        LOG.warning("falha_contexto_direcional_velas", extra={"erro": str(exc)})
        velas = []

    contexto = {
        "simbolo": simbolo,
        "saldo_disponivel_usdt": round(float(saldo or 0.0), 2),
        "features_atuais": _features_compactas(features),
        "formato_velas": "[ts, abre, maxima, minima, fecha, volume]",
        "velas_recentes": _velas_compactas(velas),
        "noticias_recentes": _noticias_compactas(noticias),
        "historico_performance": _historico_compacto(trades),
    }
    return json.dumps(contexto, ensure_ascii=False, default=str)


async def construir_contexto_analise_direcional_lote(
    simbolos: list[str],
    saldo: float,
    noticias_por_simbolo: dict[str, list[Any]] | None = None,
) -> str:
    """Contexto EM LOTE para o voto direcional (`AnalistaMercadoIA.avaliar_lote`).

    Reusa `construir_contexto_analise_direcional` por símbolo (mesmos campos, mesma omissão
    deliberada de `sinal_mecanico`) e busca todos em paralelo — o ganho de rede está em enviar
    UM payload para a IA, não em economizar as leituras do próprio banco (que já eram baratas).
    `noticias_por_simbolo` é opcional; símbolo ausente do dict usa lista vazia (mesmo fail-safe
    de `noticias=None` no caminho por símbolo).
    """
    noticias_por_simbolo = noticias_por_simbolo or {}
    contextos_brutos = await asyncio.gather(
        *(
            construir_contexto_analise_direcional(simbolo, saldo, noticias_por_simbolo.get(simbolo))
            for simbolo in simbolos
        ),
        return_exceptions=True,
    )

    itens: list[dict[str, Any]] = []
    for simbolo, resultado in zip(simbolos, contextos_brutos):
        if isinstance(resultado, Exception):
            LOG.warning("falha_contexto_direcional_lote_simbolo", extra={"simbolo": simbolo, "erro": str(resultado)})
            itens.append({"simbolo": simbolo, "saldo_disponivel_usdt": round(float(saldo or 0.0), 2)})
            continue
        itens.append(json.loads(resultado))

    return json.dumps({"simbolos": itens}, ensure_ascii=False, default=str)


async def construir_contexto_auditoria(limite: int = 50) -> str:
    """Contexto para a auditoria pós-trade (agregados + trades detalhados)."""
    try:
        trades = await RepositorioOrdens.listar_recentes(limite=limite)
    except Exception as exc:
        LOG.warning("falha_contexto_auditoria", extra={"erro": str(exc)})
        trades = []
    fechados = [t for t in trades if t.get("lucro_usdt") is not None]
    wins = [t for t in fechados if float(t["lucro_usdt"]) > 0]
    contexto = {
        "total_trades": len(trades),
        "trades_fechados": len(fechados),
        "wins": len(wins),
        "losses": len(fechados) - len(wins),
        "taxa_acerto": (len(wins) / len(fechados)) if fechados else 0.0,
        "lucro_total_usdt": sum(float(t["lucro_usdt"]) for t in fechados),
        "trades_detalhados": [
            {
                "simbolo": t.get("simbolo"),
                "estrategia": t.get("estrategia"),
                "regime": t.get("regime"),
                "resultado": _resultado_trade(t),
                "lucro_usdt": t.get("lucro_usdt"),
                "duracao_min": (float(t["duracao_ms"]) / 60000.0) if t.get("duracao_ms") else None,
            }
            for t in fechados
        ],
    }
    return json.dumps(contexto, ensure_ascii=False, default=str)
