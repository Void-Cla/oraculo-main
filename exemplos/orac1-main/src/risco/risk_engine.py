from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.core.settings import env_float


def config_risco_padrao() -> dict[str, Any]:
    return {
        "risk_per_trade": 0.005,
        "max_drawdown": 0.05,
        "max_drawdown_diario": 0.03,
        "max_daily_loss_usdt": 1.0,
        "max_loss_trade_usdt": 0.20,
        "max_exposicao_ativo": 0.20,
        "max_trades_abertos": 0,
        "max_trades_por_hora": 0,
        "cooldown_minutos": 10,
        "bloquear_flip_flop": True,
        "lucro_liquido_minimo": env_float("LUCRO_LIQUIDO_MINIMO_PCT", env_float("SIGNAL_MIN_NET_PROFIT_PCT", 0.0045), minimo=0.0),
        "lucro_liquido_minimo_usdt": env_float("LUCRO_LIQUIDO_MINIMO_USDT", 0.10, minimo=0.0),
        "paper_trading": True,
    }


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def avaliar_sinal_para_usuario(
    usuario: dict[str, Any],
    sinal: dict[str, Any],
    saldo: dict[str, Any] | None = None,
    estado_execucao: dict[str, Any] | None = None,
) -> dict[str, Any]:
    risk_cfg = config_risco_padrao()
    risk_cfg.update(usuario.get("risk_config", {}))

    if usuario.get("testnet"):
        risk_cfg["lucro_liquido_minimo"] = env_float("LUCRO_MINIMO_TESTNET", 0.0, minimo=0.0)
        risk_cfg["lucro_liquido_minimo_usdt"] = env_float("LUCRO_MINIMO_USDT_TESTNET", 0.0, minimo=0.0)

    saldo = saldo or {}
    estado_execucao = estado_execucao or {}
    acao = str(sinal.get("acao", "HOLD") or "HOLD").upper()
    simbolo = str(sinal.get("simbolo", "") or "")
    papel = bool(risk_cfg.get("paper_trading", True))
    if usuario.get("testnet"):
        papel = False

    if acao not in {"BUY", "SELL", "HOLD"}:
        return {
            "usuario_id": usuario["id"],
            "usuario_nome": usuario["nome"],
            "simbolo": simbolo,
            "acao": "HOLD",
            "aprovado": False,
            "motivos": ["acao_invalida"],
            "fracao_capital": 0.0,
            "notional_sugerido": 0.0,
            "stop_loss_pct": max(float(sinal.get("stop_loss_pct", 0.0) or 0.0), 0.001),
            "take_profit_pct": float(sinal.get("take_profit_pct", 0.0) or 0.0),
            "lucro_liquido_esperado_pct": float(sinal.get("lucro_liquido_esperado_pct", 0.0) or 0.0),
            "lucro_liquido_esperado_usdt": 0.0,
            "confirmacao_multi_timeframe": sinal.get("confirmacao_multi_timeframe", {}),
            "probabilidade_trade": sinal.get("probabilidade_trade", {}),
            "janela_decisao": sinal.get("janela_decisao", {}),
            "paper_trading": papel,
            "risk_config_aplicado": risk_cfg,
        }

    if acao == "HOLD":
        return {
            "usuario_id": usuario["id"],
            "usuario_nome": usuario["nome"],
            "simbolo": simbolo,
            "acao": acao,
            "aprovado": False,
            "motivos": ["sinal_hold"],
            "fracao_capital": 0.0,
            "notional_sugerido": 0.0,
            "stop_loss_pct": max(float(sinal.get("stop_loss_pct", 0.0) or 0.0), 0.001),
            "take_profit_pct": float(sinal.get("take_profit_pct", 0.0) or 0.0),
            "lucro_liquido_esperado_pct": float(sinal.get("lucro_liquido_esperado_pct", 0.0) or 0.0),
            "lucro_liquido_esperado_usdt": 0.0,
            "confirmacao_multi_timeframe": sinal.get("confirmacao_multi_timeframe", {}),
            "probabilidade_trade": sinal.get("probabilidade_trade", {}),
            "janela_decisao": sinal.get("janela_decisao", {}),
            "paper_trading": papel,
            "risk_config_aplicado": risk_cfg,
        }

    saldo_total = float(saldo.get("saldo_total", 0.0) or 0.0)
    saldo_livre = float(saldo.get("saldo_livre", saldo_total) or 0.0)
    drawdown_atual = float(estado_execucao.get("drawdown_atual", 0.0) or 0.0)
    drawdown_diario = float(estado_execucao.get("drawdown_diario", 0.0) or 0.0)
    perda_diaria_usdt = float(estado_execucao.get("perda_diaria_usdt", 0.0) or 0.0)
    exposicao_ativo = float(estado_execucao.get("exposicao_ativo", 0.0) or 0.0)
    trades_abertos = int(estado_execucao.get("trades_abertos", 0) or 0)
    trades_ultima_hora = int(estado_execucao.get("trades_ultima_hora", 0) or 0)
    ultimo_trade_ts = int(estado_execucao.get("ultimo_trade_ts", 0) or 0)
    ultima_acao = str(estado_execucao.get("ultima_acao", "") or "").upper()
    sinal_ts = int(sinal.get("ts", 0) or 0)
    lucro_liquido_esperado = float(sinal.get("lucro_liquido_esperado_pct", 0.0) or 0.0)
    cooldown_minutos = int(risk_cfg.get("cooldown_minutos", 10) or 10)
    cooldown_ms = max(0, cooldown_minutos) * 60 * 1000

    motivos: list[str] = []
    aprovado = True

    if saldo_total <= 0.0 or saldo_livre <= 0.0:
        aprovado = False
        motivos.append("saldo_insuficiente")
    if drawdown_atual >= float(risk_cfg["max_drawdown"]):
        aprovado = False
        motivos.append("drawdown_excedido")
    if drawdown_diario >= float(risk_cfg.get("max_drawdown_diario", 0.03) or 0.03):
        aprovado = False
        motivos.append("drawdown_diario_excedido")
    if perda_diaria_usdt >= float(risk_cfg.get("max_daily_loss_usdt", 1.0) or 1.0):
        aprovado = False
        motivos.append("perda_diaria_usdt_excedida")
    if exposicao_ativo >= float(risk_cfg["max_exposicao_ativo"]):
        aprovado = False
        motivos.append("exposicao_excedida")

    max_trades_abertos = int(risk_cfg["max_trades_abertos"])
    if max_trades_abertos > 0 and trades_abertos >= max_trades_abertos:
        aprovado = False
        motivos.append("limite_trades_abertos")

    max_trades_hora = int(risk_cfg.get("max_trades_por_hora", 3) or 3)
    if max_trades_hora > 0 and trades_ultima_hora >= max_trades_hora:
        aprovado = False
        motivos.append("limite_trades_por_hora")

    if cooldown_ms > 0 and ultimo_trade_ts > 0 and sinal_ts > 0 and (sinal_ts - ultimo_trade_ts) < cooldown_ms:
        aprovado = False
        motivos.append("cooldown_ativo")

    if (
        bool(risk_cfg.get("bloquear_flip_flop", True))
        and ultima_acao in {"BUY", "SELL"}
        and acao in {"BUY", "SELL"}
        and ultima_acao != acao
        and (cooldown_ms == 0 or ultimo_trade_ts <= 0 or sinal_ts <= 0 or (sinal_ts - ultimo_trade_ts) < (cooldown_ms * 2))
    ):
        aprovado = False
        motivos.append("flip_flop_bloqueado")

    if lucro_liquido_esperado < float(risk_cfg.get("lucro_liquido_minimo", 0.002) or 0.002):
        aprovado = False
        motivos.append("lucro_liquido_abaixo_do_minimo")

    stop_loss_pct = max(float(sinal.get("stop_loss_pct", 0.0) or 0.0), 0.001)
    confianca = _clamp(float(sinal.get("confianca", 0.0) or 0.0), 0.0, 0.99)
    capital_risco = min(
        saldo_total * float(risk_cfg["risk_per_trade"]),
        float(risk_cfg.get("max_loss_trade_usdt", 0.20) or 0.20),
    )
    notional_por_stop = capital_risco / stop_loss_pct if stop_loss_pct > 0 else 0.0
    exposicao_restante = max(0.0, float(risk_cfg["max_exposicao_ativo"]) - exposicao_ativo)
    notional_limite = saldo_total * exposicao_restante
    notional_sugerido = min(notional_por_stop, notional_limite, saldo_livre)
    notional_sugerido *= max(0.35, confianca)
    fracao_capital = (notional_sugerido / saldo_total) if saldo_total > 0 else 0.0
    lucro_liquido_esperado_usdt = notional_sugerido * lucro_liquido_esperado

    target_lucro_usdt = env_float("TARGET_LUCRO_LIQ_USDT", 0.0)
    if target_lucro_usdt > 0 and lucro_liquido_esperado > 0:
        max_increase = env_float("TARGET_NOTIONAL_MAX_INCREASE_FACTOR", 2.0, minimo=1.0)
        required_notional = float(Decimal(str(target_lucro_usdt)) / Decimal(str(lucro_liquido_esperado)))
        allowed_max_notional = notional_sugerido * max_increase
        allowed_by_limits = min(notional_limite, saldo_livre)
        if required_notional <= allowed_max_notional and required_notional <= allowed_by_limits:
            notional_sugerido = required_notional
            fracao_capital = (notional_sugerido / saldo_total) if saldo_total > 0 else 0.0
            lucro_liquido_esperado_usdt = notional_sugerido * lucro_liquido_esperado

    if fracao_capital <= 0.0:
        aprovado = False
        if "saldo_insuficiente" not in motivos:
            motivos.append("fracao_calculada_invalida")
    if lucro_liquido_esperado_usdt < float(risk_cfg.get("lucro_liquido_minimo_usdt", 0.05) or 0.05):
        aprovado = False
        motivos.append("lucro_liquido_usdt_abaixo_do_minimo")

    return {
        "usuario_id": usuario["id"],
        "usuario_nome": usuario["nome"],
        "simbolo": simbolo,
        "acao": acao,
        "aprovado": aprovado,
        "motivos": motivos,
        "fracao_capital": _clamp(fracao_capital, 0.0, exposicao_restante if saldo_total > 0 else 0.0),
        "notional_sugerido": max(notional_sugerido, 0.0),
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": float(sinal.get("take_profit_pct", 0.0) or 0.0),
        "lucro_liquido_esperado_pct": lucro_liquido_esperado,
        "lucro_liquido_esperado_usdt": max(lucro_liquido_esperado_usdt, 0.0),
        "confirmacao_multi_timeframe": sinal.get("confirmacao_multi_timeframe", {}),
        "probabilidade_trade": sinal.get("probabilidade_trade", {}),
        "janela_decisao": sinal.get("janela_decisao", {}),
        "paper_trading": papel,
        "risk_config_aplicado": risk_cfg,
    }
