"""Constantes de mercado — FONTE ÚNICA DE VERDADE.

Estes limiares definem o regime de volatilidade e DEVEM ser idênticos em todo o
sistema. Antes (INC-06) `regime_detector.py` e `repositorio_features.py` tinham
valores divergentes para o piso de volatilidade (0.0035 vs 0.003), o que rotulava
o mesmo candle com regimes diferentes dependendo do módulo. Centralizar aqui
elimina a divergência silenciosa.

Origem dos valores: análise de volatilidade histórica de BTCUSDT (curto prazo).
Alvo da arquitetura: mover para `src/dominio/` na Fase 6 (ver contexto.md DA-06).
"""
from __future__ import annotations

# vol_ref >= VOLATILIDADE_ALTA  → regime de alta volatilidade (HIGH_VOL / "HIGH")
VOLATILIDADE_ALTA: float = 0.012

# vol_ref <= VOLATILIDADE_BAIXA → regime de baixa volatilidade (LOW_VOL / "LOW")
# Entre os dois extremos: regime intermediário (RANGE / "MED").
VOLATILIDADE_BAIXA: float = 0.0035

# Amplitude relativa que, sozinha, também caracteriza alta volatilidade.
AMPLITUDE_ALTA: float = 0.018

# Retorno de 5m considerado "lateral" (sem direção) para classificar baixa volatilidade.
RETORNO_LATERAL_MAX: float = 0.0015
