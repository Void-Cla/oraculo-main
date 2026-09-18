from __future__ import annotations

# Toda operação completa paga custo de transação na entrada E na saída (round-trip).
# Contar uma única perna subestima sistematicamente o custo e infla o EV. (BUG-02, DA-02)
NUMERO_DE_PERNAS = 2


class EVCalculator:
    # Default de fee = taker real da Binance Spot (0.1% = 0.001, decimal). O valor antigo
    # (0.0012) era fictício — não correspondia a taker (0.001) nem a maker c/ desconto
    # (0.00075) — e superestimava custo ~20% para quem instancia sem passar `fee` explícito
    # (ex.: walk-forward standalone), tornando o EV mais negativo do que deveria ser.
    def __init__(self, fee: float = 0.001, slippage: float = 0.0005) -> None:
        self.fee = max(0.0, float(fee))
        self.slippage = max(0.0, float(slippage))

    def custos_totais(self, spread: float = 0.0) -> float:
        # Taxa e slippage incidem nas duas pernas; o spread é custo único da decisão.
        return (self.fee + self.slippage) * NUMERO_DE_PERNAS + max(0.0, float(spread))

    def calculate(self, p_win: float, avg_win: float, avg_loss: float, spread: float = 0.0) -> float:
        p_win = max(0.0, min(1.0, float(p_win)))
        p_loss = 1.0 - p_win
        avg_win = max(0.0, float(avg_win))
        avg_loss = max(0.0, float(avg_loss))
        return (p_win * avg_win) - (p_loss * avg_loss) - self.custos_totais(spread)
