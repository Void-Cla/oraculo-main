import asyncio

from src.executor.executor_usuario import ExecutorIsoladoUsuario
from src.risco.risk_engine import avaliar_sinal_para_usuario


def _usuario() -> dict:
    return {
        "id": 1,
        "nome": "trader_risco",
        "testnet": True,
        "risk_config": {
            "risk_per_trade": 0.01,
            "max_drawdown": 0.05,
            "max_drawdown_diario": 0.03,
            "max_exposicao_ativo": 0.20,
            "max_trades_abertos": 3,
            "max_trades_por_hora": 3,
            "cooldown_minutos": 10,
            "bloquear_flip_flop": True,
            "lucro_liquido_minimo": 0.0025,
            "paper_trading": True,
        },
    }


def _sinal_base() -> dict:
    return {
        "simbolo": "BTCUSDT",
        "acao": "BUY",
        "confianca": 0.81,
        "stop_loss_pct": 0.004,
        "take_profit_pct": 0.010,
        "ts": 1_750_000_000_000,
        "lucro_liquido_esperado_pct": 0.0045,
        "confirmacao_multi_timeframe": {"score_buy": 4, "permitir_buy": True, "permitir_sell": False},
        "probabilidade_trade": {"action": "BUY", "prob_up": 0.71, "ev_buy": 0.0021, "ev_sell": -0.0012},
        "janela_decisao": {"janela_minutos": 20, "executar_apos_ts": 1_750_000_600_000},
    }


def test_risk_engine_bloqueia_cooldown_flip_flop_e_limite_horario():
    aprovacao = avaliar_sinal_para_usuario(
        usuario=_usuario(),
        sinal=_sinal_base(),
        saldo={"saldo_total": 1000.0, "saldo_livre": 900.0},
        estado_execucao={
            "drawdown_atual": 0.01,
            "drawdown_diario": 0.01,
            "exposicao_ativo": 0.05,
            "trades_abertos": 1,
            "trades_ultima_hora": 3,
            "ultimo_trade_ts": 1_749_999_700_000,
            "ultima_acao": "SELL",
        },
    )
    assert aprovacao["aprovado"] is False
    assert "limite_trades_por_hora" in aprovacao["motivos"]
    assert "cooldown_ativo" in aprovacao["motivos"]
    assert "flip_flop_bloqueado" in aprovacao["motivos"]


def test_risk_engine_bloqueia_ev_liquido_insuficiente():
    usuario = _usuario()
    usuario["testnet"] = False
    usuario["risk_config"] = {
        **usuario["risk_config"],
        "risk_per_trade": 0.05,
        "max_exposicao_ativo": 1.0,
        "max_loss_trade_usdt": 10.0,
        "lucro_liquido_minimo": 0.0,
        "lucro_liquido_minimo_usdt": 0.0,
        "filtro_ev_minimo_usdt": 1.0,
    }
    sinal = {
        **_sinal_base(),
        "probabilidade_trade": {"action": "BUY", "prob_up": 0.51, "prob_down": 0.49},
        "take_profit_pct": 0.001,
        "stop_loss_pct": 0.001,
        "lucro_liquido_esperado_pct": 0.01,
    }

    aprovacao = avaliar_sinal_para_usuario(
        usuario=usuario,
        sinal=sinal,
        saldo={"saldo_total": 1000.0, "saldo_livre": 1000.0},
        estado_execucao={},
    )

    assert aprovacao["aprovado"] is False
    assert any(motivo.startswith("ev_insuficiente") for motivo in aprovacao["motivos"])


def test_risk_engine_preserva_ev_liquido_quando_aprovado():
    usuario = _usuario()
    usuario["testnet"] = False
    usuario["risk_config"] = {
        **usuario["risk_config"],
        "risk_per_trade": 0.05,
        "max_exposicao_ativo": 1.0,
        "max_loss_trade_usdt": 10.0,
        "lucro_liquido_minimo": 0.0,
        "lucro_liquido_minimo_usdt": 0.0,
        "filtro_ev_minimo_usdt": 1.0,
    }

    aprovacao = avaliar_sinal_para_usuario(
        usuario=usuario,
        sinal=_sinal_base(),
        saldo={"saldo_total": 1000.0, "saldo_livre": 1000.0},
        estado_execucao={},
    )

    assert aprovacao["aprovado"] is True
    assert aprovacao["ev_liquido_usdt"] >= 1.0


def test_risk_engine_testnet_nao_remove_minimo_de_lucro():
    usuario = _usuario()
    usuario["risk_config"] = {
        **usuario["risk_config"],
        "lucro_liquido_minimo": 0.004,
        "lucro_liquido_minimo_usdt": 0.10,
        "filtro_ev_minimo_usdt": 0.0,
    }
    sinal = {**_sinal_base(), "lucro_liquido_esperado_pct": 0.001}

    aprovacao = avaliar_sinal_para_usuario(
        usuario=usuario,
        sinal=sinal,
        saldo={"saldo_total": 1000.0, "saldo_livre": 1000.0},
        estado_execucao={},
    )

    assert aprovacao["aprovado"] is False
    assert "lucro_liquido_abaixo_do_minimo" in aprovacao["motivos"]


def test_executor_planeja_ordem_agendada_com_gatilho():
    usuario = _usuario()
    executor = ExecutorIsoladoUsuario(usuario)
    plano = asyncio.run(
        executor.preparar_execucao(
            {
                "simbolo": "BTCUSDT",
                "acao": "BUY",
                "paper_trading": True,
                "fracao_capital": 0.05,
                "notional_sugerido": 500.0,
                "janela_decisao": {"janela_minutos": 20, "executar_apos_ts": 1_750_000_600_000},
                "confirmacao_multi_timeframe": {"score_buy": 4},
                "probabilidade_trade": {"action": "BUY", "prob_up": 0.71},
                "lucro_liquido_esperado_pct": 0.0045,
            },
            preco_referencia=100_000.0,
        )
    )

    simulacao = plano["simulacao_ordem"]
    assert plano["gatilho_offset_pct"] > 0.0
    assert simulacao["tipo_ordem_planejada"] == "LIMIT_AGENDADA"
    assert simulacao["preco_gatilho"] < 100_000.0
    assert simulacao["executar_apos_ts"] == 1_750_000_600_000
