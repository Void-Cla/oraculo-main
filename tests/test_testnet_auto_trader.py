import pytest

from src.servicos.testnet_auto_trader import (
    TestnetAutoTrader as TraderAutoTestnet,
    _ajustes_microtrading_auto,
    _aplicar_teto_notional,
    _avaliar_saida_ciclo,
    _data_operacional,
    _definir_proxima_acao_esperada,
    _limites_lucro_ciclo,
    _novo_estado,
    _ranquear_simbolos_monitorados,
    _resetar_perda_diaria_se_novo_dia,
    _selecionar_simbolo_foco,
    _usuario_virtual,
)
from src.contratos.trading import SignalDecision
from src.contratos.trading import RiskApproval


class _ClienteContaFalso:
    def __init__(self, *, saldo_usdt=100.0, saldo_base=0.0, saldos=None, trades=None):
        self._saldo_usdt = saldo_usdt
        self._saldo_base = saldo_base
        self._saldos = saldos or {}
        self._trades = trades or []

    async def obter_conta_raw(self):
        if self._saldos:
            return {
                "balances": [
                    {"asset": ativo, "free": str(valor), "locked": "0"}
                    for ativo, valor in self._saldos.items()
                ]
            }
        return {
            "balances": [
                {"asset": "USDT", "free": str(self._saldo_usdt), "locked": "0"},
                {"asset": "BTC", "free": str(self._saldo_base), "locked": "0"},
            ]
        }

    async def obter_trades_conta(self, simbolo="BTCUSDT", limit=200):
        if isinstance(self._trades, dict):
            return list(self._trades.get(simbolo, []))
        return list(self._trades)

    async def obter_ordens_abertas(self, simbolo="BTCUSDT"):
        return []

    async def obter_resumo_conta(self, simbolo_referencia="BTCUSDT", preco_referencia=None):
        preco = float(preco_referencia or 50000.0)
        return {
            "saldo_total_estimado_usdt": self._saldo_usdt + (self._saldo_base * preco),
        }


class _ClienteMercadoFalso:
    def __init__(self, precos=None):
        self._precos = precos or {}

    async def obter_preco_atual(self, simbolo="BTCUSDT"):
        return float(self._precos.get(simbolo, 50000.0))


class _GerenciadorOrdensFalso:
    def __init__(self):
        self.ordens = []

    async def obter_filtros_simbolo(self, simbolo):
        return {"min_notional": 5.0, "min_qty": 0.00001, "step_size": 0.00001}

    def ajustar_quantidade(self, quantidade, step_size, min_qty):
        if quantidade < min_qty:
            return 0.0
        return quantidade

    async def criar_ordem_market(self, simbolo, lado, quantidade=None, quote_order_qty=None):
        ordem = {
            "symbol": simbolo,
            "side": lado,
            "quantity": quantidade,
            "quote_order_qty": quote_order_qty,
            "orderId": len(self.ordens) + 1,
            "status": "FILLED",
        }
        self.ordens.append(ordem)
        return ordem


def test_saida_ciclo_nao_aciona_stop_apenas_por_custos_operacionais():
    state = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 100})
    state.update(
        {
            "ciclo_ativo": True,
            "ciclo_quantidade": 0.01,
            "ciclo_preco_entrada": 10000.0,
            "ciclo_notional_entrada": 100.0,
            "ciclo_iniciado_ts": 1,
            "ciclo_preco_pico": 10000.0,
        }
    )
    sinal = SignalDecision.from_mapping(
        {
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "ts": 2,
            "confianca": 0.7,
            "stop_loss_pct": 0.002,
            "take_profit_pct": 0.01,
            "lucro_liquido_esperado_pct": 0.0,
            "features": {"close": 10000.0, "spread_rel": 0.0},
        }
    )

    resultado = _avaliar_saida_ciclo(
        state=state,
        sinal=sinal,
        ajustes_sinal={"signal_trade_fee_pct": 0.0012, "signal_slippage_pct": 0.0005},
        saldo_base=0.01,
        preco_atual=10000.0,
        perfil={"stop_protecao_pct": 0.002},
    )

    assert resultado["vender"] is False
    assert resultado["motivo"] == "aguardando_lucro_minimo_liquido"


def test_saida_ciclo_corta_perda_por_padrao(monkeypatch):
    # Default seguro (sair antes de prejuízo): sem opt-in, o stop-loss CORTA a perda.
    monkeypatch.delenv("AUTO_SEGURAR_NO_PREJUIZO", raising=False)
    state = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 100})
    state.update(
        {
            "ciclo_ativo": True,
            "ciclo_quantidade": 0.01,
            "ciclo_preco_entrada": 10000.0,
            "ciclo_notional_entrada": 100.0,
            "ciclo_iniciado_ts": 1,
            "ciclo_preco_pico": 10000.0,
        }
    )
    sinal = SignalDecision.from_mapping(
        {
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "ts": 2,
            "confianca": 0.7,
            "stop_loss_pct": 0.002,
            "take_profit_pct": 0.01,
            "lucro_liquido_esperado_pct": 0.0,
            "features": {"close": 9970.0, "spread_rel": 0.0},
        }
    )

    resultado = _avaliar_saida_ciclo(
        state=state,
        sinal=sinal,
        ajustes_sinal={"signal_trade_fee_pct": 0.0012, "signal_slippage_pct": 0.0005},
        saldo_base=0.01,
        preco_atual=9970.0,
        perfil={"stop_protecao_pct": 0.002},
    )

    assert resultado["vender"] is True
    assert resultado["motivo"] == "stop_protecao_acionado"


def test_saida_ciclo_segura_no_prejuizo_apenas_com_opt_in(monkeypatch):
    # Comportamento antigo (segurar perdedor) só com opt-in explícito e desaconselhado.
    monkeypatch.setenv("AUTO_SEGURAR_NO_PREJUIZO", "true")
    state = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 100})
    state.update(
        {
            "ciclo_ativo": True,
            "ciclo_quantidade": 0.01,
            "ciclo_preco_entrada": 10000.0,
            "ciclo_notional_entrada": 100.0,
            "ciclo_iniciado_ts": 1,
            "ciclo_preco_pico": 10000.0,
        }
    )
    sinal = SignalDecision.from_mapping(
        {
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "ts": 2,
            "confianca": 0.7,
            "stop_loss_pct": 0.002,
            "take_profit_pct": 0.01,
            "lucro_liquido_esperado_pct": 0.0,
            "features": {"close": 9970.0, "spread_rel": 0.0},
        }
    )

    resultado = _avaliar_saida_ciclo(
        state=state,
        sinal=sinal,
        ajustes_sinal={"signal_trade_fee_pct": 0.0012, "signal_slippage_pct": 0.0005},
        saldo_base=0.01,
        preco_atual=9970.0,
        perfil={"stop_protecao_pct": 0.002},
    )

    assert resultado["vender"] is False
    assert resultado["motivo"] == "prejuizo_liquido_bloqueado"


def test_estado_limita_notional_operacional(monkeypatch):
    monkeypatch.setenv("AUTO_MAX_NOTIONAL_USDT", "100")
    state = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 70000})

    assert state["notional_usdt"] == 100.0


def test_usuario_virtual_preserva_freios_e_calibra_pisos_testnet():
    usuario = _usuario_virtual(
        {
            "max_trades_abertos": 3,
            "max_trades_por_hora": 30,
            "cooldown_minutos": 1,
            "bloquear_flip_flop": False,
            "max_exposicao_ativo": 1.0,
            "risk_per_trade": 1.0,
            "max_loss_trade_usdt": 1000.0,
            "lucro_liquido_minimo": 0.005,
            "lucro_liquido_minimo_usdt": 1.0,
            "filtro_ev_minimo_usdt": 2.0,
            "paper_trading": True,
        },
        modo_testnet=True,
    )
    risco = usuario["risk_config"]

    assert risco["max_trades_abertos"] == 1
    assert risco["max_trades_por_hora"] == 3
    assert risco["cooldown_minutos"] == 10
    assert risco["bloquear_flip_flop"] is True
    assert risco["max_exposicao_ativo"] == 0.20
    assert risco["risk_per_trade"] == 0.005
    assert risco["max_loss_trade_usdt"] == 0.20
    assert risco["lucro_liquido_minimo"] == pytest.approx(0.0002)
    assert risco["lucro_liquido_minimo_usdt"] == pytest.approx(0.001)
    assert risco["filtro_ev_minimo_usdt"] == pytest.approx(0.001)
    assert risco["modo_testnet"] is True


def test_aplicar_teto_revalida_ev_apos_reducao_de_notional():
    aprovacao = RiskApproval.from_mapping(
        {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "aprovado": True,
            "paper_trading": False,
            "fracao_capital": 0.10,
            "notional_sugerido": 1000.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.01,
            "lucro_liquido_esperado_usdt": 10.0,
            "ev_liquido_usdt": 2.0,
            "risk_config_aplicado": {"filtro_ev_minimo_usdt": 1.0},
        }
    )

    ajustada = _aplicar_teto_notional(aprovacao, limite_usdt=100.0, saldo_total=1000.0)

    assert ajustada.aprovado is False
    assert ajustada.ev_liquido_usdt == pytest.approx(0.2)
    assert any(motivo.startswith("ev_insuficiente_apos_teto") for motivo in ajustada.motivos)


