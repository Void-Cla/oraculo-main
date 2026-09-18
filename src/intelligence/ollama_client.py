"""Cliente Ollama (LLM local) — REST via httpx, fail-open e cost-control herdados da base.

CONTEXTO (up.md §5.2): 4º provedor plugável (`AI_PROVIDER=ollama`), para o bot continuar tendo
uma "opinião de IA" mesmo se a internet cair ou os provedores de nuvem (Gemini/GPT/Claude)
estiverem fora do ar/sem cota. Roda 100% local via servidor Ollama (`http://localhost:11434`
por padrão) — sem chave de API, sem dado de mercado saindo da máquina. O invariante de
segurança do projeto vale IGUALMENTE aqui: a IA (local ou nuvem) NUNCA aprova/levanta gate
financeiro — herdado sem nenhuma mudança de `ProvedorIABase.analisar` (fail-open, DA-23).

IMPORTANTE — o bot JÁ sobrevive sem NENHUMA IA (DA-23/24: consultiva, fail-open; se
`criar_provedor_ia()` retorna None, a camada agêntica simplesmente não liga). O Ollama não é
"requisito de sobrevivência" — é uma melhoria de DISPONIBILIDADE da opinião consultiva,
zero-custo e sem dependência de rede externa.

Diferença de "chave": Ollama não usa API key (servidor local, tipicamente sem auth). Para
reusar o cost-control da base (que trata `_api_key` vazio como "provedor sem credencial —
desligado"), usamos um sentinel fixo NÃO-secreto — não é segredo real, só satisfaz o contrato
`chave_presente=True` quando o dono escolhe `AI_PROVIDER=ollama`. Se o servidor Ollama não
estiver rodando, a chamada de rede falha (connection refused) e cai no MESMO caminho fail-open
de qualquer outro provedor (timeout/erro ⇒ None, cooldown após falhas consecutivas — nunca
trava o loop mecânico).
"""
from __future__ import annotations

from src.core.settings import env_str
from src.intelligence.provedor_ia import ProvedorIABase

# Ollama não usa API key (servidor local). Sentinel NÃO-secreto só para satisfazer o contrato
# `chave_presente` da base (escolher AI_PROVIDER=ollama já é o "opt-in" — não há chave a validar).
_SENTINEL_SEM_CHAVE = "ollama-local-sem-chave"


class OllamaClient(ProvedorIABase):
    """Cliente consultivo LLM local (Ollama). Fail-open: qualquer problema ⇒ `analisar` retorna None."""

    def __init__(self, url_base: str | None = None, modelo: str | None = None) -> None:
        self._url_base = (url_base if url_base is not None else env_str("OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
        # Modelos 7-8B quantizados seguram JSON estruturado com latência aceitável em CPU
        # (a IA está fora do hot path por desenho — DA-30 — então segundos de latência aqui
        # são irrelevantes ao ciclo de trading de 30s). Dono deve `ollama pull` o modelo antes.
        modelo_efetivo = (modelo or env_str("OLLAMA_MODEL", "qwen2.5:7b-instruct")).strip()
        super().__init__(
            nome_provedor="ollama",
            api_key=_SENTINEL_SEM_CHAVE,
            modelo=modelo_efetivo,
        )

    async def _executar_chamada(self, system_prompt: str, user_context: str, temperature: float) -> str:
        import httpx

        payload = {
            "model": self._modelo,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_context},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": float(temperature)},
        }
        async with httpx.AsyncClient(timeout=self._timeout) as cliente:
            resposta = await cliente.post(f"{self._url_base}/api/chat", json=payload)
            resposta.raise_for_status()
            dados = resposta.json()
        return str((dados.get("message") or {}).get("content", ""))
