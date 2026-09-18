"""Voto DIRECIONAL de peso igual da IA — segunda camada agêntica, distinta do veto.

DECISÃO DE NEGÓCIO (autorizada explicitamente pelo dono do projeto, 2026-07-01): a IA Gemini
passa a ter um voto DIRECIONAL (BUY/SELL/HOLD) com peso NOMINAL igual ao do motor mecânico
dentro do consenso ponderado (`src/sinais/consenso.py`, fonte `"ia_gemini"`), em vez de apenas
vetar. Isto é uma mudança arquitetural que RELAXA a proteção histórica "IA só veta" (DA-23) —
mas apenas para esta camada nova. As duas camadas COEXISTEM:

  (1) Este módulo (`AnalistaMercadoIA.avaliar_direcional`) — opina A FAVOR ou CONTRA a direção,
      entra como mais uma fonte no consenso ponderado, com peso nominal igual à fonte
      "estrategia". Isto acontece ANTES da checagem de gates financeiros.
  (2) `PreExecutionFilter` (`pre_execution_filter.py`) — veto final independente, consultado
      DEPOIS de todos os gates (EV, risco, edge), mesmo que o consenso já tenha decidido.
      Continua ativo e inalterado.

As duas são fail-open/fail-safe INDEPENDENTEMENTE uma da outra — uma falhar não afeta a outra.

LOTE (economia de RPM/TPM, 2026-07-01): sob rate limit apertado (ex.: tier gratuito do Gemini,
15 RPM), consultar a IA símbolo-a-símbolo multiplica o consumo pelo número de pares monitorados
a CADA ciclo. `avaliar_lote()` faz UMA chamada de rede cobrindo todos os símbolos de uma vez
(um prompt, um array de contextos, um array de votos na resposta) e guarda o resultado num
cache curto (TTL). `avaliar_direcional(simbolo=...)` — a MESMA API já consumida por
`signal_engine.gerar_sinal_orquestrado` — passa a consultar esse cache primeiro; se não há
lote fresco para o símbolo (cache frio, símbolo fora do lote, ou lote nunca chamado), cai de
volta no caminho por-símbolo original, byte a byte idêntico ao comportamento anterior. Ou
seja: quem já usa `avaliar_direcional` sozinho continua funcionando sem mudar nada; quem
prima o cache com `avaliar_lote` primeiro ganha a economia de rede automaticamente.

REGRA CRÍTICA DE FAIL-SAFE (não-negociável): se a IA estiver indisponível, com erro, em timeout,
em cooldown ou sem chave configurada, `avaliar_direcional` retorna um voto NEUTRO com
`confianca=0.0` e `acao="HOLD"`. O mecanismo de consenso pondera `score = score_direcional *
confianca` (ver `src/sinais/consenso.py`, fonte "ia_gemini") — com `confianca=0.0` o score da
fonte já é 0.0, e sua contribuição na média pesada colapsa a ~zero mesmo com peso NOMINAL alto.
Ou seja: o peso é igual "no papel" (na fórmula), mas uma IA que falhou ou está insegura não
consegue puxar a decisão — isso é seguro por construção, sem precisar de lógica de fallback
especial no consenso.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from src.core.settings import env_float
from src.intelligence.context_builder import (
    construir_contexto_analise_direcional,
    construir_contexto_analise_direcional_lote,
)
from src.intelligence.prompt_templates import PROMPT_ANALISE_DIRECIONAL, PROMPT_ANALISE_DIRECIONAL_LOTE
from src.intelligence.provedor_ia import ProvedorIA
from src.observabilidade.logger import get_logger

LOG = get_logger("market_analyst")

_ACOES_VALIDAS = {"BUY", "SELL", "HOLD"}

# THROTTLE DA IA (DA-31, 2026-07-02): o free tier do Gemini é minúsculo (medido: 2.5-flash-lite
# = 1000 requisições/DIA, o maior; 3.5-flash = 20/dia). Um bot 24/7 a cada 30s faria ~2880
# chamadas/dia — estoura em minutos. A camada de IA passa a ser CONSULTIVA RARA: no máximo 1
# chamada de lote a cada `AI_MIN_INTERVALO_SEGUNDOS` (default 600s = 10min). Entre uma consulta
# e outra, o cache serve o último voto (o mercado não muda de tese a cada 30s — um voto
# direcional de 10min atrás continua informativo). 600s ⇒ ~144 chamadas/dia, cabe folgado em
# 1000 RPD. O motor MECÂNICO segue rodando a cada ciclo (30s) sem depender da IA — a IA só
# tempera a direção quando há um voto fresco em cache. Configurável por env; 0 desliga o
# throttle (volta ao comportamento de 1 chamada por ciclo elegível — só faz sentido com billing).
def _min_intervalo_ia_s() -> float:
    from src.core.settings import env_float

    return env_float("AI_MIN_INTERVALO_SEGUNDOS", 600.0, minimo=0.0)


# TTL do cache de SUCESSO: alinhado ao intervalo de throttle — o voto vale enquanto não for
# hora de consultar de novo. Calculado no ponto de uso (via `_min_intervalo_ia_s`), com um piso
# de 45s para o caso de throttle desligado (0), preservando o comportamento antigo de cobrir
# um ciclo do auto-trader sem servir voto obsoleto.
_LOTE_CACHE_TTL_PISO_S = 45.0

# TTL do cache de FALHA do lote — mais curto que o de sucesso (DA-30.1, fix de bug de produção,
# 2026-07-02): sob 429/timeout/erro, o resultado é sempre HOLD/confiança 0.0 (fail-safe), mas
# ainda assim precisa ser CACHEADO — do contrário qualquer chamador de `avaliar_direcional`
# no MESMO ciclo (o loop do orquestrador para os demais símbolos elegíveis, ou o trader
# consultando o símbolo em foco) encontra cache frio e tenta de novo INDIVIDUALMENTE, o que
# na prática transformou 1 falha de lote em até 6 chamadas de rede extras em produção (ver
# log.txt, 5 erros 429 consecutivos até o cooldown de 60min dar exit). 30s (< 45s do sucesso)
# porque uma falha pode ser transitória — não vale a pena prender o bot em HOLD forçado por
# tanto tempo quanto um voto real.
_LOTE_CACHE_TTL_FALHA_S = 30.0


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


@dataclass(slots=True)
class VotoIA:
    """Voto direcional normalizado da IA — sempre seguro de consumir (nunca None)."""

    acao: str = "HOLD"                 # "BUY" | "SELL" | "HOLD" — qualquer outra coisa vira HOLD
    score_direcional: float = 0.0      # -1.0 (SELL forte) a +1.0 (BUY forte), clampado
    confianca: float = 0.0             # 0.0 a 1.0, clampado — 0.0 = fail-safe (colapsa peso no consenso)
    rationale: str = ""
    fonte: str = "indisponivel"        # gemini | indisponivel | erro | timeout | desativado
    sentimento_mercado: float = 0.0    # -1.0 a 1.0 — sentimento geral, separado do score direcional

    def to_dict(self) -> dict[str, Any]:
        return {
            "acao": self.acao,
            "score_direcional": self.score_direcional,
            "confianca": self.confianca,
            "rationale": self.rationale,
            "fonte": self.fonte,
            "sentimento_mercado": self.sentimento_mercado,
        }


def _voto_neutro(fonte: str, rationale: str = "") -> VotoIA:
    """Voto de fail-safe: HOLD com confiança zero — peso efetivo ~zero no consenso (ver docstring do módulo)."""
    return VotoIA(acao="HOLD", score_direcional=0.0, confianca=0.0, rationale=rationale, fonte=fonte, sentimento_mercado=0.0)


def _normalizar_voto(bruto: dict[str, Any] | None) -> VotoIA:
    if not isinstance(bruto, dict):
        return _voto_neutro("erro", rationale="resposta_ia_invalida")

    acao = str(bruto.get("action", "HOLD") or "HOLD").strip().upper()
    if acao not in _ACOES_VALIDAS:
        acao = "HOLD"  # fail-safe: qualquer ação fora do enum vira HOLD

    try:
        score = _clamp(float(bruto.get("score_direcional", 0.0) or 0.0), -1.0, 1.0)
    except (TypeError, ValueError):
        score = 0.0
    try:
        confianca = _clamp(float(bruto.get("confidence", 0.0) or 0.0), 0.0, 1.0)
    except (TypeError, ValueError):
        confianca = 0.0
    try:
        sentimento = _clamp(float(bruto.get("sentimento_mercado", 0.0) or 0.0), -1.0, 1.0)
    except (TypeError, ValueError):
        sentimento = 0.0

    rationale = str(bruto.get("rationale", "") or "")[:300]

    return VotoIA(
        acao=acao,
        score_direcional=score,
        confianca=confianca,
        rationale=rationale,
        fonte="gemini",
        sentimento_mercado=sentimento,
    )


class AnalistaMercadoIA:
    """Segundo analista independente — dá à IA um voto direcional (não-veto) sobre BUY/SELL/HOLD.

    Reutiliza a MESMA infraestrutura de `PreExecutionFilter`: um `ProvedorIA` (fail-open,
    cost-controlled, compartilhado — ver DA-23 e comentário de custo em `signal_engine.py`),
    `context_builder` e `response_sanitizer` (via `ProvedorIA.analisar`). Não reimplementa
    cliente HTTP nem parsing de JSON. O provedor concreto (gemini|gpt|claude) é escolhido pela
    factory `criar_provedor_ia()` conforme `AI_PROVIDER` — este módulo é agnóstico a ele.
    """

    def __init__(
        self,
        gemini: ProvedorIA,
        *,
        habilitado: bool = True,
        timeout_s: float | None = None,
    ) -> None:
        self._gemini = gemini
        self._habilitado = bool(habilitado)
        # Reusa o mesmo timeout curto/agressivo do filtro de veto — o sinal não pode travar
        # esperando rede indefinidamente (mesmo espírito de AI_FILTER_TIMEOUT_SEGUNDOS).
        self._timeout = (
            float(timeout_s) if timeout_s is not None else env_float("AI_FILTER_TIMEOUT_SEGUNDOS", 12.0, minimo=1.0)
        )
        # Cache do último lote: {simbolo: (VotoIA, ts_epoch_s)}. Populado só por `avaliar_lote`;
        # `avaliar_direcional` lê, nunca escreve — mantém as duas APIs desacopladas.
        self._cache_lote: dict[str, tuple[VotoIA, float]] = {}
        # Timestamp da última consulta de lote BEM-SUCEDIDA (fonte real "gemini") — base do
        # throttle: só consulta a rede de novo depois de `AI_MIN_INTERVALO_SEGUNDOS`.
        self._ultimo_lote_ok_ts = 0.0
        self._ultimo_contexto_diario = -1

    async def preparar_contexto_diario(
        self,
        *,
        simbolos: list[str],
        saldo: float = 0.0,
        noticias_por_simbolo: dict[str, list[Any]] | None = None,
    ) -> None:
        """Faz uma leitura diária das notícias e deixa os votos no cache do analista."""
        dia_atual = int(time.time() // 86_400)
        if dia_atual == self._ultimo_contexto_diario or not simbolos:
            return
        self._ultimo_contexto_diario = dia_atual
        await self.avaliar_lote(
            simbolos=simbolos,
            saldo=saldo,
            noticias_por_simbolo=noticias_por_simbolo,
        )

    def _ttl_sucesso_s(self) -> float:
        # Voto de sucesso vale pelo intervalo de throttle (ou o piso de 45s se throttle=0).
        return max(_min_intervalo_ia_s(), _LOTE_CACHE_TTL_PISO_S)

    def _voto_em_cache(self, simbolo: str) -> VotoIA | None:
        entrada = self._cache_lote.get(simbolo)
        if entrada is None:
            return None
        voto, ts = entrada
        # Voto de FALHA (erro/timeout/indisponível/formato inválido) usa TTL curto — ver
        # `_LOTE_CACHE_TTL_FALHA_S`. Voto de sucesso real ("gemini") vale pelo intervalo de throttle.
        ttl = self._ttl_sucesso_s() if voto.fonte == "gemini" else _LOTE_CACHE_TTL_FALHA_S
        if (time.time() - ts) > ttl:
            return None
        return voto

    def _cachear_lote(self, votos: dict[str, VotoIA]) -> None:
        agora = time.time()
        for simbolo, voto in votos.items():
            self._cache_lote[simbolo] = (voto, agora)

    async def avaliar_lote(
        self,
        *,
        simbolos: list[str],
        saldo: float = 0.0,
        noticias_por_simbolo: dict[str, list[Any]] | None = None,
    ) -> dict[str, VotoIA]:
        """Consulta a IA para TODOS os `simbolos` numa ÚNICA chamada de rede. NUNCA lança.

        Preenche o cache interno (lido por `avaliar_direcional`) e também retorna o dict
        `{simbolo: VotoIA}` diretamente, para quem prefere consumir o lote sem passar pelo
        cache (ex.: o scanner multiativo, que já itera todos os símbolos de qualquer forma).

        Fail-safe: qualquer falha (timeout/erro/JSON inválido/indisponível) devolve HOLD/
        confiança 0.0 para TODOS os símbolos do lote — o mesmo comportamento de fail-safe que
        cada chamada individual teria, só que aplicado de uma vez. O resultado de falha TAMBÉM
        é cacheado (TTL curto, `_LOTE_CACHE_TTL_FALHA_S`) — DA-30.1: não cachear a falha permitia
        que qualquer chamador de `avaliar_direcional` no MESMO ciclo (símbolos elegíveis restantes
        no orquestrador, ou o trader consultando o símbolo em foco) encontrasse cache frio e
        tentasse de novo INDIVIDUALMENTE, multiplicando 1 falha de rede em várias chamadas
        extras (bug real observado em produção — ver log.txt, 429 em cascata até o cooldown).
        """
        if not simbolos:
            return {}
        if not self._habilitado:
            votos = {s: _voto_neutro("desativado", rationale="analista_ia_desativado") for s in simbolos}
            self._cachear_lote(votos)
            return votos

        # THROTTLE (DA-31): se a última consulta BEM-SUCEDIDA foi há menos de
        # `AI_MIN_INTERVALO_SEGUNDOS`, NÃO toca a rede — devolve o voto em cache (ainda fresco,
        # pois o TTL de sucesso == intervalo de throttle). Sem voto em cache p/ o símbolo (ex.:
        # símbolo novo no meio do intervalo), devolve neutro sem chamar rede. Isso mantém o
        # consumo de IA em ~1 chamada por intervalo (cabe no free tier do Gemini) enquanto o
        # motor mecânico segue decidindo a cada ciclo. throttle=0 desliga (billing/tier pago).
        intervalo = _min_intervalo_ia_s()
        if intervalo > 0.0 and (time.time() - self._ultimo_lote_ok_ts) < intervalo:
            return {s: (self._voto_em_cache(s) or _voto_neutro("throttle", rationale="ia_em_intervalo")) for s in simbolos}

        # O intervalo protege a cota também quando a tentativa falha. Sem este marcador,
        # 404/401/429 fazia o lote ser repetido a cada ciclo até todos os provedores entrarem
        # em cooldown, enquanto o motor local continuava trabalhando sem necessidade.
        self._ultimo_lote_ok_ts = time.time()
        try:
            contexto = await construir_contexto_analise_direcional_lote(simbolos, saldo, noticias_por_simbolo)
            bruto = await asyncio.wait_for(
                self._gemini.analisar(PROMPT_ANALISE_DIRECIONAL_LOTE, contexto, temperature=0.3),
                timeout=self._timeout,
            )
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            LOG.warning("analista_ia_lote_timeout", extra={"simbolos": simbolos})
            votos = {s: _voto_neutro("timeout", rationale="timeout_ia") for s in simbolos}
            self._cachear_lote(votos)
            return votos
        except Exception as exc:  # fail-safe: IA jamais derruba/trava o caminho mecânico
            LOG.error("analista_ia_lote_erro", extra={"simbolos": simbolos, "erro": str(exc)})
            votos = {s: _voto_neutro("erro", rationale=str(exc)[:200]) for s in simbolos}
            self._cachear_lote(votos)
            return votos

        if bruto is None:
            votos = {s: _voto_neutro("indisponivel", rationale="ia_indisponivel") for s in simbolos}
            self._cachear_lote(votos)
            return votos

        votos_brutos = bruto.get("votos") if isinstance(bruto, dict) else None
        if not isinstance(votos_brutos, list):
            LOG.warning("analista_ia_lote_formato_invalido", extra={"simbolos": simbolos})
            votos = {s: _voto_neutro("erro", rationale="formato_lote_invalido") for s in simbolos}
            self._cachear_lote(votos)
            return votos

        por_simbolo_bruto = {
            str(item.get("simbolo", "")).upper(): item for item in votos_brutos if isinstance(item, dict)
        }
        resultado: dict[str, VotoIA] = {}
        for simbolo in simbolos:
            item = por_simbolo_bruto.get(simbolo.upper())
            voto = _normalizar_voto(item) if item is not None else _voto_neutro("erro", rationale="simbolo_ausente_no_lote")
            resultado[simbolo] = voto
        self._cachear_lote(resultado)
        # Marca o sucesso: reinicia a janela de throttle só quando houve voto REAL da IA.
        self._ultimo_lote_ok_ts = time.time()

        LOG.info("analista_ia_lote_voto", extra={"simbolos": simbolos, "acoes": {s: v.acao for s, v in resultado.items()}})
        return resultado

    async def avaliar_direcional(
        self,
        *,
        simbolo: str,
        sinal_mecanico: dict[str, Any] | None = None,
        saldo: float = 0.0,
        noticias: list[Any] | None = None,
    ) -> VotoIA:
        """Consulta a IA para um voto direcional independente. NUNCA lança exceção.

        `sinal_mecanico` é aceito na assinatura por simetria com `PreExecutionFilter.avaliar`
        e para uso futuro em logging/auditoria — mas NÃO é enviado ao prompt (ver
        `construir_contexto_analise_direcional`), propositalmente, para não ancorar a IA na
        decisão do motor mecânico antes dela formar a própria opinião.

        Consulta primeiro o cache de `avaliar_lote` (ver docstring do módulo — economia de
        RPM/TPM). Cache frio para este símbolo ⇒ caminho por-símbolo original, sem mudança de
        comportamento (é o que os testes deste módulo travam).
        """
        if not self._habilitado:
            return _voto_neutro("desativado", rationale="analista_ia_desativado")
        voto_cache = self._voto_em_cache(simbolo)
        if voto_cache is not None:
            return voto_cache
        try:
            contexto = await construir_contexto_analise_direcional(simbolo, saldo, noticias)
            bruto = await asyncio.wait_for(
                self._gemini.analisar(PROMPT_ANALISE_DIRECIONAL, contexto, temperature=0.3),
                timeout=self._timeout,
            )
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            LOG.warning("analista_ia_timeout", extra={"simbolo": simbolo})
            return _voto_neutro("timeout", rationale="timeout_ia")
        except Exception as exc:  # fail-safe: IA jamais derruba/trava o caminho mecânico
            LOG.error("analista_ia_erro", extra={"simbolo": simbolo, "erro": str(exc)})
            return _voto_neutro("erro", rationale=str(exc)[:200])

        if bruto is None:
            # ProvedorIA.analisar já cobre: sem chave, cooldown, limite de custo, JSON inválido.
            return _voto_neutro("indisponivel", rationale="ia_indisponivel")

        voto = _normalizar_voto(bruto)
        LOG.info(
            "analista_ia_voto",
            extra={
                "simbolo": simbolo,
                "acao": voto.acao,
                "score_direcional": voto.score_direcional,
                "confianca": voto.confianca,
            },
        )
        return voto