@pytest.mark.asyncio
async def test_fechamento_ciclo_aciona_bloqueio_persistente_por_perda_diaria(monkeypatch):
    trader = TraderAutoTestnet()
    state = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 100, "max_daily_loss_usdt": 1.0})
    state.update(
        {
            "ciclo_ativo": True,
            "ciclo_lucro_liquido_aberto_usdt": -1.25,
            "ciclo_retorno_liquido_aberto_pct": -0.0125,
            "ciclo_notional_entrada": 100.0,
            "ciclo_iniciado_ts": 0,
            "daily_loss_usdt": 0.0,
        }
    )
    gravados = []

    async def _definir(chave, valor):
        gravados.append((chave, valor))

    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioConfig.definir", _definir)

    await trader._registrar_fechamento_ciclo(
        simbolo="BTCUSDT",
        state=state,
        preco_saida_usdt=9900.0,
        motivo="stop_protecao_acionado",
    )

    assert state["circuit_tripped"] is True
    assert state["ultimo_motivo"] == "limite_perda_diaria_atingido"
    assert ("retomada_operacoes_bloqueadas", True) in gravados
    assert ("retomada_modo", "pausado") in gravados


def _monitoramento_multiativo_falso(
    *,
    pares=None,
    melhor=None,
    saldos=None,
    precos_usdt=None,
    taker=0.0009,
):
    pares_lista = list(pares or [])
    return {
        "perfil_taxas": {"taker_decimal_efetiva": taker},
        "saldos_monitorados": saldos or {
            "USDT": {"livre": 100.0, "travado": 0.0, "total": 100.0, "valor_estimado_usdt": 100.0},
            "BTC": {"livre": 0.0, "travado": 0.0, "total": 0.0, "valor_estimado_usdt": 0.0},
        },
        "precos_usdt": precos_usdt or {"USDT": 1.0, "BTC": 50000.0, "ETH": 4000.0, "BNB": 600.0},
        "capital_manager": {"saldo_total_estimado_usdt": 100.0},
        "scanner": {
            "pares": pares_lista,
            "melhor_oportunidade": melhor or (pares_lista[0] if pares_lista else None),
        },
    }


def _monitoramento_multiativo_stub(payload=None):
    async def _stub(**kwargs):
        return payload or _monitoramento_multiativo_falso()

    return _stub


def test_ranqueador_multiativo_prioriza_saida_de_par_promissor():
    estado = _novo_estado({"simbolo": "ETHBTC", "intervalo_segundos": 5, "notional_usdt": 25})
    estado["simbolo_foco"] = "ETHBTC"
    estado["pares_estado"]["BTCUSDT"] = {
        "simbolo": "BTCUSDT",
        "ciclo_ativo": False,
        "estado_ciclo": "EM_POSICAO",
        "proxima_acao_esperada": "SELL",
    }
    estado["pares_estado"]["ETHBTC"] = {
        "simbolo": "ETHBTC",
        "ciclo_ativo": True,
        "estado_ciclo": "STOP_PROTECAO",
        "ultimo_motivo": "notional_abaixo_do_minimo_saida",
        "proxima_acao_esperada": "SELL",
    }

    saldos = {
        "USDT": {"livre": 100.0, "travado": 0.0, "total": 100.0, "valor_estimado_usdt": 100.0},
        "BTC": {"livre": 0.001, "travado": 0.0, "total": 0.001, "valor_estimado_usdt": 50.0},
        "ETH": {"livre": 0.001, "travado": 0.0, "total": 0.001, "valor_estimado_usdt": 4.0},
    }
    scanner = {
        "melhor_oportunidade": {"simbolo": "BTCUSDT", "acao_sugerida": "SELL", "lucro_liquido_esperado_pct": 0.004},
        "pares": [
            {"simbolo": "BTCUSDT", "acao_sugerida": "SELL", "lucro_liquido_esperado_pct": 0.004, "score_oportunidade": 0.62},
            {"simbolo": "ETHBTC", "acao_sugerida": "HOLD", "lucro_liquido_esperado_pct": 0.0, "score_oportunidade": 0.05},
        ],
    }
    sinais = {
        "BTCUSDT": {"simbolo": "BTCUSDT", "acao": "SELL", "lucro_liquido_esperado_pct": 0.004},
        "ETHBTC": {"simbolo": "ETHBTC", "acao": "HOLD", "lucro_liquido_esperado_pct": 0.0},
    }

    ranking = _ranquear_simbolos_monitorados(
        estado,
        scanner=scanner,
        saldos=saldos,
        precos_usdt={"USDT": 1.0, "BTC": 50000.0, "ETH": 4000.0, "BNB": 600.0},
        sinais=sinais,
    )

    assert ranking[0]["simbolo"] == "BTCUSDT"
    assert ranking[0]["acao_prioritaria"] == "SELL"


def test_ranqueador_nao_promove_sell_quando_fluxo_do_par_aguarda_compra():
    estado = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 500})
    estado["pares_estado"]["BTCUSDT"] = {
        "simbolo": "BTCUSDT",
        "ciclo_ativo": False,
        "estado_ciclo": "AGUARDANDO_ENTRADA",
        "ultimo_motivo": "proxima_acao_esperada_e_compra",
        "proxima_acao_esperada": "BUY",
    }
    estado["pares_estado"]["ETHUSDT"] = {
        "simbolo": "ETHUSDT",
        "ciclo_ativo": False,
        "estado_ciclo": "AGUARDANDO_ENTRADA",
        "proxima_acao_esperada": "BUY",
    }

    ranking = _ranquear_simbolos_monitorados(
        estado,
        scanner={
            "melhor_oportunidade": {"simbolo": "ETHUSDT", "acao_sugerida": "BUY", "lucro_liquido_esperado_pct": 0.01},
            "pares": [
                {"simbolo": "BTCUSDT", "acao_sugerida": "SELL", "lucro_liquido_esperado_pct": 0.004, "score_oportunidade": 0.55},
                {"simbolo": "ETHUSDT", "acao_sugerida": "BUY", "lucro_liquido_esperado_pct": 0.01, "score_oportunidade": 0.65},
            ],
        },
        saldos={
            "USDT": {"livre": 500.0, "travado": 0.0, "total": 500.0, "valor_estimado_usdt": 500.0},
            "BTC": {"livre": 0.001, "travado": 0.0, "total": 0.001, "valor_estimado_usdt": 68.0},
            "ETH": {"livre": 0.0, "travado": 0.0, "total": 0.0, "valor_estimado_usdt": 0.0},
        },
        precos_usdt={"USDT": 1.0, "BTC": 68000.0, "ETH": 3400.0, "BNB": 600.0},
        sinais={
            "BTCUSDT": {"simbolo": "BTCUSDT", "acao": "SELL", "lucro_liquido_esperado_pct": 0.004},
            "ETHUSDT": {"simbolo": "ETHUSDT", "acao": "BUY", "lucro_liquido_esperado_pct": 0.01},
        },
    )

    assert ranking[0]["simbolo"] == "ETHUSDT"
    assert next(item for item in ranking if item["simbolo"] == "BTCUSDT")["acao_prioritaria"] == "HOLD"
    assert _selecionar_simbolo_foco(estado, ranking) == "ETHUSDT"


def test_proxima_acao_esperada_ignora_residuo_abaixo_de_cinco_usdt():
    contexto = _definir_proxima_acao_esperada(
        extrato={"ultima_acao": "SELL"},
        saldo_base=0.001,
        preco_atual_usdt=2.07017,
        min_notional_operacional_usdt=6.9,
        min_qty=0.00001,
    )

    assert contexto["acao"] == "BUY"
    assert contexto["motivo"] == "ultima_venda_encerrada_sem_posicao_aberta"
    assert contexto["tem_posicao_operacional"] is False


@pytest.mark.asyncio
async def test_auto_trader_respeita_hold_sem_executar(monkeypatch):
    trader = TraderAutoTestnet()
    token = "hold"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 10.4, "ask_price": 10.6, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.montar_monitoramento_multiativo", _monitoramento_multiativo_stub())
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "ts": 1,
            "confianca": 0.8,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.01,
            "features": {"close": 50000.0},
            "motivo": "modelo_em_hold",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "aprovado": False,
            "motivos": ["sinal_hold"],
            "fracao_capital": 0.0,
            "notional_sugerido": 0.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.01,
            "lucro_liquido_esperado_usdt": 0.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorOrdensFalso()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(),
        cliente_mercado=_ClienteMercadoFalso(),
        ger=ger,
    )

    assert ger.ordens == []
    assert trader._state[token]["ultimo_sinal"] == "HOLD"
    assert trader._state[token]["ultima_acao"] == "HOLD"


