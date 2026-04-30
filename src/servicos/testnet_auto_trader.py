from __future__ import annotations

import asyncio
import copy
import time
from typing import Any

from src.binance_api.cliente import ClienteBinance
from src.binance_api.coletor_velas_rest import coletar_e_persistir
from src.contratos.trading import ExecutionPlan, RiskApproval, SignalDecision
from src.executor.executor_usuario import ExecutorIsoladoUsuario
from src.executor.gerenciador_ordens import GerenciadorOrdens, NotionalTooSmall
from src.modelagem.treinador_online import ajustar_online
from src.multiativo.config import ativo_cotacao, pares_monitorados, par_usdt_do_ativo, validar_par_monitorado
from src.multiativo.fee_optimizer import montar_perfil_taxas
from src.multiativo.orquestrador import montar_monitoramento_multiativo
from src.observabilidade.logger import get_logger
from src.persistencia.repositorio_auditoria import RepositorioAuditoria
from src.persistencia.repositorio_config import RepositorioConfig
from src.persistencia.repositorio_livro_topo import RepositorioLivroTopo
from src.persistencia.repositorio_ohlcv import RepositorioOhlcv
from src.persistencia.repositorio_outcomes import RepositorioOutcomes
from src.risco.risk_engine import avaliar_sinal_para_usuario
from src.servicos.ajustes import obter_ajustes_risco, obter_ajustes_sinal
from src.core.settings import env_int, env_float
from src.servicos.noticias import obter_noticias_para_peso
from src.sinais.signal_engine import gerar_sinal_orquestrado
from src.tarefas.retomada import operacoes_bloqueadas_por_retomada

LOG = get_logger("auto_trader")

_CHAVES_GLOBAIS_ESTADO = {
    "notional_usdt",
    "intervalo_segundos",
    "modo_testnet",
    "modo",
    "ativo",
    "consecutive_errors",
    "circuit_tripped",
    "daily_loss_usdt",
    "max_daily_loss_usdt",
    "consecutive_errors_limit",
    "pares_estado",
    "simbolo_foco",
    "pares_ranqueados",
}


def _saldo_ativo(conta: dict[str, Any], ativo: str) -> float:
    for balance in conta.get("balances", []):
        if str(balance.get("asset", "")).upper() != ativo.upper():
            continue
        return float(balance.get("free", 0.0) or 0.0)
    return 0.0


def _ativo_base(simbolo: str) -> str:
    simbolo = simbolo.upper()
    if simbolo.endswith("USDT"):
        return simbolo[:-4]
    return simbolo[:-3]


def _ativo_quote(simbolo: str) -> str:
    return ativo_cotacao(simbolo)


def _preco_ativo_usdt(ativo: str, precos_usdt: dict[str, float]) -> float:
    if ativo.upper() == "USDT":
        return 1.0
    return max(0.0, float(precos_usdt.get(ativo.upper(), 0.0) or 0.0))


def _preco_par_usdt(simbolo: str, preco_par: float, precos_usdt: dict[str, float]) -> float:
    return max(0.0, float(preco_par or 0.0)) * _preco_ativo_usdt(_ativo_quote(simbolo), precos_usdt)


def _notional_quote_para_usdt(notional_quote: float, preco_quote_usdt: float) -> float:
    return max(0.0, float(notional_quote or 0.0)) * max(0.0, float(preco_quote_usdt or 0.0))


def _limiar_residuo_ignorado_usdt() -> float:
    return env_float("AUTO_IGNORAR_RESIDUO_ABAIXO_USDT", 5.0, minimo=0.0)


def _valor_posicao_usdt(saldo_base: float, preco_atual_usdt: float) -> float:
    return max(0.0, saldo_base) * max(0.0, preco_atual_usdt)


def _custos_ciclo_pct(ajustes_sinal: dict[str, Any], spread_rel: float) -> float:
    taxa_trade = max(0.0, float(ajustes_sinal.get("signal_trade_fee_pct", 0.0012) or 0.0))
    slippage = max(0.0, float(ajustes_sinal.get("signal_slippage_pct", 0.0005) or 0.0))
    return (taxa_trade * 2.0) + (slippage * 2.0) + max(0.0, spread_rel)


def _piso_lucro_percentual(
    ajustes_sinal: dict[str, Any],
    *,
    notional_usdt: float,
    lucro_liquido_minimo_usdt: float,
) -> float:
    notional_base = max(0.0, float(notional_usdt or 0.0))
    spread_piso = env_float("AUTO_SPREAD_PISO_PCT", 0.0002, minimo=0.0)
    multiplicador_seguranca = env_float("AUTO_EDGE_SAFETY_MULTIPLIER", 1.05, minimo=1.0)
    piso_pct_env = env_float("AUTO_MIN_NET_PROFIT_PCT_FLOOR", 0.0004, minimo=0.0)
    custos_pct = _custos_ciclo_pct(ajustes_sinal, spread_piso)
    # `lucro_liquido_esperado_pct` ja vem liquido de custos do signal engine.
    # Aqui entra apenas uma margem operacional extra, nao o custo inteiro novamente.
    piso_por_buffer = custos_pct * max(0.0, multiplicador_seguranca - 1.0)
    piso_por_usdt = (float(lucro_liquido_minimo_usdt or 0.0) / notional_base) if notional_base > 0.0 else 0.0
    # No modo auto, o piso de lucro precisa responder ao capital e ao alvo
    # liquido real do perfil. Nao reutilizamos cegamente o override manual
    # salvo em `ajustes_sinal`, porque ele pode ficar muito alto para
    # micro-oportunidades e travar o bot inteiro.
    return max(piso_por_buffer, piso_por_usdt, piso_pct_env)


def _data_operacional() -> str:
    return time.strftime("%Y-%m-%d")


def _meta_lucro_segura_do_dia(state: dict[str, Any], capital_diario_usdt: float) -> float:
    historico = list((state.get("historico_ciclos") or [])[-12:])
    lucros_positivos = [float(item.get("lucro_liquido_usdt", 0.0) or 0.0) for item in historico if float(item.get("lucro_liquido_usdt", 0.0) or 0.0) > 0.0]
    meta_base = max(0.15, float(capital_diario_usdt or 0.0) * 0.02)
    if lucros_positivos:
        media_positiva = sum(lucros_positivos) / max(len(lucros_positivos), 1)
        meta_base = max(meta_base, media_positiva)
        meta_base = min(meta_base, max(lucros_positivos) * 1.2)
    return round(max(0.15, meta_base), 4)


def _construir_perfis_capital(
    state: dict[str, Any],
    *,
    capital_total_usdt: float,
    ajustes_sinal: dict[str, Any],
    min_notional_usdt: float,
) -> list[dict[str, Any]]:
    capital_total = max(0.0, float(capital_total_usdt or 0.0))
    capital_mini = capital_total * 0.50
    capital_ganancioso = capital_total * 0.25
    capital_diario = max(0.0, capital_total - capital_mini - capital_ganancioso)
    meta_diaria_usdt = _meta_lucro_segura_do_dia(state, capital_diario)
    perfil_diario_bloqueado = str(state.get("perfil_diario_ultima_data") or "") == _data_operacional()

    perfis_brutos = [
        {
            "id": "mini",
            "nome": "Mini trading",
            "descricao": "50% do capital para oportunidades frequentes com lucro liquido minimo de US$ 0,01.",
            "fracao_capital": 0.50,
            "capital_usdt": capital_mini,
            "lucro_minimo_usdt": 0.01,
            "min_confianca": 0.42,
            "min_probabilidade": 0.55,
            "min_confirmacoes": 1,
            "tempo_minimo_posicao_segundos": 0,
            "multiplicador_trailing": 0.20,
            "stop_protecao_pct": 0.0015,
            "requer_sinal_sell_para_saida": False,
            "incremento_alvo_pct": 0.0,
        },
        {
            "id": "ganancioso",
            "nome": "Trading ganancioso",
            "descricao": "25% do capital para operacoes mais seletivas com alvo minimo de US$ 0,50.",
            "fracao_capital": 0.25,
            "capital_usdt": capital_ganancioso,
            "lucro_minimo_usdt": 0.50,
            "min_confianca": 0.55,
            "min_probabilidade": 0.60,
            "min_confirmacoes": 2,
            "tempo_minimo_posicao_segundos": 45,
            "multiplicador_trailing": 0.45,
            "stop_protecao_pct": 0.0020,
            "requer_sinal_sell_para_saida": True,
            "incremento_alvo_pct": 0.10,
        },
        {
            "id": "diario",
            "nome": "Trade diario",
            "descricao": "25% do capital reservado para a melhor oportunidade segura do dia.",
            "fracao_capital": 0.25,
            "capital_usdt": capital_diario,
            "lucro_minimo_usdt": meta_diaria_usdt,
            "min_confianca": 0.60,
            "min_probabilidade": 0.62,
            "min_confirmacoes": 2,
            "tempo_minimo_posicao_segundos": 300,
            "multiplicador_trailing": 0.55,
            "stop_protecao_pct": 0.0030,
            "requer_sinal_sell_para_saida": True,
            "incremento_alvo_pct": 0.20,
        },
    ]

    perfis: list[dict[str, Any]] = []
    for perfil in perfis_brutos:
        capital_perfil = max(0.0, float(perfil["capital_usdt"] or 0.0))
        lucro_minimo = max(0.01, float(perfil["lucro_minimo_usdt"] or 0.0))
        lucro_minimo_pct = _piso_lucro_percentual(
            ajustes_sinal,
            notional_usdt=capital_perfil,
            lucro_liquido_minimo_usdt=lucro_minimo,
        ) if capital_perfil > 0.0 else 0.0
        habilitado = capital_perfil >= max(min_notional_usdt, 1e-9)
        motivo = "pronto"
        if not habilitado:
            motivo = "capital_do_perfil_abaixo_do_minimo"
        elif perfil["id"] == "diario" and perfil_diario_bloqueado:
            habilitado = False
            motivo = "trade_diario_ja_usado_hoje"
        perfis.append(
            {
                **perfil,
                "capital_usdt": capital_perfil,
                "lucro_minimo_usdt": lucro_minimo,
                "lucro_minimo_pct": lucro_minimo_pct,
                "habilitado": habilitado,
                "motivo_status": motivo,
                "usado_hoje": bool(perfil["id"] == "diario" and perfil_diario_bloqueado),
                "lucro_esperado_usdt": 0.0,
                "confirmacao_composta": {},
            }
        )
    state["perfis_capital"] = perfis
    return perfis


def _obter_perfil(perfis: list[dict[str, Any]], perfil_id: str | None) -> dict[str, Any] | None:
    perfil_id_norm = str(perfil_id or "").strip().lower()
    for perfil in perfis:
        if str(perfil.get("id") or "").lower() == perfil_id_norm:
            return dict(perfil)
    return None


def _avaliar_confirmacao_composta(
    *,
    sinal: SignalDecision,
    perfil: dict[str, Any] | None,
    para_saida: bool = False,
) -> dict[str, Any]:
    perfil = dict(perfil or {})
    consenso = dict(sinal.detalhe.get("consenso") or {})
    required_conf = env_float("MIN_SIGNAL_CONFIDENCE", 0.50, minimo=0.0)
    min_confianca = max(0.35, float(perfil.get("min_confianca", required_conf) or required_conf))
    min_probabilidade = max(0.50, float(perfil.get("min_probabilidade", min_confianca) or min_confianca))
    min_confirmacoes = max(1, int(perfil.get("min_confirmacoes", 1) or 1))
    if para_saida:
        min_confirmacoes = max(1, min_confirmacoes - 1)

    acao_referencia = "SELL" if para_saida else str(sinal.acao or "HOLD").upper()
    llm_conf = float((sinal.probabilidade_trade or {}).get("llm", 0.0) or 0.0)
    prob_up = float((sinal.probabilidade_trade or {}).get("prob_up", 0.0) or 0.0)
    prob_down = float((sinal.probabilidade_trade or {}).get("prob_down", 0.0) or 0.0)
    prob_direcional = prob_down if acao_referencia == "SELL" else prob_up
    multi_conf = bool((sinal.confirmacao_multi_timeframe or {}).get("confirmado", False))
    score_consenso = abs(float(consenso.get("score_total", 0.0) or 0.0))
    acao_consenso = str(consenso.get("acao_consenso", "HOLD") or "HOLD").upper()
    confirmado_orquestrador = bool(sinal.detalhe.get("confirmado", False))

    fontes = []
    if float(sinal.confianca or 0.0) >= min_confianca:
        fontes.append("sinal")
    if llm_conf >= min_confianca:
        fontes.append("llm")
    if prob_direcional >= min_probabilidade:
        fontes.append("probabilidade")
    if multi_conf:
        fontes.append("multi_timeframe")
    if acao_consenso == acao_referencia and score_consenso >= 0.08:
        fontes.append("consenso")
    if confirmado_orquestrador:
        fontes.append("orquestrador")

    pontuacao = len(fontes)
    confirmado = pontuacao >= min_confirmacoes
    return {
        "confirmado": confirmado,
        "pontuacao": pontuacao,
        "min_confirmacoes": min_confirmacoes,
        "min_confianca": min_confianca,
        "min_probabilidade": min_probabilidade,
        "fontes": fontes,
        "llm": llm_conf,
        "prob_direcional": prob_direcional,
        "multi_timeframe": multi_conf,
        "acao_consenso": acao_consenso,
    }


