from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class SignalDecision:
    simbolo: str
    acao: str
    ts: int
    confianca: float
    stop_loss_pct: float
    take_profit_pct: float
    lucro_liquido_esperado_pct: float
    features: dict[str, Any] = field(default_factory=dict)
    confirmacao_multi_timeframe: dict[str, Any] = field(default_factory=dict)
    probabilidade_trade: dict[str, Any] = field(default_factory=dict)
    janela_decisao: dict[str, Any] = field(default_factory=dict)
    detalhe: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "SignalDecision":
        dados = dict(payload)
        known = {
            "simbolo",
            "acao",
            "ts",
            "confianca",
            "stop_loss_pct",
            "take_profit_pct",
            "lucro_liquido_esperado_pct",
            "features",
            "confirmacao_multi_timeframe",
            "probabilidade_trade",
            "janela_decisao",
        }
        return cls(
            simbolo=str(dados.get("simbolo", "")),
            acao=str(dados.get("acao", "HOLD")),
            ts=int(dados.get("ts", 0) or 0),
            confianca=float(dados.get("confianca", 0.0) or 0.0),
            stop_loss_pct=float(dados.get("stop_loss_pct", 0.0) or 0.0),
            take_profit_pct=float(dados.get("take_profit_pct", 0.0) or 0.0),
            lucro_liquido_esperado_pct=float(dados.get("lucro_liquido_esperado_pct", 0.0) or 0.0),
            features=dict(dados.get("features") or {}),
            confirmacao_multi_timeframe=dict(dados.get("confirmacao_multi_timeframe") or {}),
            probabilidade_trade=dict(dados.get("probabilidade_trade") or {}),
            janela_decisao=dict(dados.get("janela_decisao") or {}),
            detalhe={chave: valor for chave, valor in dados.items() if chave not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        detalhe = payload.pop("detalhe", {})
        payload.update(detalhe)
        return payload


@dataclass(slots=True)
class RiskApproval:
    usuario_id: int
    usuario_nome: str
    simbolo: str
    acao: str
    aprovado: bool
    paper_trading: bool
    fracao_capital: float
    notional_sugerido: float
    stop_loss_pct: float
    take_profit_pct: float
    lucro_liquido_esperado_pct: float
    lucro_liquido_esperado_usdt: float
    ev_liquido_usdt: float = 0.0
    motivos: list[str] = field(default_factory=list)
    confirmacao_multi_timeframe: dict[str, Any] = field(default_factory=dict)
    probabilidade_trade: dict[str, Any] = field(default_factory=dict)
    janela_decisao: dict[str, Any] = field(default_factory=dict)
    risk_config_aplicado: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "RiskApproval":
        dados = dict(payload)
        return cls(
            usuario_id=int(dados.get("usuario_id", 0) or 0),
            usuario_nome=str(dados.get("usuario_nome", "")),
            simbolo=str(dados.get("simbolo", "")),
            acao=str(dados.get("acao", "HOLD")),
            aprovado=bool(dados.get("aprovado", False)),
            paper_trading=bool(dados.get("paper_trading", False)),
            fracao_capital=float(dados.get("fracao_capital", 0.0) or 0.0),
            notional_sugerido=float(dados.get("notional_sugerido", 0.0) or 0.0),
            stop_loss_pct=float(dados.get("stop_loss_pct", 0.0) or 0.0),
            take_profit_pct=float(dados.get("take_profit_pct", 0.0) or 0.0),
            lucro_liquido_esperado_pct=float(dados.get("lucro_liquido_esperado_pct", 0.0) or 0.0),
            lucro_liquido_esperado_usdt=float(dados.get("lucro_liquido_esperado_usdt", 0.0) or 0.0),
            ev_liquido_usdt=float(dados.get("ev_liquido_usdt", 0.0) or 0.0),
            motivos=list(dados.get("motivos") or []),
            confirmacao_multi_timeframe=dict(dados.get("confirmacao_multi_timeframe") or {}),
            probabilidade_trade=dict(dados.get("probabilidade_trade") or {}),
            janela_decisao=dict(dados.get("janela_decisao") or {}),
            risk_config_aplicado=dict(dados.get("risk_config_aplicado") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutionPlan:
    usuario_id: int
    usuario_nome: str
    simbolo: str
    acao: str
    modo: str
    fracao_capital: float
    notional_sugerido: float
    gatilho_offset_pct: float
    janela_decisao: dict[str, Any] = field(default_factory=dict)
    confirmacao_multi_timeframe: dict[str, Any] = field(default_factory=dict)
    probabilidade_trade: dict[str, Any] = field(default_factory=dict)
    simulacao_ordem: dict[str, Any] = field(default_factory=dict)
    lucro_liquido_esperado_pct: float = 0.0

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "ExecutionPlan":
        dados = dict(payload)
        return cls(
            usuario_id=int(dados.get("usuario_id", 0) or 0),
            usuario_nome=str(dados.get("usuario_nome", "")),
            simbolo=str(dados.get("simbolo", "")),
            acao=str(dados.get("acao", "HOLD")),
            modo=str(dados.get("modo", "paper")),
            fracao_capital=float(dados.get("fracao_capital", 0.0) or 0.0),
            notional_sugerido=float(dados.get("notional_sugerido", 0.0) or 0.0),
            gatilho_offset_pct=float(dados.get("gatilho_offset_pct", 0.0) or 0.0),
            janela_decisao=dict(dados.get("janela_decisao") or {}),
            confirmacao_multi_timeframe=dict(dados.get("confirmacao_multi_timeframe") or {}),
            probabilidade_trade=dict(dados.get("probabilidade_trade") or {}),
            simulacao_ordem=dict(dados.get("simulacao_ordem") or {}),
            lucro_liquido_esperado_pct=float(dados.get("lucro_liquido_esperado_pct", 0.0) or 0.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutionResult:
    ordem_id: int
    status: str
    modo: str
    detalhe: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