@pytest.mark.asyncio
async def test_auto_trader_troca_foco_para_par_mais_promissor(monkeypatch):
    trader = TraderAutoTestnet()
    token = "foco_multiativo"
    trader._state[token] = _novo_estado({"simbolo": "ETHBTC", "intervalo_segundos": 5, "notional_usdt": 25})
    trader._state[token]["pares_estado"]["ETHBTC"] = {
        "simbolo": "ETHBTC",
        "ciclo_ativo": True,
        "estado_ciclo": "STOP_PROTECAO",
        "ultimo_motivo": "notional_abaixo_do_minimo_saida",
        "proxima_acao_esperada": "SELL",
    }

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 10.4, "ask_price": 10.6, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _preparar_execucao(self, aprovacao_risco, preco_referencia):
        return {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "modo": "testnet",
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "gatilho_offset_pct": 0.0,
            "janela_decisao": {},
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "lucro_liquido_esperado_pct": 0.02,
            "simulacao_ordem": {
                "quantidade": 0.0004,
                "preco_referencia": 50000.0,
                "notional_estimado": 20.0,
            },
        }

    monitoramento = _monitoramento_multiativo_falso(
        pares=[
            {"simbolo": "BTCUSDT", "acao_sugerida": "BUY", "lucro_liquido_esperado_pct": 0.25, "score_oportunidade": 0.60},
            {"simbolo": "ETHBTC", "acao_sugerida": "HOLD", "lucro_liquido_esperado_pct": 0.0, "score_oportunidade": 0.01},
        ],
        melhor={"simbolo": "BTCUSDT", "acao_sugerida": "BUY", "lucro_liquido_esperado_pct": 0.25, "score_oportunidade": 0.60},
    )
    monitoramento["sinais"] = {
        "BTCUSDT": {
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "ts": 1,
            "confianca": 0.92,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.02,
            "features": {"close": 50000.0},
            "motivo": "scanner_confirmou_buy",
        },
        "ETHBTC": {
            "simbolo": "ETHBTC",
            "acao": "HOLD",
            "ts": 1,
            "confianca": 0.5,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.0,
            "features": {"close": 0.08},
            "motivo": "travado_no_notional",
        },
    }

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.montar_monitoramento_multiativo",
        _monitoramento_multiativo_stub(monitoramento),
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "aprovado": True,
            "motivos": [],
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.02,
            "lucro_liquido_esperado_usdt": 0.4,
            "ev_liquido_usdt": 20.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ExecutorIsoladoUsuario.preparar_execucao", _preparar_execucao)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorOrdensFalso()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=100.0, saldo_base=0.0),
        cliente_mercado=_ClienteMercadoFalso(precos={"BTCUSDT": 50000.0, "ETHBTC": 0.08}),
        ger=ger,
    )

    assert len(ger.ordens) == 1
    assert ger.ordens[0]["symbol"] == "BTCUSDT"
    assert trader._state[token]["simbolo_foco"] == "BTCUSDT"
    assert trader._state[token]["simbolo"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_auto_trader_nao_prende_foco_em_par_cruzado_com_residual_abaixo_do_minimo(monkeypatch):
    trader = TraderAutoTestnet()
    token = "foco_residual_cruzado"
    trader._state[token] = _novo_estado({"simbolo": "ETHBTC", "intervalo_segundos": 5, "notional_usdt": 500})
    trader._state[token]["pares_estado"]["ETHBTC"] = {
        "simbolo": "ETHBTC",
        "ciclo_ativo": True,
        "estado_ciclo": "STOP_PROTECAO",
        "ultimo_motivo": "notional_abaixo_do_minimo_saida",
        "proxima_acao_esperada": "SELL",
    }

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 10.4, "ask_price": 10.6, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _preparar_execucao(self, aprovacao_risco, preco_referencia):
        return {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "modo": "testnet",
            "fracao_capital": 0.02,
            "notional_sugerido": 150.0,
            "gatilho_offset_pct": 0.0,
            "janela_decisao": {},
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "lucro_liquido_esperado_pct": 0.01,
            "simulacao_ordem": {
                "quantidade": 0.0021,
                "preco_referencia": 69000.0,
                "notional_estimado": 150.0,
            },
        }

    monitoramento = _monitoramento_multiativo_falso(
        pares=[
            {"simbolo": "BTCUSDT", "acao_sugerida": "BUY", "lucro_liquido_esperado_pct": 0.008, "score_oportunidade": 0.78},
            {"simbolo": "ETHBTC", "acao_sugerida": "SELL", "lucro_liquido_esperado_pct": 0.001, "score_oportunidade": 0.22},
        ],
        melhor={"simbolo": "BTCUSDT", "acao_sugerida": "BUY", "lucro_liquido_esperado_pct": 0.008, "score_oportunidade": 0.78},
        saldos={
            "USDT": {"livre": 500.0, "travado": 0.0, "total": 500.0, "valor_estimado_usdt": 500.0},
            "BTC": {"livre": 0.0, "travado": 0.0, "total": 0.0, "valor_estimado_usdt": 0.0},
            "ETH": {"livre": 0.001, "travado": 0.0, "total": 0.001, "valor_estimado_usdt": 2.07},
        },
        precos_usdt={"USDT": 1.0, "BTC": 69000.0, "ETH": 2070.0, "BNB": 600.0},
    )
    monitoramento["capital_manager"] = {"saldo_total_estimado_usdt": 502.07}
    monitoramento["sinais"] = {
        "BTCUSDT": {
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "ts": 1,
            "confianca": 0.91,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.008,
            "features": {"close": 69000.0},
            "motivo": "oportunidade_limpa",
        },
        "ETHBTC": {
            "simbolo": "ETHBTC",
            "acao": "SELL",
            "ts": 1,
            "confianca": 0.60,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.001,
            "features": {"close": 0.03},
            "motivo": "residual_sem_notional_operacional",
        },
    }

    class _GerenciadorComFiltrosPorSimbolo(_GerenciadorOrdensFalso):
        async def obter_filtros_simbolo(self, simbolo):
            if simbolo == "ETHBTC":
                return {"min_notional": 0.0001, "min_qty": 0.0001, "step_size": 0.0001}
            return {"min_notional": 5.0, "min_qty": 0.00001, "step_size": 0.00001}

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.montar_monitoramento_multiativo",
        _monitoramento_multiativo_stub(monitoramento),
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "aprovado": True,
            "motivos": [],
            "fracao_capital": 0.30,
            "notional_sugerido": 150.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.008,
            "lucro_liquido_esperado_usdt": 1.2,
            "ev_liquido_usdt": 20.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ExecutorIsoladoUsuario.preparar_execucao", _preparar_execucao)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorComFiltrosPorSimbolo()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldos={"USDT": 500.0, "ETH": 0.001, "BTC": 0.0}),
        cliente_mercado=_ClienteMercadoFalso(precos={"BTCUSDT": 69000.0, "ETHBTC": 0.03}),
        ger=ger,
    )

    assert len(ger.ordens) == 1
    assert ger.ordens[0]["symbol"] == "BTCUSDT"
    assert trader._state[token]["simbolo_foco"] == "BTCUSDT"
    assert trader._state[token]["pares_ranqueados"][0]["simbolo"] == "BTCUSDT"
    assert trader._state[token]["ultima_acao"] == "BUY"


