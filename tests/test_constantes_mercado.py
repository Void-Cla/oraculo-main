"""Garante fonte única de limiares de regime (INC-06) e o gate de custo do profit_guard (INC-04)."""
from __future__ import annotations

from src.core.constantes_mercado import VOLATILIDADE_ALTA, VOLATILIDADE_BAIXA
from src.multiativo.profit_guard import avaliar_profit_guard


def test_limiares_vol_regime_sao_fonte_unica():
    # regime_detector e repositorio_features DEVEM usar exatamente as mesmas constantes.
    import src.meta_strategy.regime_detector as rd
    import src.persistencia.repositorio_features as rf

    assert rd.VOLATILIDADE_ALTA is VOLATILIDADE_ALTA
    assert rd.VOLATILIDADE_BAIXA is VOLATILIDADE_BAIXA
    assert rf.VOLATILIDADE_ALTA is VOLATILIDADE_ALTA
    assert rf.VOLATILIDADE_BAIXA is VOLATILIDADE_BAIXA
    assert VOLATILIDADE_ALTA > VOLATILIDADE_BAIXA


def test_regime_detector_e_repositorio_concordam_no_rotulo_de_volatilidade():
    from src.meta_strategy.regime_detector import detectar_regime

    # vol baixíssima + lateral → LOW no detector; mesmo limiar usado no repositório.
    baixo = detectar_regime({"vol5": 0.001, "vol10": 0.001, "r_5m": 0.0})
    assert baixo["regime"] == "LOW_VOL"
    # vol alta → HIGH_VOL
    alto = detectar_regime({"vol5": 0.02, "vol10": 0.02})
    assert alto["regime"] == "HIGH_VOL"


def test_profit_guard_usa_custo_em_gate_independente():
    # INC-04: lucro líquido minúsculo (mas acima do piso) com custo alto deve ser reprovado
    # pela margem de robustez, não aprovado por confiar cegamente no chamador.
    guard = avaliar_profit_guard(
        lucro_liquido_pct=0.001,    # acima do min_pct padrão (0.0005), mas abaixo da margem
        notional_usdt=100.0,
        spread_rel=0.001,
        taxas_totais_pct=0.02,      # custo round-trip alto (2%) → margem mínima 0.0025
        slippage_pct=0.002,
        minimo_usdt=0.0,            # neutraliza o piso em USDT para isolar o gate de custo
    )
    assert "margem_insuficiente_sobre_custo" in guard["motivos"]
    assert guard["aprovado"] is False
    assert guard["custo_round_trip_pct"] > 0.0


def test_profit_guard_aprova_lucro_com_folga_sobre_custo():
    guard = avaliar_profit_guard(
        lucro_liquido_pct=0.006,    # folga ampla sobre o custo
        notional_usdt=100.0,
        spread_rel=0.0002,
        taxas_totais_pct=0.002,
        slippage_pct=0.0005,
    )
    assert "margem_insuficiente_sobre_custo" not in guard["motivos"]
    assert guard["aprovado"] is True
