from __future__ import annotations

import os

from .ev_calculator import EVCalculator
from .probability_calibrator import ProbabilityCalibrator
from .trade_selector import TradeSelector


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


class ProbabilisticTradeEngine:
    def __init__(
        self,
        *,
        fee: float | None = None,
        slippage: float | None = None,
        min_ev: float | None = None,
        min_prob: float | None = None,
        temperature: float | None = None,
        scale: float | None = None,
    ) -> None:
        fee = float(fee if fee is not None else 0.001)
        slippage = float(slippage if slippage is not None else 0.0005)
        min_ev = float(min_ev if min_ev is not None else 0.0001)
        min_prob = float(min_prob if min_prob is not None else 0.55)
        temperature = float(temperature if temperature is not None else 1.0)
        scale = float(scale if scale is not None else 10.0)
        self.calibrator = ProbabilityCalibrator(temperature=temperature, scale=scale)
        self.ev_calc = EVCalculator(fee=fee, slippage=slippage)
        self.selector = TradeSelector(min_ev=min_ev, min_prob=min_prob)

    def evaluate_trade(
        self,
        *,
        raw_prediction: float,
        take_profit: float,
        stop_loss: float,
        spread: float = 0.0,
        score_confirmacao: float = 0.0,
        sentimento_noticias: float = 0.0,
    ) -> dict[str, float | str]:
        ajuste = _clamp((float(score_confirmacao) * 0.85) + (float(sentimento_noticias) * 0.45), -1.5, 1.5)
        probs = self.calibrator.calibrate(raw_prediction=float(raw_prediction), ajuste_externo=ajuste)
        prob_up = float(probs["prob_up"])
        prob_down = float(probs["prob_down"])
        take_profit = max(float(take_profit), 0.0)
        stop_loss = max(float(stop_loss), 0.0)
        spread = max(float(spread), 0.0)
        ev_buy = self.ev_calc.calculate(prob_up, take_profit, stop_loss, spread)
        ev_sell = self.ev_calc.calculate(prob_down, take_profit, stop_loss, spread)
        action = self.selector.decide(ev_buy, ev_sell, prob_up, prob_down)
        return {
            "action": action,
            "prob_up": prob_up,
            "prob_down": prob_down,
            "ev_buy": ev_buy,
            "ev_sell": ev_sell,
            "ajuste_externo": ajuste,
            "logit": float(probs["logit"]),
            "custos_totais_pct": self.ev_calc.custos_totais(spread),
        }