@pytest.mark.asyncio
async def test_auto_trader_pula_sell_incompativel_com_fluxo_e_compra_par_viavel(monkeypatch):
    trader = TraderAutoTestnet()
    token = "pula_sell_incompativel"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 500})
    trader._state[token]["pares_estado"]["BTCUSDT"] = {
        "simbolo": "BTCUSDT",
        "ciclo_ativo": False,
        "estado_ciclo": "AGUARDANDO_ENTRADA",
        "ultimo_motivo": "proxima_acao_esperada_e_compra",
        "proxima_acao_esperada": "BUY",
    }
    trader._state[token]["pares_estado"]["ETHUSDT"] = {
        "simbolo": "ETHUSDT",
        "ciclo_ativo": False,
        "estado_ciclo": "AGUARDANDO_ENTRADA",
        "proxima_acao_esperada": "BUY",
    }

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 10.4, "ask_price": 10.6, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _preparar_execucao(self, aprovacao_risco, preco_referencia):
        return {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "ETHUSDT",
            "acao": "BUY",
            "modo": "testnet",
            "fracao_capital": 0.02,
            "notional_sugerido": 200.0,
            "gatilho_offset_pct": 0.0,
            "janela_decisao": {},
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "lucro_liquido_esperado_pct": 0.01,
            "simulacao_ordem": {
                "quantidade": 0.06,
                "preco_referencia": 3400.0,
                "notional_estimado": 200.0,
            },
        }

    monitoramento = _monitoramento_multiativo_falso(
        pares=[
            {"simbolo": "BTCUSDT", "acao_sugerida": "SELL", "lucro_liquido_esperado_pct": 0.004, "score_oportunidade": 0.72},
            {"simbolo": "ETHUSDT", "acao_sugerida": "BUY", "lucro_liquido_esperado_pct": 0.01, "score_oportunidade": 0.85},
        ],
        melhor={"simbolo": "ETHUSDT", "acao_sugerida": "BUY", "lucro_liquido_esperado_pct": 0.01, "score_oportunidade": 0.85},
        saldos={
            "USDT": {"livre": 500.0, "travado": 0.0, "total": 500.0, "valor_estimado_usdt": 500.0},
            "BTC": {"livre": 0.001, "travado": 0.0, "total": 0.001, "valor_estimado_usdt": 68.0},
            "ETH": {"livre": 0.0, "travado": 0.0, "total": 0.0, "valor_estimado_usdt": 0.0},
        },
        precos_usdt={"USDT": 1.0, "BTC": 68000.0, "ETH": 3400.0, "BNB": 600.0},
    )
    monitoramento["capital_manager"] = {"saldo_total_estimado_usdt": 568.0}
    monitoramento["sinais"] = {
        "BTCUSDT": {
            "simbolo": "BTCUSDT",
            "acao": "SELL",
            "ts": 1,
            "confianca": 0.88,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.004,
            "features": {"close": 68000.0},
            "motivo": "sell_incompativel_com_fluxo",
        },
        "ETHUSDT": {
            "simbolo": "ETHUSDT",
            "acao": "BUY",
            "ts": 1,
            "confianca": 0.93,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.01,
            "features": {"close": 3400.0},
            "motivo": "mini_oportunidade_viavel",
        },
    }

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.montar_monitoramento_multiativo",
        _monitoramento_multiativo_stub(monitoramento),
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "ETHUSDT",
            "acao": "BUY",
            "aprovado": True,
            "motivos": [],
            "fracao_capital": 0.40,
            "notional_sugerido": 200.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.01,
            "lucro_liquido_esperado_usdt": 2.0,
            "ev_liquido_usdt": 20.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ExecutorIsoladoUsuario.preparar_execucao", _preparar_execucao)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorOrdensFalso()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldos={"USDT": 500.0, "BTC": 0.001, "ETH": 0.0}),
        cliente_mercado=_ClienteMercadoFalso(precos={"BTCUSDT": 68000.0, "ETHUSDT": 3400.0}),
        ger=ger,
    )

    assert len(ger.ordens) == 1
    assert ger.ordens[0]["symbol"] == "ETHUSDT"
    assert trader._state[token]["simbolo_foco"] == "ETHUSDT"
    assert trader._state[token]["ultimo_motivo"] == "mini_oportunidade_viavel"


@pytest.mark.asyncio
async def test_auto_trader_compra_so_quando_pipeline_aprova(monkeypatch):
    trader = TraderAutoTestnet()
    token = "buy"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 10.4, "ask_price": 10.6, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _preparar_execucao(self, aprovacao_risco, preco_referencia):
        return {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "modo": "testnet",
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "gatilho_offset_pct": 0.0,
            "janela_decisao": {},
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "lucro_liquido_esperado_pct": 0.02,
            "simulacao_ordem": {
                "quantidade": 0.0004,
                "preco_referencia": 50000.0,
                "notional_estimado": 20.0,
            },
        }

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.montar_monitoramento_multiativo", _monitoramento_multiativo_stub())
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "ts": 1,
            "confianca": 0.92,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.02,
            "features": {"close": 50000.0},
            "motivo": "compra_orquestrada",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "aprovado": True,
            "motivos": [],
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.02,
            "lucro_liquido_esperado_usdt": 0.4,
            "ev_liquido_usdt": 20.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ExecutorIsoladoUsuario.preparar_execucao", _preparar_execucao)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    class _GerenciadorOrdensParCruzado(_GerenciadorOrdensFalso):
        async def obter_filtros_simbolo(self, simbolo):
            return {"min_notional": 0.00001, "min_qty": 0.00001, "step_size": 0.00001}

    ger = _GerenciadorOrdensParCruzado()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=100.0, saldo_base=0.0),
        cliente_mercado=_ClienteMercadoFalso(),
        ger=ger,
    )

    assert len(ger.ordens) == 1
    assert ger.ordens[0]["side"] == "BUY"
    assert ger.ordens[0]["quote_order_qty"] == 12.5
    assert trader._state[token]["ultima_acao"] == "BUY"
    assert trader._state[token]["perfil_ciclo_id"] == "mini"


@pytest.mark.asyncio
async def test_auto_trader_nao_alterna_para_sell_sem_sinal(monkeypatch):
    trader = TraderAutoTestnet()
    token = "sequencia"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 10.4, "ask_price": 10.6, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _preparar_execucao(self, aprovacao_risco, preco_referencia):
        return {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "modo": "testnet",
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "gatilho_offset_pct": 0.0,
            "janela_decisao": {},
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "lucro_liquido_esperado_pct": 0.02,
            "simulacao_ordem": {
                "quantidade": 0.0004,
                "preco_referencia": 50000.0,
                "notional_estimado": 20.0,
            },
        }

    sinais = [
        {
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "ts": 1,
            "confianca": 0.9,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.02,
            "features": {"close": 50000.0},
            "motivo": "compra_valida",
        },
        {
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "ts": 2,
            "confianca": 0.8,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.0,
            "features": {"close": 50500.0},
            "motivo": "segurar_posicao",
        },
    ]
    aprovacoes = [
        {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "aprovado": True,
            "motivos": [],
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.02,
            "lucro_liquido_esperado_usdt": 0.4,
            "ev_liquido_usdt": 20.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
        {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "aprovado": False,
            "motivos": ["sinal_hold"],
            "fracao_capital": 0.0,
            "notional_sugerido": 0.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.0,
            "lucro_liquido_esperado_usdt": 0.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    ]

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.montar_monitoramento_multiativo", _monitoramento_multiativo_stub())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.gerar_sinal_orquestrado", lambda **kwargs: sinais.pop(0))
    monkeypatch.setattr("src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario", lambda **kwargs: aprovacoes.pop(0))
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ExecutorIsoladoUsuario.preparar_execucao", _preparar_execucao)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorOrdensFalso()
    cliente_conta = _ClienteContaFalso(saldo_usdt=100.0, saldo_base=0.0)
    cliente_mercado = _ClienteMercadoFalso()

    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=cliente_conta,
        cliente_mercado=cliente_mercado,
        ger=ger,
    )
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=cliente_conta,
        cliente_mercado=cliente_mercado,
        ger=ger,
    )

    assert len(ger.ordens) == 1
    assert [item["side"] for item in ger.ordens] == ["BUY"]
    assert trader._state[token]["ultimo_sinal"] == "HOLD"
    assert trader._state[token]["ultima_acao"] == "HOLD"


@pytest.mark.asyncio
async def test_auto_trader_nao_abre_nova_compra_com_ciclo_ativo(monkeypatch):
    trader = TraderAutoTestnet()
    token = "ciclo_unico"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})
    trader._state[token].update(
        {
            "sequencia_ciclo": 1,
            "ciclo_id": 1,
            "ciclo_ativo": True,
            "estado_ciclo": "EM_POSICAO",
            "ciclo_origem": "auto",
            "ciclo_iniciado_ts": 1,
            "ciclo_quantidade": 0.0004,
            "ciclo_preco_entrada": 50000.0,
            "ciclo_notional_entrada": 20.0,
        }
    )

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 10.4, "ask_price": 10.6, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _preparar_execucao(self, aprovacao_risco, preco_referencia):
        return {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "modo": "testnet",
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "gatilho_offset_pct": 0.0,
            "janela_decisao": {},
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "lucro_liquido_esperado_pct": 0.02,
            "simulacao_ordem": {
                "quantidade": 0.0004,
                "preco_referencia": 50000.0,
                "notional_estimado": 20.0,
            },
        }

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.montar_monitoramento_multiativo", _monitoramento_multiativo_stub())
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "ts": 1,
            "confianca": 0.92,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.02,
            "features": {"close": 50000.0},
            "motivo": "compra_forte",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "aprovado": True,
            "motivos": [],
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.02,
            "lucro_liquido_esperado_usdt": 0.4,
            "ev_liquido_usdt": 20.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ExecutorIsoladoUsuario.preparar_execucao", _preparar_execucao)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    class _GerenciadorOrdensParCruzado(_GerenciadorOrdensFalso):
        async def obter_filtros_simbolo(self, simbolo):
            return {"min_notional": 0.00001, "min_qty": 0.00001, "step_size": 0.00001}

    ger = _GerenciadorOrdensParCruzado()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=50.0, saldo_base=0.001),
        cliente_mercado=_ClienteMercadoFalso(),
        ger=ger,
    )

    assert ger.ordens == []
    assert trader._state[token]["ciclo_ativo"] is True
    assert trader._state[token]["ultima_acao"] == "HOLD"
    assert trader._state[token]["ultimo_motivo"] == "aguardando_lucro_minimo_liquido"


