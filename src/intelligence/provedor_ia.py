"""Provedor de IA plugável — Protocolo comum + base de cost-control + factory.

CONTEXTO (pedido explícito do dono do projeto, 2026-07-01): a camada agêntica de decisão
deixa de ser HARDCODED para Gemini. O cliente escolhe o provedor via uma única variável de
 ambiente `AI_PROVIDER` (`nvidia` | `gemini` | `gpt` | `claude` | `ollama`). O comportamento observável é
IDÊNTICO ao anterior (fail-open, cost-control, timeout duro, anti-vazamento de chave) — só
muda QUAL API é chamada. `ollama` (2026-07-10, up.md §5.2) roda 100% local — sem chave, sem
dependência de rede externa — para a camada consultiva sobreviver mesmo com a nuvem fora do ar.

Arquitetura (separação de responsabilidades):
  - `ProvedorIA` (Protocol): a interface EXATA que os 3 consumidores já usam
    (`pre_execution_filter`, `market_analyst`, `post_trade_auditor`) — todos só chamam
    `.analisar()`; `.disponivel()`/`.health()` são auxiliares.
  - `ProvedorIABase` (classe base abstrata): implementa TODO o cost-control compartilhado
    (limite dia/hora, cooldown por falhas consecutivas, reset de janelas, redação anti-vazamento
    e o wrapper `analisar` fail-open com timeout duro). As subclasses concretas só implementam
    `_executar_chamada(...)` (a chamada de rede específica de cada provedor) e definem seus
    próprios defaults (nome da env var da chave, modelo, endpoint).
  - `criar_provedor_ia()` (factory): lê `AI_PROVIDER` e devolve o cliente correspondente, ou
    `None` se a chave do provedor escolhido não estiver configurada (camada desativada = fail-open,
    exatamente como o comportamento antigo de "sem GEMINI_API_KEY = camada desligada").

 FAIL-OPEN é sagrado: qualquer provedor, em qualquer falha (timeout/erro/cooldown/limite/JSON
inválido/sem chave), retorna `None` de `analisar`. O bot mecânico NUNCA quebra nem trava por
causa da IA. Timeout duro em toda chamada de rede.
"""
from __future__ import annotations

import asyncio
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from src.core.settings import env_int, env_str
from src.intelligence.response_sanitizer import extrair_json
from src.observabilidade.logger import get_logger

LOG = get_logger("provedor_ia")

# Janelas de cost-control (mesma semântica do GeminiClient original).
_SEGUNDOS_POR_DIA = 86_400
_SEGUNDOS_POR_HORA = 3_600
# Segundos por minuto — o cooldown é configurado em minutos e convertido para segundos.
_SEGUNDOS_POR_MINUTO = 60

# Provedores suportados (case-insensitive na factory). Default: NVIDIA NIM (OpenAI-compat).
PROVEDOR_PADRAO = "nvidia"
PROVEDORES_SUPORTADOS = ("nvidia", "gemini", "gpt", "claude", "ollama")


@runtime_checkable
class ProvedorIA(Protocol):
    """Interface consumida pelos 3 clientes agênticos. Só `analisar` é chamado no caminho quente."""

    async def analisar(
        self, system_prompt: str, user_context: str, *, temperature: float = 0.2
    ) -> dict[str, Any] | None:
        """Consulta a IA e retorna o dict parseado, ou None (cooldown/limite/erro/timeout/sem-chave).

        NUNCA lança exceção — fail-open por contrato."""
        ...

    def disponivel(self) -> bool:
        """True se há chave e o provedor não está em cooldown nem estourou limite dia/hora."""
        ...

    def health(self) -> dict[str, Any]:
        """Snapshot de saúde (chave presente, modelo, cost-control, cooldown). Inclui `provedor`."""
        ...


