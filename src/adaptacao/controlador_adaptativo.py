from __future__ import annotations

import time
from typing import Any

# ──────────────────────────────────────────────
# Hard floors — NUNCA violar independente do mercado
# ──────────────────────────────────────────────
LUCRO_MINIMO_USDT: float = 0.01       # objetivo central: lucro líquido > $0.01
EV_MINIMO_USDT: float = 0.01          # expected value mínimo por trade
PROB_MINIMA: float = 0.50             # nunca aceitar menos de 50% de chance
COOLDOWN_MINIMO_SEG: int = 15         # intervalo mínimo entre trades (15s)
MIN_SCORE_MINIMO: float = 0.20        # score mínimo de oportunidade

# ──────────────────────────────────────────────
# Valores iniciais (ajustados adaptativamente)
# ──────────────────────────────────────────────
PARAMS_INICIAIS: dict[str, Any] = {
    "cooldown_seg": 45,
    "min_prob": 0.55,
    "min_score_oportunidade": 0.35,
    "filtro_ev_minimo_usdt": EV_MINIMO_USDT,
    "lucro_liquido_minimo_usdt": LUCRO_MINIMO_USDT,
    "lucro_liquido_minimo_pct": 0.0005,
    "binance_taxa_maker_pct": 0.1,     # % real sem assumir desconto BNB
    "binance_taxa_taker_pct": 0.1,     # % real sem assumir desconto BNB
    "slippage_pct": 0.0005,            # decimal (0.05%), NÃO multiplicado por 100
    "signal_min_ev": 0.0001,
    "signal_min_prob": 0.55,
    "signal_min_net_profit_pct": 0.0005,
    "max_spread_rel": 0.003,
    "signal_confirm_threshold": 1,
    "peso_modelo_numerico": 0.65,
    "peso_modelo_llm": 0.35,
    "limiar_variacao_numerica": 0.0015,
    "limiar_score_operacao": 0.18,
    "max_vol5": 0.02,
    "max_posicao_fracao": 0.05,
    "signal_prob_temperature": 1.0,
    "signal_prob_scale": 10.0,
    "signal_decision_window_minutes": 5,
    "signal_trade_fee_pct": 0.001,     # 0.1% decimal (atualizado pelo fee_optimizer)
    "signal_slippage_pct": 0.0005,
}

# Intervalos de ajuste
_AJUSTE_INTERVALO_SEG: float = 30.0   # roda o ajuste a cada 30s
_JANELA_HISTORICO_SEG: float = 300.0  # analisa os últimos 5 minutos
_MAX_HISTORICO: int = 100


