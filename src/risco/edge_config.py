"""Governança de EDGE — gate de lucratividade para conta REAL (GRD/QNT/EXE).

O bot só arrisca DINHEIRO REAL num símbolo quando existe um EDGE LÍQUIDO VALIDADO
out-of-sample (walk-forward) para ele — e enquanto essa validação estiver FRESCA.
Fora disso, a entrada real é BLOQUEADA. Testnet/exploração NÃO passam por este gate
(são coleta de dado / validação de fluxo, sem risco de capital).

PROPRIEDADES DE SEGURANÇA (principalmente seguro — fail-safe por construção):
  1. DEFAULT-CLOSED: símbolo desconhecido → entrada real NEGADA.
  2. FRESCOR: edge validado há mais de EDGE_VALIDADE_DIAS → EXPIRA → NEGADO.
     (auto-expira sozinho; nenhum edge "validado uma vez" opera para sempre).
  3. `ativo=True` só é gravado por um walk-forward que PROVOU net/trade > 0 com IC>0 e
     amostra suficiente (`registrar_resultado_edge`). Nenhum caminho liga `ativo` à mão.
  4. Apenas ENTRADAS reais (BUY de abertura) passam pelo gate. SAÍDAS (SELL) nunca são
     bloqueadas — travar uma venda prenderia capital (isso seria, por si, um risco).
  5. FAIL-CLOSED no chamador: qualquer erro ao consultar o gate ⇒ tratar como NEGADO.

Persistência: `RepositorioConfig` (chave `edge_config`), durável e relida no startup —
mesmo padrão do circuit_breaker (DA-13) e da retomada. Fonte do veredito: walk_forward
(DA-02: custo round-trip via EVCalculator, fonte única). Honestidade (CLAUDE.md): hoje o
registro está VAZIO porque o walk-forward não achou edge líquido — então toda entrada real
fica bloqueada por desenho, e o bot opera apenas em testnet/exploração até surgir edge real.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.core.settings import env_float, env_int
from src.observabilidade.logger import get_logger

if TYPE_CHECKING:  # evita puxar numpy (via walk_forward) para o hot path do autotrader
    from src.backtester.walk_forward import ResultadoBacktest

LOG = get_logger("edge_config")

# Chave única no RepositorioConfig (registro global de edges validados do processo).
_CHAVE_CONFIG: str = "edge_config"
_MS_POR_DIA: int = 86_400_000


def _validade_dias() -> int:
    """Janela de frescor: edge validado há mais que isto EXPIRA (auto-desliga = fail-safe)."""
    return env_int("EDGE_VALIDADE_DIAS", 7, minimo=1)


def _min_trades_validacao() -> int:
    """Mínimo de trades out-of-sample para confiar no veredito (mais estrito que o walk_forward)."""
    return env_int("EDGE_MIN_TRADES", 30, minimo=1)


def _ic_minimo() -> float:
    """IC walk-forward mínimo para considerar que há sinal preditivo real (margem sobre ruído)."""
    return env_float("EDGE_IC_MINIMO", 0.02, minimo=0.0)


def _margem_minima_pct() -> float:
    """Retorno LÍQUIDO médio/trade mínimo (já descontado o custo round-trip) p/ ligar o edge."""
    return env_float("EDGE_MARGEM_MINIMA_PCT", 0.0, minimo=0.0)


@dataclass
class EdgeConfig:
    """Veredito de edge por símbolo — só `ativo=True` libera entrada real (ver módulo)."""

    simbolo: str
    ativo: bool
    horizonte: int = 0
    seletividade_min_pct: float = 0.0   # |predição| mínima p/ entrar (= alvo + custo round-trip)
    alvo_liquido_pct: float = 0.0
    ic_validado: float = 0.0
    n_trades_validacao: int = 0
    retorno_liquido_medio_trade: float = 0.0
    win_rate: float = 0.0
    custo_pct_round_trip: float = 0.0
    validado_em_ms: int = 0
    fonte: str = "walk_forward"

    def to_dict(self) -> dict[str, Any]:
        return {
            "simbolo": self.simbolo,
            "ativo": bool(self.ativo),
            "horizonte": int(self.horizonte),
            "seletividade_min_pct": float(self.seletividade_min_pct),
            "alvo_liquido_pct": float(self.alvo_liquido_pct),
            "ic_validado": float(self.ic_validado),
            "n_trades_validacao": int(self.n_trades_validacao),
            "retorno_liquido_medio_trade": float(self.retorno_liquido_medio_trade),
            "win_rate": float(self.win_rate),
            "custo_pct_round_trip": float(self.custo_pct_round_trip),
            "validado_em_ms": int(self.validado_em_ms),
            "fonte": str(self.fonte),
        }

    @classmethod
    def from_dict(cls, dados: dict[str, Any]) -> "EdgeConfig":
        return cls(
            simbolo=str(dados.get("simbolo", "")).upper(),
            ativo=bool(dados.get("ativo", False)),
            horizonte=int(dados.get("horizonte", 0) or 0),
            seletividade_min_pct=float(dados.get("seletividade_min_pct", 0.0) or 0.0),
            alvo_liquido_pct=float(dados.get("alvo_liquido_pct", 0.0) or 0.0),
            ic_validado=float(dados.get("ic_validado", 0.0) or 0.0),
            n_trades_validacao=int(dados.get("n_trades_validacao", 0) or 0),
            retorno_liquido_medio_trade=float(dados.get("retorno_liquido_medio_trade", 0.0) or 0.0),
            win_rate=float(dados.get("win_rate", 0.0) or 0.0),
            custo_pct_round_trip=float(dados.get("custo_pct_round_trip", 0.0) or 0.0),
            validado_em_ms=int(dados.get("validado_em_ms", 0) or 0),
            fonte=str(dados.get("fonte", "walk_forward") or "walk_forward"),
        )

    def idade_dias(self, agora_ms: int) -> float:
        if self.validado_em_ms <= 0:
            return float("inf")
        return max(0.0, (agora_ms - self.validado_em_ms) / _MS_POR_DIA)


@dataclass
class ResultadoGateEdge:
    """Resultado do gate de edge para conta real. `aprovado=False` ⇒ NÃO abrir posição real."""

    aprovado: bool
    motivo: str
    detalhe: dict[str, Any] = field(default_factory=dict)


def avaliar_edge(
    config: EdgeConfig | None,
    *,
    agora_ms: int,
    validade_dias: int | None = None,
) -> ResultadoGateEdge:
    """Núcleo PURO do gate (sem I/O) — testável e determinístico.

    NEGA por padrão. Só aprova edge `ativo` E dentro da janela de frescor.
    """
    validade = _validade_dias() if validade_dias is None else max(1, int(validade_dias))
    if config is None:
        return ResultadoGateEdge(False, "edge_inexistente", {"validade_dias": validade})
    base = config.to_dict()
    if not config.ativo:
        return ResultadoGateEdge(False, "edge_inativo", base)
    idade = config.idade_dias(agora_ms)
    if idade > validade:
        return ResultadoGateEdge(
            False, "edge_expirado", {**base, "idade_dias": round(idade, 2), "validade_dias": validade}
        )
    return ResultadoGateEdge(
        True, "edge_validado_fresco", {**base, "idade_dias": round(idade, 2), "validade_dias": validade}
    )


class RegistroEdge:
    """Coleção de `EdgeConfig` por símbolo, persistida em `RepositorioConfig` (durável)."""

    def __init__(self) -> None:
        self._por_simbolo: dict[str, EdgeConfig] = {}

    # ── Acesso em memória ────────────────────────────────────────────────────
    def obter(self, simbolo: str) -> EdgeConfig | None:
        return self._por_simbolo.get((simbolo or "").upper())

    def atualizar(self, config: EdgeConfig) -> None:
        self._por_simbolo[config.simbolo.upper()] = config

    def itens(self) -> dict[str, EdgeConfig]:
        return dict(self._por_simbolo)

    def resumo(self) -> dict[str, Any]:
        agora = int(time.time() * 1000)
        validade = _validade_dias()
        simbolos = {
            s: {
                **c.to_dict(),
                "idade_dias": round(c.idade_dias(agora), 2),
                "aprovado_para_real": avaliar_edge(c, agora_ms=agora, validade_dias=validade).aprovado,
            }
            for s, c in self._por_simbolo.items()
        }
        ativos = [s for s, d in simbolos.items() if d["aprovado_para_real"]]
        return {
            "validade_dias": validade,
            "min_trades": _min_trades_validacao(),
            "ic_minimo": _ic_minimo(),
            "margem_minima_pct": _margem_minima_pct(),
            "total_simbolos": len(simbolos),
            "simbolos_aprovados_para_real": ativos,
            "ha_edge_para_real": bool(ativos),
            "simbolos": simbolos,
        }

    # ── Persistência (sobrevive a restart) ───────────────────────────────────
    async def carregar(self) -> "RegistroEdge":
        from src.persistencia.repositorio_config import RepositorioConfig

        dados = await RepositorioConfig.obter(_CHAVE_CONFIG)
        self._por_simbolo = {}
        if isinstance(dados, dict):
            for simbolo, payload in dados.items():
                if isinstance(payload, dict):
                    cfg = EdgeConfig.from_dict({**payload, "simbolo": simbolo})
                    self._por_simbolo[cfg.simbolo.upper()] = cfg
        return self

    async def salvar(self) -> None:
        from src.persistencia.repositorio_config import RepositorioConfig

        await RepositorioConfig.definir(
            _CHAVE_CONFIG, {s: c.to_dict() for s, c in self._por_simbolo.items()}
        )


def _edge_aprovavel(resultado: "ResultadoBacktest") -> bool:
    """Critério (mais estrito que o walk_forward) para LIGAR uma entrada real (`ativo=True`)."""
    return (
        bool(getattr(resultado, "tem_edge_liquido", False))
        and int(getattr(resultado, "n_trades", 0)) >= _min_trades_validacao()
        and float(getattr(resultado, "ic_walk_forward", 0.0)) >= _ic_minimo()
        and float(getattr(resultado, "retorno_liquido_medio_trade", 0.0)) >= _margem_minima_pct()
    )


def construir_config_de_resultado(
    resultado: "ResultadoBacktest", *, agora_ms: int | None = None
) -> EdgeConfig:
    """Traduz um `ResultadoBacktest` (walk-forward) em `EdgeConfig` (sem persistir).

    `ativo` reflete o veredito honesto do backtest sob critério conservador. Lê o resultado
    estruturalmente (duck typing) para não acoplar este módulo ao numpy do walk_forward.
    """
    agora = int(time.time() * 1000) if agora_ms is None else int(agora_ms)
    ativo = _edge_aprovavel(resultado)
    return EdgeConfig(
        simbolo=str(getattr(resultado, "simbolo", "")).upper(),
        ativo=ativo,
        horizonte=int(getattr(resultado, "horizonte", 0) or 0),
        seletividade_min_pct=float(getattr(resultado, "bruto_necessario_pct", 0.0) or 0.0),
        alvo_liquido_pct=float(getattr(resultado, "alvo_liquido_pct", 0.0) or 0.0),
        ic_validado=float(getattr(resultado, "ic_walk_forward", 0.0) or 0.0),
        n_trades_validacao=int(getattr(resultado, "n_trades", 0) or 0),
        retorno_liquido_medio_trade=float(getattr(resultado, "retorno_liquido_medio_trade", 0.0) or 0.0),
        win_rate=float(getattr(resultado, "win_rate_liquido", 0.0) or 0.0),
        custo_pct_round_trip=float(getattr(resultado, "custo_pct_round_trip", 0.0) or 0.0),
        validado_em_ms=agora,
        fonte="walk_forward",
    )


def registrar_resultado_edge(
    registro: RegistroEdge, resultado: "ResultadoBacktest", *, agora_ms: int | None = None
) -> EdgeConfig:
    """Grava (em memória) o veredito de um backtest no registro. O chamador persiste com `salvar()`.

    Se houver mais de um horizonte para o mesmo símbolo, mantém o que LIBERA o real; entre dois
    do mesmo status, mantém o de maior retorno líquido médio (escolha conservadora e estável).
    """
    novo = construir_config_de_resultado(resultado, agora_ms=agora_ms)
    atual = registro.obter(novo.simbolo)
    if atual is not None:
        melhor_atual = (atual.ativo, atual.retorno_liquido_medio_trade)
        melhor_novo = (novo.ativo, novo.retorno_liquido_medio_trade)
        if melhor_atual >= melhor_novo:
            return atual
    registro.atualizar(novo)
    LOG.info(
        "edge_registrado",
        extra={
            "simbolo": novo.simbolo, "ativo": novo.ativo, "horizonte": novo.horizonte,
            "ic": round(novo.ic_validado, 4), "net_trade": round(novo.retorno_liquido_medio_trade, 6),
            "n_trades": novo.n_trades_validacao,
        },
    )
    return novo


async def persistir_resultados_edge(resultados: list["ResultadoBacktest"]) -> dict[str, Any]:
    """Atualiza o registro durável a partir de uma lista de backtests e devolve o resumo.

    Usado pelo runner do walk-forward para que rodar o backtest CONFIGURE o edge do bot.
    """
    registro = await RegistroEdge().carregar()
    for resultado in resultados:
        if getattr(resultado, "simbolo", ""):
            registrar_resultado_edge(registro, resultado)
    await registro.salvar()
    return registro.resumo()


async def edge_aprovado_conta_real(simbolo: str, *, agora_ms: int | None = None) -> ResultadoGateEdge:
    """Gate assíncrono de alto nível: carrega o registro durável e avalia o símbolo.

    NEGA por padrão (símbolo ausente/inativo/expirado). Conveniência do caminho de execução.
    """
    agora = int(time.time() * 1000) if agora_ms is None else int(agora_ms)
    registro = await RegistroEdge().carregar()
    return avaliar_edge(registro.obter(simbolo), agora_ms=agora)


async def resumo_edge() -> dict[str, Any]:
    """Resumo do registro de edge para a API (`/v1/edge`) e diagnóstico."""
    registro = await RegistroEdge().carregar()
    return registro.resumo()
