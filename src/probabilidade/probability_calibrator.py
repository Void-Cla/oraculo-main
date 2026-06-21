from __future__ import annotations

import math

# Acima deste argumento, math.exp() estoura o range de float64 (~709) e levanta
# OverflowError — o que derrubaria o signal_engine inteiro. (BUG-06)
_MAX_EXP_ARG = 709.0


class ProbabilityCalibrator:
    def __init__(self, temperature: float = 1.0, scale: float = 10.0) -> None:
        self.temperature = max(float(temperature), 1e-6)
        self.scale = max(float(scale), 1e-6)

    def sigmoid(self, valor: float) -> float:
        # Sigmoid numericamente estável: satura nos extremos em vez de estourar exp().
        arg = -(valor / self.temperature)
        if arg >= _MAX_EXP_ARG:
            return 0.0
        if arg <= -_MAX_EXP_ARG:
            return 1.0
        return 1.0 / (1.0 + math.exp(arg))

    def calibrate(self, raw_prediction: float, ajuste_externo: float = 0.0) -> dict[str, float]:
        logit = (float(raw_prediction) * self.scale) + float(ajuste_externo)
        prob_up = self.sigmoid(logit)
        prob_down = 1.0 - prob_up
        return {
            "prob_up": max(0.0, min(1.0, prob_up)),
            "prob_down": max(0.0, min(1.0, prob_down)),
            "logit": logit,
        }
