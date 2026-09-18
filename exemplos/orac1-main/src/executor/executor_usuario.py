from __future__ import annotations

from typing import Any

from src.core.settings import env_float
from src.executor.gerenciador_ordens import GerenciadorOrdens


class ExecutorIsoladoUsuario:
    def __init__(self, usuario: dict[str, Any]) -> None:
        self.usuario = usuario
        self.gerenciador = GerenciadorOrdens()

    async def preparar_execucao(self, aprovacao_risco: dict[str, Any], preco_referencia: float) -> dict[str, Any]:
        quantidade = max(aprovacao_risco["notional_sugerido"] / max(preco_referencia, 1e-9), 0.0)
        gatilho_offset = env_float("SIGNAL_TRIGGER_OFFSET_PCT", 0.001, minimo=0.0)
        lado = aprovacao_risco["acao"]
        preco_gatilho = preco_referencia * (1.0 - gatilho_offset if lado == "BUY" else 1.0 + gatilho_offset)
        janela_decisao = aprovacao_risco.get("janela_decisao", {})
        simulacao = self.gerenciador.simular_ordem(
            lado=lado,
            quantidade=quantidade,
            preco=preco_referencia,
            preco_gatilho=preco_gatilho,
            executar_apos_ts=int(janela_decisao.get("executar_apos_ts", 0) or 0),
            janela_decisao_minutos=int(janela_decisao.get("janela_minutos", 0) or 0),
        )
        return {
            "usuario_id": self.usuario["id"],
            "usuario_nome": self.usuario["nome"],
            "simbolo": aprovacao_risco["simbolo"],
            "acao": lado,
            "modo": "paper" if aprovacao_risco["paper_trading"] else ("testnet" if self.usuario["testnet"] else "real"),
            "fracao_capital": aprovacao_risco["fracao_capital"],
            "notional_sugerido": aprovacao_risco["notional_sugerido"],
            "gatilho_offset_pct": gatilho_offset,
            "janela_decisao": janela_decisao,
            "confirmacao_multi_timeframe": aprovacao_risco.get("confirmacao_multi_timeframe", {}),
            "probabilidade_trade": aprovacao_risco.get("probabilidade_trade", {}),
            "lucro_liquido_esperado_pct": aprovacao_risco.get("lucro_liquido_esperado_pct", 0.0),
            "simulacao_ordem": simulacao,
        }