class ProvedorIARotativo:
    """Roteia chamadas entre instâncias do mesmo provedor sem duplicar tentativas."""

    def __init__(self, provedores: list[ProvedorIA]) -> None:
        if not provedores:
            raise ValueError("provedores_rotativos_vazios")
        self._provedores = provedores
        self._indice = 0

    async def analisar(
        self, system_prompt: str, user_context: str, *, temperature: float = 0.2
    ) -> dict[str, Any] | None:
        total = len(self._provedores)
        inicio = self._indice
        tentou = False
        for deslocamento in range(total):
            indice = (inicio + deslocamento) % total
            provedor = self._provedores[indice]
            if not provedor.disponivel():
                continue
            tentou = True
            self._indice = (indice + 1) % total
            resultado = await provedor.analisar(system_prompt, user_context, temperature=temperature)
            if resultado is not None:
                return resultado
        if tentou:
            return None
        return None

    def disponivel(self) -> bool:
        return any(provedor.disponivel() for provedor in self._provedores)

    def health(self) -> dict[str, Any]:
        saudes = [provedor.health() for provedor in self._provedores]
        return {
            "provedor": "rotativo",
            "provedores": saudes,
            "chaves_configuradas": len(saudes),
            "chave_presente": any(bool(saude.get("chave_presente")) for saude in saudes),
            "disponivel": self.disponivel(),
            "chamadas_dia": sum(int(saude.get("chamadas_dia", 0) or 0) for saude in saudes),
            "chamadas_hora": sum(int(saude.get("chamadas_hora", 0) or 0) for saude in saudes),
        }