@pytest.mark.asyncio
async def test_auto_trader_reconcilia_saldo_legado_antes_de_abrir_nova_compra(monkeypatch):
    trader = TraderAutoTestnet()
    token = "saldo_legado"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 20})

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 10.4, "ask_price": 10.6, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _preparar_execucao(self, aprovacao_risco, preco_referencia):
        return {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "modo": "testnet",
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "gatilho_offset_pct": 0.0,
            "janela_decisao": {},
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "lucro_liquido_esperado_pct": 0.02,
            "simulacao_ordem": {
                "quantidade": 0.0004,
                "preco_referencia": 50000.0,
                "notional_estimado": 20.0,
            },
        }

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.montar_monitoramento_multiativo", _monitoramento_multiativo_stub())
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "ts": 1,
            "confianca": 0.92,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.02,
            "features": {"close": 50000.0},
            "motivo": "entrada_micro_trader",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "aprovado": True,
            "motivos": [],
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.02,
            "lucro_liquido_esperado_usdt": 0.4,
            "ev_liquido_usdt": 20.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ExecutorIsoladoUsuario.preparar_execucao", _preparar_execucao)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorOrdensFalso()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=100.0, saldo_base=1.0),
        cliente_mercado=_ClienteMercadoFalso(),
        ger=ger,
    )

    assert ger.ordens == []
    assert trader._state[token]["ciclo_ativo"] is True
    assert trader._state[token]["ciclo_origem"] == "carteira"
    assert trader._state[token]["ciclo_quantidade"] == pytest.approx(1.0)
    assert trader._state[token]["proxima_acao_esperada"] == "SELL"
    assert trader._state[token]["perfil_ciclo_id"] == "mini"


@pytest.mark.asyncio
async def test_auto_trader_libera_saida_de_ciclo_mesmo_com_risco_bloqueando(monkeypatch):
    trader = TraderAutoTestnet()
    token = "saida_forcada"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})
    trader._state[token].update(
        {
            "sequencia_ciclo": 1,
            "ciclo_id": 1,
            "ciclo_ativo": True,
            "estado_ciclo": "EM_POSICAO",
            "ciclo_origem": "auto",
            "ciclo_iniciado_ts": 1,
            "ciclo_quantidade": 0.001,
            "ciclo_preco_entrada": 50000.0,
            "ciclo_notional_entrada": 50.0,
        }
    )

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 10.4, "ask_price": 10.6, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _preparar_execucao(self, aprovacao_risco, preco_referencia):
        return {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "SELL",
            "modo": "testnet",
            "fracao_capital": 0.02,
            "notional_sugerido": 50.0,
            "gatilho_offset_pct": 0.0,
            "janela_decisao": {},
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "lucro_liquido_esperado_pct": 0.03,
            "simulacao_ordem": {
                "quantidade": 0.001,
                "preco_referencia": 50000.0,
                "notional_estimado": 50.0,
            },
        }

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.montar_monitoramento_multiativo", _monitoramento_multiativo_stub())
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "SELL",
            "ts": 1,
            "confianca": 0.95,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.03,
            "features": {"close": 50500.0, "spread_rel": 0.0},
            "motivo": "saida_otimizada",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "SELL",
            "aprovado": False,
            "motivos": ["cooldown_ativo", "flip_flop_bloqueado"],
            "fracao_capital": 0.0,
            "notional_sugerido": 0.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.03,
            "lucro_liquido_esperado_usdt": 0.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ExecutorIsoladoUsuario.preparar_execucao", _preparar_execucao)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorOrdensFalso()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=0.0, saldo_base=0.001),
        cliente_mercado=_ClienteMercadoFalso(precos={"BTCUSDT": 50500.0}),
        ger=ger,
    )

    assert len(ger.ordens) == 1
    assert ger.ordens[0]["side"] == "SELL"
    assert trader._state[token]["ciclo_ativo"] is False
    assert trader._state[token]["ultima_acao"] == "SELL"


@pytest.mark.asyncio
async def test_auto_trader_bloqueia_sell_de_ciclo_sem_lucro_liquido(monkeypatch):
    trader = TraderAutoTestnet()
    token = "sell_sem_lucro"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})
    trader._state[token].update(
        {
            "sequencia_ciclo": 1,
            "ciclo_id": 1,
            "ciclo_ativo": True,
            "estado_ciclo": "EM_POSICAO",
            "ciclo_origem": "auto",
            "ciclo_iniciado_ts": 1,
            "ciclo_quantidade": 0.001,
            "ciclo_preco_entrada": 50000.0,
            "ciclo_notional_entrada": 50.0,
        }
    )

    async def _noop(*args, **kwargs):
        return None

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 49950, "high": 50000, "low": 49800, "close": 49900, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 49899.0, "ask_price": 49901.0, "bid_qty": 1.0, "ask_qty": 1.0}

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.montar_monitoramento_multiativo", _monitoramento_multiativo_stub())
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "SELL",
            "ts": 1,
            "confianca": 0.95,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.03,
            "features": {"close": 49900.0, "spread_rel": 0.0},
            "motivo": "saida_sugerida_sem_lucro_real",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "SELL",
            "aprovado": True,
            "motivos": [],
            "fracao_capital": 0.02,
            "notional_sugerido": 50.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.03,
            "lucro_liquido_esperado_usdt": 1.5,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorOrdensFalso()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=0.0, saldo_base=0.001),
        cliente_mercado=_ClienteMercadoFalso(precos={"BTCUSDT": 49900.0}),
        ger=ger,
    )

    assert ger.ordens == []
    assert trader._state[token]["ciclo_ativo"] is True
    assert trader._state[token]["ultima_acao"] == "HOLD"
    assert trader._state[token]["ultimo_motivo"] == "aguardando_lucro_minimo_liquido"


@pytest.mark.asyncio
async def test_auto_trader_realiza_lucro_minimo_liquido_com_hold(monkeypatch):
    trader = TraderAutoTestnet()
    token = "realiza_micro_lucro"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})
    trader._state[token].update(
        {
            "sequencia_ciclo": 1,
            "ciclo_id": 1,
            "ciclo_ativo": True,
            "estado_ciclo": "EM_POSICAO",
            "ciclo_origem": "auto",
            "ciclo_iniciado_ts": 1,
            "ciclo_quantidade": 0.001,
            "ciclo_preco_entrada": 50000.0,
            "ciclo_notional_entrada": 50.0,
        }
    )

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 10.4, "ask_price": 10.6, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _preparar_execucao(self, aprovacao_risco, preco_referencia):
        return {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "SELL",
            "modo": "testnet",
            "fracao_capital": 0.02,
            "notional_sugerido": 50.5,
            "gatilho_offset_pct": 0.0,
            "janela_decisao": {},
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "lucro_liquido_esperado_pct": -0.0026,
            "simulacao_ordem": {
                "quantidade": 0.001,
                "preco_referencia": 50500.0,
                "notional_estimado": 50.5,
            },
        }

    class _MercadoComLucro:
        async def obter_preco_atual(self, simbolo="BTCUSDT"):
            return 50500.0

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.montar_monitoramento_multiativo", _monitoramento_multiativo_stub())
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "ts": 1,
            "confianca": 0.8,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": -0.0026,
            "features": {"close": 50500.0, "spread_rel": 0.0},
            "motivo": "segurar_nao_compensa",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "aprovado": False,
            "motivos": ["sinal_hold"],
            "fracao_capital": 0.0,
            "notional_sugerido": 0.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": -0.0026,
            "lucro_liquido_esperado_usdt": 0.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ExecutorIsoladoUsuario.preparar_execucao", _preparar_execucao)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorOrdensFalso()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=0.0, saldo_base=0.001),
        cliente_mercado=_MercadoComLucro(),
        ger=ger,
    )

    assert len(ger.ordens) == 1
    assert ger.ordens[0]["side"] == "SELL"
    assert trader._state[token]["ultima_acao"] == "SELL"
    assert trader._state[token]["ultimo_motivo"] == "lucro_minimo_liquido_atingido"


def test_limite_minimo_liquido_do_ciclo_aceita_um_centavo():
    limites = _limites_lucro_ciclo(
        notional_entrada=5.0,
        ajustes_sinal={"signal_min_net_profit_pct": 0.002},
    )

    assert round(limites["minimo_usdt"], 2) == 0.01
    assert round(limites["minimo_pct"], 4) == 0.002


def test_ajustes_microtrading_auto_calibram_lucro_e_filtros_por_capital():
    ajustes = _ajustes_microtrading_auto(
        {
            "signal_min_net_profit_pct": 0.002,
            "signal_confirm_threshold": 3,
            "signal_decision_window_minutes": 20,
            "limiar_score_operacao": 0.18,
            "limiar_variacao_numerica": 0.0015,
            "signal_min_ev": 0.0008,
            "signal_min_prob": 0.58,
        },
        notional_usdt=25.0,
        lucro_liquido_minimo_usdt=0.01,
    )

    assert ajustes["auto_lucro_liquido_minimo_usdt"] == pytest.approx(0.01)
    assert ajustes["signal_min_net_profit_pct"] == pytest.approx(0.0004)
    assert ajustes["signal_confirm_threshold"] == 3
    assert ajustes["signal_decision_window_minutes"] == 20
    assert ajustes["limiar_score_operacao"] == pytest.approx(0.18)
    assert ajustes["limiar_variacao_numerica"] == pytest.approx(0.0018)
    assert ajustes["signal_min_ev"] == pytest.approx(0.0008)
    assert ajustes["signal_min_prob"] == pytest.approx(0.58)


