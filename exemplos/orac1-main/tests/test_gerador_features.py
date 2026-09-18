from src.calculos.gerador_features import calcular_features_1m


def test_gerador_features_produz_campos_criticos():
    klines = [
        [1, 100.0, 101.0, 99.0, 100.5, 10.0],
        [2, 100.5, 102.0, 100.0, 101.8, 11.0],
        [3, 101.8, 103.0, 101.0, 102.5, 12.0],
        [4, 102.5, 104.0, 102.0, 103.7, 13.0],
        [5, 103.7, 105.0, 103.0, 104.6, 12.5],
    ]
    livro = {"bid_price": 104.5, "bid_qty": 4.0, "ask_price": 104.7, "ask_qty": 3.0}

    features = calcular_features_1m(klines, livro_topo=livro, sent_score=0.2)

    assert features["ts"] == 5
    assert features["close"] == 104.6
    assert "r_1m" in features
    assert "vol5" in features
    assert "microprice" in features
    assert "pressao_rel" in features
    assert features["sent_score"] == 0.2