def _selecionar_perfil_entrada(
    *,
    state: dict[str, Any],
    sinal: SignalDecision,
    perfis: list[dict[str, Any]],
    min_notional_usdt: float,
    saldo_quote_livre_usdt: float,
) -> tuple[dict[str, Any] | None, str]:
    if str(sinal.acao or "HOLD").upper() != "BUY":
        return (None, "acao_atual_nao_usa_perfil_de_entrada")

    candidatos: list[dict[str, Any]] = []
    for perfil in perfis:
        capital_util = min(max(0.0, float(perfil.get("capital_usdt", 0.0) or 0.0)), max(0.0, float(saldo_quote_livre_usdt or 0.0)))
        if capital_util < max(min_notional_usdt, 1e-9):
            continue
        if not bool(perfil.get("habilitado")):
            continue
        confirmacao = _avaliar_confirmacao_composta(sinal=sinal, perfil=perfil)
        lucro_esperado_usdt = capital_util * max(0.0, float(sinal.lucro_liquido_esperado_pct or 0.0))
        if lucro_esperado_usdt + 1e-9 < float(perfil.get("lucro_minimo_usdt", 0.0) or 0.0):
            continue
        if not confirmacao["confirmado"]:
            continue
        prioridade = {"mini": 1, "ganancioso": 2, "diario": 3}.get(str(perfil.get("id") or "").lower(), 0)
        score = lucro_esperado_usdt + (float(sinal.confianca or 0.0) * 0.05) + (float(confirmacao["pontuacao"]) * 0.01)
        candidatos.append(
            {
                **perfil,
                "capital_usdt_util": capital_util,
                "lucro_esperado_usdt": lucro_esperado_usdt,
                "confirmacao_composta": confirmacao,
                "_prioridade": prioridade,
                "_score": score,
            }
        )

    if not candidatos:
        return (None, "nenhum_perfil_encontrou_lucro_liquido_viavel")
    melhor = max(candidatos, key=lambda item: (float(item["_prioridade"]), float(item["_score"])))
    melhor = {chave: valor for chave, valor in melhor.items() if not str(chave).startswith("_")}
    state["perfis_capital"] = [
        melhor if str(perfil.get("id") or "") == str(melhor.get("id") or "") else perfil
        for perfil in perfis
    ]
    return (melhor, "perfil_selecionado")


def _tem_posicao_ativa(
    *,
    saldo_base: float,
    preco_atual_usdt: float,
    min_notional_usdt: float,
    min_qty: float,
) -> bool:
    return saldo_base >= max(min_qty, 0.0) and _valor_posicao_usdt(saldo_base, preco_atual_usdt) >= max(min_notional_usdt, 1e-9)


def _novo_id_ciclo(state: dict[str, Any]) -> int:
    proximo = int(state.get("sequencia_ciclo", 0) or 0) + 1
    state["sequencia_ciclo"] = proximo
    return proximo


def _preco_compra_referencia(trades: list[dict[str, Any]], preco_padrao: float) -> float:
    compras = [item for item in trades if bool(item.get("isBuyer"))]
    ultima_compra = max(compras, key=lambda item: int(item.get("time", 0) or 0), default=None)
    try:
        return float((ultima_compra or {}).get("price", preco_padrao) or preco_padrao)
    except (TypeError, ValueError):
        return float(preco_padrao or 0.0)


def _resumir_extrato_par(trades: list[dict[str, Any]], preco_padrao_par: float) -> dict[str, Any]:
    ordenados = sorted((trades or []), key=lambda item: int(item.get("time", 0) or 0), reverse=True)
    ultimo_trade = ordenados[0] if ordenados else {}
    ultima_compra = next((item for item in ordenados if bool(item.get("isBuyer"))), {})
    ultima_venda = next((item for item in ordenados if not bool(item.get("isBuyer"))), {})

    def _preco_trade(trade: dict[str, Any]) -> float:
        try:
            return float((trade or {}).get("price", preco_padrao_par) or preco_padrao_par)
        except (TypeError, ValueError):
            return float(preco_padrao_par or 0.0)

    ultima_acao = "SEM_HISTORICO"
    if ultimo_trade:
        ultima_acao = "BUY" if bool(ultimo_trade.get("isBuyer")) else "SELL"

    return {
        "ultima_acao": ultima_acao,
        "ultimo_trade_ts": int((ultimo_trade or {}).get("time", 0) or 0),
        "ultimo_trade_preco_par": _preco_trade(ultimo_trade),
        "ultima_compra_ts": int((ultima_compra or {}).get("time", 0) or 0),
        "ultima_compra_preco_par": _preco_trade(ultima_compra),
        "ultima_venda_ts": int((ultima_venda or {}).get("time", 0) or 0),
        "ultima_venda_preco_par": _preco_trade(ultima_venda),
        "tem_historico": bool(ordenados),
    }


def _definir_proxima_acao_esperada(
    *,
    extrato: dict[str, Any],
    saldo_base: float,
    preco_atual_usdt: float,
    min_notional_operacional_usdt: float,
    min_qty: float,
) -> dict[str, Any]:
    notional_base = _valor_posicao_usdt(saldo_base, preco_atual_usdt)
    limiar_residuo_usdt = _limiar_residuo_ignorado_usdt()
    piso_operacional_usdt = max(min_notional_operacional_usdt, limiar_residuo_usdt, 1e-9)
    tem_posicao_operacional = saldo_base >= max(min_qty, 0.0) and notional_base >= piso_operacional_usdt
    if tem_posicao_operacional:
        ultima_acao = str(extrato.get("ultima_acao") or "SEM_HISTORICO").upper()
        if ultima_acao == "BUY":
            motivo = "ultima_compra_aberta_no_par"
        elif ultima_acao == "SELL":
            motivo = "saldo_base_remanescente_apos_venda"
        else:
            motivo = "saldo_base_disponivel_para_realizacao"
        return {
            "acao": "SELL",
            "motivo": motivo,
            "tem_posicao_operacional": True,
            "notional_base_usdt": notional_base,
        }

    saldo_residual = saldo_base >= max(min_qty, 0.0) and notional_base >= max(limiar_residuo_usdt, 1e-9)
    ultima_acao = str(extrato.get("ultima_acao") or "SEM_HISTORICO").upper()
    if saldo_residual:
        motivo = "saldo_residual_abaixo_do_minimo_operacional"
    elif ultima_acao == "SELL":
        motivo = "ultima_venda_encerrada_sem_posicao_aberta"
    elif ultima_acao == "BUY":
        motivo = "ultima_compra_ja_foi_encerrada"
    else:
        motivo = "sem_historico_no_par"
    return {
        "acao": "BUY",
        "motivo": motivo,
        "tem_posicao_operacional": False,
        "notional_base_usdt": notional_base,
    }


def _saldo_livre(saldos: dict[str, dict[str, float]], ativo: str) -> float:
    return max(0.0, float(((saldos.get(ativo.upper()) or {}).get("livre")) or 0.0))


def _saldo_total_estimado_usdt(saldos: dict[str, dict[str, float]]) -> float:
    return max(
        0.0,
        sum(float((item or {}).get("valor_estimado_usdt", 0.0) or 0.0) for item in saldos.values()),
    )


def _saldo_ativo_usdt(saldos: dict[str, dict[str, float]], ativo: str, precos_usdt: dict[str, float]) -> float:
    saldo_livre = _saldo_livre(saldos, ativo)
    if ativo.upper() == "USDT":
        valor_usdt = saldo_livre
    else:
        valor_usdt = saldo_livre * _preco_ativo_usdt(ativo, precos_usdt)
    if 0.0 < valor_usdt < _limiar_residuo_ignorado_usdt():
        return 0.0
    return valor_usdt


def _selecionar_simbolo_entrada(
    state: dict[str, Any],
    scanner: dict[str, Any] | None,
    *,
    saldos: dict[str, dict[str, float]] | None = None,
    precos_usdt: dict[str, float] | None = None,
) -> str:
    simbolo_atual = str(state.get("simbolo", "BTCUSDT") or "BTCUSDT").upper()
    try:
        fallback = validar_par_monitorado(simbolo_atual)
    except ValueError:
        fallback = pares_monitorados()[0]
    saldos = saldos or {}
    precos_usdt = precos_usdt or {}
    pares = list((scanner or {}).get("pares") or [])
    for item in pares:
        simbolo = str(item.get("simbolo") or "").upper()
        acao = str(item.get("acao_sugerida") or "HOLD").upper()
        lucro_pct = float(item.get("lucro_liquido_esperado_pct", 0.0) or 0.0)
        quote_usdt = _saldo_ativo_usdt(saldos, _ativo_quote(simbolo), precos_usdt)
        if simbolo and acao == "BUY" and lucro_pct > 0.0 and quote_usdt > 0.0:
            return simbolo
    for item in pares:
        simbolo = str(item.get("simbolo") or "").upper()
        base_usdt = _saldo_ativo_usdt(saldos, _ativo_base(simbolo), precos_usdt)
        if simbolo and base_usdt > 0.0:
            return simbolo
    return fallback


