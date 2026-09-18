"""Cliente Claude (Anthropic) da camada de decisão — REST via httpx, fail-open e cost-control.

Herda TODO o cost-control e o wrapper `analisar` fail-open de `ProvedorIABase` (mesmo
comportamento observável do Gemini/GPT). Aqui ficam só as especificidades da Anthropic:
endpoint `/v1/messages`, headers próprios, modelo default e a montagem do payload.

Decisões de produção:
  - httpx (padrão do projeto, SEM o SDK `anthropic`) contra `https://api.anthropic.com/v1/messages`.
  - A chave vai no HEADER `x-api-key` — NUNCA na URL (mesmo cuidado anti-vazamento das outras).
  - NÃO enviamos `temperature`: os modelos novos (Sonnet 5 / Opus 4.x, e o default barato
    `claude-haiku-4-5`) retornam 400 se receberem `temperature`/`top_p`/`budget_tokens`. O
    parâmetro `temperature` é aceito na assinatura por compatibilidade da interface `ProvedorIA`,
    mas NÃO é repassado ao Claude (por isso o argumento é ignorado de propósito abaixo).
  - `system` vai no campo top-level `system`; o `user_context` vai como a única mensagem `user`.
  - Chave: `CLAUDE_API_KEY` OU `ANTHROPIC_API_KEY` (aceita ambas).
"""
from __future__ import annotations

from src.core.settings import env_str
from src.intelligence.provedor_ia import ProvedorIABase

_URL = "https://api.anthropic.com/v1/messages"
# Versão da API Anthropic exigida no header (valor fixo publicado pela Anthropic).
_ANTHROPIC_VERSION = "2023-06-01"


class ClaudeClient(ProvedorIABase):
    """Cliente consultivo Claude (Anthropic). Fail-open: qualquer problema ⇒ `analisar` retorna None."""

    def __init__(self, api_key: str | None = None, modelo: str | None = None) -> None:
        # Aceita CLAUDE_API_KEY ou ANTHROPIC_API_KEY.
        chave = (
            api_key
            if api_key is not None
            else (env_str("CLAUDE_API_KEY", "") or env_str("ANTHROPIC_API_KEY", ""))
        ).strip()
        # Default barato/rápido para saída JSON (equivalente ao gemini-2.0-flash em custo/velocidade).
        modelo_efetivo = (modelo or env_str("CLAUDE_MODEL", "claude-haiku-4-5")).strip()
        super().__init__(
            nome_provedor="claude",
            api_key=chave,
            modelo=modelo_efetivo,
        )

    async def _executar_chamada(
        self, system_prompt: str, user_context: str, temperature: float
    ) -> str:
        import httpx

        # `temperature` é intencionalmente IGNORADO — modelos novos (Sonnet 5/Opus 4.x/Haiku 4.5)
        # rejeitam o campo (HTTP 400). Aceito na assinatura só por compatibilidade da interface.
        _ = temperature
        payload = {
            "model": self._modelo,
            "max_tokens": self._max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_context}],
        }
        # Chave no HEADER (x-api-key), NUNCA na URL — erros HTTP não vazam o segredo.
        async with httpx.AsyncClient(timeout=self._timeout) as cliente:
            resposta = await cliente.post(
                _URL,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": _ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json=payload,
            )
            resposta.raise_for_status()
            dados = resposta.json()
        conteudo = dados.get("content") or []
        if not conteudo:
            return ""
        # Resposta Anthropic: content é lista de blocos; o texto vem no primeiro bloco de tipo "text".
        return str(conteudo[0].get("text", ""))
