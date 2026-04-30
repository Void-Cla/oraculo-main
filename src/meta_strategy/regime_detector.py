from __future__ import annotations

from typing import Any


def detectar_regime(features: dict[str, Any]) -> dict[str, Any]:
    vol5 = float(features.get("vol5", 0.0) or 0.0)
    vol10 = float(features.get("vol10", 0.0) or 0.0)
    r_5m = float(features.get("r_5m", 0.0) or 0.0)
    r_15m = float(features.get("r_15m", 0.0) or 0.0)
    ema5 = float(features.get("ema5", 0.0) or 0.0)
    ema10 = float(features.get("ema10", 0.0) or 0.0)
    amplitude_rel = float(features.get("amplitude_rel", 0.0) or 0.0)

    vol_ref = max(vol5, vol10)
    regime = "RANGE"
    score = 0.45

    if vol_ref >= 0.012 or amplitude_rel >= 0.018:
        regime = "HIGH_VOL"
        score = 0.8
    elif abs(r_5m) <= 0.0015 and vol_ref <= 0.0035:
        regime = "LOW_VOL"
        score = 0.7
    elif ema5 > ema10 and r_15m >= 0:
        regime = "TREND_UP"
        score = 0.72
    elif ema5 < ema10 and r_15m <= 0:
        regime = "TREND_DOWN"
        score = 0.72

    return {
        "regime": regime,
        "score_regime": score,
        "detalhes": {
            "vol_ref": vol_ref,
            "r_5m": r_5m,
            "r_15m": r_15m,
            "ema5": ema5,
            "ema10": ema10,
            "amplitude_rel": amplitude_rel,
        },
    }