def _ranquear_simbolos_monitorados(
    estado_global: dict[str, Any],
    *,
    scanner: dict[str, Any] | None,
    saldos: dict[str, dict[str, float]] | None,
    precos_usdt: dict[str, float] | None,
    sinais: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    scanner = dict(scanner or {})
    saldos = saldos or {}
    precos_usdt = precos_usdt or {}
    sinais = sinais or {}
    scanner_index = {
        str(item.get("simbolo") or "").upper(): dict(item)
        for item in list(scanner.get("pares") or [])
        if str(item.get("simbolo") or "").strip()
    }
    melhor_scanner = str((scanner.get("melhor_oportunidade") or {}).get("simbolo") or "").upper()
    ranking: list[dict[str, Any]] = []

    for simbolo in pares_monitorados():
        estado_par = _obter_estado_par(estado_global, simbolo)
        scanner_item = scanner_index.get(simbolo, {})
        sinal_item = dict(sinais.get(simbolo) or {})
        base_usdt = _saldo_ativo_usdt(saldos, _ativo_base(simbolo), precos_usdt)
        quote_usdt = _saldo_ativo_usdt(saldos, _ativo_quote(simbolo), precos_usdt)
        ciclo_ativo = bool(estado_par.get("ciclo_ativo"))
        estado_ciclo = str(estado_par.get("estado_ciclo") or "").upper()
        ultimo_motivo = str(estado_par.get("ultimo_motivo") or "")
        esperado = str(estado_par.get("proxima_acao_esperada") or "BUY").upper()
        acao_sugerida = str(
            sinal_item.get(
                "acao",
                scanner_item.get("acao_sugerida", "HOLD"),
            )
            or "HOLD"
        ).upper()
        lucro_pct = float(
            sinal_item.get(
                "lucro_liquido_esperado_pct",
                scanner_item.get("lucro_liquido_esperado_pct", 0.0),
            )
            or 0.0
        )
        score_oportunidade = float(scanner_item.get("score_oportunidade", 0.0) or 0.0)
        bloqueado = ultimo_motivo in {
            "notional_abaixo_do_minimo_saida",
            "notional_ajuste_falhou_saida",
            "saldo_legado_abaixo_do_minimo_operacional",
            "saida_sem_confirmacao_composta",
        }

        acao_prioritaria = "HOLD"
        motivo = "monitoramento_passivo"
        prioridade = 0.0

        fluxo_aguarda_compra = (not ciclo_ativo) and esperado == "BUY"
        if base_usdt > 0.0 and (acao_sugerida == "SELL" or esperado == "SELL" or ciclo_ativo):
            if fluxo_aguarda_compra and acao_sugerida == "SELL":
                acao_prioritaria = "HOLD"
                motivo = "fluxo_do_par_aguarda_compra"
                prioridade = 8.0 + max(0.0, score_oportunidade) * 10.0
            else:
                acao_prioritaria = "SELL"
                motivo = "posicao_pronta_para_monitorar_saida"
                prioridade = 220.0 + min(base_usdt, 500.0) * 0.05
                if acao_sugerida == "SELL":
                    prioridade += 35.0
                if esperado == "SELL":
                    prioridade += 20.0
                if ciclo_ativo:
                    prioridade += 15.0
                if estado_ciclo in {"STOP_PROTECAO", "REALIZANDO_LUCRO", "TRAVANDO_LUCRO"}:
                    prioridade += 15.0
                if bloqueado:
                    prioridade -= 260.0
                    motivo = "posicao_bloqueada_abaixo_do_minimo_operacional"
        elif acao_sugerida == "BUY" and quote_usdt > 0.0:
            acao_prioritaria = "BUY"
            motivo = "oportunidade_de_entrada"
            prioridade = 100.0 + min(quote_usdt, 500.0) * 0.01
            if simbolo == melhor_scanner:
                prioridade += 18.0
        else:
            if simbolo == str(estado_global.get("simbolo_foco") or "").upper():
                prioridade += 5.0

        prioridade += max(0.0, lucro_pct) * 1000.0
        prioridade += max(0.0, score_oportunidade) * 100.0
        ranking.append(
            {
                "simbolo": simbolo,
                "prioridade": round(prioridade, 4),
                "acao_prioritaria": acao_prioritaria,
                "motivo_prioridade": motivo,
                "ciclo_ativo": ciclo_ativo,
                "estado_ciclo": estado_ciclo or "AGUARDANDO_ENTRADA",
                "saldo_base_usdt": round(base_usdt, 4),
                "saldo_quote_usdt": round(quote_usdt, 4),
                "lucro_liquido_esperado_pct": round(lucro_pct, 6),
                "score_oportunidade": round(score_oportunidade, 6),
            }
        )

    ranking.sort(
        key=lambda item: (
            float(item.get("prioridade", 0.0) or 0.0),
            1 if str(item.get("acao_prioritaria") or "").upper() == "SELL" else 0,
            str(item.get("simbolo") or ""),
        ),
        reverse=True,
    )
    return ranking


def _selecionar_simbolo_foco(
    estado_global: dict[str, Any],
    ranking: list[dict[str, Any]],
) -> str:
    simbolo_fallback = str((ranking[0] if ranking else {}).get("simbolo") or "").upper()
    for item in ranking:
        simbolo = str(item.get("simbolo") or "").upper()
        if not simbolo:
            continue
        estado_par = _obter_estado_par(estado_global, simbolo)
        esperado = str(estado_par.get("proxima_acao_esperada") or "BUY").upper()
        ciclo_ativo = bool(estado_par.get("ciclo_ativo"))
        acao_prioritaria = str(item.get("acao_prioritaria") or "HOLD").upper()
        if not ciclo_ativo and esperado == "BUY" and acao_prioritaria == "SELL":
            continue
        return simbolo
    return simbolo_fallback


def _ajustes_sinal_com_taxa_efetiva(ajustes_sinal: dict[str, Any], perfil_taxas: dict[str, Any]) -> dict[str, Any]:
    ajustes_exec = dict(ajustes_sinal)
    taxa_taker_efetiva = float(perfil_taxas.get("taker_decimal_efetiva", 0.0) or 0.0)
    if taxa_taker_efetiva > 0.0:
        ajustes_exec["signal_trade_fee_pct"] = taxa_taker_efetiva
    return ajustes_exec


def _ajustes_microtrading_auto(
    ajustes_sinal: dict[str, Any],
    *,
    notional_usdt: float,
    lucro_liquido_minimo_usdt: float,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ajustes_auto = dict(ajustes_sinal)
    notional_base = max(0.0, float(notional_usdt or 0.0))
    lucro_minimo_usdt = max(env_float("AUTO_LUCRO_LIQUIDO_MINIMO_USDT_FLOOR", 0.01, minimo=0.01), float(lucro_liquido_minimo_usdt or 0.0))
    piso_lucro_pct = _piso_lucro_percentual(
        ajustes_auto,
        notional_usdt=notional_base,
        lucro_liquido_minimo_usdt=lucro_minimo_usdt,
    )
    ajustes_auto["auto_lucro_liquido_minimo_usdt"] = lucro_minimo_usdt
    ajustes_auto["signal_min_net_profit_pct"] = piso_lucro_pct
    ajustes_auto["signal_confirm_threshold"] = max(int(ajustes_auto.get("signal_confirm_threshold", 2) or 2), 2)
    ajustes_auto["signal_decision_window_minutes"] = max(int(ajustes_auto.get("signal_decision_window_minutes", 10) or 10), 3)
    ajustes_auto["limiar_score_operacao"] = max(float(ajustes_auto.get("limiar_score_operacao", 0.18) or 0.18), 0.18)
    ajustes_auto["limiar_variacao_numerica"] = max(float(ajustes_auto.get("limiar_variacao_numerica", 0.0015) or 0.0015), 0.0018)
    ajustes_auto["signal_min_ev"] = max(float(ajustes_auto.get("signal_min_ev", 0.0006) or 0.0006), max(0.0006, piso_lucro_pct * 0.40))
    ajustes_auto["signal_min_prob"] = max(float(ajustes_auto.get("signal_min_prob", 0.57) or 0.57), 0.57)
    historico = list(((state or {}).get("historico_ciclos")) or [])[-6:]
    if historico:
        ganhos = [float(item.get("lucro_liquido_usdt", 0.0) or 0.0) for item in historico]
        retornos = [float(item.get("retorno_liquido_pct", 0.0) or 0.0) for item in historico]
        win_rate = sum(1 for item in ganhos if item > 0.0) / max(len(ganhos), 1)
        lucro_medio = sum(ganhos) / max(len(ganhos), 1)
        retorno_medio = sum(retornos) / max(len(retornos), 1)
        if win_rate >= 0.75 and lucro_medio > lucro_minimo_usdt and retorno_medio > piso_lucro_pct:
            ajustes_auto["signal_min_prob"] = max(0.55, float(ajustes_auto["signal_min_prob"]) - 0.01)
            ajustes_auto["signal_min_ev"] = max(0.0005, float(ajustes_auto["signal_min_ev"]) * 0.94)
            ajustes_auto["limiar_score_operacao"] = max(0.16, float(ajustes_auto["limiar_score_operacao"]) - 0.01)
            ajustes_auto["signal_min_net_profit_pct"] = max(piso_lucro_pct, float(ajustes_auto["signal_min_net_profit_pct"]) * 0.94)
        elif win_rate <= 0.55 or lucro_medio <= 0.0 or retorno_medio <= 0.0:
            ajustes_auto["signal_min_prob"] = min(0.64, float(ajustes_auto["signal_min_prob"]) + 0.01)
            ajustes_auto["signal_min_ev"] = min(0.0015, float(ajustes_auto["signal_min_ev"]) * 1.08)
            ajustes_auto["limiar_score_operacao"] = min(0.24, float(ajustes_auto["limiar_score_operacao"]) + 0.01)
            ajustes_auto["signal_min_net_profit_pct"] = min(0.0030, float(ajustes_auto["signal_min_net_profit_pct"]) * 1.08)
    return ajustes_auto


def _registrar_contexto_entrada_ciclo(state: dict[str, Any], *, sinal: SignalDecision) -> None:
    previsao_modelo = dict(sinal.detalhe.get("previsao_modelo") or {})
    state["ciclo_features_entrada"] = dict(sinal.features or {})
    state["ciclo_previsao_ts"] = int(sinal.ts or int(time.time() * 1000))
    state["ciclo_previsao_y_hat"] = float(
        previsao_modelo.get("y_cal", previsao_modelo.get("y_hat", state.get("ciclo_preco_entrada", 0.0))) or 0.0
    )


def _quantidade_carteira_para_capital(
    *,
    saldo_base_total: float,
    preco_atual_usdt: float,
    notional_teto: float,
    step_size: float,
    min_qty: float,
    ger: GerenciadorOrdens,
) -> float:
    quantidade_alvo = max(0.0, float(saldo_base_total or 0.0))
    if notional_teto > 0.0 and preco_atual_usdt > 0.0:
        quantidade_alvo = min(quantidade_alvo, notional_teto / preco_atual_usdt)
    return ger.ajustar_quantidade(quantidade_alvo, step_size, min_qty)


def _min_notional_operacional(min_notional: float) -> float:
    fator = env_float("AUTO_NOTIONAL_SAFETY_MULTIPLIER", 1.01, minimo=1.0)
    return max(0.0, float(min_notional or 0.0)) * fator


def _resumo_historico_ciclos(state: dict[str, Any]) -> dict[str, Any]:
    historico = list((state.get("historico_ciclos") or [])[-10:])
    if not historico:
        return {
            "total_ciclos": 0,
            "win_rate": 0.0,
            "lucro_liquido_total_usdt": 0.0,
            "lucro_liquido_medio_usdt": 0.0,
        }
    ganhos = [float(item.get("lucro_liquido_usdt", 0.0) or 0.0) for item in historico]
    total = len(ganhos)
    lucro_total = sum(ganhos)
    return {
        "total_ciclos": total,
        "win_rate": sum(1 for item in ganhos if item > 0.0) / max(total, 1),
        "lucro_liquido_total_usdt": lucro_total,
        "lucro_liquido_medio_usdt": lucro_total / max(total, 1),
    }


def _saldo_base_gerenciado(state: dict[str, Any], saldo_base_total: float) -> float:
    if not state.get("ciclo_ativo"):
        return 0.0
    quantidade_ciclo = max(0.0, float(state.get("ciclo_quantidade", 0.0) or 0.0))
    return min(max(0.0, saldo_base_total), quantidade_ciclo)


def _abrir_ciclo(
    state: dict[str, Any],
    *,
    origem: str,
    quantidade: float,
    preco_entrada: float,
    notional_entrada: float,
    agora_ms: int,
    perfil: dict[str, Any] | None = None,
) -> None:
    perfil = dict(perfil or {})
    state["ciclo_id"] = _novo_id_ciclo(state)
    state["ciclo_ativo"] = True
    state["estado_ciclo"] = "EM_POSICAO"
    state["ciclo_origem"] = origem
    state["ciclo_iniciado_ts"] = agora_ms
    state["ciclo_quantidade"] = max(0.0, quantidade)
    state["ciclo_preco_entrada"] = max(0.0, preco_entrada)
    state["ciclo_notional_entrada"] = max(0.0, notional_entrada)
    state["ciclo_preco_pico"] = max(0.0, preco_entrada)
    state["ciclo_retorno_liquido_aberto_pct"] = 0.0
    state["ciclo_lucro_liquido_aberto_usdt"] = 0.0
    state["ciclo_melhor_retorno_liquido_pct"] = 0.0
    state["ciclo_melhor_lucro_liquido_usdt"] = 0.0
    state["ciclo_lucro_minimo_pct"] = 0.0
    state["ciclo_lucro_minimo_usdt"] = 0.0
    state["ciclo_trailing_retracao_pct"] = 0.0
    state["ciclo_custos_estimados_pct"] = 0.0
    state["saldo_legado_detectado"] = False
    state["ultimo_ciclo_encerrado_ts"] = 0
    state["ultimo_ciclo_motivo_encerramento"] = None
    state["perfil_ciclo_id"] = perfil.get("id")
    state["perfil_ciclo_nome"] = perfil.get("nome")
    state["perfil_ciclo_capital_usdt"] = max(0.0, float(perfil.get("capital_usdt_util", perfil.get("capital_usdt", 0.0)) or 0.0))
    state["perfil_ciclo_lucro_minimo_usdt"] = max(0.0, float(perfil.get("lucro_minimo_usdt", 0.0) or 0.0))
    state["perfil_ativo_id"] = state["perfil_ciclo_id"]
    state["perfil_ativo_nome"] = state["perfil_ciclo_nome"]
    state["perfil_ativo_capital_usdt"] = state["perfil_ciclo_capital_usdt"]
    state["perfil_ativo_lucro_minimo_usdt"] = state["perfil_ciclo_lucro_minimo_usdt"]
    state["perfil_ativo_lucro_esperado_usdt"] = max(0.0, float(perfil.get("lucro_esperado_usdt", 0.0) or 0.0))
    state["ultima_confirmacao_composta"] = dict(perfil.get("confirmacao_composta") or {})
    if str(perfil.get("id") or "").lower() == "diario":
        state["perfil_diario_ultima_data"] = _data_operacional()
        state["perfil_diario_ultima_execucao_ts"] = agora_ms


def _encerrar_ciclo(state: dict[str, Any], *, motivo: str, agora_ms: int) -> None:
    if str(state.get("perfil_ciclo_id") or "").lower() == "diario":
        state["perfil_diario_ultima_data"] = _data_operacional()
        state["perfil_diario_ultima_execucao_ts"] = agora_ms
    state["ciclo_ativo"] = False
    state["estado_ciclo"] = "AGUARDANDO_ENTRADA"
    state["ciclo_origem"] = None
    state["ciclo_quantidade"] = 0.0
    state["ciclo_preco_entrada"] = 0.0
    state["ciclo_notional_entrada"] = 0.0
    state["ciclo_preco_atual"] = 0.0
    state["ciclo_retorno_aberto_pct"] = 0.0
    state["ciclo_lucro_aberto_usdt"] = 0.0
    state["ciclo_retorno_liquido_aberto_pct"] = 0.0
    state["ciclo_lucro_liquido_aberto_usdt"] = 0.0
    state["ciclo_melhor_retorno_liquido_pct"] = 0.0
    state["ciclo_melhor_lucro_liquido_usdt"] = 0.0
    state["ciclo_lucro_minimo_pct"] = 0.0
    state["ciclo_lucro_minimo_usdt"] = 0.0
    state["ciclo_trailing_retracao_pct"] = 0.0
    state["ciclo_custos_estimados_pct"] = 0.0
    state["ciclo_preco_pico"] = 0.0
    state["ultimo_ciclo_encerrado_ts"] = agora_ms
    state["ultimo_ciclo_motivo_encerramento"] = motivo
    state["perfil_ciclo_id"] = None
    state["perfil_ciclo_nome"] = None
    state["perfil_ciclo_capital_usdt"] = 0.0
    state["perfil_ciclo_lucro_minimo_usdt"] = 0.0


def _atualizar_monitoramento_ciclo(state: dict[str, Any], *, saldo_base: float, preco_atual: float) -> None:
    if not state.get("ciclo_ativo"):
        state["ciclo_preco_atual"] = max(0.0, preco_atual)
        state["ciclo_retorno_aberto_pct"] = 0.0
        state["ciclo_lucro_aberto_usdt"] = 0.0
        return

    preco_entrada = float(state.get("ciclo_preco_entrada", 0.0) or 0.0)
    retorno_pct = ((preco_atual - preco_entrada) / preco_entrada) if preco_entrada > 0 else 0.0
    lucro_aberto = saldo_base * (preco_atual - preco_entrada) if preco_entrada > 0 else 0.0
    state["estado_ciclo"] = "EM_POSICAO"
    state["ciclo_quantidade"] = max(0.0, saldo_base)
    state["ciclo_preco_atual"] = max(0.0, preco_atual)
    state["ciclo_retorno_aberto_pct"] = retorno_pct
    state["ciclo_lucro_aberto_usdt"] = lucro_aberto
    if preco_atual >= float(state.get("ciclo_preco_pico", 0.0) or 0.0):
        state["ciclo_preco_pico"] = max(0.0, preco_atual)


def _atualizar_metricas_lucro_ciclo(
    *,
    state: dict[str, Any],
    saldo_base: float,
    preco_atual: float,
    ajustes_sinal: dict[str, Any],
    spread_rel: float,
) -> dict[str, float]:
    notional_entrada = max(
        float(state.get("ciclo_notional_entrada", 0.0) or 0.0),
        max(0.0, saldo_base) * max(float(state.get("ciclo_preco_entrada", 0.0) or 0.0), 0.0),
    )
    retorno_bruto_pct = float(state.get("ciclo_retorno_aberto_pct", 0.0) or 0.0)
    custos_pct = _custos_ciclo_pct(ajustes_sinal, spread_rel)
    retorno_liquido_pct = retorno_bruto_pct - custos_pct
    lucro_liquido_usdt = notional_entrada * retorno_liquido_pct
    melhor_pct = max(float(state.get("ciclo_melhor_retorno_liquido_pct", 0.0) or 0.0), retorno_liquido_pct)
    melhor_usdt = max(float(state.get("ciclo_melhor_lucro_liquido_usdt", 0.0) or 0.0), lucro_liquido_usdt)
    state["ciclo_retorno_liquido_aberto_pct"] = retorno_liquido_pct
    state["ciclo_lucro_liquido_aberto_usdt"] = lucro_liquido_usdt
    state["ciclo_melhor_retorno_liquido_pct"] = melhor_pct
    state["ciclo_melhor_lucro_liquido_usdt"] = melhor_usdt
    state["ciclo_custos_estimados_pct"] = custos_pct
    if retorno_liquido_pct >= melhor_pct:
        state["ciclo_preco_pico"] = max(preco_atual, float(state.get("ciclo_preco_pico", 0.0) or 0.0))
    return {
        "notional_entrada": notional_entrada,
        "retorno_liquido_pct": retorno_liquido_pct,
        "lucro_liquido_usdt": lucro_liquido_usdt,
        "melhor_retorno_liquido_pct": melhor_pct,
        "melhor_lucro_liquido_usdt": melhor_usdt,
        "custos_pct": custos_pct,
    }


def _limites_lucro_ciclo(
    *,
    notional_entrada: float,
    ajustes_sinal: dict[str, Any],
    perfil: dict[str, Any] | None = None,
) -> dict[str, float]:
    perfil = dict(perfil or {})
    minimo_pct_cfg = max(0.0, float(ajustes_sinal.get("signal_min_net_profit_pct", 0.002) or 0.0))
    minimo_usdt_cfg = max(
        0.01,
        float(ajustes_sinal.get("auto_lucro_liquido_minimo_usdt", 0.01) or 0.01),
        float(perfil.get("lucro_minimo_usdt", 0.0) or 0.0),
    )
    incremento_alvo_pct = max(0.0, float(perfil.get("incremento_alvo_pct", 0.0) or 0.0))
    minimo_pct_cfg *= 1.0 + incremento_alvo_pct
    minimo_usdt = max(minimo_usdt_cfg, notional_entrada * minimo_pct_cfg)
    minimo_pct = (minimo_usdt / notional_entrada) if notional_entrada > 0 else minimo_pct_cfg
    trailing_pct = max(minimo_pct * max(0.10, float(perfil.get("multiplicador_trailing", 0.35) or 0.35)), 0.0004)
    return {
        "minimo_usdt": minimo_usdt,
        "minimo_pct": minimo_pct,
        "trailing_pct": trailing_pct,
    }


def _avaliar_saida_ciclo(
    *,
    state: dict[str, Any],
    sinal: SignalDecision,
    ajustes_sinal: dict[str, Any],
    saldo_base: float,
    preco_atual: float,
    perfil: dict[str, Any] | None = None,
) -> dict[str, Any]:
    perfil = dict(perfil or {})
    spread_rel = abs(float(sinal.features.get("spread_rel", 0.0) or 0.0))
    _atualizar_monitoramento_ciclo(state, saldo_base=saldo_base, preco_atual=preco_atual)
    metricas = _atualizar_metricas_lucro_ciclo(
        state=state,
        saldo_base=saldo_base,
        preco_atual=preco_atual,
        ajustes_sinal=ajustes_sinal,
        spread_rel=spread_rel,
    )
    limites = _limites_lucro_ciclo(
        notional_entrada=metricas["notional_entrada"],
        ajustes_sinal=ajustes_sinal,
        perfil=perfil,
    )
    state["ciclo_lucro_minimo_pct"] = limites["minimo_pct"]
    state["ciclo_lucro_minimo_usdt"] = limites["minimo_usdt"]
    state["ciclo_trailing_retracao_pct"] = limites["trailing_pct"]

    retracao_pct = max(0.0, metricas["melhor_retorno_liquido_pct"] - metricas["retorno_liquido_pct"])
    stop_protecao_pct = max(float(sinal.stop_loss_pct or 0.0), float(perfil.get("stop_protecao_pct", 0.0015) or 0.0015), 0.0015)
    tempo_minimo_posicao = max(0, int(perfil.get("tempo_minimo_posicao_segundos", 0) or 0))
    tempo_em_posicao_segundos = max(0.0, (time.time() * 1000 - int(state.get("ciclo_iniciado_ts", 0) or 0)) / 1000.0)
    saida_liberada_por_tempo = tempo_em_posicao_segundos >= tempo_minimo_posicao
    requer_sinal_sell = bool(perfil.get("requer_sinal_sell_para_saida", False))
    sinal_permite_realizacao = sinal.acao in {"HOLD", "SELL"} if not requer_sinal_sell else sinal.acao == "SELL"
    lucro_minimo_atingido = (
        metricas["lucro_liquido_usdt"] >= limites["minimo_usdt"]
        and metricas["retorno_liquido_pct"] >= limites["minimo_pct"]
    )

    if float(state.get("ciclo_retorno_aberto_pct", 0.0) or 0.0) <= -stop_protecao_pct:
        return {
            "vender": True,
            "motivo": "stop_protecao_acionado",
            "estado_ciclo": "STOP_PROTECAO",
            "retracao_pct": retracao_pct,
            "tempo_em_posicao_segundos": tempo_em_posicao_segundos,
            **metricas,
            **limites,
        }

    if lucro_minimo_atingido and saida_liberada_por_tempo and sinal_permite_realizacao:
        return {
            "vender": True,
            "motivo": "lucro_minimo_liquido_atingido",
            "estado_ciclo": "REALIZANDO_LUCRO",
            "retracao_pct": retracao_pct,
            "tempo_em_posicao_segundos": tempo_em_posicao_segundos,
            **metricas,
            **limites,
        }

    if (
        metricas["melhor_lucro_liquido_usdt"] >= limites["minimo_usdt"]
        and metricas["lucro_liquido_usdt"] > 0.0
        and saida_liberada_por_tempo
        and retracao_pct >= limites["trailing_pct"]
    ):
        return {
            "vender": True,
            "motivo": "trailing_de_lucro_acionado",
            "estado_ciclo": "TRAVANDO_LUCRO",
            "retracao_pct": retracao_pct,
            "tempo_em_posicao_segundos": tempo_em_posicao_segundos,
            **metricas,
            **limites,
        }

    motivo = "aguardando_lucro_minimo_liquido"
    if lucro_minimo_atingido and not saida_liberada_por_tempo:
        motivo = "tempo_minimo_da_estrategia_nao_atingido"
    elif lucro_minimo_atingido and not sinal_permite_realizacao:
        motivo = "perfil_aguardando_sinal_de_saida"
    elif lucro_minimo_atingido and sinal.acao == "BUY":
        motivo = "compra_sustentada_acima_do_minimo"
    elif metricas["lucro_liquido_usdt"] > 0.0:
        motivo = "lucro_aberto_abaixo_do_minimo"
    return {
        "vender": False,
        "motivo": motivo,
        "estado_ciclo": "MONITORANDO_LUCRO",
        "retracao_pct": retracao_pct,
        "tempo_em_posicao_segundos": tempo_em_posicao_segundos,
        **metricas,
        **limites,
    }


def _sincronizar_ciclo(
    *,
    state: dict[str, Any],
    simbolo: str,
    trades: list[dict[str, Any]],
    saldo_base: float,
    preco_atual_par: float,
    preco_atual_usdt: float,
    min_notional_operacional_usdt: float,
    min_qty: float,
    step_size: float,
    perfis_capital: list[dict[str, Any]],
    precos_usdt: dict[str, float],
    ger: GerenciadorOrdens,
) -> bool:
    agora_ms = int(time.time() * 1000)
    limiar_residuo_usdt = _limiar_residuo_ignorado_usdt()
    extrato = _resumir_extrato_par(trades, preco_atual_par)
    state["extrato_par"] = dict(extrato)
    state["ultima_acao_par"] = extrato["ultima_acao"]
    state["ultima_acao_par_ts"] = extrato["ultimo_trade_ts"]
    contexto = _definir_proxima_acao_esperada(
        extrato=extrato,
        saldo_base=saldo_base,
        preco_atual_usdt=preco_atual_usdt,
        min_notional_operacional_usdt=min_notional_operacional_usdt,
        min_qty=min_qty,
    )
    state["proxima_acao_esperada"] = contexto["acao"]
    state["motivo_proxima_acao"] = contexto["motivo"]
    saldo_total_presente = saldo_base >= max(min_qty, 0.0) and _valor_posicao_usdt(saldo_base, preco_atual_usdt) >= max(limiar_residuo_usdt, 1e-9)
    saldo_gerenciado = _saldo_base_gerenciado(state, saldo_base)
    tem_posicao_gerenciada = saldo_gerenciado >= max(min_qty, 0.0) and _valor_posicao_usdt(saldo_gerenciado, preco_atual_usdt) >= max(limiar_residuo_usdt, 1e-9)

    if state.get("ciclo_ativo") and not tem_posicao_gerenciada:
        _encerrar_ciclo(state, motivo="posicao_do_bot_encerrada", agora_ms=agora_ms)
        saldo_gerenciado = 0.0
        tem_posicao_gerenciada = False

    if not state.get("ciclo_ativo") and bool(contexto.get("tem_posicao_operacional")):
        quantidade_reconciliada = _quantidade_carteira_para_capital(
            saldo_base_total=saldo_base,
            preco_atual_usdt=preco_atual_usdt,
            notional_teto=0.0,
            step_size=step_size,
            min_qty=min_qty,
            ger=ger,
        )
        perfil_reconciliado = (
            _obter_perfil(perfis_capital, state.get("perfil_ciclo_id"))
            or _obter_perfil(perfis_capital, state.get("perfil_ativo_id"))
            or _obter_perfil(perfis_capital, "mini")
            or {}
        )
        preco_entrada_par = float(
            extrato.get("ultima_compra_preco_par")
            or extrato.get("ultimo_trade_preco_par")
            or preco_atual_par
            or 0.0
        )
        preco_entrada_usdt = _preco_par_usdt(simbolo, preco_entrada_par, precos_usdt)
        ts_entrada = int(extrato.get("ultima_compra_ts", 0) or extrato.get("ultimo_trade_ts", 0) or agora_ms)
        if quantidade_reconciliada > 0.0 and preco_entrada_usdt > 0.0:
            origem = "extrato" if bool(extrato.get("tem_historico")) else "carteira"
            _abrir_ciclo(
                state,
                origem=origem,
                quantidade=quantidade_reconciliada,
                preco_entrada=preco_entrada_usdt,
                notional_entrada=quantidade_reconciliada * preco_entrada_usdt,
                agora_ms=ts_entrada,
                perfil=perfil_reconciliado,
            )
            state["ultimo_motivo"] = "ciclo_reconciliado_pelo_extrato" if origem == "extrato" else "ciclo_assumido_do_saldo_da_conta"
            saldo_gerenciado = _saldo_base_gerenciado(state, saldo_base)
            tem_posicao_gerenciada = saldo_gerenciado >= max(min_qty, 0.0) and _valor_posicao_usdt(saldo_gerenciado, preco_atual_usdt) >= max(limiar_residuo_usdt, 1e-9)

    state["saldo_legado_detectado"] = bool(saldo_total_presente and not state.get("ciclo_ativo"))
    if state["saldo_legado_detectado"] and not state.get("ultimo_motivo"):
        state["ultimo_motivo"] = "saldo_legado_ignorado_pelo_bot"

    _atualizar_monitoramento_ciclo(state, saldo_base=saldo_gerenciado if tem_posicao_gerenciada else 0.0, preco_atual=preco_atual_usdt)
    return tem_posicao_gerenciada


def _novo_estado(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "simbolo": str(config.get("simbolo", "BTCUSDT")).upper(),
        "intervalo_segundos": max(5, int(config.get("intervalo_segundos", 30) or 30)),
        "notional_usdt": max(0.0, float(config.get("notional_usdt", 0.0) or 0.0)),
        "modo_testnet": bool(config.get("modo_testnet", True)),
        "modo": "testnet" if bool(config.get("modo_testnet", True)) else "real",
        "ativo": True,
        "ultimo_ts": 0,
        "ultimo_erro": None,
        "ultimo_sinal": "HOLD",
        "ultima_acao": None,
        "ultimo_motivo": "aguardando_primeira_leitura",
        "ultimo_lucro_esperado_pct": 0.0,
        "ultimo_preco": 0.0,
        "historico_execucoes_ts": [],
        "ultimo_trade_ts_execucao": 0,
        "ultima_acao_execucao": "",
        "extrato_par": {},
        "ultima_acao_par": "SEM_HISTORICO",
        "ultima_acao_par_ts": 0,
        "proxima_acao_esperada": "BUY",
        "motivo_proxima_acao": "sem_historico_no_par",
        "perfil_ativo_id": None,
        "perfil_ativo_nome": None,
        "perfil_ativo_capital_usdt": 0.0,
        "perfil_ativo_lucro_minimo_usdt": 0.0,
        "perfil_ativo_lucro_esperado_usdt": 0.0,
        "perfil_ciclo_id": None,
        "perfil_ciclo_nome": None,
        "perfil_ciclo_capital_usdt": 0.0,
        "perfil_ciclo_lucro_minimo_usdt": 0.0,
        "perfis_capital": [],
        "ultima_confirmacao_composta": {},
        "perfil_diario_ultima_data": None,
        "perfil_diario_ultima_execucao_ts": 0,
        "sequencia_ciclo": 0,
        "ciclo_id": 0,
        "ciclo_ativo": False,
        "estado_ciclo": "AGUARDANDO_ENTRADA",
        "ciclo_origem": None,
        "ciclo_iniciado_ts": 0,
        "ciclo_quantidade": 0.0,
        "ciclo_preco_entrada": 0.0,
        "ciclo_notional_entrada": 0.0,
        "ciclo_preco_atual": 0.0,
        "ciclo_retorno_aberto_pct": 0.0,
        "ciclo_lucro_aberto_usdt": 0.0,
        "ciclo_retorno_liquido_aberto_pct": 0.0,
        "ciclo_lucro_liquido_aberto_usdt": 0.0,
        "ciclo_melhor_retorno_liquido_pct": 0.0,
        "ciclo_melhor_lucro_liquido_usdt": 0.0,
        "ciclo_lucro_minimo_pct": 0.0,
        "ciclo_lucro_minimo_usdt": 0.0,
        "ciclo_trailing_retracao_pct": 0.0,
        "ciclo_custos_estimados_pct": 0.0,
        "ciclo_preco_pico": 0.0,
        "saldo_legado_detectado": False,
        "ultimo_ciclo_encerrado_ts": 0,
        "ultimo_ciclo_motivo_encerramento": None,
        "ciclo_features_entrada": {},
        "ciclo_previsao_ts": 0,
        "ciclo_previsao_y_hat": 0.0,
        "historico_ciclos": [],
        "ultimo_retreino_ts": 0,
        "ultimo_retreino_status": None,
        # Monitoramento / circuit-breaker
        "consecutive_errors": 0,
        "circuit_tripped": False,
        "daily_loss_usdt": 0.0,
        "max_daily_loss_usdt": float(config.get("max_daily_loss_usdt") or 50.0),
        "consecutive_errors_limit": int(config.get("consecutive_errors_limit", 5) or 5),
        "pares_estado": {},
        "simbolo_foco": str(config.get("simbolo", "BTCUSDT")).upper(),
        "pares_ranqueados": [],
    }


def _aplicar_config_estado(state: dict[str, Any], config: dict[str, Any]) -> None:
    state["simbolo"] = str(config.get("simbolo", state.get("simbolo", "BTCUSDT"))).upper()
    state["intervalo_segundos"] = max(5, int(config.get("intervalo_segundos", state.get("intervalo_segundos", 30)) or 30))
    state["notional_usdt"] = max(0.0, float(config.get("notional_usdt", state.get("notional_usdt", 0.0)) or 0.0))
    if "modo_testnet" in config:
        state["modo_testnet"] = bool(config.get("modo_testnet"))
        state["modo"] = "testnet" if state["modo_testnet"] else "real"


def _extrair_estado_par(state: dict[str, Any]) -> dict[str, Any]:
    return {
        chave: copy.deepcopy(valor)
        for chave, valor in state.items()
        if chave not in _CHAVES_GLOBAIS_ESTADO
    }


def _estado_par_base(estado_global: dict[str, Any], simbolo: str) -> dict[str, Any]:
    base = _novo_estado(
        {
            "simbolo": simbolo,
            "intervalo_segundos": estado_global.get("intervalo_segundos", 30),
            "notional_usdt": estado_global.get("notional_usdt", 0.0),
            "modo_testnet": estado_global.get("modo_testnet", True),
            "max_daily_loss_usdt": estado_global.get("max_daily_loss_usdt", 50.0),
            "consecutive_errors_limit": estado_global.get("consecutive_errors_limit", 5),
        }
    )
    return _extrair_estado_par(base)


def _obter_estado_par(estado_global: dict[str, Any], simbolo: str) -> dict[str, Any]:
    simbolo_norm = str(simbolo or "BTCUSDT").upper()
    pares_estado = estado_global.setdefault("pares_estado", {})
    if simbolo_norm not in pares_estado:
        if str(estado_global.get("simbolo") or "").upper() == simbolo_norm:
            pares_estado[simbolo_norm] = _extrair_estado_par(estado_global)
        else:
            pares_estado[simbolo_norm] = _estado_par_base(estado_global, simbolo_norm)
    return pares_estado[simbolo_norm]


def _espelhar_estado_par_no_global(estado_global: dict[str, Any], estado_par: dict[str, Any]) -> None:
    for chave, valor in _extrair_estado_par(estado_par).items():
        estado_global[chave] = copy.deepcopy(valor)


def _usuario_virtual(ajustes_risco: dict[str, Any], *, modo_testnet: bool) -> dict[str, Any]:
    risk_config = dict(ajustes_risco)
    risk_config["max_trades_abertos"] = 1
    risk_config["max_trades_por_hora"] = max(int(risk_config.get("max_trades_por_hora", 0) or 0), 30)
    risk_config["cooldown_minutos"] = min(int(risk_config.get("cooldown_minutos", 0) or 0), 1)
    risk_config["bloquear_flip_flop"] = False
    risk_config["max_exposicao_ativo"] = max(float(risk_config.get("max_exposicao_ativo", 0.20) or 0.20), 1.0)
    risk_config["risk_per_trade"] = max(float(risk_config.get("risk_per_trade", 0.005) or 0.005), 1.0)
    risk_config["max_loss_trade_usdt"] = max(float(risk_config.get("max_loss_trade_usdt", 0.20) or 0.20), 1000.0)
    return {
        "id": 0,
        "nome": "auto_trader",
        "testnet": bool(modo_testnet),
        "ativo": True,
        "risk_config": risk_config,
    }


def _estado_execucao_atual(
    *,
    state: dict[str, Any],
    trades: list[dict[str, Any]],
    ordens_abertas: list[dict[str, Any]],
    saldo_total: float,
    saldo_base: float,
    preco_atual_usdt: float,
) -> dict[str, Any]:
    agora = int(time.time() * 1000)
    historico_local = [
        int(ts)
        for ts in list(state.get("historico_execucoes_ts", []))
        if (agora - int(ts or 0)) <= 3_600_000
    ]
    state["historico_execucoes_ts"] = historico_local

    ultimo_trade_ts_local = int(state.get("ultimo_trade_ts_execucao", 0) or 0)
    ultima_acao_local = str(state.get("ultima_acao_execucao", "") or "").upper()
    ultimo_trade_ts = ultimo_trade_ts_local
    ultima_acao = ultima_acao_local
    exposicao_ativo = ((saldo_base * preco_atual_usdt) / saldo_total) if saldo_total > 0 and preco_atual_usdt > 0 else 0.0

    return {
        "drawdown_atual": 0.0,
        "drawdown_diario": 0.0,
        "perda_diaria_usdt": 0.0,
        "exposicao_ativo": max(0.0, exposicao_ativo),
        "trades_abertos": 1 if state.get("ciclo_ativo") else 0,
        "trades_ultima_hora": len(historico_local),
        "ultimo_trade_ts": ultimo_trade_ts,
        "ultima_acao": ultima_acao,
    }


def _aplicar_teto_notional(aprovacao: RiskApproval, limite_usdt: float, saldo_total: float) -> RiskApproval:
    if limite_usdt <= 0.0:
        return aprovacao
    payload = aprovacao.to_dict()
    novo_notional = min(float(payload.get("notional_sugerido", 0.0) or 0.0), limite_usdt)
    payload["notional_sugerido"] = max(0.0, novo_notional)
    payload["fracao_capital"] = (novo_notional / saldo_total) if saldo_total > 0 else 0.0
    if novo_notional <= 0.0:
        payload["aprovado"] = False
        payload["motivos"] = list(payload.get("motivos") or []) + ["notional_configurado_invalido"]
    return RiskApproval.from_mapping(payload)


def _liberar_saida_ciclo(aprovacao: RiskApproval, *, saldo_base: float, preco_atual: float) -> RiskApproval:
    payload = aprovacao.to_dict()
    payload["acao"] = "SELL"
    payload["aprovado"] = True
    payload["notional_sugerido"] = max(float(payload.get("notional_sugerido", 0.0) or 0.0), saldo_base * preco_atual)
    return RiskApproval.from_mapping(payload)


class TestnetAutoTrader:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._state: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def iniciar(self, token: str, sessao: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        config_exec = {**dict(config), "modo_testnet": bool(sessao.get("modo_testnet", False))}
        async with self._lock:
            task = self._tasks.get(token)
            if task and not task.done():
                state = self._state.get(token)
                if state is not None:
                    _aplicar_config_estado(state, config_exec)
                return self.status(token)
            self._state[token] = _novo_estado(config_exec)
            self._tasks[token] = asyncio.create_task(self._loop(token, sessao))
            return self.status(token)

    async def atualizar_config(self, token: str, config: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            state = self._state.get(token)
            if state is None:
                self._state[token] = _novo_estado(config)
            else:
                _aplicar_config_estado(state, config)
            return self.status(token)

    async def parar(self, token: str) -> dict[str, Any]:
        async with self._lock:
            task = self._tasks.pop(token, None)
            if task:
                task.cancel()
            self._state.pop(token, None)
        return {"ativo": False}

    async def encerrar_todos(self) -> None:
        async with self._lock:
            tasks = list(self._tasks.values())
            self._tasks.clear()
            self._state.clear()
        for task in tasks:
            task.cancel()

    def status(self, token: str) -> dict[str, Any]:
        task = self._tasks.get(token)
        state = self._state.get(token, {})
        ativo = bool(task and not task.done())
        ciclo_ativo = bool(state.get("ciclo_ativo"))
        estado_ciclo = state.get("estado_ciclo")
        ultimo_motivo = state.get("ultimo_motivo")
        if not ativo and not ciclo_ativo:
            estado_ciclo = "PAUSADO"
            ultimo_motivo = "bot_pausado"
        resumo_ciclos = _resumo_historico_ciclos(state)
        return {
            "ativo": ativo,
            "modo": state.get("modo"),
            "modo_testnet": bool(state.get("modo_testnet", True)),
            "simbolo_foco": state.get("simbolo_foco") or state.get("simbolo"),
            "config": {
                "simbolo": state.get("simbolo"),
                "intervalo_segundos": state.get("intervalo_segundos"),
                "notional_usdt": state.get("notional_usdt"),
            },
            "ultimo_ts": state.get("ultimo_ts"),
            "ultimo_erro": state.get("ultimo_erro"),
            "ultimo_sinal": state.get("ultimo_sinal"),
            "ultima_acao": state.get("ultima_acao"),
            "ultimo_motivo": ultimo_motivo,
            "ultimo_lucro_esperado_pct": state.get("ultimo_lucro_esperado_pct"),
            "ultimo_preco": state.get("ultimo_preco"),
            "extrato_par": dict(state.get("extrato_par") or {}),
            "ultima_acao_par": state.get("ultima_acao_par"),
            "ultima_acao_par_ts": state.get("ultima_acao_par_ts"),
            "proxima_acao_esperada": state.get("proxima_acao_esperada"),
            "motivo_proxima_acao": state.get("motivo_proxima_acao"),
            "perfil_ativo": {
                "id": state.get("perfil_ciclo_id") or state.get("perfil_ativo_id"),
                "nome": state.get("perfil_ciclo_nome") or state.get("perfil_ativo_nome"),
                "capital_usdt": state.get("perfil_ciclo_capital_usdt") or state.get("perfil_ativo_capital_usdt"),
                "lucro_minimo_usdt": state.get("perfil_ciclo_lucro_minimo_usdt") or state.get("perfil_ativo_lucro_minimo_usdt"),
                "lucro_esperado_usdt": state.get("perfil_ativo_lucro_esperado_usdt"),
            },
            "perfis_capital": list(state.get("perfis_capital") or []),
            "ultima_confirmacao_composta": dict(state.get("ultima_confirmacao_composta") or {}),
            "perfil_diario_ultima_data": state.get("perfil_diario_ultima_data"),
            "perfil_diario_ultima_execucao_ts": state.get("perfil_diario_ultima_execucao_ts"),
            "ciclo_ativo": ciclo_ativo,
            "estado_ciclo": estado_ciclo,
            "ciclo_id": state.get("ciclo_id"),
            "ciclo_origem": state.get("ciclo_origem"),
            "ciclo_iniciado_ts": state.get("ciclo_iniciado_ts"),
            "ciclo_quantidade": state.get("ciclo_quantidade"),
            "ciclo_preco_entrada": state.get("ciclo_preco_entrada"),
            "ciclo_preco_atual": state.get("ciclo_preco_atual"),
            "ciclo_retorno_aberto_pct": state.get("ciclo_retorno_aberto_pct"),
            "ciclo_lucro_aberto_usdt": state.get("ciclo_lucro_aberto_usdt"),
            "ciclo_retorno_liquido_aberto_pct": state.get("ciclo_retorno_liquido_aberto_pct"),
            "ciclo_lucro_liquido_aberto_usdt": state.get("ciclo_lucro_liquido_aberto_usdt"),
            "ciclo_melhor_retorno_liquido_pct": state.get("ciclo_melhor_retorno_liquido_pct"),
            "ciclo_melhor_lucro_liquido_usdt": state.get("ciclo_melhor_lucro_liquido_usdt"),
            "ciclo_lucro_minimo_pct": state.get("ciclo_lucro_minimo_pct"),
            "ciclo_lucro_minimo_usdt": state.get("ciclo_lucro_minimo_usdt"),
            "ciclo_trailing_retracao_pct": state.get("ciclo_trailing_retracao_pct"),
            "ciclo_custos_estimados_pct": state.get("ciclo_custos_estimados_pct"),
            "ciclo_preco_pico": state.get("ciclo_preco_pico"),
            "saldo_legado_detectado": state.get("saldo_legado_detectado"),
            "ultimo_ciclo_encerrado_ts": state.get("ultimo_ciclo_encerrado_ts"),
            "ultimo_ciclo_motivo_encerramento": state.get("ultimo_ciclo_motivo_encerramento"),
            "historico_ciclos_resumo": resumo_ciclos,
            "ultimo_retreino_ts": state.get("ultimo_retreino_ts"),
            "ultimo_retreino_status": state.get("ultimo_retreino_status"),
            "pares_ranqueados": list(state.get("pares_ranqueados") or []),
        }

    async def _registrar_evento(self, *, simbolo: str, state: dict[str, Any], payload: dict[str, Any]) -> None:
        await RepositorioAuditoria.registrar(
            simbolo=simbolo,
            tipo="auto_trade",
            created_ts=int(time.time() * 1000),
            payload={
                "modo": state.get("modo"),
                "modo_testnet": state.get("modo_testnet"),
                "ultimo_sinal": state.get("ultimo_sinal"),
                "ultima_acao": state.get("ultima_acao"),
                "ultimo_motivo": state.get("ultimo_motivo"),
                "ultimo_lucro_esperado_pct": state.get("ultimo_lucro_esperado_pct"),
                "perfil_ativo_id": state.get("perfil_ativo_id"),
                "perfil_ciclo_id": state.get("perfil_ciclo_id"),
                "ultima_confirmacao_composta": state.get("ultima_confirmacao_composta"),
                "estado_ciclo": state.get("estado_ciclo"),
                "ciclo_ativo": state.get("ciclo_ativo"),
                "ciclo_id": state.get("ciclo_id"),
                "ciclo_retorno_aberto_pct": state.get("ciclo_retorno_aberto_pct"),
                "ciclo_retorno_liquido_aberto_pct": state.get("ciclo_retorno_liquido_aberto_pct"),
                "ciclo_lucro_liquido_aberto_usdt": state.get("ciclo_lucro_liquido_aberto_usdt"),
                "saldo_legado_detectado": state.get("saldo_legado_detectado"),
                **payload,
            },
        )

    async def _registrar_fechamento_ciclo(
        self,
        *,
        simbolo: str,
        state: dict[str, Any],
        preco_saida_usdt: float,
        motivo: str,
    ) -> None:
        agora_ms = int(time.time() * 1000)
        lucro_liquido_usdt = float(state.get("ciclo_lucro_liquido_aberto_usdt", 0.0) or 0.0)
        retorno_liquido_pct = float(state.get("ciclo_retorno_liquido_aberto_pct", 0.0) or 0.0)
        notional_entrada = float(state.get("ciclo_notional_entrada", 0.0) or 0.0)
        duracao_ms = max(0, agora_ms - int(state.get("ciclo_iniciado_ts", 0) or agora_ms))
        historico = list(state.get("historico_ciclos") or [])
        historico.append(
            {
                "ts_encerramento": agora_ms,
                "motivo": motivo,
                "origem": state.get("ciclo_origem"),
                "simbolo": simbolo,
                "perfil_id": state.get("perfil_ciclo_id"),
                "perfil_nome": state.get("perfil_ciclo_nome"),
                "notional_entrada": notional_entrada,
                "lucro_liquido_usdt": lucro_liquido_usdt,
                "retorno_liquido_pct": retorno_liquido_pct,
                "duracao_ms": duracao_ms,
            }
        )
        state["historico_ciclos"] = historico[-20:]

        features_entrada = dict(state.get("ciclo_features_entrada") or {})
        y_hat = float(state.get("ciclo_previsao_y_hat", 0.0) or 0.0)
        ts_previsao = int(state.get("ciclo_previsao_ts", 0) or agora_ms)
        try:
            if features_entrada and preco_saida_usdt > 0.0:
                ajustar_online(simbolo, features_entrada, preco_saida_usdt)
                await RepositorioOutcomes.salvar(
                    ts_previsao=ts_previsao,
                    ts_target=agora_ms,
                    simbolo=simbolo,
                    y_true=preco_saida_usdt,
                    y_hat=y_hat if y_hat > 0.0 else float(state.get("ciclo_preco_entrada", preco_saida_usdt) or preco_saida_usdt),
                )
                state["ultimo_retreino_status"] = "ok"
            else:
                state["ultimo_retreino_status"] = "sem_contexto_para_retreino"
        except Exception as exc:
            state["ultimo_retreino_status"] = f"falha:{exc}"
        state["ultimo_retreino_ts"] = agora_ms
        # Atualiza perda diária estimada para circuit-breaker
        try:
            lucro_liquido_usdt = float(lucro_liquido_usdt or 0.0)
            if lucro_liquido_usdt < 0.0:
                perda_diaria = float(state.get("daily_loss_usdt", 0.0) or 0.0) + abs(lucro_liquido_usdt)
                state["daily_loss_usdt"] = perda_diaria
                limite_perda = max(0.0, float(state.get("max_daily_loss_usdt", 0.0) or 0.0))
                if limite_perda > 0.0 and perda_diaria >= limite_perda:
                    state["circuit_tripped"] = True
                    state["ultima_acao"] = "PAUSADO"
                    state["ultimo_motivo"] = "limite_perda_diaria_atingido"
                    await RepositorioConfig.definir("retomada_operacoes_bloqueadas", True)
                    await RepositorioConfig.definir("retomada_modo", "pausado")
                    await RepositorioConfig.definir("bloqueio_operacional_motivo", "limite_perda_diaria_atingido")
                    LOG.error(
                        "circuit_breaker_perda_diaria_acionado",
                        extra={"simbolo": simbolo, "perda_diaria_usdt": perda_diaria, "limite_perda_usdt": limite_perda},
                    )
        except Exception as exc:
            LOG.warning("falha_atualizar_perda_diaria", extra={"simbolo": simbolo, "erro": str(exc)})

    async def _executar_ciclo(
        self,
        *,
        token: str,
        sessao: dict[str, Any],
        cliente_conta: ClienteBinance,
        cliente_mercado: ClienteBinance,
        ger: GerenciadorOrdens,
    ) -> None:
        estado_global = self._state.get(token)
        if estado_global is None:
            return

        notional_teto = float(estado_global.get("notional_usdt", 0.0) or 0.0)
        modo_testnet = bool(sessao.get("modo_testnet", False))
        estado_global["modo_testnet"] = modo_testnet
        estado_global["modo"] = "testnet" if modo_testnet else "real"
        ajustes_risco = (await obter_ajustes_risco())["aplicado"]
        lucro_liquido_minimo_usdt = max(0.01, float(ajustes_risco.get("lucro_liquido_minimo_usdt", 0.01) or 0.01))
        ajustes_sinal_base = _ajustes_microtrading_auto(
            (await obter_ajustes_sinal())["aplicado"],
            notional_usdt=notional_teto,
            lucro_liquido_minimo_usdt=lucro_liquido_minimo_usdt,
            state=estado_global,
        )
        conta_raw = await cliente_conta.obter_conta_raw()
        monitoramento_multiativo = await montar_monitoramento_multiativo(
            sessao=sessao,
            cliente=cliente_mercado,
            conta_raw=conta_raw,
            persistir_mercado=False,
            ajustes_sinal=ajustes_sinal_base,
            capital_planejado_usdt=notional_teto,
            lucro_liquido_minimo_usdt=lucro_liquido_minimo_usdt,
        )
        perfil_taxas = dict(monitoramento_multiativo.get("perfil_taxas") or {})
        ajustes_sinal = _ajustes_sinal_com_taxa_efetiva(ajustes_sinal_base, perfil_taxas)
        saldos_monitorados = dict(monitoramento_multiativo.get("saldos_monitorados") or {})
        precos_usdt = dict(monitoramento_multiativo.get("precos_usdt") or {})
        sinais_monitorados = dict(monitoramento_multiativo.get("sinais") or {})
        scanner = dict(monitoramento_multiativo.get("scanner") or {})

        pares_ranqueados = _ranquear_simbolos_monitorados(
            estado_global,
            scanner=scanner,
            saldos=saldos_monitorados,
            precos_usdt=precos_usdt,
            sinais=sinais_monitorados,
        )
        simbolo = _selecionar_simbolo_foco(estado_global, pares_ranqueados)
        if not simbolo:
            simbolo = _selecionar_simbolo_entrada(
                estado_global,
                scanner,
                saldos=saldos_monitorados,
                precos_usdt=precos_usdt,
            )
        try:
            simbolo = validar_par_monitorado(simbolo)
        except ValueError:
            simbolo = pares_monitorados()[0]
        estado_global["simbolo_foco"] = simbolo
        estado_global["pares_ranqueados"] = copy.deepcopy(pares_ranqueados)
        state = _obter_estado_par(estado_global, simbolo)
        state["simbolo"] = simbolo

        def _espelhar_estado_corrente() -> None:
            estado_global["simbolo_foco"] = simbolo
            estado_global["pares_ranqueados"] = copy.deepcopy(pares_ranqueados)
            _espelhar_estado_par_no_global(estado_global, state)

        base_asset = _ativo_base(simbolo)
        quote_asset = _ativo_quote(simbolo)
        preco_quote_usdt = _preco_ativo_usdt(quote_asset, precos_usdt)
        if quote_asset != "USDT" and preco_quote_usdt <= 0.0:
            raise RuntimeError(f"preco_usdt_indisponivel_para_{quote_asset.lower()}")

        filtros = await ger.obter_filtros_simbolo(simbolo)
        min_notional = float(filtros.get("min_notional", 0.0) or 0.0)
        min_qty = float(filtros.get("min_qty", 0.0) or 0.0)
        step_size = float(filtros.get("step_size", 0.0) or 0.0)
        min_notional_operacional = _min_notional_operacional(min_notional)
        min_notional_usdt = _notional_quote_para_usdt(min_notional, preco_quote_usdt)
        min_notional_operacional_usdt = _notional_quote_para_usdt(min_notional_operacional, preco_quote_usdt)

        preco_atual_par = await cliente_mercado.obter_preco_atual(simbolo)
        preco_atual_usdt = _preco_par_usdt(simbolo, preco_atual_par, precos_usdt)
        trades, ordens_abertas = await asyncio.gather(
            cliente_conta.obter_trades_conta(simbolo=simbolo, limit=200),
            cliente_conta.obter_ordens_abertas(simbolo=simbolo),
        )

        saldo_total = max(
            _saldo_total_estimado_usdt(saldos_monitorados),
            max(0.0, float((monitoramento_multiativo.get("capital_manager") or {}).get("saldo_total_estimado_usdt", 0.0) or 0.0)),
        )
        saldo_base_total = max(_saldo_livre(saldos_monitorados, base_asset), _saldo_ativo(conta_raw, base_asset))
        # Prefer `conta_raw` (exchange-reported balances) as source-of-truth for
        # actual available funds. Use monitoring-derived balances only as fallback.
        saldo_conta_raw = _saldo_ativo(conta_raw, quote_asset)
        saldo_monitor = _saldo_livre(saldos_monitorados, quote_asset)
        if saldo_conta_raw > 0.0:
            saldo_quote_total = saldo_conta_raw
            fonte_saldo = "conta_raw"
        else:
            saldo_quote_total = saldo_monitor
            fonte_saldo = "monitoring"
        saldo_quote_livre_usdt = saldo_quote_total if quote_asset == "USDT" else (saldo_quote_total * preco_quote_usdt)
        LOG.debug("saldo_fuente_escolhida", extra={"simbolo": simbolo, "fonte_saldo": fonte_saldo, "saldo_quote_total": saldo_quote_total, "saldo_quote_livre_usdt": saldo_quote_livre_usdt})
        perfis_capital = _construir_perfis_capital(
            state,
            capital_total_usdt=notional_teto,
            ajustes_sinal=ajustes_sinal,
            min_notional_usdt=min_notional_usdt,
        )
        ciclo_ativo = _sincronizar_ciclo(
            state=state,
            simbolo=simbolo,
            trades=trades,
            saldo_base=saldo_base_total,
            preco_atual_par=preco_atual_par,
            preco_atual_usdt=preco_atual_usdt,
            min_notional_operacional_usdt=min_notional_operacional_usdt,
            min_qty=min_qty,
            step_size=step_size,
            perfis_capital=perfis_capital,
            precos_usdt=precos_usdt,
            ger=ger,
        )
        saldo_base = _saldo_base_gerenciado(state, saldo_base_total)
        saldo_contexto = {
            "saldo_total": max(saldo_total, saldo_quote_livre_usdt),
            "saldo_livre": max(0.0, saldo_quote_livre_usdt),
        }
        estado_execucao = _estado_execucao_atual(
            state=state,
            trades=trades,
            ordens_abertas=ordens_abertas,
            saldo_total=max(saldo_total, saldo_quote_livre_usdt),
            saldo_base=saldo_base,
            preco_atual_usdt=preco_atual_usdt,
        )

        sinal_monitorado = dict(sinais_monitorados.get(simbolo) or {})
        if sinal_monitorado:
            sinal = SignalDecision.from_mapping(sinal_monitorado)
        else:
            await coletar_e_persistir(simbolo=simbolo, limit=120, cliente=cliente_mercado)
            klines = await RepositorioOhlcv.obter_ultimas(simbolo, limite=120)
            livro_topo = await RepositorioLivroTopo.obter_ultimo(simbolo)
            if not klines:
                raise RuntimeError("sem_klines_para_auto_trader")

            noticias_cache = await obter_noticias_para_peso(simbolo=par_usdt_do_ativo(base_asset))
            noticias = list(noticias_cache.get("itens", []))
            sinal = SignalDecision.from_mapping(
                gerar_sinal_orquestrado(
                    simbolo=simbolo,
                    klines=klines,
                    livro_topo=livro_topo,
                    noticias=noticias,
                    saldo=saldo_contexto,
                    ajustes_sinal=ajustes_sinal,
                )
            )
        state["ultimo_sinal"] = sinal.acao
        state["ultimo_lucro_esperado_pct"] = sinal.lucro_liquido_esperado_pct
        state["ultimo_preco"] = preco_atual_usdt

        if await operacoes_bloqueadas_por_retomada():
            aprovacao = RiskApproval.from_mapping(
                {
                    "usuario_id": 0,
                    "usuario_nome": "auto_trader",
                    "simbolo": simbolo,
                    "acao": sinal.acao,
                    "aprovado": False,
                    "paper_trading": True,
                    "fracao_capital": 0.0,
                    "notional_sugerido": 0.0,
                    "stop_loss_pct": sinal.stop_loss_pct,
                    "take_profit_pct": sinal.take_profit_pct,
                    "lucro_liquido_esperado_pct": sinal.lucro_liquido_esperado_pct,
                    "lucro_liquido_esperado_usdt": 0.0,
                    "motivos": ["retomada_operacoes_bloqueadas"],
                    "confirmacao_multi_timeframe": sinal.confirmacao_multi_timeframe,
                    "probabilidade_trade": sinal.probabilidade_trade,
                    "janela_decisao": sinal.janela_decisao,
                    "risk_config_aplicado": ajustes_risco,
                }
            )
        else:
            aprovacao = RiskApproval.from_mapping(
                avaliar_sinal_para_usuario(
                    usuario=_usuario_virtual(ajustes_risco, modo_testnet=modo_testnet),
                    sinal=sinal.to_dict(),
                    saldo=saldo_contexto,
                    estado_execucao=estado_execucao,
                )
            )
        perfil_operacao = _obter_perfil(perfis_capital, state.get("perfil_ciclo_id")) if ciclo_ativo else None
        motivo_perfil = "ciclo_em_execucao" if perfil_operacao else "sem_perfil_selecionado"
        if not ciclo_ativo:
            perfil_operacao, motivo_perfil = _selecionar_perfil_entrada(
                state=state,
                sinal=sinal,
                perfis=perfis_capital,
                min_notional_usdt=min_notional_usdt,
                saldo_quote_livre_usdt=saldo_quote_livre_usdt,
            )

        if perfil_operacao is not None:
            state["perfil_ativo_id"] = perfil_operacao.get("id")
            state["perfil_ativo_nome"] = perfil_operacao.get("nome")
            state["perfil_ativo_capital_usdt"] = max(
                0.0,
                float(perfil_operacao.get("capital_usdt_util", perfil_operacao.get("capital_usdt", 0.0)) or 0.0),
            )
            state["perfil_ativo_lucro_minimo_usdt"] = max(0.0, float(perfil_operacao.get("lucro_minimo_usdt", 0.0) or 0.0))
            state["perfil_ativo_lucro_esperado_usdt"] = max(0.0, float(perfil_operacao.get("lucro_esperado_usdt", 0.0) or 0.0))
            state["ultima_confirmacao_composta"] = dict(perfil_operacao.get("confirmacao_composta") or {})
        elif not ciclo_ativo:
            state["perfil_ativo_id"] = None
            state["perfil_ativo_nome"] = None
            state["perfil_ativo_capital_usdt"] = 0.0
            state["perfil_ativo_lucro_minimo_usdt"] = 0.0
            state["perfil_ativo_lucro_esperado_usdt"] = 0.0
            state["ultima_confirmacao_composta"] = {}
        perfil_ciclo = _obter_perfil(perfis_capital, state.get("perfil_ciclo_id")) or perfil_operacao

        notional_teto_operacao = notional_teto
        if perfil_operacao is not None and not ciclo_ativo and str(sinal.acao or "HOLD").upper() == "BUY":
            notional_teto_operacao = min(
                max(0.0, float(perfil_operacao.get("capital_usdt_util", perfil_operacao.get("capital_usdt", 0.0)) or 0.0)),
                max(0.0, notional_teto),
            )
        aprovacao = _aplicar_teto_notional(
            aprovacao,
            min(notional_teto_operacao, max(0.0, saldo_quote_livre_usdt)),
            max(saldo_total, saldo_quote_livre_usdt),
        )

        # garantir que `gestao_saida` existe mesmo quando não entrar no ramo
        gestao_saida = None

        if False and not ciclo_ativo and saldo_quote_livre_usdt < max(min_notional, 1e-9):
            quantidade_carteira = _quantidade_carteira_para_capital(
                saldo_base_total=saldo_base_total,
                preco_atual_usdt=preco_atual_usdt,
                notional_teto=notional_teto,
                step_size=step_size,
                min_qty=min_qty,
                ger=ger,
            )
            notional_carteira = quantidade_carteira * preco_atual_par
            if quantidade_carteira > 0.0 and notional_carteira < max(min_notional_operacional, 1e-9):
                state["ultima_acao"] = "HOLD"
                state["ultimo_motivo"] = "saldo_legado_abaixo_do_minimo_operacional"
                await self._registrar_evento(
                    simbolo=simbolo,
                    state=state,
                    payload={
                        "resultado": "sem_execucao",
                        "motivo": state["ultimo_motivo"],
                        "notional_estimado_quote": notional_carteira,
                        "min_notional": min_notional,
                        "min_notional_operacional": min_notional_operacional,
                    },
                )
                _espelhar_estado_corrente()
                return
            if quantidade_carteira > 0.0 and notional_carteira >= max(min_notional_operacional, 1e-9):
                perfil_carteira = _obter_perfil(perfis_capital, state.get("perfil_ativo_id")) or _obter_perfil(perfis_capital, "mini") or {}
                _abrir_ciclo(
                    state,
                    origem="carteira",
                    quantidade=quantidade_carteira,
                    preco_entrada=preco_atual_usdt,
                    notional_entrada=quantidade_carteira * preco_atual_usdt,
                    agora_ms=int(time.time() * 1000),
                    perfil=perfil_carteira,
                )
                _registrar_contexto_entrada_ciclo(state, sinal=sinal)
                state["ultimo_motivo"] = "ciclo_assumido_do_saldo_da_conta"
                ciclo_ativo = True
                saldo_base = _saldo_base_gerenciado(state, saldo_base_total)
                _atualizar_monitoramento_ciclo(state, saldo_base=saldo_base, preco_atual=preco_atual_usdt)

                gestao_saida = None
                if ciclo_ativo:
                    gestao_saida = _avaliar_saida_ciclo(
                        state=state,
                        sinal=sinal,
                        ajustes_sinal=ajustes_sinal,
                        saldo_base=saldo_base,
                        preco_atual=preco_atual_usdt,
                        perfil=perfil_carteira,
                    )
                    state["estado_ciclo"] = str(gestao_saida.get("estado_ciclo"))

                # `aprovacao` já foi calculada antes do fluxo de abertura/assunção de
                # ciclo — evitar reatribuição local que causava UnboundLocalError.

        # Se já estamos em ciclo ativo (ou acabamos de assumi-lo), avalia a
        # possibilidade de saída. Alguns caminhos acima podem não ter definido
        # `gestao_saida`, então computamos aqui quando necessário.
        if ciclo_ativo and gestao_saida is None:
            gestao_saida = _avaliar_saida_ciclo(
                state=state,
                sinal=sinal,
                ajustes_sinal=ajustes_sinal,
                saldo_base=saldo_base,
                preco_atual=preco_atual_usdt,
                perfil=perfil_ciclo,
            )
            state["estado_ciclo"] = str(gestao_saida.get("estado_ciclo"))
            state["ultimo_motivo"] = str((gestao_saida or {}).get("motivo") or state.get("ultimo_motivo"))

        venda_autonoma = bool(gestao_saida and gestao_saida.get("vender"))
        acao_execucao = "SELL" if venda_autonoma else sinal.acao
        motivo_execucao = str(gestao_saida.get("motivo")) if gestao_saida else str(sinal.detalhe.get("motivo", "execucao_realizada"))

        if not ciclo_ativo and str(state.get("motivo_proxima_acao") or "") == "saldo_residual_abaixo_do_minimo_operacional":
            state["ultima_acao"] = "HOLD"
            state["ultimo_motivo"] = "saldo_legado_abaixo_do_minimo_operacional"
            await self._registrar_evento(
                simbolo=simbolo,
                state=state,
                payload={
                    "resultado": "sem_execucao",
                    "motivo": state["ultimo_motivo"],
                    "sinal": sinal.to_dict(),
                    "aprovacao_risco": aprovacao.to_dict(),
                },
            )
            _espelhar_estado_corrente()
            return

        if not ciclo_ativo and str(state.get("proxima_acao_esperada") or "BUY").upper() == "BUY" and acao_execucao == "SELL":
            state["ultima_acao"] = "HOLD"
            state["ultimo_motivo"] = "proxima_acao_esperada_e_compra"
            await self._registrar_evento(
                simbolo=simbolo,
                state=state,
                payload={
                    "resultado": "sem_execucao",
                    "motivo": state["ultimo_motivo"],
                    "sinal": sinal.to_dict(),
                    "aprovacao_risco": aprovacao.to_dict(),
                },
            )
            _espelhar_estado_corrente()
            return

        if acao_execucao == "BUY" and not ciclo_ativo:
            if perfil_operacao is None:
                state["ultima_acao"] = "AGUARDANDO"
                state["ultimo_motivo"] = motivo_perfil
                await self._registrar_evento(
                    simbolo=simbolo,
                    state=state,
                    payload={
                        "resultado": "sem_execucao",
                        "motivo": state["ultimo_motivo"],
                        "sinal": sinal.to_dict(),
                        "aprovacao_risco": aprovacao.to_dict(),
                        "perfis_capital": state.get("perfis_capital"),
                    },
                )
                _espelhar_estado_corrente()
                return
            confirmacao_entrada = dict(perfil_operacao.get("confirmacao_composta") or _avaliar_confirmacao_composta(sinal=sinal, perfil=perfil_operacao))
            state["ultima_confirmacao_composta"] = confirmacao_entrada
            if not bool(confirmacao_entrada.get("confirmado")):
                state["ultima_acao"] = "AGUARDANDO"
                state["ultimo_motivo"] = "entrada_sem_confirmacao_composta"
                await self._registrar_evento(
                    simbolo=simbolo,
                    state=state,
                    payload={
                        "resultado": "sem_execucao",
                        "motivo": state["ultimo_motivo"],
                        "sinal": sinal.to_dict(),
                        "aprovacao_risco": aprovacao.to_dict(),
                        "perfil_ativo": perfil_operacao,
                    },
                )
                _espelhar_estado_corrente()
                return

        if venda_autonoma or (ciclo_ativo and sinal.acao == "SELL"):
            if not venda_autonoma:
                perfil_saida = perfil_ciclo
                confirmacao_saida = _avaliar_confirmacao_composta(sinal=sinal, perfil=perfil_saida, para_saida=True)
                state["ultima_confirmacao_composta"] = confirmacao_saida
                if not bool(confirmacao_saida.get("confirmado")):
                    state["ultima_acao"] = "AGUARDANDO"
                    state["ultimo_motivo"] = "saida_sem_confirmacao_composta"
                    await self._registrar_evento(
                        simbolo=simbolo,
                        state=state,
                        payload={
                            "resultado": "sem_execucao",
                            "motivo": state["ultimo_motivo"],
                            "sinal": sinal.to_dict(),
                            "aprovacao_risco": aprovacao.to_dict(),
                            "perfil_ativo": perfil_saida,
                        },
                    )
                    _espelhar_estado_corrente()
                    return
            aprovacao = _liberar_saida_ciclo(aprovacao, saldo_base=saldo_base, preco_atual=preco_atual_usdt)
        quantidade_venda_inicial = 0.0
        if not ciclo_ativo and acao_execucao == "SELL":
            quantidade_venda_inicial = _quantidade_carteira_para_capital(
                saldo_base_total=saldo_base_total,
                preco_atual_usdt=preco_atual_usdt,
                notional_teto=notional_teto_operacao,
                step_size=step_size,
                min_qty=min_qty,
                ger=ger,
            )

        if ciclo_ativo and acao_execucao == "BUY":
            state["ultima_acao"] = "HOLD"
            state["ultimo_motivo"] = str((gestao_saida or {}).get("motivo") or "ciclo_ativo_aguardando_saida")
            await self._registrar_evento(
                simbolo=simbolo,
                state=state,
                payload={
                    "resultado": "sem_execucao",
                    "motivo": state["ultimo_motivo"],
                    "sinal": sinal.to_dict(),
                    "aprovacao_risco": aprovacao.to_dict(),
                },
            )
            _espelhar_estado_corrente()
            return

        if not ciclo_ativo and acao_execucao == "SELL" and quantidade_venda_inicial <= 0.0:
            state["ultima_acao"] = "HOLD"
            state["ultimo_motivo"] = "sem_posicao_para_vender"
            await self._registrar_evento(
                simbolo=simbolo,
                state=state,
                payload={
                    "resultado": "sem_execucao",
                    "motivo": state["ultimo_motivo"],
                    "sinal": sinal.to_dict(),
                    "aprovacao_risco": aprovacao.to_dict(),
                },
            )
            _espelhar_estado_corrente()
            return

        if acao_execucao == "HOLD" or (not aprovacao.aprovado and not venda_autonoma):
            state["ultima_acao"] = "HOLD"
            if ciclo_ativo:
                state["ultimo_motivo"] = str((gestao_saida or {}).get("motivo") or sinal.detalhe.get("motivo", "monitorando_posicao"))
            else:
                state["ultimo_motivo"] = ";".join(aprovacao.motivos) if aprovacao.motivos else str(sinal.detalhe.get("motivo", "hold"))
            await self._registrar_evento(
                simbolo=simbolo,
                state=state,
                payload={
                    "resultado": "sem_execucao",
                    "sinal": sinal.to_dict(),
                    "aprovacao_risco": aprovacao.to_dict(),
                },
            )
            _espelhar_estado_corrente()
            return

        janela = dict(aprovacao.janela_decisao or {})
        executar_apos_ts = int(janela.get("executar_apos_ts", 0) or 0)
        agora = int(time.time() * 1000)
        if executar_apos_ts > agora and not venda_autonoma:
            state["ultima_acao"] = "AGUARDANDO"
            state["ultimo_motivo"] = "aguardando_janela_decisao"
            await self._registrar_evento(
                simbolo=simbolo,
                state=state,
                payload={
                    "resultado": "aguardando_janela",
                    "executar_apos_ts": executar_apos_ts,
                    "sinal": sinal.to_dict(),
                    "aprovacao_risco": aprovacao.to_dict(),
                },
            )
            _espelhar_estado_corrente()
            return

        plano = ExecutionPlan.from_mapping(
            await ExecutorIsoladoUsuario(_usuario_virtual(ajustes_risco, modo_testnet=modo_testnet)).preparar_execucao(
                aprovacao.to_dict(),
                preco_referencia=float(sinal.features.get("close", preco_atual_par) or preco_atual_par),
            )
        )

        ordem = None
        if acao_execucao == "BUY":
            notional_compra_usdt = min(
                max(0.0, float(aprovacao.notional_sugerido or 0.0)),
                max(0.0, saldo_quote_livre_usdt),
            )
            if quote_asset == "USDT" and notional_compra_usdt < max(min_notional, 1e-9):
                # Log detailed balance info to aid debugging when bot reports
                # 'saldo_quote_insuficiente_para_compra' despite apparent large account balance.
                LOG.warning(
                    "saldo_insuficiente_detectado",
                    extra={
                        "simbolo": simbolo,
                        "quote_asset": quote_asset,
                        "saldo_quote_total": saldo_quote_total,
                        "saldo_quote_livre_usdt": saldo_quote_livre_usdt,
                        "saldo_total_estimado_usdt": saldo_total,
                        "notional_compra_usdt": notional_compra_usdt,
                        "min_notional": min_notional,
                        "notional_teto": notional_teto,
                        "plano_simulacao": plano.to_dict(),
                    },
                )
                state["ultima_acao"] = "HOLD"
                state["ultimo_motivo"] = "saldo_quote_insuficiente_para_compra"
                await self._registrar_evento(
                    simbolo=simbolo,
                    state=state,
                    payload={"resultado": "sem_execucao", "motivo": state["ultimo_motivo"], "plano_execucao": plano.to_dict()},
                )
                _espelhar_estado_corrente()
                return
            if quote_asset == "USDT":
                try:
                    ordem = await ger.criar_ordem_market(simbolo, "BUY", quote_order_qty=notional_compra_usdt)
                    notional_executado_usdt = max(float(ordem.get("cummulativeQuoteQty", 0.0) or 0.0), notional_compra_usdt)
                except NotionalTooSmall:
                    # fallback: try to compute base quantity from notional and place by quantity
                    try:
                        if preco_atual_usdt <= 0.0:
                            raise
                        quantidade_fallback = notional_compra_usdt / preco_atual_usdt
                        quantidade_fallback = ger.ajustar_quantidade(quantidade_fallback, step_size, min_qty)
                        if quantidade_fallback <= 0.0:
                            raise NotionalTooSmall("fallback_quantity_too_small")
                        ordem = await ger.criar_ordem_market(simbolo, "BUY", quantidade=quantidade_fallback)
                        notional_executado_usdt = max(quantidade_fallback * preco_atual_usdt, notional_compra_usdt)
                    except NotionalTooSmall:
                        state["ultima_acao"] = "HOLD"
                        state["ultimo_motivo"] = "notional_ajuste_falhou"
                        await self._registrar_evento(
                            simbolo=simbolo,
                            state=state,
                            payload={"resultado": "sem_execucao", "motivo": state["ultimo_motivo"], "plano_execucao": plano.to_dict()},
                        )
                        _espelhar_estado_corrente()
                        return
                    except Exception:
                        state["ultima_acao"] = "HOLD"
                        state["ultimo_motivo"] = "notional_fallback_erro"
                        await self._registrar_evento(
                            simbolo=simbolo,
                            state=state,
                            payload={"resultado": "sem_execucao", "motivo": state["ultimo_motivo"], "plano_execucao": plano.to_dict()},
                        )
                        _espelhar_estado_corrente()
                        return
            else:
                if preco_quote_usdt <= 0.0 or preco_atual_par <= 0.0:
                    state["ultima_acao"] = "HOLD"
                    state["ultimo_motivo"] = "preco_quote_indisponivel"
                    await self._registrar_evento(
                        simbolo=simbolo,
                        state=state,
                        payload={"resultado": "sem_execucao", "motivo": state["ultimo_motivo"], "plano_execucao": plano.to_dict()},
                    )
                    _espelhar_estado_corrente()
                    return
                quote_qty = notional_compra_usdt / preco_quote_usdt
                quantidade = ger.ajustar_quantidade(quote_qty / preco_atual_par, step_size, min_qty)
                if quantidade <= 0.0:
                    state["ultima_acao"] = "HOLD"
                    state["ultimo_motivo"] = "saldo_quote_insuficiente_para_compra"
                    await self._registrar_evento(
                        simbolo=simbolo,
                        state=state,
                        payload={"resultado": "sem_execucao", "motivo": state["ultimo_motivo"], "plano_execucao": plano.to_dict()},
                    )
                    _espelhar_estado_corrente()
                    return
                if (quantidade * preco_atual_par) < max(min_notional, 1e-9):
                    state["ultima_acao"] = "HOLD"
                    state["ultimo_motivo"] = "notional_abaixo_do_minimo"
                    await self._registrar_evento(
                        simbolo=simbolo,
                        state=state,
                        payload={"resultado": "sem_execucao", "motivo": state["ultimo_motivo"], "plano_execucao": plano.to_dict()},
                    )
                    _espelhar_estado_corrente()
                    return
                ordem = await ger.criar_ordem_market(simbolo, "BUY", quantidade=quantidade)
                notional_executado_usdt = max(quantidade * preco_atual_par * preco_quote_usdt, notional_compra_usdt)
            quantidade_comprada = float(ordem.get("executedQty", 0.0) or 0.0)
            if quantidade_comprada <= 0.0:
                quantidade_comprada = float(plano.simulacao_ordem.get("quantidade", 0.0) or 0.0)
            if quantidade_comprada <= 0.0 and preco_atual_usdt > 0.0:
                quantidade_comprada = notional_compra_usdt / preco_atual_usdt
            _abrir_ciclo(
                state,
                origem="auto",
                quantidade=quantidade_comprada,
                preco_entrada=preco_atual_usdt,
                notional_entrada=notional_executado_usdt,
                agora_ms=int(time.time() * 1000),
                perfil=perfil_operacao,
            )
            _registrar_contexto_entrada_ciclo(state, sinal=sinal)
            _atualizar_monitoramento_ciclo(state, saldo_base=quantidade_comprada, preco_atual=preco_atual_usdt)
        else:
            quantidade_base_venda = max(0.0, saldo_base) if ciclo_ativo else quantidade_venda_inicial
            quantidade = ger.ajustar_quantidade(quantidade_base_venda, step_size, min_qty)
            if quantidade <= 0.0:
                state["ultima_acao"] = "HOLD"
                state["ultimo_motivo"] = "saldo_base_insuficiente_para_venda"
                await self._registrar_evento(
                    simbolo=simbolo,
                    state=state,
                    payload={"resultado": "sem_execucao", "motivo": state["ultimo_motivo"], "plano_execucao": plano.to_dict()},
                )
                _espelhar_estado_corrente()
                return
            notional_venda = quantidade * preco_atual_par
            if notional_venda < max(min_notional_operacional, 1e-9):
                state["ultima_acao"] = "HOLD"
                state["ultimo_motivo"] = "notional_abaixo_do_minimo_saida"
                await self._registrar_evento(
                    simbolo=simbolo,
                    state=state,
                    payload={
                        "resultado": "sem_execucao",
                        "motivo": state["ultimo_motivo"],
                        "plano_execucao": plano.to_dict(),
                        "notional_estimado_quote": notional_venda,
                        "min_notional": min_notional,
                        "min_notional_operacional": min_notional_operacional,
                    },
                )
                _espelhar_estado_corrente()
                return
            try:
                ordem = await ger.criar_ordem_market(simbolo, "SELL", quantidade=quantidade)
            except NotionalTooSmall:
                state["ultima_acao"] = "HOLD"
                state["ultimo_motivo"] = "notional_ajuste_falhou_saida"
                await self._registrar_evento(
                    simbolo=simbolo,
                    state=state,
                    payload={"resultado": "sem_execucao", "motivo": state["ultimo_motivo"], "plano_execucao": plano.to_dict()},
                )
                _espelhar_estado_corrente()
                return
            if ciclo_ativo:
                await self._registrar_fechamento_ciclo(
                    simbolo=simbolo,
                    state=state,
                    preco_saida_usdt=preco_atual_usdt,
                    motivo=str((gestao_saida or {}).get("motivo") or "saida_executada"),
                )
                _encerrar_ciclo(
                    state,
                    motivo=str((gestao_saida or {}).get("motivo") or "saida_executada"),
                    agora_ms=int(time.time() * 1000),
                )
                _atualizar_monitoramento_ciclo(state, saldo_base=0.0, preco_atual=preco_atual_usdt)
            else:
                state["ultimo_ciclo_encerrado_ts"] = int(time.time() * 1000)
                state["ultimo_ciclo_motivo_encerramento"] = "rotacao_inicial_para_quote"

        state["ultima_acao"] = acao_execucao
        state["ultimo_motivo"] = motivo_execucao
        state["ultimo_trade_ts_execucao"] = int(time.time() * 1000)
        state["ultima_acao_execucao"] = acao_execucao
        historico_local = list(state.get("historico_execucoes_ts", []))
        historico_local.append(state["ultimo_trade_ts_execucao"])
        state["historico_execucoes_ts"] = historico_local[-50:]

        await self._registrar_evento(
            simbolo=simbolo,
            state=state,
            payload={
                "resultado": "execucao_realizada",
                "sinal": sinal.to_dict(),
                "aprovacao_risco": aprovacao.to_dict(),
                "plano_execucao": plano.to_dict(),
                "ordem": {
                    "id": ordem.get("orderId"),
                    "status": ordem.get("status"),
                    "lado": acao_execucao,
                },
            },
        )
        _espelhar_estado_corrente()

    async def _loop(self, token: str, sessao: dict[str, Any]) -> None:
        state = self._state.get(token)
        if state is None:
            return

        cliente_conta = ClienteBinance(
            api_key=str(sessao["api_key"]),
            api_secret=str(sessao["api_secret"]),
            testnet=bool(sessao.get("modo_testnet", False)),
        )
        cliente_mercado = ClienteBinance(testnet=False)
        ger = GerenciadorOrdens(
            api_key=str(sessao["api_key"]),
            api_secret=str(sessao["api_secret"]),
            testnet=bool(sessao.get("modo_testnet", False)),
        )
        try:
            while True:
                # Circuit-breaker: se acionado, pause o loop até reset manual
                if state.get("circuit_tripped"):
                    LOG.error("circuit_breaker_acionado", extra={"token": token, "simbolo": state.get("simbolo")})
                    await asyncio.sleep(30)
                    continue
                try:
                    await self._executar_ciclo(
                        token=token,
                        sessao=sessao,
                        cliente_conta=cliente_conta,
                        cliente_mercado=cliente_mercado,
                        ger=ger,
                    )
                    # sucesso -> reset erro consecutivo
                    state["consecutive_errors"] = 0
                    state["ultimo_erro"] = None
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    state["ultimo_erro"] = str(exc)
                    state["ultima_acao"] = "ERRO"
                    state["ultimo_motivo"] = str(exc)
                    LOG.warning("falha_auto_trade", extra={"simbolo": state.get("simbolo"), "erro": str(exc)})
                    await self._registrar_evento(
                        simbolo=str(state.get("simbolo") or "BTCUSDT"),
                        state=state,
                        payload={"resultado": "erro", "erro": str(exc)},
                    )
                    # incrementar contador e possivel trip
                    state["consecutive_errors"] = int(state.get("consecutive_errors", 0) or 0) + 1
                    limit = int(state.get("consecutive_errors_limit", 5) or 5)
                    if int(state.get("consecutive_errors", 0)) >= limit:
                        state["circuit_tripped"] = True
                        await self._registrar_evento(simbolo=str(state.get("simbolo") or ""), state=state, payload={"motivo": "consecutive_errors_limit_reached"})
                state["ultimo_ts"] = int(time.time() * 1000)
                await asyncio.sleep(max(5, int(state.get("intervalo_segundos", 30) or 30)))
        except asyncio.CancelledError:
            raise
        finally:
            await cliente_conta.fechar()
            await cliente_mercado.fechar()
            await ger.fechar()


AutoTrader = TestnetAutoTrader
