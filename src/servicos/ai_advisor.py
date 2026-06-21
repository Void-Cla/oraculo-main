"""AI Advisor — lê DB + estado de mercado, consulta LLM e retorna recomendação de trade.

Fluxo:
  1. Carrega últimas N predições + outcomes do DB (acurácia recente)
  2. Carrega features atuais + regime + spread + volume
  3. Monta prompt estruturado
  4. Chama GPT-4o-mini (fallback: heurística local)
  5. Retorna dict com direcao, confianca_boost, capital_pct_sugerido, reasoning, risco
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

_GPT_KEY = os.getenv("GPT_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
_MODELO = "gpt-4o-mini"
_MAX_TOKENS = 300
_TIMEOUT = 8.0

# capital_pct sugerido por faixa de confiança
_CAPITAL_PCT_MAP = {
    (0.80, 1.01): 80,
    (0.70, 0.80): 60,
    (0.60, 0.70): 40,
    (0.50, 0.60): 20,
    (0.00, 0.50): 10,
}


def _capital_pct_para_confianca(confianca: float) -> int:
    for (lo, hi), pct in _CAPITAL_PCT_MAP.items():
        if lo <= confianca < hi:
            return pct
    return 10


def _remover_cerca_markdown(texto: str) -> str:
    """Remove a cerca de código markdown (```json ... ```) por SUBSTRING, não por
    conjunto de caracteres. `lstrip("```json")` apagava qualquer `{`,`j`,`s`,`o`,`n`
    inicial e podia corromper o JSON; removeprefix tira só o prefixo exato."""
    texto = (texto or "").strip()
    return texto.removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def _heuristica_local(
    regime: str,
    pred_acuracia: float,
    momentum: float,
    spread_rel: float,
) -> dict[str, Any]:
    """Fallback sem LLM: regras simples baseadas em regime e acurácia."""
    confianca = 0.50
    direcao = "HOLD"
    risco = "baixo"
    if pred_acuracia >= 0.65 and spread_rel < 0.002:
        if regime in ("TREND_UP",) and momentum > 0:
            direcao = "BUY"
            confianca = min(0.75, 0.55 + pred_acuracia * 0.25)
        elif regime in ("TREND_DOWN",) and momentum < 0:
            direcao = "SELL"
            confianca = min(0.72, 0.55 + pred_acuracia * 0.22)
        elif regime == "HIGH_VOL":
            risco = "alto"
        elif regime == "RANGE":
            direcao = "BUY" if momentum > 0.002 else ("SELL" if momentum < -0.002 else "HOLD")
            confianca = 0.54
    return {
        "direcao": direcao,
        "confianca": round(confianca, 3),
        "capital_pct_sugerido": _capital_pct_para_confianca(confianca),
        "reasoning": f"heuristica_local: regime={regime} acurácia={pred_acuracia:.2%} momentum={momentum:.5f} spread={spread_rel:.4%}",
        "risco": risco,
        "modelo": "heuristica_local",
    }


def _montar_prompt(
    simbolo: str,
    regime: str,
    features: dict[str, Any],
    predicoes: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    saldo_usdt: float,
) -> str:
    acertos = sum(1 for o in outcomes if o.get("err_rel") is not None and abs(float(o["err_rel"] or 0)) < 0.005)
    acuracia = round(acertos / max(len(outcomes), 1), 3)
    ultimo_y_hat = float((predicoes[-1] if predicoes else {}).get("y_hat") or 0.0)
    ultimo_y_cal = float((predicoes[-1] if predicoes else {}).get("y_cal") or ultimo_y_hat)
    close = float(features.get("close") or features.get("preco_atual") or 0.0)
    r_1m = float(features.get("r_1m") or 0.0)
    vol5 = float(features.get("vol5") or 0.0)
    spread = float(features.get("spread_rel") or 0.0)
    book_imb = float(features.get("book_imb") or 0.0)
    momentum = float(features.get("r_3m") or r_1m)
    return (
        f"Você é um trader quantitativo especialista em Binance spot.\n"
        f"Analise os dados abaixo e retorne APENAS JSON com os campos: "
        f"direcao (BUY/SELL/HOLD), confianca (0.0-1.0), capital_pct_sugerido (10/20/30/40/50/60/70/80/90/100), "
        f"reasoning (string curta), risco (baixo/medio/alto).\n\n"
        f"Par: {simbolo} | Regime: {regime} | Preco: {close:.2f} USDT\n"
        f"Retorno 1m: {r_1m:.5f} | Retorno 3m: {momentum:.5f} | Vol5: {vol5:.5f}\n"
        f"Spread: {spread:.5f} | BookImb: {book_imb:.4f}\n"
        f"Modelo prediz: {ultimo_y_cal:.5f} (raw: {ultimo_y_hat:.5f})\n"
        f"Acurácia recente ({len(outcomes)} amostras): {acuracia:.1%}\n"
        f"Saldo disponível: {saldo_usdt:.2f} USDT\n\n"
        f"Priorize segurança — capital_pct_sugerido alto APENAS se confianca >= 0.70 e risco=baixo.\n"
        f"Retorne somente o JSON, sem markdown nem texto extra."
    )


async def _chamar_gpt(prompt: str) -> dict[str, Any] | None:
    if not _GPT_KEY:
        return None
    try:
        import aiohttp
        payload = {
            "model": _MODELO,
            "max_tokens": _MAX_TOKENS,
            "temperature": 0.15,
            "messages": [{"role": "user", "content": prompt}],
        }
        timeout = aiohttp.ClientTimeout(total=_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {_GPT_KEY}", "Content-Type": "application/json"},
                json=payload,
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        texto = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        resultado = json.loads(_remover_cerca_markdown(texto))
        resultado["modelo"] = _MODELO
        return resultado
    except Exception:
        return None


async def obter_insight(
    *,
    simbolo: str,
    regime: str,
    features: dict[str, Any],
    predicoes: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    saldo_usdt: float = 0.0,
) -> dict[str, Any]:
    """Ponto de entrada principal. Retorna insight de trade com fallback garantido."""
    momentum = float(features.get("r_3m") or features.get("r_1m") or 0.0)
    spread_rel = float(features.get("spread_rel") or 0.0)
    acertos = sum(1 for o in outcomes if o.get("err_rel") is not None and abs(float(o["err_rel"] or 0)) < 0.005)
    pred_acuracia = round(acertos / max(len(outcomes), 1), 3)
    # Tenta LLM se tiver chave
    if _GPT_KEY:
        prompt = _montar_prompt(simbolo, regime, features, predicoes, outcomes, saldo_usdt)
        resultado = await _chamar_gpt(prompt)
        if resultado and "direcao" in resultado:
            direcao = str(resultado.get("direcao", "HOLD")).upper()
            confianca = float(resultado.get("confianca") or 0.5)
            capital_pct = int(resultado.get("capital_pct_sugerido") or _capital_pct_para_confianca(confianca))
            return {
                "direcao": direcao,
                "confianca": round(min(0.99, max(0.0, confianca)), 3),
                "capital_pct_sugerido": max(10, min(100, capital_pct)),
                "reasoning": str(resultado.get("reasoning") or ""),
                "risco": str(resultado.get("risco") or "medio"),
                "modelo": _MODELO,
                "ts": int(time.time() * 1000),
            }
    # Fallback: heurística local
    resultado = _heuristica_local(regime, pred_acuracia, momentum, spread_rel)
    resultado["ts"] = int(time.time() * 1000)
    return resultado


async def saude_llm(simbolo: str | None = None) -> dict[str, Any]:
    """Saúde do conselheiro LLM em runtime: chave presente, modo fallback e último insight.

    `fonte_ultimo_insight`=heuristica_local indica que o GPT não respondeu/não há chave —
    o sistema segue honesto (não finge ter consultado o LLM). Ver INC-02.
    """
    from src.persistencia.conexao import get_conexao  # import tardio: evita acoplar I/O ao módulo

    chave_presente = bool(_GPT_KEY)
    ultimo: dict[str, Any] | None = None
    try:
        async with get_conexao() as con:
            if simbolo:
                cur = await con.execute(
                    "SELECT created_ts, simbolo, modelo, direcao, confianca, reasoning "
                    "FROM ai_insights WHERE simbolo=? ORDER BY created_ts DESC LIMIT 1",
                    (str(simbolo).upper(),),
                )
            else:
                cur = await con.execute(
                    "SELECT created_ts, simbolo, modelo, direcao, confianca, reasoning "
                    "FROM ai_insights ORDER BY created_ts DESC LIMIT 1"
                )
            row = await cur.fetchone()
        if row:
            ultimo = {
                "ts": int(row[0]), "simbolo": row[1], "modelo": row[2],
                "direcao": row[3], "confianca": row[4], "reasoning": row[5],
            }
    except Exception:
        ultimo = None
    fonte = (ultimo or {}).get("modelo") or ("gpt" if chave_presente else "heuristica_local")
    return {
        "gpt_chave_presente": chave_presente,
        "modelo_configurado": _MODELO if chave_presente else "heuristica_local",
        "modo_fallback_ativo": not chave_presente,
        "ultimo_insight": ultimo,
        "fonte_ultimo_insight": fonte,
        "ts": int(time.time() * 1000),
    }


async def persistir_insight(
    conn: Any,  # aiosqlite.Connection
    simbolo: str,
    insight: dict[str, Any],
    dados_entrada: dict[str, Any] | None = None,
) -> None:
    """Persiste insight na tabela ai_insights (sem bloquear o fluxo principal)."""
    try:
        await conn.execute(
            """INSERT INTO ai_insights
               (created_ts, simbolo, modelo, direcao, confianca, capital_pct_sugerido,
                reasoning, risco, dados_entrada_json, executado)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                int(time.time() * 1000),
                simbolo,
                insight.get("modelo", "heuristica_local"),
                insight.get("direcao", "HOLD"),
                float(insight.get("confianca") or 0.0),
                int(insight.get("capital_pct_sugerido") or 10),
                str(insight.get("reasoning") or ""),
                str(insight.get("risco") or "baixo"),
                json.dumps(dados_entrada or {}, ensure_ascii=False),
            ),
        )
        await conn.commit()
    except Exception:
        pass
