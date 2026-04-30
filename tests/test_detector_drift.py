from src.sinais.detector_drift import _desvio_padrao


def test_desvio_padrao_constante():
    assert _desvio_padrao([10.0, 10.0, 10.0]) == 0.0


def test_desvio_padrao_insuficiente():
    assert _desvio_padrao([10.0]) is None


def test_desvio_padrao_calculado():
    dp = _desvio_padrao([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    assert round(dp, 4) == 2.0