class ProvedorIABase(ABC):
    """Base com cost-control compartilhado + wrapper `analisar` fail-open.

    A subclasse concreta implementa apenas `_executar_chamada` (rede específica do provedor) e
    passa, no `__init__` da base, os defaults do provedor (nome/modelo/env vars da chave). Todo
    o resto (limite dia/hora, cooldown por falhas, timeout, redação, parsing JSON) é herdado —
    garantindo comportamento IDÊNTICO entre provedores, incluindo o Gemini legado.

    Convenção das env vars de cost-control: são GENÉRICAS (`IA_MAX_CALLS_DIA`, `IA_MAX_CALLS_HORA`,
    `IA_TIMEOUT_SEGUNDOS`, `IA_FALHAS_COOLDOWN`, `IA_COOLDOWN_MIN`, `IA_MAX_TOKENS`) e valem para
    QUALQUER provedor. As subclasses podem passar `prefixos_legado` (ex.: ["GEMINI"]) para que
    nomes antigos (`GEMINI_MAX_CALLS_DIA`, ...) continuem sendo respeitados — assim quem já
    configurou o Gemini não precisa mexer no `.env`. O nome legado, quando presente, TEM
    precedência (o cliente já o configurou de propósito).
    """

    # Defaults de cost-control (mesmos valores que o GeminiClient usava originalmente).
    _PADRAO_TIMEOUT_S = 15.0
    _PADRAO_MAX_DIA = 50
    _PADRAO_MAX_HORA = 10
    _PADRAO_FALHAS_COOLDOWN = 5
    _PADRAO_COOLDOWN_MIN = 60
    _PADRAO_MAX_TOKENS = 1024

    def __init__(
        self,
        *,
        nome_provedor: str,
        api_key: str,
        modelo: str,
        prefixos_legado: tuple[str, ...] = (),
    ) -> None:
        self._nome_provedor = nome_provedor
        self._api_key = api_key.strip()
        self._modelo = modelo.strip()
        # Cost-control: env genérica `IA_*`, com fallback para nomes legados (ex.: GEMINI_*).
        self._timeout = self._config_float("TIMEOUT_SEGUNDOS", self._PADRAO_TIMEOUT_S, minimo=1.0, prefixos_legado=prefixos_legado)
        self._max_dia = self._config_int("MAX_CALLS_DIA", self._PADRAO_MAX_DIA, minimo=0, prefixos_legado=prefixos_legado)
        self._max_hora = self._config_int("MAX_CALLS_HORA", self._PADRAO_MAX_HORA, minimo=0, prefixos_legado=prefixos_legado)
        self._falhas_p_cooldown = self._config_int("FALHAS_COOLDOWN", self._PADRAO_FALHAS_COOLDOWN, minimo=1, prefixos_legado=prefixos_legado)
        self._cooldown_min = self._config_int("COOLDOWN_MIN", self._PADRAO_COOLDOWN_MIN, minimo=1, prefixos_legado=prefixos_legado)
        self._max_tokens = self._config_int("MAX_TOKENS", self._PADRAO_MAX_TOKENS, minimo=64, prefixos_legado=prefixos_legado)
        # Estado de cost-control (janela rolante por dia/hora + cooldown por falhas).
        self._chamadas_dia = 0
        self._chamadas_hora = 0
        self._falhas_consecutivas = 0
        self._cooldown_ate = 0.0
        self._dia_corrente = int(time.time() // _SEGUNDOS_POR_DIA)
        self._hora_corrente = int(time.time() // _SEGUNDOS_POR_HORA)

    # ── Leitura de config genérica IA_* com fallback legado ──────────────────
    def _config_int(
        self, sufixo: str, padrao: int, *, minimo: int, prefixos_legado: tuple[str, ...]
    ) -> int:
        """Lê `IA_<sufixo>`; se ausente, tenta os nomes legados `<PREFIXO>_<sufixo>` na ordem."""
        import os

        for prefixo in prefixos_legado:
            if os.getenv(f"{prefixo}_{sufixo}") is not None:
                return env_int(f"{prefixo}_{sufixo}", padrao, minimo=minimo)
        return env_int(f"IA_{sufixo}", padrao, minimo=minimo)

    def _config_float(
        self, sufixo: str, padrao: float, *, minimo: float, prefixos_legado: tuple[str, ...]
    ) -> float:
        import os

        from src.core.settings import env_float

        for prefixo in prefixos_legado:
            if os.getenv(f"{prefixo}_{sufixo}") is not None:
                return env_float(f"{prefixo}_{sufixo}", padrao, minimo=minimo)
        return env_float(f"IA_{sufixo}", padrao, minimo=minimo)

    # ── Cost-control ─────────────────────────────────────────────────────────
    def _resetar_janelas(self, agora: float) -> None:
        dia = int(agora // _SEGUNDOS_POR_DIA)
        hora = int(agora // _SEGUNDOS_POR_HORA)
        if dia != self._dia_corrente:
            self._dia_corrente = dia
            self._chamadas_dia = 0
        if hora != self._hora_corrente:
            self._hora_corrente = hora
            self._chamadas_hora = 0

    def disponivel(self) -> bool:
        if not self._api_key:
            return False
        agora = time.time()
        self._resetar_janelas(agora)
        if agora < self._cooldown_ate:
            return False
        if self._max_dia and self._chamadas_dia >= self._max_dia:
            return False
        if self._max_hora and self._chamadas_hora >= self._max_hora:
            return False
        return True

    def _registrar_falha(self) -> None:
        self._falhas_consecutivas += 1
        if self._falhas_consecutivas >= self._falhas_p_cooldown:
            self._cooldown_ate = time.time() + self._cooldown_min * _SEGUNDOS_POR_MINUTO
            LOG.error(
                "ia_cooldown_ativado",
                extra={
                    "provedor": self._nome_provedor,
                    "falhas": self._falhas_consecutivas,
                    "cooldown_min": self._cooldown_min,
                },
            )

    def _redigir(self, texto: str) -> str:
        """Remove a API key de qualquer string antes de logar (defesa contra vazamento em log)."""
        if self._api_key and self._api_key in texto:
            return texto.replace(self._api_key, "***REDACTED***")
        return texto

    # ── Chamada de rede (implementada por cada provedor concreto) ────────────
    @abstractmethod
    async def _executar_chamada(
        self, system_prompt: str, user_context: str, temperature: float
    ) -> str:
        """Faz a chamada REST específica do provedor e retorna o TEXTO cru (JSON string).

        Recebe `system_prompt` e `user_context` SEPARADOS para que provedores com API de
        mensagens por papéis (OpenAI, Anthropic) montem `system`/`user` corretamente. Provedores
        de prompt único (Gemini) concatenam internamente. NÃO deve tratar exceção — o wrapper
        `analisar` da base captura tudo e faz o fail-open."""
        raise NotImplementedError

    # ── API pública (NUNCA lança) ────────────────────────────────────────────
    async def analisar(
        self, system_prompt: str, user_context: str, *, temperature: float = 0.2
    ) -> dict[str, Any] | None:
        """Consulta a IA e retorna o dict parseado, ou None (cooldown/limite/erro/timeout)."""
        if not self.disponivel():
            return None
        # DA-31: conta a TENTATIVA de rede ANTES de disparar — não só o sucesso. Antes, um 429
        # do Google (exceção) NÃO incrementava os contadores, então o teto interno
        # (IA_MAX_CALLS_DIA/HORA) nunca segurava as tentativas: o bot continuava batendo na API
        # a cada ciclo, só parando após 5 falhas consecutivas (cooldown). Como a quota do Google
        # (RPD/RPM) conta CADA requisição enviada — inclusive as que voltam 429 — o contador
        # interno tem que espelhar isso para de fato proteger a cota. Assim o teto interno vira
        # um limite REAL de requisições/dia à rede, independente do resultado.
        self._chamadas_dia += 1
        self._chamadas_hora += 1
        try:
            texto = await asyncio.wait_for(
                self._executar_chamada(system_prompt, user_context, temperature),
                timeout=self._timeout,
            )
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            LOG.warning("ia_timeout", extra={"provedor": self._nome_provedor, "timeout_s": self._timeout})
            self._registrar_falha()
            return None
        except Exception as exc:  # fail-open: a IA jamais derruba/trava o caminho mecânico
            LOG.error(
                "ia_erro",
                extra={"provedor": self._nome_provedor, "erro": self._redigir(f"{type(exc).__name__}: {exc}")},
            )
            mensagem = str(exc)
            if any(f" {status} " in mensagem or f" {status}" in mensagem for status in ("401", "403", "404", "410")):
                self._cooldown_ate = time.time() + 86_400
                LOG.error(
                    "ia_provedor_desativado_erro_permanente",
                    extra={"provedor": self._nome_provedor, "retomada": "reinicio_ou_ajuste_de_configuracao"},
                )
            self._registrar_falha()
            return None

        resultado = extrair_json(texto)
        if resultado is None:
            LOG.warning("ia_json_invalido", extra={"provedor": self._nome_provedor})
            self._registrar_falha()
            return None
        self._falhas_consecutivas = 0
        self._cooldown_ate = 0.0
        return resultado

    def health(self) -> dict[str, Any]:
        agora = time.time()
        return {
            "provedor": self._nome_provedor,
            "chave_presente": bool(self._api_key),
            "modelo": self._modelo,
            "disponivel": self.disponivel(),
            "chamadas_dia": self._chamadas_dia,
            "chamadas_hora": self._chamadas_hora,
            "max_dia": self._max_dia,
            "max_hora": self._max_hora,
            "falhas_consecutivas": self._falhas_consecutivas,
            "em_cooldown": agora < self._cooldown_ate,
            "cooldown_restante_s": max(0, int(self._cooldown_ate - agora)),
        }


def criar_provedor_ia_especifico(nome: str) -> ProvedorIA | None:
    """Cria um provedor específico, sem fallback para outro serviço."""
    escolhido = nome.strip().lower()
    if escolhido not in PROVEDORES_SUPORTADOS:
        raise ValueError(f"provedor_ia_invalido:{escolhido}")
    return _criar_cliente(escolhido)


def criar_provedor_ia() -> ProvedorIA | None:
    """Cria o provedor de IA conforme `AI_PROVIDER`. Retorna None se
    nenhum provedor configurado estiver disponível (camada agêntica desativada — fail-open).

    `AI_PROVIDER` define a preferência; se o provedor preferido não tiver chave, os demais
    provedores configurados são usados como fallback nesta ordem: nvidia, gemini, gpt, claude.
    Trocar a preferência é mudar `AI_PROVIDER` e preencher as chaves correspondentes:
      - nvidia → `NVIDIA_API_KEY`/`Nvidia_API_Key` (modelo `NVIDIA_MODEL`, default `z-ai/glm-5.2`)
    - gemini → `GEMINI_API_KEY`, `GEMINI_API_KEYS` ou `GEMINI_API_KEY_1..N`
             (modelo `GEMINI_MODEL`, default `gemini-flash-latest`)
      - gpt    → `GPT_API_KEY`/`OPENAI_API_KEY` (modelo `GPT_MODEL`, default `gpt-4o-mini`)
      - claude → `CLAUDE_API_KEY`/`ANTHROPIC_API_KEY` (modelo `CLAUDE_MODEL`, default `claude-haiku-4-5`)
      - ollama → LLM LOCAL, sem chave (`OLLAMA_URL` default `http://127.0.0.1:11434`, modelo
                 `OLLAMA_MODEL` default `qwen2.5:7b-instruct`) — mantém a camada consultiva viva
                 mesmo sem internet/cota de nuvem. Servidor Ollama fora do ar ⇒ mesmo fail-open
                 de qualquer provedor (erro de rede ⇒ None, cooldown após falhas consecutivas).

    Valor inválido de `AI_PROVIDER` → loga aviso e cai no default `nvidia` (não quebra o boot).
    """
    escolhido = env_str("AI_PROVIDER", PROVEDOR_PADRAO).strip().lower()
    if escolhido not in PROVEDORES_SUPORTADOS:
        LOG.warning(
            "ai_provider_invalido_usando_default",
            extra={"recebido": escolhido, "default": PROVEDOR_PADRAO, "suportados": list(PROVEDORES_SUPORTADOS)},
        )
        escolhido = PROVEDOR_PADRAO

    if escolhido == "ollama":
        cliente_local = _criar_cliente("ollama")
        LOG.info("camada_agentica_ativada", extra={"provedor": "ollama", "provedores_disponiveis": 1})
        return cliente_local

    ordem = [escolhido] + [nome for nome in ("nvidia", "gemini", "gpt", "claude") if nome != escolhido]
    clientes = [cliente for nome in ordem if (cliente := _criar_cliente(nome)) is not None]
    if not clientes:
        LOG.info("camada_agentica_desativada_sem_chave", extra={"provedor": escolhido})
        return None
    cliente_final: ProvedorIA = clientes[0] if len(clientes) == 1 else ProvedorIARotativo(clientes)
    LOG.info(
        "camada_agentica_ativada",
        extra={"provedor": cliente_final.health().get("provedor"), "provedores_disponiveis": len(clientes)},
    )
    return cliente_final


def _criar_cliente(nome: str) -> ProvedorIA | None:
    """Cria um provedor concreto somente quando há credencial disponível."""
    if nome == "nvidia":
        from src.intelligence.nvidia_client import NvidiaClient

        chaves = _chaves_nvidia()
        if not chaves:
            return None
        return ProvedorIARotativo([NvidiaClient(api_key=chave) for chave in chaves]) if len(chaves) > 1 else NvidiaClient(api_key=chaves[0])
    if nome == "gemini":
        from src.intelligence.gemini_client import GeminiClient

        chaves = _chaves_gemini()
        if not chaves:
            return None
        return ProvedorIARotativo([GeminiClient(api_key=chave) for chave in chaves]) if len(chaves) > 1 else GeminiClient(api_key=chaves[0])
    if nome == "ollama":
        from src.intelligence.ollama_client import OllamaClient

        return OllamaClient()
    if nome == "gpt":
        from src.intelligence.gpt_client import GPTClient

        cliente = GPTClient()
    elif nome == "claude":
        from src.intelligence.claude_client import ClaudeClient

        cliente = ClaudeClient()
    else:
        return None
    return cliente if cliente.health().get("chave_presente") else None


def _chaves_gemini() -> list[str]:
    """Lê uma ou várias chaves sem registrar os valores em logs ou diagnósticos."""
    valores: list[str] = []
    lista = os.getenv("GEMINI_API_KEYS", "")
    valores.extend(parte.strip() for parte in lista.replace(";", ",").replace("\n", ",").split(","))
    for indice in range(1, 21):
        valores.append(os.getenv(f"GEMINI_API_KEY_{indice}", "").strip())
    valores.append(os.getenv("GEMINI_API_KEY", "").strip())
    return list(dict.fromkeys(valor for valor in valores if valor))


def _chaves_nvidia() -> list[str]:
    """Lê chaves NVIDIA em lista ou variáveis numeradas, sem expor os valores."""
    valores: list[str] = []
    lista = os.getenv("NVIDIA_API_KEYS", "")
    valores.extend(parte.strip() for parte in lista.replace(";", ",").replace("\n", ",").split(","))
    for indice in range(1, 21):
        valores.append(os.getenv(f"NVIDIA_API_KEY_{indice}", "").strip())
    for nome in ("NVIDIA_API_KEY", "Nvidia_API_Key", "Nvidia_API_KEY", "NVAPI_KEY"):
        valores.append(os.getenv(nome, "").strip())
    return list(dict.fromkeys(valor for valor in valores if valor))
