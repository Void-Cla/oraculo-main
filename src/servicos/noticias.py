from __future__ import annotations

import asyncio
import html
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import aiohttp
import httpx

from src.observabilidade.logger import get_logger
from src.persistencia.repositorio_auditoria import RepositorioAuditoria
from src.persistencia.repositorio_config import RepositorioConfig

LOG = get_logger("noticias")

_FONTES_CONFIAVEIS = [
    {"nome": "Reuters", "dominio": "reuters.com"},
    {"nome": "Bloomberg", "dominio": "bloomberg.com"},
    {"nome": "Financial Times", "dominio": "ft.com"},
    {"nome": "Wall Street Journal", "dominio": "wsj.com"},
    {"nome": "CNBC", "dominio": "cnbc.com"},
    {"nome": "MarketWatch", "dominio": "marketwatch.com"},
    {"nome": "Barron's", "dominio": "barrons.com"},
    {"nome": "Associated Press", "dominio": "apnews.com"},
    {"nome": "Yahoo Finance", "dominio": "finance.yahoo.com"},
    {"nome": "Investing.com", "dominio": "investing.com"},
    {"nome": "CoinDesk", "dominio": "coindesk.com"},
    {"nome": "Cointelegraph", "dominio": "cointelegraph.com"},
    {"nome": "Decrypt", "dominio": "decrypt.co"},
    {"nome": "The Block", "dominio": "theblock.co"},
    {"nome": "Bitcoin Magazine", "dominio": "bitcoinmagazine.com"},
    {"nome": "Forbes", "dominio": "forbes.com"},
    {"nome": "Federal Reserve", "dominio": "federalreserve.gov"},
    {"nome": "U.S. Treasury", "dominio": "treasury.gov"},
    {"nome": "SEC", "dominio": "sec.gov"},
    {"nome": "CFTC", "dominio": "cftc.gov"},
    {"nome": "IMF", "dominio": "imf.org"},
    {"nome": "World Bank", "dominio": "worldbank.org"},
    {"nome": "BIS", "dominio": "bis.org"},
    {"nome": "ECB", "dominio": "ecb.europa.eu"},
    {"nome": "Blockworks", "dominio": "blockworks.co"},
    {"nome": "CryptoSlate", "dominio": "cryptoslate.com"},
    {"nome": "CoinMarketCap", "dominio": "coinmarketcap.com"},
    {"nome": "Binance Blog", "dominio": "binance.com"},
    {"nome": "BeInCrypto", "dominio": "beincrypto.com"},
    {"nome": "The Defiant", "dominio": "thedefiant.io"},
]

_TERMOS_POSITIVOS = {
    "etf",
    "inflow",
    "approval",
    "adoption",
    "bullish",
    "growth",
    "buy",
    "reserve",
    "easing",
}
_TERMOS_NEGATIVOS = {
    "war",
    "attack",
    "ban",
    "hack",
    "bearish",
    "selloff",
    "liquidation",
    "tariff",
    "recession",
    "inflation",
}

_TERMOS_SIMBOLO = {
    "BTC": "BTC OR Bitcoin OR BTCUSDT OR ETF OR digital gold",
    "ETH": "ETH OR Ethereum OR ETHUSDT OR smart contracts OR staking",
    "BNB": "BNB OR Binance Coin OR BNBUSDT OR exchange token OR launchpool",
    "USDT": "USDT OR Tether OR stablecoin OR liquidity",
}


def _peso_base_fonte(fonte: dict[str, str]) -> float:
    nome = str(fonte.get("nome") or "").lower()
    dominio = str(fonte.get("dominio") or "").lower()
    if nome in {"reuters", "bloomberg", "financial times", "wall street journal"}:
        return 0.98
    if nome in {"associated press", "cnbc", "marketwatch", "barron's", "forbes"}:
        return 0.92
    if nome in {"yahoo finance", "investing.com", "coindesk", "cointelegraph", "decrypt", "the block", "blockworks"}:
        return 0.88
    if nome in {"bitcoin magazine", "cryptoslate", "coinmarketcap", "binance blog", "beincrypto", "the defiant"}:
        return 0.82
    if dominio.endswith(".gov") or nome in {"federal reserve", "u.s. treasury", "sec", "cftc"}:
        return 0.94
    if nome in {"imf", "world bank", "bis", "ecb"}:
        return 0.90
    return 0.78