def test_ajustes_microtrading_auto_capa_overrides_altos_no_testnet():
    ajustes = _ajustes_microtrading_auto(
        {
            "signal_min_net_profit_pct": 0.006,
            "signal_confirm_threshold": 3,
            "signal_decision_window_minutes": 20,
            "limiar_score_operacao": 0.45,
            "limiar_variacao_numerica": 0.003,
            "signal_min_ev": 0.004,
            "signal_min_prob": 0.68,
        },
        notional_usdt=100.0,
        lucro_liquido_minimo_usdt=1.0,
        modo_testnet=True,
    )

    assert ajustes["auto_lucro_liquido_minimo_usdt"] == pytest.approx(0.001)
    assert ajustes["signal_min_net_profit_pct"] == pytest.approx(0.0004)
    assert ajustes["signal_min_ev"] == pytest.approx(0.0008)
    assert ajustes["signal_min_prob"] == pytest.approx(0.62)


@pytest.mark.asyncio
async def test_auto_trader_compra_par_cruzado_com_saldo_da_moeda_de_cotacao(monkeypatch):
    trader = TraderAutoTestnet()
    token = "ethbtc"
    trader._state[token] = _novo_estado({"simbolo": "ETHBTC", "intervalo_segundos": 5, "notional_usdt": 10})

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 0.08, "high": 0.081, "low": 0.079, "close": 0.08, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 0.0799, "ask_price": 0.0801, "bid_qty": 2.0, "ask_qty": 2.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _preparar_execucao(self, aprovacao_risco, preco_referencia):
        return {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "ETHBTC",
            "acao": "BUY",
            "modo": "testnet",
            "fracao_capital": 0.02,
            "notional_sugerido": 10.0,
            "gatilho_offset_pct": 0.0,
            "janela_decisao": {},
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "lucro_liquido_esperado_pct": 0.02,
            "simulacao_ordem": {
                "quantidade": 0.0025,
                "preco_referencia": 0.08,
                "notional_estimado": 0.0002,
            },
        }

    saldos = {
        "BTC": {"livre": 0.001, "travado": 0.0, "total": 0.001, "valor_estimado_usdt": 50.0},
        "ETH": {"livre": 0.0, "travado": 0.0, "total": 0.0, "valor_estimado_usdt": 0.0},
        "USDT": {"livre": 0.0, "travado": 0.0, "total": 0.0, "valor_estimado_usdt": 0.0},
    }

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="ETHUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.montar_monitoramento_multiativo",
        _monitoramento_multiativo_stub(
            _monitoramento_multiativo_falso(
                pares=[{"simbolo": "ETHBTC", "acao_sugerida": "BUY", "lucro_liquido_esperado_pct": 0.35}],
                melhor={"simbolo": "ETHBTC", "acao_sugerida": "BUY", "lucro_liquido_esperado_pct": 0.35},
                saldos=saldos,
                precos_usdt={"USDT": 1.0, "BTC": 50000.0, "ETH": 4000.0, "BNB": 600.0},
            )
        ),
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "ETHBTC",
            "acao": "BUY",
            "ts": 1,
            "confianca": 0.93,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.004,
            "features": {"close": 0.08, "spread_rel": 0.0002},
            "motivo": "micro_entrada_ethbtc",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "ETHBTC",
            "acao": "BUY",
            "aprovado": True,
            "motivos": [],
            "fracao_capital": 0.2,
            "notional_sugerido": 10.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.004,
            "lucro_liquido_esperado_usdt": 2.0,
            "ev_liquido_usdt": 20.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ExecutorIsoladoUsuario.preparar_execucao", _preparar_execucao)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    class _GerenciadorOrdensParCruzado(_GerenciadorOrdensFalso):
        async def obter_filtros_simbolo(self, simbolo):
            return {"min_notional": 0.00001, "min_qty": 0.00001, "step_size": 0.00001}

    ger = _GerenciadorOrdensParCruzado()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldos={"BTC": 0.001, "USDT": 0.0, "ETH": 0.0}),
        cliente_mercado=_ClienteMercadoFalso(precos={"ETHBTC": 0.08}),
        ger=ger,
    )

    assert len(ger.ordens) == 1
    assert ger.ordens[0]["symbol"] == "ETHBTC"
    assert ger.ordens[0]["side"] == "BUY"
    assert ger.ordens[0]["quantity"] is not None
    assert ger.ordens[0]["quote_order_qty"] is None


@pytest.mark.asyncio
async def test_auto_trader_retreina_e_persiste_outcome_ao_fechar_ciclo(monkeypatch):
    trader = TraderAutoTestnet()
    token = "retreino_ciclo"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})
    trader._state[token].update(
        {
            "sequencia_ciclo": 1,
            "ciclo_id": 1,
            "ciclo_ativo": True,
            "estado_ciclo": "EM_POSICAO",
            "ciclo_origem": "auto",
            "ciclo_iniciado_ts": 1,
            "ciclo_quantidade": 0.001,
            "ciclo_preco_entrada": 50000.0,
            "ciclo_notional_entrada": 50.0,
            "ciclo_features_entrada": {"close": 50000.0, "spread_rel": 0.0},
            "ciclo_previsao_ts": 1111,
            "ciclo_previsao_y_hat": 50300.0,
        }
    )
    chamadas_retreino = []
    chamadas_outcome = []

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 10.4, "ask_price": 10.6, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _preparar_execucao(self, aprovacao_risco, preco_referencia):
        return {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "SELL",
            "modo": "testnet",
            "fracao_capital": 0.02,
            "notional_sugerido": 50.5,
            "gatilho_offset_pct": 0.0,
            "janela_decisao": {},
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "lucro_liquido_esperado_pct": -0.001,
            "simulacao_ordem": {
                "quantidade": 0.001,
                "preco_referencia": 50500.0,
                "notional_estimado": 50.5,
            },
        }

    class _MercadoComLucro:
        async def obter_preco_atual(self, simbolo="BTCUSDT"):
            return 50500.0

    def _ajustar_online(simbolo, features, y):
        chamadas_retreino.append({"simbolo": simbolo, "features": dict(features), "y": y})

    async def _salvar_outcome(**kwargs):
        chamadas_outcome.append(dict(kwargs))

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.montar_monitoramento_multiativo", _monitoramento_multiativo_stub())
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "ts": 2,
            "confianca": 0.84,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": -0.001,
            "features": {"close": 50500.0, "spread_rel": 0.0},
            "motivo": "segurar_nao_compensa",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "aprovado": False,
            "motivos": ["sinal_hold"],
            "fracao_capital": 0.0,
            "notional_sugerido": 0.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": -0.001,
            "lucro_liquido_esperado_usdt": 0.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ExecutorIsoladoUsuario.preparar_execucao", _preparar_execucao)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ajustar_online", _ajustar_online)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOutcomes.salvar", _salvar_outcome)

    ger = _GerenciadorOrdensFalso()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=0.0, saldo_base=0.001),
        cliente_mercado=_MercadoComLucro(),
        ger=ger,
    )

    assert len(ger.ordens) == 1
    assert ger.ordens[0]["side"] == "SELL"
    assert len(chamadas_retreino) == 1
    assert chamadas_retreino[0]["simbolo"] == "BTCUSDT"
    assert chamadas_retreino[0]["y"] == 50500.0
    assert len(chamadas_outcome) == 1
    assert chamadas_outcome[0]["y_true"] == 50500.0
    assert chamadas_outcome[0]["y_hat"] == 50300.0
    assert trader._state[token]["ultimo_retreino_status"] == "ok"
    assert trader._state[token]["historico_ciclos"][-1]["lucro_liquido_usdt"] > 0.0


@pytest.mark.asyncio
async def test_auto_trader_assume_ciclo_da_carteira_quando_capital_inicial_esta_em_cripto(monkeypatch):
    trader = TraderAutoTestnet()
    token = "capital_em_cripto"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 10.4, "ask_price": 10.6, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    saldos = {
        "USDT": {"livre": 0.0, "travado": 0.0, "total": 0.0, "valor_estimado_usdt": 0.0},
        "BTC": {"livre": 0.001, "travado": 0.0, "total": 0.001, "valor_estimado_usdt": 50.0},
    }

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.montar_monitoramento_multiativo",
        _monitoramento_multiativo_stub(_monitoramento_multiativo_falso(saldos=saldos)),
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "ts": 1,
            "confianca": 0.7,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.0,
            "features": {"close": 50000.0, "spread_rel": 0.0},
            "motivo": "aguardando_saida",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "aprovado": False,
            "motivos": ["sinal_hold"],
            "fracao_capital": 0.0,
            "notional_sugerido": 0.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.0,
            "lucro_liquido_esperado_usdt": 0.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorOrdensFalso()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": False},
        cliente_conta=_ClienteContaFalso(saldo_usdt=0.0, saldo_base=0.001),
        cliente_mercado=_ClienteMercadoFalso(),
        ger=ger,
    )

    assert ger.ordens == []
    assert trader._state[token]["modo"] == "real"
    assert trader._state[token]["ciclo_ativo"] is True
    assert trader._state[token]["ciclo_origem"] == "carteira"
    assert trader._state[token]["ultimo_motivo"] == "aguardando_lucro_minimo_liquido"


