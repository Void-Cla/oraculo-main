from __future__ import annotations


class TradeSelector:
    def __init__(
        self,
        min_ev: float = 0.001,
        min_prob: float = 0.60,
        # Razão mínima entre o movimento esperado (take_profit/stop_loss) e o custo
        # round-trip de taxas: só operar em janelas de volatilidade onde o movimento
        # esperado é pelo menos 3x o custo de abrir+fechar a posição (origem: relatório
        # de auditoria externo, filtro de movimento mínimo).
        razao_bruto_custo_minima: float = 3.0,
        # Custo round-trip default (fração, ex.: 0.003 = 0.3%). O CALLER real deve passar
        # o custo round-trip vindo do EVCalculator/filtro_ev (fonte única, DA-02) — este
        # valor é só um fallback conservador, não um novo cálculo de custo.
        custo_round_trip_pct: float = 0.003,
    ) -> None:
        self.min_ev = float(min_ev)
        self.min_prob = float(min_prob)
        self.razao_bruto_custo_minima = float(razao_bruto_custo_minima)
        self.custo_round_trip_pct = float(custo_round_trip_pct)

    def decide(
        self,
        ev_buy: float,
        ev_sell: float,
        prob_up: float,
        prob_down: float,
        take_profit: float = 0.0,
        stop_loss: float = 0.0,
    ) -> str:
        # Filtro de movimento mínimo: só aplicado quando o caller de fato passa
        # take_profit/stop_loss (>0) — caso contrário mantém compatibilidade retroativa
        # com quem chama sem esses parâmetros (ex.: ProbabilisticTradeEngine hoje).
        if take_profit > 0.0 or stop_loss > 0.0:
            movimento_max = max(take_profit, stop_loss)
            if movimento_max < self.razao_bruto_custo_minima * self.custo_round_trip_pct:
                return "HOLD"
        # Empate exato cai no HOLD (nem `>=` em BUY nem em SELL): remove o viés
        # sistemático que favorecia BUY sempre que ev_buy == ev_sell.
        if ev_buy > self.min_ev and prob_up > self.min_prob and ev_buy > ev_sell:
            return "BUY"
        if ev_sell > self.min_ev and prob_down > self.min_prob and ev_sell > ev_buy:
            return "SELL"
        return "HOLD"
