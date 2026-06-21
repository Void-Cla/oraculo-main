"""Circuit breaker financeiro — PSF-04 / DA-03.

Interrompe TODA operação de trading quando o drawdown acumulado numa janela rolante
excede o limite configurado. O halt:
  - é ATIVADO automaticamente ao exceder o limite;
  - só pode ser RESETADO por ação humana explícita (nunca automaticamente);
  - PERSISTE em banco (sobrevive a restart do processo).

Capital perdido não volta — na dúvida, o breaker permanece em halt.
"""
from __future__ import annotations

import time
from typing import Any

from src.core.settings import env_float, env_int
from src.observabilidade.logger import get_logger

LOG = get_logger("circuit_breaker")

# Chave única no RepositorioConfig (estado global do processo de trading).
_CHAVE_ESTADO: str = "circuit_breaker_estado"
_MS_POR_HORA: int = 3_600_000


class CircuitBreaker:
    """Monitora drawdown em janela rolante e ativa halt irreversível-por-máquina."""

    def __init__(self, limite_drawdown_pct: float | None = None, janela_horas: int | None = None) -> None:
        # Limite de drawdown (%) e tamanho da janela (horas) — configuráveis por ambiente.
        self.limite_drawdown_pct: float = (
            float(limite_drawdown_pct) if limite_drawdown_pct is not None
            else env_float("CIRCUIT_BREAKER_DRAWDOWN_PCT", 5.0, minimo=0.0)
        )
        self.janela_horas: int = (
            int(janela_horas) if janela_horas is not None
            else env_int("CIRCUIT_BREAKER_JANELA_HORAS", 24, minimo=1)
        )
        self._em_halt: bool = False
        self._halt_motivo: str = ""
        self._halt_ts: int = 0
        self._drawdown_halt_pct: float = 0.0
        # Eventos da janela: lista de (ts_ms, pnl_usdt).
        self._eventos: list[tuple[int, float]] = []

    # ── Núcleo determinístico (sem I/O) ─────────────────────────────────────
    def registrar_resultado(self, pnl_usdt: float, capital_total: float) -> bool:
        """Registra o resultado de uma operação e retorna se o sistema está em halt."""
        agora = int(time.time() * 1000)
        self._eventos.append((agora, float(pnl_usdt or 0.0)))
        self._podar_janela(agora)
        if not self._em_halt:
            drawdown = self._drawdown_atual_pct(capital_total)
            if drawdown >= self.limite_drawdown_pct:
                self._ativar_halt(drawdown, agora)
        return self._em_halt

    def esta_em_halt(self) -> bool:
        return self._em_halt

    def resetar_halt(self, autorizado_por: str) -> dict[str, Any]:
        """Reset do halt — EXIGE identificação de quem autorizou (ação humana)."""
        autor = str(autorizado_por or "").strip()
        if not autor:
            raise ValueError("reset_de_halt_exige_autorizacao_humana_explicita")
        estado_anterior = self.estado()
        self._em_halt = False
        self._halt_motivo = ""
        self._halt_ts = 0
        self._drawdown_halt_pct = 0.0
        self._eventos.clear()
        LOG.warning("circuit_breaker_resetado", extra={"autorizado_por": autor, "estado_anterior": estado_anterior})
        return self.estado()

    def estado(self) -> dict[str, Any]:
        return {
            "em_halt": self._em_halt,
            "motivo": self._halt_motivo,
            "halt_ts": self._halt_ts,
            "drawdown_halt_pct": self._drawdown_halt_pct,
            "limite_drawdown_pct": self.limite_drawdown_pct,
            "janela_horas": self.janela_horas,
        }

    def _drawdown_atual_pct(self, capital_total: float) -> float:
        capital = max(0.0, float(capital_total or 0.0))
        if capital <= 0.0:
            return 0.0
        perdas = sum(-pnl for _, pnl in self._eventos if pnl < 0.0)
        return (perdas / capital) * 100.0

    def _ativar_halt(self, drawdown_pct: float, agora_ms: int) -> None:
        self._em_halt = True
        self._drawdown_halt_pct = round(drawdown_pct, 4)
        self._halt_ts = agora_ms
        self._halt_motivo = "drawdown_excedeu_limite"
        LOG.error(
            "circuit_breaker_halt_ativado",
            extra={"drawdown_pct": self._drawdown_halt_pct, "limite_pct": self.limite_drawdown_pct},
        )

    def _podar_janela(self, agora_ms: int) -> None:
        corte = agora_ms - self.janela_horas * _MS_POR_HORA
        self._eventos = [(ts, pnl) for ts, pnl in self._eventos if ts >= corte]

    # ── Persistência (sobrevive a restart) ──────────────────────────────────
    async def carregar(self) -> None:
        """Carrega o estado de halt persistido — chamado no startup do trading."""
        from src.persistencia.repositorio_config import RepositorioConfig

        dados = await RepositorioConfig.obter(_CHAVE_ESTADO)
        if isinstance(dados, dict):
            self._em_halt = bool(dados.get("em_halt", False))
            self._halt_motivo = str(dados.get("motivo", "") or "")
            self._halt_ts = int(dados.get("halt_ts", 0) or 0)
            self._drawdown_halt_pct = float(dados.get("drawdown_halt_pct", 0.0) or 0.0)

    async def salvar(self) -> None:
        """Persiste o estado de halt — chamado após ativar/resetar."""
        from src.persistencia.repositorio_config import RepositorioConfig

        await RepositorioConfig.definir(_CHAVE_ESTADO, self.estado())
