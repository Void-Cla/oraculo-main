"""Teste isolado da chave Gemini — fora do bot, sem cost-control/gate do projeto.

Faz UMA chamada mínima direto na API REST do Google (mesmo endpoint que
`src/intelligence/gemini_client.py` usa) para diagnosticar se a chave/cota está OK.
Não depende de nenhum módulo do oráculo — só lê GEMINI_API_KEY do .env.

Uso:
    python scripts/testar_chave_gemini.py
"""
from __future__ import annotations

import os
import sys

import httpx


def _ler_env(caminho: str = ".env") -> dict[str, str]:
    valores: dict[str, str] = {}
    if not os.path.exists(caminho):
        return valores
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, _, valor = linha.partition("=")
            valores[chave.strip()] = valor.strip()
    return valores


def main() -> int:
    env = _ler_env()
    chave = os.getenv("GEMINI_API_KEY") or env.get("GEMINI_API_KEY", "")
    modelo = os.getenv("GEMINI_MODEL") or env.get("GEMINI_MODEL", "gemini-2.0-flash")

    if not chave:
        print("[FALHA] GEMINI_API_KEY vazia (nem em os.environ, nem em .env)")
        return 1

    print(f"[INFO] Testando chave ...{chave[-8:]} (modelo={modelo})")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": "Responda apenas: OK"}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 16},
    }

    try:
        resposta = httpx.post(
            url, headers={"x-goog-api-key": chave}, json=payload, timeout=15.0
        )
    except httpx.RequestError as exc:
        print(f"[FALHA] Erro de conexão: {exc}")
        return 1

    print(f"[INFO] HTTP {resposta.status_code}")

    if resposta.status_code == 200:
        dados = resposta.json()
        candidatos = dados.get("candidates") or []
        partes = (candidatos[0].get("content", {}) if candidatos else {}).get("parts") or []
        texto = partes[0].get("text", "") if partes else ""
        print(f"[OK] Chave funcional. Resposta: {texto!r}")
        return 0

    if resposta.status_code == 429:
        print("[FALHA] 429 Too Many Requests — cota estourada (RPM/RPD do tier atual).")
        print(f"        Corpo: {resposta.text[:500]}")
        return 1

    if resposta.status_code in (401, 403):
        print("[FALHA] Chave inválida/sem permissão (401/403).")
        print(f"        Corpo: {resposta.text[:500]}")
        return 1

    print(f"[FALHA] Status inesperado {resposta.status_code}")
    print(f"        Corpo: {resposta.text[:500]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
