from __future__ import annotations

import math


class ProbabilityCalibrator:
    def __init__(self, temperature: float = 1.0, scale: float = 10.0) -> None:
        self.temperature = max(float(temperature), 1e-6)
        self.scale = max(float(scale), 1e-6)

    def sigmoid(self, valor: float) -> float:
        return 1.0 / (1.0 + math.exp(-(valor / self.temperature)))

    def calibrate(self, raw_prediction: float, ajuste_externo: float = 0.0) -> dict[str, float]:
        logit = (float(raw_prediction) * self.scale) + float(ajuste_externo)
        prob_up = self.sigmoid(logit)
        prob_down = 1.0 - prob_up
        return {
            "prob_up": max(0.0, min(1.0, prob_up)),
            "prob_down": max(0.0, min(1.0, prob_down)),
            "logit": logit,
        }
