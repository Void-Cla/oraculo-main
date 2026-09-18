"""EDGE LÓGICO + relaxamento do gate de entrada em exploração (correção do 0-trades em 13h)."""
import pytest

from src.contratos.trading import SignalDecision


# ── Núcleo puro do edge lógico ───────────────────────────────────────────────
def test_edge_logico_aprova_quando_liquido_cobre_custo():
    from src.risco.edge_logico import avaliar_edge_logico

    r = avaliar_edge_logico(
        retorno_liquido_esperado_pct=0.004, confianca=0.6,
        fee=0.001, slippage=0.0005, modo_exploracao=True,
    )
    assert r.aprovado is True
    assert r.motivo == "edge_logico_ok"
    # bruto esperado = líquido + custo round-trip ((0.001+0.0005)*2 = 0.003)
    assert r.custo_round_trip_pct == pytest.approx(0.003)
    assert r.bruto_esperado_pct == pytest.approx(0.007)


def test_edge_logico_nega_confianca_baixa():
    from src.risco.edge_logico import avaliar_edge_logico

    r = avaliar_edge_logico(
        retorno_liquido_esperado_pct=0.01, confianca=0.2,
        fee=0.001, slippage=0.0005, modo_exploracao=True,
    )
    assert r.aprovado is False
    assert r.motivo == "confianca_insuficiente"


def test_edge_logico_nega_quando_nao_cobre_custo_real():
    # Em conta real a margem mínima é > 0 → retorno líquido <= 0 não entra.
    from src.risco.edge_logico import avaliar_edge_logico

    r = avaliar_edge_logico(
        retorno_liquido_esperado_pct=0.0, confianca=0.9,
        fee=0.001, slippage=0.0005, modo_exploracao=False,
    )
    assert r.aprovado is False
    assert r.motivo == "retorno_liquido_nao_cobre_custo_mais_margem"


def test_edge_logico_exploracao_aceita_break_even():
    # Em exploração a margem mínima é 0 → retorno líquido 0 com confiança ok ENTRA.
    from src.risco.edge_logico import avaliar_edge_logico

    r = avaliar_edge_logico(
        retorno_liquido_esperado_pct=0.0, confianca=0.6,
        fee=0.001, slippage=0.0005, modo_exploracao=True,
    )
    assert r.aprovado is True


# ── Relaxamento do gate de perfil em exploração (causa do `nenhum_perfil...`) ──
def _sinal_buy(lucro_liq=0.005, confianca=0.6):
    return SignalDecision.from_mapping({
        "simbolo": "BTCUSDT", "acao": "BUY", "ts": 1, "confianca": confianca,
        "stop_loss_pct": 0.002, "take_profit_pct": 0.01, "lucro_liquido_esperado_pct": lucro_liq,
        "features": {}, "probabilidade_trade": {}, "confirmacao_multi_timeframe": {},
    })


def _perfil_dificil():
    # Perfil com piso de lucro ALTO e que não passaria na confirmação composta.
    return {
        "id": "mini", "nome": "Mini", "habilitado": True, "capital_usdt": 50.0,
        "lucro_minimo_usdt": 999.0, "min_confianca": 0.99, "min_probabilidade": 0.99,
        "min_confirmacoes": 5,
    }


def test_perfil_nao_exploracao_bloqueia():
    # Comportamento legado: fora de exploração, perfil difícil bloqueia (retorna None).
    from src.servicos.testnet_auto_trader import _selecionar_perfil_entrada

    perfil, motivo = _selecionar_perfil_entrada(
        state={}, sinal=_sinal_buy(), perfis=[_perfil_dificil()],
        min_notional_usdt=10.0, saldo_quote_livre_usdt=100.0, modo_exploracao=False,
    )
    assert perfil is None
    assert motivo == "nenhum_perfil_encontrou_lucro_liquido_viavel"


def test_perfil_exploracao_seleciona_apesar_dos_filtros():
    # FIX: em exploração, piso de lucro/confirmação são advisory → seleciona o perfil
    # (o gate real passa a ser o edge lógico + Gemini). Sem isto, 0 trades em 13h.
    from src.servicos.testnet_auto_trader import _selecionar_perfil_entrada

    perfil, motivo = _selecionar_perfil_entrada(
        state={}, sinal=_sinal_buy(), perfis=[_perfil_dificil()],
        min_notional_usdt=10.0, saldo_quote_livre_usdt=100.0, modo_exploracao=True,
    )
    assert perfil is not None
    assert motivo == "perfil_selecionado_exploracao_fallback"


def test_perfil_exploracao_ainda_respeita_capital_minimo():
    # Mesmo em exploração, capital abaixo do min_notional NÃO entra (limite da corretora).
    from src.servicos.testnet_auto_trader import _selecionar_perfil_entrada

    perfil, _ = _selecionar_perfil_entrada(
        state={}, sinal=_sinal_buy(), perfis=[{**_perfil_dificil(), "capital_usdt": 3.0}],
        min_notional_usdt=10.0, saldo_quote_livre_usdt=100.0, modo_exploracao=True,
    )
    assert perfil is None


def test_perfil_entrada_prefere_mini_para_ciclos_rapidos():
    """Com saldo alto, não escolher ganancioso/diario ($0.50+) quando mini ($0.01) qualifica."""
    from src.servicos.testnet_auto_trader import _selecionar_perfil_entrada

    perfis = [
        {
            "id": "mini", "nome": "Mini", "habilitado": True, "capital_usdt": 500.0,
            "lucro_minimo_usdt": 0.01, "min_confianca": 0.42, "min_probabilidade": 0.55,
            "min_confirmacoes": 1, "tempo_minimo_posicao_segundos": 0,
        },
        {
            "id": "ganancioso", "nome": "Ganancioso", "habilitado": True, "capital_usdt": 250.0,
            "lucro_minimo_usdt": 0.50, "min_confianca": 0.42, "min_probabilidade": 0.55,
            "min_confirmacoes": 1, "tempo_minimo_posicao_segundos": 45,
        },
    ]
    perfil, motivo = _selecionar_perfil_entrada(
        state={},
        sinal=_sinal_buy(lucro_liq=0.002, confianca=0.7),
        perfis=perfis,
        min_notional_usdt=10.0,
        saldo_quote_livre_usdt=1000.0,
        modo_exploracao=False,
    )
    assert perfil is not None
    assert perfil["id"] == "mini"
    assert motivo == "perfil_selecionado"


# ── Helper do autotrader (edge lógico a partir do sinal + taxas) ─────────────
def test_autotrader_helper_edge_logico():
    from src.servicos.testnet_auto_trader import TestnetAutoTrader

    trader = TestnetAutoTrader()
    ajustes = {"binance_taxa_taker_pct": 0.1, "slippage_pct": 0.0005, "permitir_ev_negativo": True}
    r = trader._avaliar_edge_logico_entrada(sinal=_sinal_buy(lucro_liq=0.005, confianca=0.6), ajustes_risco=ajustes)
    assert r.aprovado is True
    r2 = trader._avaliar_edge_logico_entrada(sinal=_sinal_buy(lucro_liq=-0.01, confianca=0.6), ajustes_risco=ajustes)
    assert r2.aprovado is False
