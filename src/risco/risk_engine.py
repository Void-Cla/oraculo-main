from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.risco.filtro_ev import sinal_passa_filtro_ev

# ──────────────────────────────────────────────────────────────
# Defaults hardcoded — sem os.getenv
# Todos os valores ajustáveis dinamicamente via risk_cfg injetado
# ──────────────────────────────────────────────────────────────

def config_risco_padrao() -> dict[str, Any]:
    return {
        "risk_per_trade": 0.005,
        "max_drawdown": 0.05,
        "max_drawdown_diario": 0.03,
        "max_daily_loss_usdt": 1.0,
        "max_loss_trade_usdt": 0.20,
        "max_exposicao_ativo": 0.20,
        "max_trades_abertos": 5,
        "max_trades_por_hora": 40,
        "cooldown_minutos": 1,
        "bloquear_flip_flop": True,
        "lucro_liquido_minimo": 0.0005,
        "lucro_liquido_minimo_usdt": 0.01,
        "filtro_ev_minimo_usdt": 0.01,
        "binance_taxa_maker_pct": 0.1,
        "binance_taxa_taker_pct": 0.1,
        "slippage_pct": 0.0005,
        "paper_trading": True,
    }


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def ev_minimo_liquido_usdt(risk_cfg: dict[str, Any]) -> float:
    # Piso de EV mínimo exigido. Por padrão é rígido em $0.01 (não opera EV abaixo disso).
    # `permitir_ev_negativo` (modo exploração, testnet-only — ver _aplicar_modo_exploracao)
    # libera operar abaixo do piso, aceitando EV negativo. A POLÍTICA (só testnet) é imposta
    # pelo chamador; aqui só respeitamos o flag — mecanismo separado da política.
    if bool(risk_cfg.get("permitir_ev_negativo", False)):
        return float(risk_cfg.get("filtro_ev_minimo_usdt", 0.0) or 0.0)
    configurado = max(0.0, float(risk_cfg.get("filtro_ev_minimo_usdt", 0.01) or 0.0))
    return max(0.01, configurado)


def _probabilidades_por_acao(sinal: dict[str, Any]) -> tuple[float, float]:
    prob = sinal.get("probabilidade_trade") if isinstance(sinal.get("probabilidade_trade"), dict) else {}
    acao = str(sinal.get("acao", "HOLD") or "HOLD").upper()
    prob_up_raw = prob.get("prob_up", sinal.get("prob_up"))
    prob_down_raw = prob.get("prob_down", sinal.get("prob_down"))

    if acao == "SELL":
        sucesso_raw = prob_down_raw if prob_down_raw is not None else None
        falha_raw = prob_up_raw if prob_up_raw is not None else None
    else:
        sucesso_raw = prob_up_raw if prob_up_raw is not None else None
        falha_raw = prob_down_raw if prob_down_raw is not None else None

    if sucesso_raw is None and falha_raw is None:
        raise ValueError("probabilidades_ausentes")
    if sucesso_raw is None:
        falha = _clamp(float(falha_raw), 0.0, 1.0)
        return (1.0 - falha, falha)
    sucesso = _clamp(float(sucesso_raw), 0.0, 1.0)
    if falha_raw is None:
        return (sucesso, 1.0 - sucesso)
    return (sucesso, _clamp(float(falha_raw), 0.0, 1.0))


def _avaliar_ev_liquido_usdt(
    sinal: dict[str, Any],
    notional_sugerido: float,
    risk_cfg: dict[str, Any],
) -> tuple[bool, float, str | None]:
    try:
        prob_sucesso, prob_falha = _probabilidades_por_acao(sinal)
        ganho_bruto = max(0.0, float(notional_sugerido) * float(sinal.get("take_profit_pct", 0.0) or 0.0))
        perda_bruta = max(0.0, float(notional_sugerido) * float(sinal.get("stop_loss_pct", 0.0) or 0.0))
        passou, ev_liquido = sinal_passa_filtro_ev(
            prob_up=prob_sucesso,
            prob_down=prob_falha,
            ganho_bruto_usdt=ganho_bruto,
            perda_bruta_usdt=perda_bruta,
            valor_ordem_usdt=max(0.0, float(notional_sugerido)),
            ev_minimo_usdt=ev_minimo_liquido_usdt(risk_cfg),
            taxa_maker_pct=float(risk_cfg.get("binance_taxa_maker_pct", 0.1) or 0.0),
            taxa_taker_pct=float(risk_cfg.get("binance_taxa_taker_pct", 0.1) or 0.0),
            slippage_pct=float(risk_cfg.get("slippage_pct", 0.0005) or 0.0),
        )
        return passou, ev_liquido, None
    except Exception as exc:
        return False, 0.0, str(exc)


