from __future__ import annotations


class TradeSelector:
    def __init__(self, min_ev: float = 0.001, min_prob: float = 0.60) -> None:
        self.min_ev = float(min_ev)
        self.min_prob = float(min_prob)

    def decide(self, ev_buy: float, ev_sell: float, prob_up: float, prob_down: float) -> str:
        if ev_buy > self.min_ev and prob_up > self.min_prob and ev_buy >= ev_sell:
            return "BUY"
        if ev_sell > self.min_ev and prob_down > self.min_prob and ev_sell >= ev_buy:
            return "SELL"
        return "HOLD"
