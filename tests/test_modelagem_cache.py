"""PERF-01 — o GerenciadorModelo é cacheado por símbolo (sem joblib.load a cada ciclo)."""
from __future__ import annotations

import shutil

from src.modelagem.gerenciador_modelo import (
    _CACHE_GERENCIADORES,
    MODEL_DIR,
    obter_gerenciador_modelo,
)


def test_gerenciador_modelo_cacheado_por_simbolo():
    simbolo = "ZZPERFTEST"
    try:
        g1 = obter_gerenciador_modelo(simbolo)
        g2 = obter_gerenciador_modelo(simbolo)
        assert g1 is g2  # cache hit — disco inalterado → sem recarregar

        # Invalidação manual (simula novo modelo no disco) → nova instância.
        _CACHE_GERENCIADORES.pop(simbolo, None)
        g3 = obter_gerenciador_modelo(simbolo)
        assert g3 is not g1
    finally:
        _CACHE_GERENCIADORES.pop(simbolo, None)
        shutil.rmtree(MODEL_DIR / simbolo, ignore_errors=True)
