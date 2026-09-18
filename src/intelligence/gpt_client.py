"""Cliente GPT (OpenAI) da camada de decisão — REST via httpx, fail-open e cost-control.

Herda TODO o cost-control e o wrapper `analisar` fail-open de `ProvedorIABase` (mesmo
comportamento observável do Gemini/Claude). Aqui ficam só as especificidades do OpenAI:
endpoint `chat/completions`, modelo default e a montagem do payload por papéis (system/user).

ATENÇÃO — este cliente é a camada de DECISÃO agêntica, plugável via `AI_PROVIDER=gpt`. NÃO é
o `src/servicos/ai_advisor.py` (advisor consultivo à parte, via aiohttp). O `ai_advisor.py`
foi usado apenas como REFERÊNCIA do formato de request/parse da OpenAI — os dois não se cruzam.

Decisões de produção:
  - httpx (padrão do projeto, sem SDK openai) contra `https://api.openai.com/v1/chat/completions`.
  - A chave vai no HEADER `Authorization: Bearer` — NUNCA na URL (mesmo cuidado anti-vazamento).
  - `response_format={"type": "json_object"}` força a OpenAI a devolver JSON (o modelo default
    `gpt-4o-mini` suporta). O parse defensivo (`extrair_json`, na base) ainda protege o resto.
  - OpenAI ACEITA `temperature` — repassamos o parâmetro normalmente.
  - Chave: `GPT_API_KEY` OU `OPENAI_API_KEY` (aceita ambas, como o ai_advisor.py já faz).
"""
from __future__ import annotations

from src.core.settings import env_str
from src.intelligence.provedor_ia import ProvedorIABase

_URL = "https://api.openai.com/v1/chat/completions"


class GPTClient(ProvedorIABase):
    """Cliente consultivo GPT (OpenAI). Fail-open: qualquer problema ⇒ `analisar` retorna None."""

    def __init__(self, api_key: str | None = None, modelo: str | None = None) -> None:
        # Aceita GPT_API_KEY ou OPENAI_API_KEY (retrocompat com quem já configurou a segunda).
        chave = (
            api_key
            if api_key is not None
            else (env_str("GPT_API_KEY", "") or env_str("OPENAI_API_KEY", ""))
        ).strip()
        modelo_efetivo = (modelo or env_str("GPT_MODEL", "gpt-4o-mini")).strip()
        super().__init__(
            nome_provedor="gpt",
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
            "temperature": float(temperature),  # OpenAI aceita temperature — repassa normalmente.
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_context},
            ],
        }
        # Chave no HEADER (Authorization: Bearer), NUNCA na URL — erros HTTP não vazam o segredo.
        async with httpx.AsyncClient(timeout=self._timeout) as cliente:
            resposta = await cliente.post(
                _URL,
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
        return str((escolhas[0].get("message") or {}).get("content", ""))