def _fontes_confiaveis_normalizadas() -> list[dict[str, Any]]:
    return [
        {
            **fonte,
            "peso_base": round(float(fonte.get("peso_base") or _peso_base_fonte(fonte)), 4),
        }
        for fonte in _FONTES_CONFIAVEIS
    ]


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def _agora_ms() -> int:
    return int(time.time() * 1000)


def _hoje_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _max_buscas_dia() -> int:
    return 5


def _min_fontes() -> int:
    return 10


def _min_refresh_minutos() -> int:
    return 240


def _itens_por_fonte() -> int:
    return 3


def _limite_total_itens() -> int:
    return 60


def _chave_cache(simbolo: str) -> str:
    return f"noticias_cache_{simbolo.lower()}"


def _chave_estado(simbolo: str) -> str:
    return f"noticias_estado_{simbolo.lower()}"


def _termos_consulta_por_simbolo(simbolo: str) -> str:
    simbolo = simbolo.upper()
    termos: list[str] = []
    for ativo in _TERMOS_SIMBOLO:
        if ativo in simbolo:
            termos.append(_TERMOS_SIMBOLO[ativo])
    if not termos:
        termos.append("crypto OR bitcoin OR ethereum OR bnb")
    termos.append("crypto OR macro OR geopolitics OR fed OR tariff OR inflation OR regulation")
    return " OR ".join(termos)


def _consulta_google_news(dominio: str, simbolo: str) -> str:
    termos = _termos_consulta_por_simbolo(simbolo)
    consulta = quote_plus(f"site:{dominio} ({termos})")
    return f"https://news.google.com/rss/search?q={consulta}&hl=en-US&gl=US&ceid=US:en"


async def _baixar_feed(session: aiohttp.ClientSession, fonte: dict[str, str], simbolo: str) -> list[dict[str, Any]]:
    url = _consulta_google_news(fonte["dominio"], simbolo)
    try:
        async with session.get(url) as resposta:
            resposta.raise_for_status()
            xml_texto = await resposta.text()
    except Exception as exc:
        LOG.warning("falha_feed_noticias", extra={"fonte": fonte["nome"], "erro": str(exc)})
        return []

    try:
        raiz = ET.fromstring(xml_texto)
    except ET.ParseError:
        LOG.warning("falha_parse_feed_noticias", extra={"fonte": fonte["nome"]})
        return []

    itens: list[dict[str, Any]] = []
    for item in raiz.findall(".//item")[: _itens_por_fonte()]:
        titulo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        descricao = (item.findtext("description") or "").strip()
        if not titulo:
            continue
        itens.append(
            {
                "titulo": titulo,
                "descricao": descricao,
                "link": link,
                "fonte": fonte["nome"],
                "dominio": fonte["dominio"],
                "publicado_em": pub_date,
            }
        )
    return itens