def avaliar_sinal_para_usuario(
    usuario: dict[str, Any],
    sinal: dict[str, Any],
    saldo: dict[str, Any] | None = None,
    estado_execucao: dict[str, Any] | None = None,
) -> dict[str, Any]:
    risk_cfg = config_risco_padrao()
    risk_cfg.update(usuario.get("risk_config", {}))
    risk_cfg["modo_testnet"] = bool(usuario.get("testnet", False))

    saldo = saldo or {}
    estado_execucao = estado_execucao or {}
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
    cooldown_minutos = int(risk_cfg.get("cooldown_minutos", 1) or 1)
    cooldown_ms = max(0, cooldown_minutos) * 60 * 1000

    motivos: list[str] = []
    aprovado = sinal.get("acao") != "HOLD"
    if sinal.get("acao") == "HOLD":
        motivos.append("sinal_hold")

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

    max_trades_hora = int(risk_cfg.get("max_trades_por_hora", 40) or 40)
    if max_trades_hora > 0 and trades_ultima_hora >= max_trades_hora:
        aprovado = False
        motivos.append("limite_trades_por_hora")

    if cooldown_ms > 0 and ultimo_trade_ts > 0 and sinal_ts > 0 and (sinal_ts - ultimo_trade_ts) < cooldown_ms:
        aprovado = False
        motivos.append("cooldown_ativo")

    if (
        bool(risk_cfg.get("bloquear_flip_flop", True))
        and ultima_acao in {"BUY", "SELL"}
        and sinal.get("acao") in {"BUY", "SELL"}
        and ultima_acao != sinal["acao"]
        and ultimo_trade_ts > 0 and sinal_ts > 0
        and (sinal_ts - ultimo_trade_ts) < (cooldown_ms * 2)
    ):
        aprovado = False
        motivos.append("flip_flop_bloqueado")

    lucro_minimo_pct = float(risk_cfg.get("lucro_liquido_minimo", 0.0005) or 0.0)
    if lucro_liquido_esperado < lucro_minimo_pct:
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

    if fracao_capital <= 0.0 and "exposicao_excedida" not in motivos:
        aprovado = False
        motivos.append("fracao_calculada_invalida")

    lucro_minimo_usdt = float(risk_cfg.get("lucro_liquido_minimo_usdt", 0.01) or 0.01)
    if lucro_liquido_esperado_usdt < lucro_minimo_usdt:
        aprovado = False
        motivos.append("lucro_liquido_usdt_abaixo_do_minimo")

    ev_liquido_usdt = 0.0
    if aprovado:
        passou_ev, ev_liquido_usdt, erro_ev = _avaliar_ev_liquido_usdt(sinal, notional_sugerido, risk_cfg)
        if not passou_ev:
            aprovado = False
            if erro_ev:
                motivos.append(f"ev_parametros_invalidos:{erro_ev}")
            else:
                motivos.append(f"ev_insuficiente:{ev_liquido_usdt:.6f}usdt")

    papel = bool(risk_cfg.get("paper_trading", True))
    if usuario.get("testnet"):
        papel = False

    return {
        "usuario_id": usuario["id"],
        "usuario_nome": usuario["nome"],
        "simbolo": sinal["simbolo"],
        "acao": sinal["acao"],
        "aprovado": aprovado,
        "motivos": motivos,
        "fracao_capital": _clamp(fracao_capital, 0.0, exposicao_restante if saldo_total > 0 else 0.0),
        "notional_sugerido": max(notional_sugerido, 0.0),
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": float(sinal.get("take_profit_pct", 0.0) or 0.0),
        "lucro_liquido_esperado_pct": lucro_liquido_esperado,
        "lucro_liquido_esperado_usdt": max(lucro_liquido_esperado_usdt, 0.0),
        "ev_liquido_usdt": ev_liquido_usdt,
        "confirmacao_multi_timeframe": sinal.get("confirmacao_multi_timeframe", {}),
        "probabilidade_trade": sinal.get("probabilidade_trade", {}),
        "janela_decisao": sinal.get("janela_decisao", {}),
        "paper_trading": papel,
        "risk_config_aplicado": risk_cfg,
    }
