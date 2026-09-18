"""P1 — gate de confiabilidade do modelo online: modelo sub-treinado não domina o sinal.

Diagnóstico do run 2026-06-20: modelo online com 18 amostras divergiu (coef norma ~71) e
cravava SELL máximo todo ciclo. O gate de amostras mínimas elimina isso.
"""
from __future__ import annotations

import shutil

from src.modelagem.gerenciador_modelo import MODEL_DIR, GerenciadorModelo


def test_online_descartado_abaixo_do_minimo_de_amostras():
    simbolo = "ZZGATETEST"
    try:
        g = GerenciadorModelo(simbolo)
        feats = {"close": 100.0, "r_1m": 0.001, "r_5m": 0.0008}
        g.partial_fit(feats, 101.0)  # apenas 1 amostra << MIN_AMOSTRAS_ONLINE (200)
        assert g._amostras_ajustadas == 1
        # Online sub-treinado é descartado → não contamina o consenso.
        assert g._predicao_online(feats) is None
        # predict() cai no fallback são (variação pequena, sem extremo).
        y = g.predict(feats)
        assert abs(y - g._predicao_fallback(feats)) < 1e-6
    finally:
        shutil.rmtree(MODEL_DIR / simbolo, ignore_errors=True)


def test_predicao_online_extrema_nao_altera_saida_servida(monkeypatch):
    simbolo = "ZZSOMBRASERVIDA"
    try:
        g = GerenciadorModelo(simbolo)
        features = {"close": 100.0, "r_1m": 0.001, "r_5m": 0.0008}
        esperado = g.predict(features)
        chamadas = 0

        def predicao_extrema(_: dict[str, float]) -> float:
            nonlocal chamadas
            chamadas += 1
            return 1_000_000_000.0

        monkeypatch.setattr(g, "_predicao_online", predicao_extrema)

        assert g.predict(features) == esperado
        assert chamadas == 0
    finally:
        shutil.rmtree(MODEL_DIR / simbolo, ignore_errors=True)


def test_treino_online_permanece_em_sombra_e_nao_muda_saida_servida():
    simbolo = "ZZTREINOSOMBRA"
    try:
        g = GerenciadorModelo(simbolo)
        features = {"close": 100.0, "r_1m": 0.001, "r_5m": 0.0008}
        antes = g.predict(features)

        g.partial_fit(features, 1_000_000_000.0)

        assert g.predict(features) == antes
        status = g.status()
        assert status["online_em_uso"] is False
        assert status["online_em_sombra"] is True
    finally:
        shutil.rmtree(MODEL_DIR / simbolo, ignore_errors=True)