def _detalhes_fontes_para_simbolo(simbolo: str, itens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    simbolo = simbolo.upper()
    fontes = _fontes_confiaveis_normalizadas()
    estatisticas: dict[str, dict[str, Any]] = {}
    for fonte in fontes:
        estatisticas[str(fonte["nome"])] = {
            "nome": fonte["nome"],
            "dominio": fonte["dominio"],
            "peso_base": float(fonte["peso_base"]),
            "itens_encontrados": 0,
            "sentimento_medio": 0.0,
            "titulos": [],
        }

    for item in itens:
        nome_fonte = str(item.get("fonte") or "")
        if nome_fonte not in estatisticas:
            estatisticas[nome_fonte] = {
                "nome": nome_fonte,
                "dominio": str(item.get("dominio") or ""),
                "peso_base": 0.72,
                "itens_encontrados": 0,
                "sentimento_medio": 0.0,
                "titulos": [],
            }
        alvo = estatisticas[nome_fonte]
        alvo["itens_encontrados"] += 1
        alvo["sentimento_medio"] += float(item.get("sentimento", 0.0) or 0.0)
        alvo["titulos"].append(str(item.get("titulo") or ""))

    detalhes: list[dict[str, Any]] = []
    for fonte in estatisticas.values():
        itens_encontrados = int(fonte["itens_encontrados"] or 0)
        sentimento_medio = (float(fonte["sentimento_medio"] or 0.0) / itens_encontrados) if itens_encontrados > 0 else 0.0
        bonus_cobertura = min(itens_encontrados / max(_itens_por_fonte(), 1), 1.0) * 0.22
        bonus_sentimento = min(abs(sentimento_medio), 1.0) * 0.06
        peso = _clamp(float(fonte["peso_base"]) + bonus_cobertura + bonus_sentimento, 0.0, 1.0)
        nome_fonte = str(fonte["nome"])
        detalhes.append(
            {
                "nome": nome_fonte,
                "dominio": fonte["dominio"],
                "peso": round(peso, 4),
                "peso_pct": round(peso * 100.0, 1),
                "peso_base": round(float(fonte["peso_base"]), 4),
                "itens_encontrados": itens_encontrados,
                "sentimento_medio": round(sentimento_medio, 4),
                "status": "com_retorno" if itens_encontrados > 0 else "sem_retorno",
                "titulos": list(fonte["titulos"][:3]),
                "rss_url": _consulta_google_news(str(fonte["dominio"]), simbolo),
                "iframe_url": f"/v1/noticias/frame?simbolo={quote_plus(simbolo)}&fonte={quote_plus(nome_fonte)}",
            }
        )
    return sorted(detalhes, key=lambda item: (int(item["itens_encontrados"]), float(item["peso"])), reverse=True)[:10]


def fontes_confiaveis_topo_para_simbolo(simbolo: str, itens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _detalhes_fontes_para_simbolo(simbolo, itens)


async def renderizar_fonte_noticias_html(simbolo: str, fonte_nome: str) -> str:
    erro_carga = None
    try:
        payload = await obter_noticias_para_peso(simbolo=simbolo, forcar_atualizacao=False)
    except Exception as exc:
        erro_carga = str(exc)
        LOG.warning("falha_render_frame_noticias", extra={"simbolo": simbolo, "fonte": fonte_nome, "erro": erro_carga})
        payload = {
            "simbolo": simbolo,
            "meta": {"fontes_detalhadas": []},
            "itens": [],
        }
    simbolo = simbolo.upper()
    itens = [item for item in list(payload.get("itens") or []) if str(item.get("fonte") or "").strip().lower() == fonte_nome.strip().lower()][:6]
    detalhes = next(
        (
            item
            for item in list(((payload.get("meta") or {}).get("fontes_detalhadas") or []))
            if str(item.get("nome") or "").strip().lower() == fonte_nome.strip().lower()
        ),
        None,
    )
    if detalhes is None:
        detalhes = {
            "nome": fonte_nome,
            "peso_pct": 0.0,
            "dominio": "",
            "status": "sem_retorno",
            "rss_url": "",
        }

    lista_itens = "".join(
        (
            "<article class='headline'>"
            f"<a href='{html.escape(str(item.get('link') or '#'))}' target='_blank' rel='noreferrer noopener'>{html.escape(str(item.get('titulo') or '--'))}</a>"
            f"<p>{html.escape(str(item.get('resumo_analise') or item.get('descricao') or 'Sem resumo.'))}</p>"
            "</article>"
        )
        for item in itens
    )
    if not lista_itens:
        lista_itens = "<article class='headline'><p>Sem manchetes recentes dessa fonte para este simbolo.</p></article>"
    if erro_carga:
        lista_itens = (
            "<article class='headline'>"
            "<p>Falha temporaria ao montar este painel. O cache de noticias nao ficou disponivel agora.</p>"
            f"<p>Detalhe: {html.escape(erro_carga)}</p>"
            "</article>"
        ) + lista_itens

    fonte_display = html.escape(str(detalhes.get("nome") or fonte_nome))
    dominio = html.escape(str(detalhes.get("dominio") or ""))
    peso_pct = html.escape(str(detalhes.get("peso_pct") or 0.0))
    rss_url = html.escape(str(detalhes.get("rss_url") or "#"))
    site_url = f"https://{dominio}" if dominio else "#"
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{fonte_display} | {html.escape(simbolo)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #09131b;
      --card: rgba(17, 31, 42, 0.94);
      --text: #edf5fb;
      --muted: #9ab0c0;
      --line: rgba(255,255,255,0.08);
      --accent: #f0b34a;
      --cyan: #67d0d7;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Segoe UI Variable, Aptos, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(103, 208, 215, 0.12), transparent 30%),
        linear-gradient(180deg, #081016, #0f1a23);
      color: var(--text);
    }}
    main {{ padding: 14px; display: grid; gap: 12px; }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 18px;
      background:
        linear-gradient(180deg, rgba(103, 208, 215, 0.05), rgba(255,255,255,0.02)),
        var(--card);
      padding: 14px;
      overflow: hidden;
    }}
    .meta {{ display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; flex-wrap: wrap; }}
    h1 {{ margin: 0; font-size: 1rem; letter-spacing: -0.02em; }}
    p {{ margin: 0; color: var(--muted); line-height: 1.5; overflow-wrap: anywhere; }}
    .badge {{
      display: inline-flex;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(240,179,74,0.16);
      color: var(--accent);
      font-size: 0.75rem;
      font-weight: 700;
      flex-shrink: 0;
    }}
    .headline {{
      display: grid;
      gap: 6px;
      padding-top: 12px;
      margin-top: 12px;
      border-top: 1px solid var(--line);
    }}
    .headline:first-of-type {{ border-top: 0; padding-top: 0; }}
    a {{ color: var(--text); text-decoration: none; overflow-wrap: anywhere; }}
    a:hover {{ color: var(--accent); }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .links a {{
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      padding: 0 10px;
      border-radius: 999px;
      background: rgba(103, 208, 215, 0.12);
      border: 1px solid rgba(103, 208, 215, 0.24);
    }}
  </style>
</head>
<body>
  <main>
    <section class="card">
      <div class="meta">
        <div>
          <h1>{fonte_display}</h1>
          <p>{html.escape(simbolo)} | {dominio or 'dominio nao informado'}</p>
        </div>
        <span class="badge">Peso {peso_pct}%</span>
      </div>
      <div class="links">
        <a href="{site_url}" target="_blank" rel="noreferrer noopener">Abrir site</a>
        <a href="{rss_url}" target="_blank" rel="noreferrer noopener">Abrir RSS pesquisado</a>
      </div>
    </section>
    <section class="card">
      {lista_itens}
    </section>
  </main>
</body>
</html>"""


def _heuristica_sentimento(item: dict[str, Any]) -> tuple[float, list[str]]:
    texto = " ".join(
        [
            str(item.get("titulo") or ""),
            str(item.get("descricao") or ""),
            str(item.get("fonte") or ""),
        ]
    ).lower()
    positivos = sum(1 for termo in _TERMOS_POSITIVOS if termo in texto)
    negativos = sum(1 for termo in _TERMOS_NEGATIVOS if termo in texto)
    score = _clamp((positivos - negativos) / max(1, positivos + negativos), -1.0, 1.0)
    tags: list[str] = []
    if "bitcoin" in texto or "btc" in texto or "etf" in texto:
        tags.append("cripto")
    if "war" in texto or "geopolit" in texto or "tariff" in texto or "fed" in texto or "inflation" in texto:
        tags.append("macro")
    return score, sorted(set(tags))


def _modelo_llm() -> str:
    return "gpt-4o-mini"


def _extrair_output_text(resposta: dict[str, Any]) -> str:
    if resposta.get("output_text"):
        return str(resposta["output_text"])
    partes: list[str] = []
    for item in resposta.get("output", []):
        for conteudo in item.get("content", []):
            if conteudo.get("type") == "output_text" and conteudo.get("text"):
                partes.append(str(conteudo["text"]))
    return "\n".join(partes).strip()


def _parse_json_seguro(texto: str) -> dict[str, Any]:
    texto = texto.strip()
    if not texto:
        return {}
    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio == -1 or fim == -1 or fim <= inicio:
        return {}
    try:
        return json.loads(texto[inicio : fim + 1])
    except json.JSONDecodeError:
        return {}


async def _llm_estado_obter() -> dict[str, Any]:
    chave = "noticias_llm_estado"
    estado = await RepositorioConfig.obter(chave) or {}
    return estado


async def _llm_estado_salvar(estado: dict[str, Any]) -> None:
    chave = "noticias_llm_estado"
    await RepositorioConfig.definir(chave, estado)


async def _llm_registrar_chamada():
    estado = await _llm_estado_obter()
    hoje = _hoje_utc()
    if estado.get("data") != hoje:
        estado = {"data": hoje, "chamadas": 0, "falhas": 0, "ultima_falha_ts": 0}
    estado["chamadas"] = int(estado.get("chamadas", 0)) + 1
    await _llm_estado_salvar(estado)


async def _llm_registrar_falha():
    estado = await _llm_estado_obter()
    hoje = _hoje_utc()
    if estado.get("data") != hoje:
        estado = {"data": hoje, "chamadas": 0, "falhas": 0, "ultima_falha_ts": 0}
    estado["falhas"] = int(estado.get("falhas", 0)) + 1
    estado["ultima_falha_ts"] = _agora_ms()
    await _llm_estado_salvar(estado)


async def _llm_permitido() -> tuple[bool, str]:
    # Políticas simples: limite diário e cooldown após excesso de falhas
    estado = await _llm_estado_obter()
    hoje = _hoje_utc()
    if estado.get("data") != hoje:
        return True, "novo_dia"
    chamadas = int(estado.get("chamadas", 0))
    falhas = int(estado.get("falhas", 0))
    ultima_falha = int(estado.get("ultima_falha_ts", 0) or 0)
    limite_diario = 20
    max_falhas = 5
    cooldown_min = 60
    if chamadas >= limite_diario:
        return False, "limite_diario"
    if falhas >= max_falhas and (_agora_ms() - ultima_falha) < (cooldown_min * 60 * 1000):
        return False, "cooldown_por_falhas"
    return True, "ok"


async def _classificar_com_openai(itens: list[dict[str, Any]], simbolo: str) -> dict[str, Any]:
    chave = (os.getenv("OPENAI_API_KEY") or os.getenv("GPT_API_KEY") or "").strip()
    if not chave:
        return {}

    permitido, motivo = await _llm_permitido()
    if not permitido:
        LOG.warning("llm_pulando", extra={"motivo": motivo, "simbolo": simbolo})
        return {}

    modelo = _modelo_llm()
    payload_itens = [
        {
            "id": idx,
            "fonte": item["fonte"],
            "dominio": item["dominio"],
            "titulo": item["titulo"],
            "descricao": item.get("descricao"),
        }
        for idx, item in enumerate(itens[: _limite_total_itens()])
    ]
    prompt = {
        "tarefa": f"classificar noticias para impacto em {simbolo.upper()}",
        "saida": {
            "sentimento_geral": "numero entre -1 e 1",
            "confianca": "numero entre 0 e 1",
            "resumo": "texto curto em pt-BR",
            "itens": [
                {
                    "id": "indice do item",
                    "sentimento": "numero entre -1 e 1",
                    "impacto": "alto|medio|baixo",
                    "tags": ["macro", "cripto", "regulatorio", "liquidez", "geopolitica"],
                    "resumo": "frase curta",
                }
            ],
        },
        "regras": [
            "retorne JSON puro",
            "nao invente fatos",
            "use apenas os itens fornecidos",
            "se o impacto for incerto, use sentimento 0",
        ],
        "itens": payload_itens,
    }

    corpo = {
        "model": modelo,
        "reasoning": {"effort": "low"},
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Voce e um analista quantitativo de noticias para mercado cripto. "
                            f"Classifique impacto direcional e risco macro em {simbolo.upper()} em JSON puro."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": json.dumps(prompt, ensure_ascii=False)}],
            },
        ],
        "max_output_tokens": 2500,
    }

    # Retries exponenciais simples
    retries = 2
    delay_base = 0.8
    ultimo_erro: Exception | None = None
    for tentativa in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=45.0) as cliente:
                resposta = await cliente.post(
                    "https://api.openai.com/v1/responses",
                    headers={
                        "Authorization": f"Bearer {chave}",
                        "Content-Type": "application/json",
                    },
                    json=corpo,
                )
                resposta.raise_for_status()
                dados = resposta.json()
            await _llm_registrar_chamada()
            saida = _parse_json_seguro(_extrair_output_text(dados))
            if not saida:
                LOG.warning("resposta_openai_noticias_invalida", extra={"modelo": modelo})
                return {}
            return saida
        except Exception as exc:  # pragma: no cover - robust handling path
            ultimo_erro = exc
            LOG.warning("falha_openai_noticias", extra={"modelo": modelo, "erro": str(exc), "tentativa": tentativa})
            await _llm_registrar_falha()
            if tentativa < retries:
                await asyncio.sleep(delay_base * (2 ** tentativa))

    LOG.error("openai_noticias_falha_final", extra={"modelo": modelo, "erro": str(ultimo_erro)})
    return {}


async def _executar_classificacao_openai(itens: list[dict[str, Any]], simbolo: str) -> dict[str, Any]:
    try:
        return await _classificar_com_openai(itens, simbolo)
    except TypeError:
        return await _classificar_com_openai(itens)  # type: ignore[misc]


def _merge_classificacao(
    itens: list[dict[str, Any]],
    classificacao_openai: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    itens_saida: list[dict[str, Any]] = []
    mapa_openai = {
        int(item.get("id")): item
        for item in (classificacao_openai.get("itens") or [])
        if item.get("id") is not None
    }
    for idx, item in enumerate(itens):
        gpt_item = mapa_openai.get(idx, {})
        score_heuristico, tags_heuristicas = _heuristica_sentimento(item)
        sentimento = float(gpt_item.get("sentimento", score_heuristico) or score_heuristico)
        tags = sorted(set(tags_heuristicas + list(gpt_item.get("tags") or [])))
        itens_saida.append(
            {
                **item,
                "sentimento": _clamp(sentimento, -1.0, 1.0),
                "impacto": str(gpt_item.get("impacto") or "medio").lower(),
                "tags": tags,
                "resumo_analise": gpt_item.get("resumo"),
                "fonte_analise": "openai_responses_api" if gpt_item else "heuristica_local",
                # INC-02: o modelo reportado reflete a ORIGEM real deste item (não mente na auditoria).
                "modelo_llm": _modelo_llm() if gpt_item else "heuristica_local",
            }
        )

    if not itens_saida:
        sentimento_geral = 0.0
    else:
        sentimento_geral = sum(float(item["sentimento"]) for item in itens_saida) / len(itens_saida)
    meta = {
        "sentimento_geral": _clamp(float(classificacao_openai.get("sentimento_geral", sentimento_geral) or sentimento_geral), -1.0, 1.0),
        "confianca": _clamp(float(classificacao_openai.get("confianca", 0.0) or 0.0), 0.0, 1.0),
        "resumo": classificacao_openai.get("resumo") or None,
        # INC-02: coerente com status_classificacao — só reporta GPT quando veio do GPT.
        "modelo_llm": _modelo_llm() if classificacao_openai else "heuristica_local",
        "status_classificacao": "openai_responses_api" if classificacao_openai else "heuristica_local",
    }
    return itens_saida, meta


async def _coletar_noticias_fontes(simbolo: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fontes_confiaveis = _fontes_confiaveis_normalizadas()
    timeout = aiohttp.ClientTimeout(total=8.0)
    connector = aiohttp.TCPConnector(limit=12)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        tarefas = [_baixar_feed(session, fonte, simbolo) for fonte in fontes_confiaveis[: max(_min_fontes(), len(fontes_confiaveis))]]
        respostas = await asyncio.gather(*tarefas, return_exceptions=True)

    itens: list[dict[str, Any]] = []
    fontes_com_retorno: set[str] = set()
    vistos: set[tuple[str, str]] = set()
    for resposta in respostas:
        if isinstance(resposta, Exception):
            continue
        for item in resposta:
            chave = (item.get("titulo", "").strip().lower(), item.get("fonte", "").strip().lower())
            if chave in vistos:
                continue
            vistos.add(chave)
            fontes_com_retorno.add(str(item["fonte"]))
            itens.append(item)

    itens = itens[: _limite_total_itens()]
    return itens, {
        "fontes_monitoradas": len(fontes_confiaveis),
        "fontes_minimas_exigidas": _min_fontes(),
        "fontes_com_retorno": len(fontes_com_retorno),
        "fontes_utilizadas": sorted(fontes_com_retorno),
    }


async def obter_noticias_para_peso(simbolo: str = "BTCUSDT", forcar_atualizacao: bool = False) -> dict[str, Any]:
    simbolo = simbolo.upper()
    cache = await RepositorioConfig.obter(_chave_cache(simbolo)) or {}
    estado = await RepositorioConfig.obter(_chave_estado(simbolo)) or {}

    hoje = _hoje_utc()
    if estado.get("data_utc") != hoje:
        estado = {"data_utc": hoje, "count": 0, "ultima_atualizacao": 0}

    max_buscas = _max_buscas_dia()
    ultima_atualizacao = int(estado.get("ultima_atualizacao", 0) or 0)
    refresh_ms = _min_refresh_minutos() * 60 * 1000
    limite_atingido = int(estado.get("count", 0) or 0) >= max_buscas
    cache_atual = bool(cache.get("itens"))
    cache_recente = cache_atual and (_agora_ms() - ultima_atualizacao) < refresh_ms

    if cache_atual and not forcar_atualizacao:
        if limite_atingido or cache_recente:
            meta = dict(cache.get("meta") or {})
            meta.update(
                {
                    "buscas_hoje": int(estado.get("count", 0) or 0),
                    "max_buscas_dia": max_buscas,
                    "limite_busca_atingido": limite_atingido,
                    "cache_usado": True,
                    "simbolo": simbolo,
                }
            )
            return {"simbolo": simbolo, "meta": meta, "itens": cache.get("itens", [])}

    if limite_atingido and cache_atual:
        meta = dict(cache.get("meta") or {})
        meta.update(
            {
                "buscas_hoje": int(estado.get("count", 0) or 0),
                "max_buscas_dia": max_buscas,
                "limite_busca_atingido": True,
                "cache_usado": True,
                "simbolo": simbolo,
            }
        )
        return {"simbolo": simbolo, "meta": meta, "itens": cache.get("itens", [])}

    itens_brutos, meta_fontes = await _coletar_noticias_fontes(simbolo)
    classificacao_openai = await _executar_classificacao_openai(itens_brutos, simbolo)
    itens, meta_classificacao = _merge_classificacao(itens_brutos, classificacao_openai)

    estado["count"] = int(estado.get("count", 0) or 0) + 1
    estado["ultima_atualizacao"] = _agora_ms()
    payload = {
        "simbolo": simbolo,
        "meta": {
            **meta_fontes,
            **meta_classificacao,
            "fontes_detalhadas": fontes_confiaveis_topo_para_simbolo(simbolo, itens),
            "atualizado_em": estado["ultima_atualizacao"],
            "buscas_hoje": estado["count"],
            "max_buscas_dia": max_buscas,
            "limite_busca_atingido": estado["count"] >= max_buscas,
            "cache_usado": False,
        },
        "itens": itens,
    }

    await RepositorioConfig.definir(_chave_cache(simbolo), payload)
    await RepositorioConfig.definir(_chave_estado(simbolo), estado)
    await RepositorioAuditoria.registrar(
        simbolo=simbolo,
        tipo="noticias_fetch",
        payload={
            "meta": payload["meta"],
            "quantidade_itens": len(itens),
        },
    )
    return payload
