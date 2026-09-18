"""Testes do CalibradorBandit — confiança DETERMINÍSTICA (GAP-FIN-01).

A versão anterior era um stub que devolvia confiança ALEATÓRIA (0.55/0.60 por epsilon-greedy)
e essa confiança dimensionava a posição. Estes testes travam o invariante de que agora a
confiança é determinística e reflete a relação sinal/ruído do sinal — não ruído.
"""
from __future__ import annotations

from src.calibracao.bandit import (
    _CONF_MAXIMA,
    _CONF_MINIMA,
    CalibradorBandit,
)


def _features(close=100.0, y_move_rel=0.0, vol5=0.001, spread_rel=0.0):
    """Monta features com um movimento previsto relativo `y_move_rel` sobre `close`."""
    return {"close": close, "vol5": vol5, "vol10": vol5, "spread_rel": spread_rel}


def test_confianca_e_deterministica():
    """Mesmas features ⇒ mesma confiança, sempre (ao contrário do stub aleatório antigo)."""
    cal = CalibradorBandit()
    feats = _features(close=100.0, vol5=0.001, spread_rel=0.0)
    y_hat = 100.5  # movimento previsto +0.5%
    conf_esperada = cal.calibrar(y_hat, feats)[1]
    # 50 chamadas idênticas devem dar EXATAMENTE o mesmo valor (sem random).
    for _ in range(50):
        assert cal.calibrar(y_hat, feats)[1] == conf_esperada


def test_y_cal_nao_distorce_previsao():
    """y_cal == y_hat (não há calibração de escala ainda — não inventamos previsão)."""
    cal = CalibradorBandit()
    y_cal, _ = cal.calibrar(123.456, _features())
    assert y_cal == 123.456


def test_maior_snr_maior_confianca():
    """Movimento previsto maior (vs mesma volatilidade) ⇒ mais confiança (sinal/ruído)."""
    cal = CalibradorBandit()
    close = 100.0
    conf_fraco = cal.calibrar(close * 1.0005, _features(close=close, vol5=0.001))[1]  # +0.05%
    conf_forte = cal.calibrar(close * 1.010, _features(close=close, vol5=0.001))[1]   # +1.0%
    assert conf_forte > conf_fraco


def test_spread_alto_reduz_confianca():
    """Spread alto (execução cara/incerta) ⇒ menos confiança para o mesmo sinal."""
    cal = CalibradorBandit()
    close = 100.0
    y_hat = close * 1.005  # mesmo movimento nos dois casos
    conf_spread_baixo = cal.calibrar(y_hat, _features(close=close, spread_rel=0.0))[1]
    conf_spread_alto = cal.calibrar(y_hat, _features(close=close, spread_rel=0.01))[1]
    assert conf_spread_alto < conf_spread_baixo


def test_confianca_sempre_dentro_dos_limites():
    """Confiança nunca sai de [_CONF_MINIMA, _CONF_MAXIMA], mesmo em extremos."""
    cal = CalibradorBandit()
    casos = [
        _features(close=0.0),                         # sem close → SNR 0
        _features(close=100.0, y_move_rel=0.0, vol5=0.0),  # vol 0 → usa vol mínima
        {},                                           # features vazias
    ]
    for feats in casos:
        _, conf = cal.calibrar(100.0, feats)
        assert _CONF_MINIMA <= conf <= _CONF_MAXIMA


def test_movimento_gigante_com_spread_gigante_nao_estoura():
    """Combinação extrema (SNR alto + spread saturado) permanece bem-comportada e limitada."""
    cal = CalibradorBandit()
    _, conf = cal.calibrar(200.0, _features(close=100.0, vol5=0.0001, spread_rel=0.5))
    assert _CONF_MINIMA <= conf <= _CONF_MAXIMA