@pytest.mark.asyncio
async def test_auto_trader_reconcilia_ultima_compra_do_extrato_antes_de_comprar_novamente(monkeypatch):
    trader = TraderAutoTestnet()
    token = "reconcilia_buy"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 2, "open": 50000.0, "high": 50050.0, "low": 49990.0, "close": 50020.0, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 50010.0, "ask_price": 50020.0, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    saldos = {
        "USDT": {"livre": 100.0, "travado": 0.0, "total": 100.0, "valor_estimado_usdt": 100.0},
        "BTC": {"livre": 0.001, "travado": 0.0, "total": 0.001, "valor_estimado_usdt": 50.02},
    }
    trades = [
        {"time": 1000, "price": "50000.0", "qty": "0.001", "quoteQty": "50.0", "isBuyer": True},
    ]

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.montar_monitoramento_multiativo",
        _monitoramento_multiativo_stub(_monitoramento_multiativo_falso(saldos=saldos, precos_usdt={"USDT": 1.0, "BTC": 50020.0})),
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "ts": 2,
            "confianca": 0.88,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.004,
            "features": {"close": 50020.0, "spread_rel": 0.0},
            "motivo": "sinal_de_compra_repetido",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "aprovado": True,
            "motivos": [],
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.004,
            "lucro_liquido_esperado_usdt": 0.08,
            "ev_liquido_usdt": 20.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorOrdensFalso()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=100.0, saldo_base=0.001, trades=trades),
        cliente_mercado=_ClienteMercadoFalso(precos={"BTCUSDT": 50020.0}),
        ger=ger,
    )

    assert ger.ordens == []
    assert trader._state[token]["ciclo_ativo"] is True
    assert trader._state[token]["ciclo_origem"] == "extrato"
    assert trader._state[token]["ciclo_preco_entrada"] == pytest.approx(50000.0)
    assert trader._state[token]["ultima_acao_par"] == "BUY"
    assert trader._state[token]["proxima_acao_esperada"] == "SELL"


@pytest.mark.asyncio
async def test_auto_trader_flat_apos_ultima_venda_ignora_sinal_de_venda(monkeypatch):
    trader = TraderAutoTestnet()
    token = "flat_pos_sell"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 2, "open": 50000.0, "high": 50020.0, "low": 49980.0, "close": 50000.0, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 49990.0, "ask_price": 50010.0, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    trades = [
        {"time": 2000, "price": "50010.0", "qty": "0.001", "quoteQty": "50.01", "isBuyer": False},
    ]

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.montar_monitoramento_multiativo", _monitoramento_multiativo_stub())
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "SELL",
            "ts": 2,
            "confianca": 0.85,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.004,
            "features": {"close": 50000.0, "spread_rel": 0.0},
            "motivo": "sinal_de_venda_sem_posicao",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "SELL",
            "aprovado": True,
            "motivos": [],
            "fracao_capital": 0.0,
            "notional_sugerido": 0.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.004,
            "lucro_liquido_esperado_usdt": 0.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorOrdensFalso()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=100.0, saldo_base=0.0, trades=trades),
        cliente_mercado=_ClienteMercadoFalso(precos={"BTCUSDT": 50000.0}),
        ger=ger,
    )

    assert ger.ordens == []
    assert trader._state[token]["ultima_acao"] == "HOLD"
    assert trader._state[token]["pnl_alerta_motivo"] == "pnl_fifo_incompleto"
    assert trader._state[token]["ultimo_motivo"] == "proxima_acao_esperada_e_compra"


@pytest.mark.asyncio
async def test_auto_trader_nao_assume_saldo_legado_na_borda_do_notional(monkeypatch):
    trader = TraderAutoTestnet()
    token = "saldo_legado_borda"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 99.5, "high": 100.5, "low": 99.0, "close": 100.0, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 99.9, "ask_price": 100.1, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    saldos = {
        "USDT": {"livre": 0.0, "travado": 0.0, "total": 0.0, "valor_estimado_usdt": 0.0},
        "BTC": {"livre": 0.10005, "travado": 0.0, "total": 0.10005, "valor_estimado_usdt": 10.005},
    }

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.montar_monitoramento_multiativo",
        _monitoramento_multiativo_stub(_monitoramento_multiativo_falso(saldos=saldos, precos_usdt={"USDT": 1.0, "BTC": 100.0})),
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "ts": 1,
            "confianca": 0.65,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.0,
            "features": {"close": 100.0, "spread_rel": 0.0},
            "motivo": "aguardando_saida",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "aprovado": False,
            "motivos": ["sinal_hold"],
            "fracao_capital": 0.0,
            "notional_sugerido": 0.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.0,
            "lucro_liquido_esperado_usdt": 0.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    class _GerenciadorComMinNotionalMaior(_GerenciadorOrdensFalso):
        async def obter_filtros_simbolo(self, simbolo):
            return {"min_notional": 10.0, "min_qty": 0.00001, "step_size": 0.00001}

    ger = _GerenciadorComMinNotionalMaior()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=0.0, saldo_base=0.10005),
        cliente_mercado=_ClienteMercadoFalso(precos={"BTCUSDT": 100.0}),
        ger=ger,
    )

    assert ger.ordens == []
    assert trader._state[token]["ciclo_ativo"] is False
    assert trader._state[token]["ultima_acao"] == "HOLD"
    assert trader._state[token]["ultimo_motivo"] == "saldo_legado_abaixo_do_minimo_operacional"


@pytest.mark.asyncio
async def test_auto_trader_ignora_residuo_abaixo_de_cinco_dolares(monkeypatch):
    trader = TraderAutoTestnet()
    token = "residuo_ignorado"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 99.5, "high": 100.5, "low": 99.0, "close": 100.0, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 99.9, "ask_price": 100.1, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.montar_monitoramento_multiativo", _monitoramento_multiativo_stub())
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "ts": 1,
            "confianca": 0.8,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.0,
            "features": {"close": 100.0},
            "motivo": "sinal_hold",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "HOLD",
            "aprovado": False,
            "motivos": ["sinal_hold"],
            "fracao_capital": 0.0,
            "notional_sugerido": 0.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.02,
            "lucro_liquido_esperado_pct": 0.0,
            "lucro_liquido_esperado_usdt": 0.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    class _GerenciadorComMinNotionalMaior(_GerenciadorOrdensFalso):
        async def obter_filtros_simbolo(self, simbolo):
            return {"min_notional": 10.0, "min_qty": 0.00001, "step_size": 0.00001}

    ger = _GerenciadorComMinNotionalMaior()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=0.0, saldo_base=0.04),
        cliente_mercado=_ClienteMercadoFalso(precos={"BTCUSDT": 100.0}),
        ger=ger,
    )

    assert ger.ordens == []
    assert trader._state[token]["ciclo_ativo"] is False
    assert trader._state[token]["saldo_legado_detectado"] is False
    assert trader._state[token]["proxima_acao_esperada"] == "BUY"
    assert "sinal_hold" in trader._state[token]["ultimo_motivo"]
    assert trader._state[token]["ultimo_motivo"] != "saldo_legado_abaixo_do_minimo_operacional"


@pytest.mark.asyncio
async def test_auto_trader_reutiliza_sinal_final_do_scanner_multiativo(monkeypatch):
    trader = TraderAutoTestnet()
    token = "scanner_sync"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _noop(*args, **kwargs):
        return None

    async def _preparar_execucao(self, aprovacao_risco, preco_referencia):
        return {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "modo": "testnet",
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "gatilho_offset_pct": 0.0,
            "janela_decisao": {},
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "lucro_liquido_esperado_pct": 0.02,
            "simulacao_ordem": {
                "quantidade": 0.0004,
                "preco_referencia": 50000.0,
                "notional_estimado": 20.0,
            },
        }

    monitoramento = _monitoramento_multiativo_falso(
        pares=[{"simbolo": "BTCUSDT", "acao_sugerida": "BUY", "lucro_liquido_esperado_pct": 0.25}],
        melhor={"simbolo": "BTCUSDT", "acao_sugerida": "BUY", "lucro_liquido_esperado_pct": 0.25},
    )
    monitoramento["sinais"] = {
        "BTCUSDT": {
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "ts": 1,
            "confianca": 0.91,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.02,
            "features": {"close": 50000.0, "spread_rel": 0.0},
            "motivo": "scanner_confirmou_buy",
        }
    }

    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.montar_monitoramento_multiativo",
        _monitoramento_multiativo_stub(monitoramento),
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("nao deveria recalcular o sinal")),
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "aprovado": True,
            "motivos": [],
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.02,
            "lucro_liquido_esperado_usdt": 0.4,
            "ev_liquido_usdt": 20.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ExecutorIsoladoUsuario.preparar_execucao", _preparar_execucao)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorOrdensFalso()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=100.0, saldo_base=0.0),
        cliente_mercado=_ClienteMercadoFalso(precos={"BTCUSDT": 50000.0}),
        ger=ger,
    )

    assert len(ger.ordens) == 1
    assert ger.ordens[0]["side"] == "BUY"
    assert trader._state[token]["ultimo_sinal"] == "BUY"
    assert trader._state[token]["ultimo_motivo"] == "scanner_confirmou_buy"