class ControladorAdaptativo:
    """
    Autoajusta parâmetros de trading para MAXIMIZAR trades/minuto
    enquanto GARANTE lucro líquido >= 0.01 USDT por trade.

    Estratégia:
    - Se há perdas recentes → endurece thresholds para proteger capital
    - Se win rate alto → relaxa thresholds para capturar mais oportunidades
    - Se muitas rejeições por threshold → relaxa para não perder trades
    - Se poucos trades/min → reduz cooldown e thresholds
    - Hard floors nunca são violados
    """

    def __init__(self) -> None:
        self._params: dict[str, Any] = dict(PARAMS_INICIAIS)
        self._historico: list[dict[str, Any]] = []
        self._ultimo_ajuste_ts: float = 0.0

    # ──────────────────────────────────────────
    # API pública
    # ──────────────────────────────────────────

    def registrar_ciclo(
        self,
        *,
        lucro_usdt: float = 0.0,
        aprovado: bool,
        executado: bool = False,
        motivos_rejeicao: list[str] | None = None,
        taxa_efetiva_pct: float | None = None,
    ) -> None:
        """Registra resultado de um ciclo de avaliação."""
        entry: dict[str, Any] = {
            "ts": time.time(),
            "lucro_usdt": float(lucro_usdt),
            "aprovado": bool(aprovado),
            "executado": bool(executado),
            "motivos": list(motivos_rejeicao or []),
        }
        if taxa_efetiva_pct is not None:
            # Atualiza a taxa real assim que conhecida
            self._params["binance_taxa_taker_pct"] = float(taxa_efetiva_pct)
            self._params["binance_taxa_maker_pct"] = float(taxa_efetiva_pct) * 0.9
            self._params["signal_trade_fee_pct"] = float(taxa_efetiva_pct) / 100.0
        self._historico.append(entry)
        if len(self._historico) > _MAX_HISTORICO:
            self._historico = self._historico[-_MAX_HISTORICO:]

    def ajustar(self) -> dict[str, Any]:
        """
        Calcula e aplica parâmetros adaptativos.
        Retorna parâmetros atuais (com ou sem ajuste).
        """
        agora = time.time()
        if agora - self._ultimo_ajuste_ts < _AJUSTE_INTERVALO_SEG:
            return dict(self._params)
        self._ultimo_ajuste_ts = agora
        self._aplicar_regras()
        return dict(self._params)

    @property
    def params(self) -> dict[str, Any]:
        return dict(self._params)

    def status(self) -> dict[str, Any]:
        return {
            "params_atuais": dict(self._params),
            "taxa_trades_por_minuto": round(self._tpm(), 3),
            "win_rate": round(self._win_rate() or 0.0, 3),
            "houve_perda_recente": self._houve_perda_recente(),
            "rejeicoes_por_threshold_2min": self._rejeicoes_por_threshold(120),
            "total_ciclos": len(self._historico),
        }

    # ──────────────────────────────────────────
    # Métricas internas
    # ──────────────────────────────────────────

    def _janela(self, segundos: float) -> list[dict[str, Any]]:
        corte = time.time() - segundos
        return [c for c in self._historico if c["ts"] >= corte]

    def _tpm(self) -> float:
        """Trades executados nos últimos 5 minutos / 5."""
        ciclos = self._janela(_JANELA_HISTORICO_SEG)
        return sum(1 for c in ciclos if c.get("executado")) / 5.0

    def _win_rate(self) -> float | None:
        executados = [c for c in self._historico[-30:] if c.get("executado")]
        if len(executados) < 3:
            return None
        ganhos = sum(1 for c in executados if c["lucro_usdt"] >= LUCRO_MINIMO_USDT)
        return ganhos / len(executados)

    def _houve_perda_recente(self) -> bool:
        executados = [c for c in self._historico[-20:] if c.get("executado")][-5:]
        return any(c["lucro_usdt"] < 0 for c in executados)

    def _rejeicoes_por_threshold(self, janela_seg: float) -> int:
        ciclos = self._janela(janela_seg)
        _thr = {
            "probabilidade_abaixo_do_minimo",
            "score_oportunidade_baixo",
            "ev_insuficiente",
            "ev_nao_positivo",
            "lucro_liquido_pct_abaixo_do_minimo",
            "lucro_liquido_usdt_abaixo_do_minimo",
            "lucro_liquido_abaixo_do_minimo",
            "lucro_liquido_usdt_abaixo_do_minimo_2",
        }
        return sum(
            1 for c in ciclos
            if not c["aprovado"]
            and any(m.split(":")[0] in _thr for m in c["motivos"])
        )

    # ──────────────────────────────────────────
    # Motor de regras
    # ──────────────────────────────────────────

    def _aplicar_regras(self) -> None:
        p = dict(self._params)
        tpm = self._tpm()
        wr = self._win_rate()
        perda = self._houve_perda_recente()
        rej = self._rejeicoes_por_threshold(120)

        # REGRA 1 — Perda recente: endurece tudo
        if perda:
            p["min_prob"] = min(0.68, p["min_prob"] + 0.025)
            p["min_score_oportunidade"] = min(0.60, p["min_score_oportunidade"] + 0.025)
            p["cooldown_seg"] = min(180, int(p["cooldown_seg"] * 1.5))
            p["filtro_ev_minimo_usdt"] = min(0.05, p["filtro_ev_minimo_usdt"] * 1.5)
            p["lucro_liquido_minimo_pct"] = min(0.002, p["lucro_liquido_minimo_pct"] * 1.3)

        # REGRA 2 — Win rate excelente: relaxa gradualmente
        elif wr is not None and wr >= 0.72:
            p["min_prob"] = max(PROB_MINIMA, p["min_prob"] - 0.008)
            p["min_score_oportunidade"] = max(MIN_SCORE_MINIMO, p["min_score_oportunidade"] - 0.008)
            p["cooldown_seg"] = max(COOLDOWN_MINIMO_SEG, int(p["cooldown_seg"] * 0.85))
            p["filtro_ev_minimo_usdt"] = max(EV_MINIMO_USDT, p["filtro_ev_minimo_usdt"] * 0.9)
            p["lucro_liquido_minimo_pct"] = max(0.0003, p["lucro_liquido_minimo_pct"] * 0.9)

        # REGRA 3 — Muitas rejeições por threshold sem perdas: relaxa thresholds
        if rej >= 6 and not perda:
            p["min_prob"] = max(PROB_MINIMA, p["min_prob"] - 0.006)
            p["min_score_oportunidade"] = max(MIN_SCORE_MINIMO, p["min_score_oportunidade"] - 0.006)
            p["signal_min_ev"] = max(0.00005, p["signal_min_ev"] * 0.85)
            p["signal_min_net_profit_pct"] = max(0.0002, p["signal_min_net_profit_pct"] * 0.9)
            p["signal_min_prob"] = max(PROB_MINIMA, p["signal_min_prob"] - 0.005)

        # REGRA 4 — Poucos trades/min sem perdas: reduz cooldown
        if tpm < 0.3 and not perda:
            p["cooldown_seg"] = max(COOLDOWN_MINIMO_SEG, int(p["cooldown_seg"] * 0.80))

        # REGRA 5 — Muitos trades/min com win rate ok: pode ser um pouco mais seletivo
        elif tpm >= 4.0 and (wr is None or wr >= 0.65):
            p["min_prob"] = min(0.62, p["min_prob"] + 0.004)

        # ── Hard floors — nunca violar ──
        p["filtro_ev_minimo_usdt"] = max(EV_MINIMO_USDT, p["filtro_ev_minimo_usdt"])
        p["lucro_liquido_minimo_usdt"] = LUCRO_MINIMO_USDT
        p["min_prob"] = max(PROB_MINIMA, p["min_prob"])
        p["min_score_oportunidade"] = max(MIN_SCORE_MINIMO, p["min_score_oportunidade"])
        p["cooldown_seg"] = max(COOLDOWN_MINIMO_SEG, int(p["cooldown_seg"]))
        p["signal_min_prob"] = max(PROB_MINIMA, p["signal_min_prob"])
        p["signal_min_ev"] = max(0.00005, p["signal_min_ev"])
        p["signal_min_net_profit_pct"] = max(0.0002, p["signal_min_net_profit_pct"])
        p["lucro_liquido_minimo_pct"] = max(0.0002, p["lucro_liquido_minimo_pct"])

        self._params = p
