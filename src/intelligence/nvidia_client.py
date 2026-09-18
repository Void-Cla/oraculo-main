"""Cliente NVIDIA NIM (integrate.api.nvidia.com) — API OpenAI-compatível via httpx.

Herda cost-control e fail-open de `ProvedorIABase`. Endpoint e modelo default alinhados
ao NIM (`https://integrate.api.nvidia.com/v1/chat/completions`, ex.: `z-ai/glm-5.2`).

Não envia `response_format` — nem todo modelo NIM suporta; o parse JSON fica a cargo
de `extrair_json` na base (system prompt já exige JSON estruturado).
"""
from __future__ import annotations

import os

from src.core.settings import env_str
from src.intelligence.provedor_ia import ProvedorIABase

_URL_PADRAO = "https://integrate.api.nvidia.com/v1/chat/completions"
_MODELO_PADRAO = "z-ai/glm-5.2"


def _obter_chave_nvidia() -> str:
    """Aceita nomes comuns da chave (inclui `Nvidia_API_Key` do .env do dono)."""
    for nome in ("NVIDIA_API_KEY", "Nvidia_API_Key", "Nvidia_API_KEY", "NVAPI_KEY"):
        bruto = os.getenv(nome)
        if bruto and str(bruto).strip():
            return str(bruto).strip()
    return ""


class NvidiaClient(ProvedorIABase):
    """Cliente consultivo NVIDIA NIM. Fail-open: qualquer problema ⇒ `analisar` retorna None."""

    def __init__(self, api_key: str | None = None, modelo: str | None = None) -> None:
        chave = (api_key if api_key is not None else _obter_chave_nvidia()).strip()
        modelo_efetivo = (modelo or env_str("NVIDIA_MODEL", _MODELO_PADRAO)).strip()
        self._url = env_str("NVIDIA_BASE_URL", _URL_PADRAO).strip() or _URL_PADRAO
        super().__init__(
            nome_provedor="nvidia",
            api_key=chave,
            modelo=modelo_efetivo,
        )

    async def _executar_chamada(
        self, system_prompt: str, user_context: str, temperature: float
    ) -> str:
        import httpx

        payload = {
            "model": self._modelo,
            "max_tokens": self._max_tokens,
            "temperature": float(temperature),
            "top_p": 1.0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_context},
            ],
        }
        async with httpx.AsyncClient(timeout=self._timeout) as cliente:
            resposta = await cliente.post(
                self._url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "content-type": "application/json",
                },
                json=payload,
            )
            resposta.raise_for_status()
            dados = resposta.json()
        escolhas = dados.get("choices") or []
        if not escolhas:
            return ""
        delta = escolhas[0].get("message") or {}
        conteudo = delta.get("content")
        if conteudo:
            return str(conteudo)
        # Alguns modelos NIM devolvem raciocínio em campo separado — tenta extrair texto útil.
        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
        return str(reasoning or "")
