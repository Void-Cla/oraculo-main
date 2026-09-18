"""Cliente Gemini resiliente — REST via httpx (sem SDK pesado), fail-open e cost-control.

Herda TODO o cost-control (limite dia/hora, cooldown, timeout, redação anti-vazamento e o
wrapper `analisar` fail-open) de `ProvedorIABase` — comportamento observável IDÊNTICO ao
original. Aqui ficam apenas as especificidades do Gemini: endpoint REST `generateContent`,
modelo default e a montagem do payload.

Decisões de produção preservadas:
  - Usa httpx (já é dependência) contra o endpoint REST `generateContent` — evita acoplar a
    `google-generativeai` (dependência grande, difícil de mockar/testar).
  - `analisar()` (herdado) NUNCA lança exceção: retorna `dict | None` (fail-open).
  - Cost-control por dia/hora + cooldown por falhas (herdado da base).
  - A chave vai no HEADER `x-goog-api-key`, NUNCA na URL/query — assim erros HTTP (que incluem
    a URL) não vazam o segredo no log.

Compatibilidade de testes: `_chamar_api(self, prompt, temperature)` foi MANTIDO com a mesma
assinatura de antes (os testes fazem `monkeypatch` deste método passando `(prompt, temperature)`).
A base chama `_executar_chamada(system_prompt, user_context, temperature)`, que concatena o prompt
exatamente como antes e delega para `_chamar_api` — nenhum mock existente precisa mudar.
"""
from __future__ import annotations

from src.core.settings import env_str
from src.intelligence.provedor_ia import ProvedorIABase

_URL_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiClient(ProvedorIABase):
    """Cliente consultivo Gemini. Fail-open: qualquer problema ⇒ `analisar` retorna None."""

    def __init__(self, api_key: str | None = None, modelo: str | None = None) -> None:
        chave = (api_key if api_key is not None else env_str("GEMINI_API_KEY", "")).strip()
        # Default "gemini-2.5-flash-lite": MAIOR RPD do free tier (1000/dia, medido ao vivo em
        # 2026-07-02 via scripts/testar_chave_gemini.py). "gemini-2.0-flash" tem RPD=0 (desligado)
        # e "gemini-flash-latest" (alias) resolve pro 3.5-flash com RPD=20 (estoura em minutos).
        # Fixado numa versão específica de propósito — o alias flash-latest faz hot-swap sozinho
        # e pode cair num preview de quota baixa. Ver bloco de comentário no `.env`.
        modelo_efetivo = (modelo or env_str("GEMINI_MODEL", "gemini-2.5-flash-lite")).strip()
        # `prefixos_legado=("GEMINI",)` mantém `GEMINI_MAX_CALLS_DIA/HORA`, `GEMINI_TIMEOUT_SEGUNDOS`,
        # `GEMINI_FALHAS_COOLDOWN`, `GEMINI_COOLDOWN_MIN`, `GEMINI_MAX_TOKENS` funcionando para
        # quem já configurou — sem quebrar quem só conhecia os nomes antigos.
        super().__init__(
            nome_provedor="gemini",
            api_key=chave,
            modelo=modelo_efetivo,
            prefixos_legado=("GEMINI",),
        )

    async def _executar_chamada(
        self, system_prompt: str, user_context: str, temperature: float
    ) -> str:
        # Gemini usa prompt único: concatena system + contexto (mesmo formato de antes).
        prompt = f"{system_prompt}\n\n---\n\n{user_context}"
        return await self._chamar_api(prompt, temperature)

    # ── Chamada de rede (isolada p/ teste — monkeypatch deste método) ────────
    async def _chamar_api(self, prompt: str, temperature: float) -> str:
        import httpx

        url = f"{_URL_BASE}/{self._modelo}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": float(temperature),
                "maxOutputTokens": self._max_tokens,
                "responseMimeType": "application/json",
                # thinkingBudget=0 desliga o raciocínio interno do modelo (2026-07-02): sem
                # isso, modelos Gemini com "thinking" ligado por padrão (ex.: os resolvidos
                # por "gemini-flash-latest") consomem boa parte de `maxOutputTokens` PENSANDO
                # antes de escrever a resposta — confirmado gerando JSON truncado/vazio
                # (finishReason=MAX_TOKENS) com o prompt real do voto em lote. O caso de uso
                # aqui é sempre um JSON curto e estruturado (voto direcional/veto/auditoria) —
                # não precisa de raciocínio profundo, e desligar também economiza tokens/cota
                # por chamada (thinking consome do mesmo orçamento de output).
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        # A chave vai no HEADER (x-goog-api-key), NUNCA na URL/query — assim erros HTTP
        # (que incluem a URL) não vazam o segredo no log.
        async with httpx.AsyncClient(timeout=self._timeout) as cliente:
            resposta = await cliente.post(
                url, headers={"x-goog-api-key": self._api_key}, json=payload
            )
            resposta.raise_for_status()
            dados = resposta.json()
        candidatos = dados.get("candidates") or []
        partes = (candidatos[0].get("content", {}) if candidatos else {}).get("parts") or []
        return str(partes[0].get("text", "")) if partes else ""
