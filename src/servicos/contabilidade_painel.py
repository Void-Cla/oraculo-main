"""Qualifica números observacionais sem alterar o cálculo utilizado pelo risco."""
from __future__ import annotations

import math
from typing import Any


def valorizar_saldos_reais(
    conta: dict[str, Any], precos_usdt: dict[str, Any],
) -> dict[str, Any]:
    """Marca todos os saldos Binance sem substituir cotação ausente por zero."""
    balances = conta.get("balances")
    if not isinstance(balances, list) or not isinstance(precos_usdt, dict):
        return {
            "disponivel": False,
            "conversao_completa": False,
            "patrimonio_usdt": None,
            "ativos": [],
            "ativos_sem_cotacao": [],
            "motivo": "saldos_binance_indisponiveis",
        }

    precos = {str(ativo).upper(): preco for ativo, preco in precos_usdt.items()}
    ativos: list[dict[str, Any]] = []
    sem_cotacao: list[str] = []
    total_usdt = 0.0
    try:
        for saldo in balances:
            ativo = str(saldo.get("asset") or "").upper()
            livre = float(saldo.get("free", 0.0) or 0.0)
            travado = float(saldo.get("locked", 0.0) or 0.0)
            quantidade = livre + travado
            if not ativo or not all(math.isfinite(valor) and valor >= 0 for valor in (livre, travado)):
                return {
                    "disponivel": False,
                    "conversao_completa": False,
                    "patrimonio_usdt": None,
                    "ativos": [],
                    "ativos_sem_cotacao": [],
                    "motivo": "saldo_binance_invalido",
                }
            if quantidade <= 0.0:
                continue
            preco = 1.0 if ativo == "USDT" else precos.get(ativo)
            try:
                preco = float(preco)
            except (TypeError, ValueError, OverflowError):
                preco = None
            cotacao_disponivel = preco is not None and math.isfinite(preco) and preco > 0.0
            valor_usdt = round(quantidade * preco, 8) if cotacao_disponivel else None
            if valor_usdt is None:
                sem_cotacao.append(ativo)
            else:
                total_usdt += valor_usdt
            ativos.append(
                {
                    "ativo": ativo,
                    "livre": round(livre, 12),
                    "travado": round(travado, 12),
                    "total": round(quantidade, 12),
                    "preco_usdt": round(preco, 12) if cotacao_disponivel else None,
                    "valor_usdt": valor_usdt,
                    "cotacao_disponivel": cotacao_disponivel,
                }
            )
    except (AttributeError, TypeError, ValueError, OverflowError):
        return {
            "disponivel": False,
            "conversao_completa": False,
            "patrimonio_usdt": None,
            "ativos": [],
            "ativos_sem_cotacao": [],
            "motivo": "saldo_binance_invalido",
        }

    completo = not sem_cotacao
    return {
        "disponivel": True,
        "conversao_completa": completo,
        "patrimonio_usdt": round(total_usdt, 8) if completo else None,
        "ativos": ativos,
        "ativos_sem_cotacao": sem_cotacao,
        "motivo": "saldos_binance_marcados" if completo else "cotacao_ausente",
    }


def patrimonio_monitorado(
    conta: dict[str, Any], monitoramento: dict[str, Any],
) -> tuple[float | None, tuple[str, ...]]:
    """Compatibilidade: o monitoramento não pode reduzir o patrimônio da conta."""
    precos = monitoramento.get("precos_usdt") if isinstance(monitoramento, dict) else None
    resumo = valorizar_saldos_reais(conta, precos or {})
    escopo = tuple(sorted(item["ativo"] for item in resumo["ativos"]))
    return resumo["patrimonio_usdt"], escopo


def resumo_contabil(
    negociacoes: dict[str, Any], trades: list[dict[str, Any]], *,
    disponivel: bool, modo_testnet: bool, simbolo: str,
) -> dict[str, Any]:
    """Expõe a janela FIFO e suas limitações, separada de qualquer projeção do motor."""
    realizado = negociacoes.get("pnl_realizado_liquido_usdt") if disponivel else None
    aberto = negociacoes.get("pnl_nao_realizado_usdt") if disponivel else None
    incompleta = bool(negociacoes.get("cobertura_fifo_incompleta"))
    conversao_estimada = not simbolo.endswith("USDT") or any(
        float(t.get("commission", 0) or 0) > 0 and t.get("commissionAsset") != "USDT"
        for t in trades
    )
    tempos = [int(t.get("time", 0)) for t in trades]
    confiavel = disponivel and not incompleta and not conversao_estimada and len(trades) < 1000
    return {
        "realizado_usdt": realizado, "nao_realizado_usdt": aberto,
        "total_usdt": round(realizado + aberto, 8) if realizado is not None and aberto is not None else None,
        "resultado_trading_usdt": None,
        "resultado_trading_conciliado": False,
        "confiavel": confiavel, "cobertura_fifo_incompleta": incompleta,
        "fonte": "fills_binance_fifo_janela_consultada", "modo_testnet": modo_testnet,
        "inicio_historico_ts": min(tempos) if tempos else None,
        "fim_historico_ts": max(tempos) if tempos else None,
        "total_fills_consultados": len(trades),
        "total_fills_exibidos": len(negociacoes.get("historico", [])),
        "motivo": ("consulta_indisponivel" if not disponivel else
                   "historico_ou_conversao_incompletos" if not confiavel else "somente_janela_consultada"),
        "resultado_trading_motivo": "fills_taxas_e_fluxos_externos_nao_conciliados",
        "simulacao_custos": {"disponivel": False, "motivo": "custos_reais_nao_conciliados"},
    }