def test_perda_diaria_reseta_no_virar_do_dia():
    # Run multi-dia: a perda diária deve zerar quando o dia operacional muda,
    # senão vira perda cumulativa e trava o breaker cedo demais.
    state = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})
    state["daily_loss_usdt"] = 7.5
    state["daily_loss_data"] = "1999-01-01"
    _resetar_perda_diaria_se_novo_dia(state)
    assert state["daily_loss_usdt"] == 0.0
    assert state["daily_loss_data"] == _data_operacional()


def test_perda_diaria_preserva_no_mesmo_dia():
    # No mesmo dia operacional a perda acumulada NÃO pode ser zerada.
    state = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})
    state["daily_loss_usdt"] = 7.5
    state["daily_loss_data"] = _data_operacional()
    _resetar_perda_diaria_se_novo_dia(state)
    assert state["daily_loss_usdt"] == 7.5


class _GerenciadorOrdensNaoPreenche(_GerenciadorOrdensFalso):
    """Simula a Binance devolvendo ordem NÃO preenchida (status EXPIRED, executedQty 0)."""

    async def obter_filtros_simbolo(self, simbolo):
        return {"min_notional": 0.00001, "min_qty": 0.00001, "step_size": 0.00001}

    async def criar_ordem_market(self, simbolo, lado, quantidade=None, quote_order_qty=None):
        ordem = {
            "symbol": simbolo,
            "side": lado,
            "quantity": quantidade,
            "quote_order_qty": quote_order_qty,
            "orderId": len(self.ordens) + 1,
            "status": "EXPIRED",
            "executedQty": "0",
        }
        self.ordens.append(ordem)
        return ordem


@pytest.mark.asyncio
async def test_auto_trader_nao_abre_ciclo_quando_compra_nao_preenche(monkeypatch):
    # Guarda anti-posição-fantasma (causa-raiz #2 do run 13-18h): ordem BUY que volta
    # EXPIRED/executedQty=0 NÃO pode abrir ciclo — abriria ciclo_ativo sem ativo real e
    # travaria o bot em 'limite_trades_abertos'.
    trader = TraderAutoTestnet()
    token = "buy_nao_preenche"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 20})

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 10.4, "ask_price": 10.6, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _preparar_execucao(self, aprovacao_risco, preco_referencia):
        return {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "modo": "testnet",
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "gatilho_offset_pct": 0.0,
            "janela_decisao": {},
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "lucro_liquido_esperado_pct": 0.02,
            "simulacao_ordem": {
                "quantidade": 0.0004,
                "preco_referencia": 50000.0,
                "notional_estimado": 20.0,
            },
        }

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.montar_monitoramento_multiativo", _monitoramento_multiativo_stub())
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "ts": 1,
            "confianca": 0.92,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.02,
            "features": {"close": 50000.0},
            "motivo": "compra_orquestrada",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "BUY",
            "aprovado": True,
            "motivos": [],
            "fracao_capital": 0.02,
            "notional_sugerido": 20.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.02,
            "lucro_liquido_esperado_usdt": 0.4,
            "ev_liquido_usdt": 20.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ExecutorIsoladoUsuario.preparar_execucao", _preparar_execucao)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorOrdensNaoPreenche()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=100.0, saldo_base=0.0),
        cliente_mercado=_ClienteMercadoFalso(),
        ger=ger,
    )

    assert len(ger.ordens) == 1                                    # tentou a compra
    assert ger.ordens[0]["side"] == "BUY"
    assert trader._state[token]["ciclo_ativo"] is False            # mas NÃO abriu ciclo-fantasma
    assert trader._state[token]["ultima_acao"] == "HOLD"
    assert trader._state[token]["ultimo_motivo"] == "ordem_compra_nao_preenchida"


@pytest.mark.asyncio
async def test_auto_trader_nao_encerra_ciclo_quando_venda_nao_preenche(monkeypatch):
    # Guarda anti-fantasma na saída: venda que NÃO preenche não pode encerrar o ciclo —
    # encerrar registraria lucro inexistente e o bot acharia estar zerado segurando o ativo.
    trader = TraderAutoTestnet()
    token = "sell_nao_preenche"
    trader._state[token] = _novo_estado({"simbolo": "BTCUSDT", "intervalo_segundos": 5, "notional_usdt": 25})
    trader._state[token].update(
        {
            "sequencia_ciclo": 1,
            "ciclo_id": 1,
            "ciclo_ativo": True,
            "estado_ciclo": "EM_POSICAO",
            "ciclo_origem": "auto",
            "ciclo_iniciado_ts": 1,
            "ciclo_quantidade": 0.001,
            "ciclo_preco_entrada": 50000.0,
            "ciclo_notional_entrada": 50.0,
        }
    )

    async def _noop(*args, **kwargs):
        return None

    async def _klines(*args, **kwargs):
        return [{"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]

    async def _livro(*args, **kwargs):
        return {"bid_price": 10.4, "ask_price": 10.6, "bid_qty": 1.0, "ask_qty": 1.0}

    async def _ajustes(*args, **kwargs):
        return {"aplicado": {}}

    async def _preparar_execucao(self, aprovacao_risco, preco_referencia):
        return {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "SELL",
            "modo": "testnet",
            "fracao_capital": 0.02,
            "notional_sugerido": 50.0,
            "gatilho_offset_pct": 0.0,
            "janela_decisao": {},
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "lucro_liquido_esperado_pct": 0.03,
            "simulacao_ordem": {
                "quantidade": 0.001,
                "preco_referencia": 50000.0,
                "notional_estimado": 50.0,
            },
        }

    monkeypatch.setattr("src.servicos.testnet_auto_trader.coletar_e_persistir", _noop)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioOhlcv.obter_ultimas", _klines)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioLivroTopo.obter_ultimo", _livro)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_noticias_para_peso", lambda simbolo="BTCUSDT": _ajustes())
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_sinal", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.obter_ajustes_risco", _ajustes)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.montar_monitoramento_multiativo", _monitoramento_multiativo_stub())
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.gerar_sinal_orquestrado",
        lambda **kwargs: {
            "simbolo": "BTCUSDT",
            "acao": "SELL",
            "ts": 1,
            "confianca": 0.95,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.03,
            "features": {"close": 50500.0, "spread_rel": 0.0},
            "motivo": "saida_otimizada",
        },
    )
    monkeypatch.setattr(
        "src.servicos.testnet_auto_trader.avaliar_sinal_para_usuario",
        lambda **kwargs: {
            "usuario_id": 0,
            "usuario_nome": "auto",
            "simbolo": "BTCUSDT",
            "acao": "SELL",
            "aprovado": False,
            "motivos": ["cooldown_ativo"],
            "fracao_capital": 0.0,
            "notional_sugerido": 0.0,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.03,
            "lucro_liquido_esperado_pct": 0.03,
            "lucro_liquido_esperado_usdt": 0.0,
            "confirmacao_multi_timeframe": {},
            "probabilidade_trade": {},
            "janela_decisao": {"executar_apos_ts": 0},
            "paper_trading": False,
            "risk_config_aplicado": {},
        },
    )
    monkeypatch.setattr("src.servicos.testnet_auto_trader.ExecutorIsoladoUsuario.preparar_execucao", _preparar_execucao)
    monkeypatch.setattr("src.servicos.testnet_auto_trader.RepositorioAuditoria.registrar", _noop)

    ger = _GerenciadorOrdensNaoPreenche()
    await trader._executar_ciclo(
        token=token,
        sessao={"modo_testnet": True},
        cliente_conta=_ClienteContaFalso(saldo_usdt=0.0, saldo_base=0.001),
        cliente_mercado=_ClienteMercadoFalso(precos={"BTCUSDT": 50500.0}),
        ger=ger,
    )

    assert len(ger.ordens) == 1                                    # tentou a venda
    assert ger.ordens[0]["side"] == "SELL"
    assert trader._state[token]["ciclo_ativo"] is True             # ciclo PRESERVADO (não vendeu de verdade)
    assert trader._state[token]["ultimo_motivo"] == "ordem_venda_nao_preenchida"
