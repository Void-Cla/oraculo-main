from __future__ import annotations

import asyncio
from typing import Any

from src.binance_api.cliente import ClienteBinance
from src.binance_api.coletor_velas_rest import coletar_e_persistir
from src.multiativo.config import ativo_base, ativo_cotacao
from src.multiativo.orquestrador import montar_monitoramento_multiativo
from src.observabilidade.logger import get_logger
from src.servicos.dashboard import montar_dashboard
from src.servicos.noticias import obter_noticias_para_peso
from src.tarefas.tarefas_previsao import gerar_previsao_dados_persistidos

LOG = get_logger("painel_conta")

_MAPA_STATUS_ORDEM = {
    "NEW": "ABERTA",
    "PARTIALLY_FILLED": "PARCIAL",
    "FILLED": "EXECUTADA",
    "CANCELED": "CANCELADA",
    "PENDING_CANCEL": "CANCELANDO",
    "REJECTED": "REJEITADA",
    "EXPIRED": "EXPIRADA",
    "EXPIRED_IN_MATCH": "EXPIRADA",
}


def _saldo_ativo(conta: dict[str, Any], ativo: str) -> dict[str, float]:
    for balance in conta.get("balances", []):
        if str(balance.get("asset", "")).upper() != ativo.upper():
            continue
        livre = float(balance.get("free", 0.0) or 0.0)
        travado = float(balance.get("locked", 0.0) or 0.0)
        return {
            "livre": livre,
            "travado": travado,
            "total": livre + travado,
        }
    return {"livre": 0.0, "travado": 0.0, "total": 0.0}


def _taxas_conta(conta: dict[str, Any]) -> dict[str, float]:
    commission_rates = conta.get("commissionRates") or {}

    def _taxa_decimal(chave_nova: str, chave_legada: str) -> float:
        if commission_rates.get(chave_nova) not in {None, ""}:
            return float(commission_rates[chave_nova])
        if conta.get(chave_legada) not in {None, ""}:
            return float(conta[chave_legada]) / 10000.0
        return 0.0

    maker = _taxa_decimal("maker", "makerCommission")
    taker = _taxa_decimal("taker", "takerCommission")
    buyer = _taxa_decimal("buyer", "buyerCommission")
    seller = _taxa_decimal("seller", "sellerCommission")
    return {
        "maker_pct": round(maker * 100.0, 4),
        "taker_pct": round(taker * 100.0, 4),
        "compra_pct": round(buyer * 100.0, 4),
        "venda_pct": round(seller * 100.0, 4),
    }


async def _preco_ativo_usdt(
    *,
    cliente: ClienteBinance,
    ativo: str,
    cache: dict[str, float],
    preco_btcusdt: float,
) -> float:
    ativo = ativo.upper()
    if ativo in cache:
        return cache[ativo]
    if ativo == "USDT":
        cache[ativo] = 1.0
        return 1.0
    if ativo == "BTC":
        if preco_btcusdt > 0.0:
            cache[ativo] = preco_btcusdt
            return preco_btcusdt
        try:
            preco = await cliente.obter_preco_atual("BTCUSDT")
        except Exception:
            LOG.warning("falha_preco_ativo_usdt", extra={"ativo": ativo})
            preco = 0.0
        cache[ativo] = preco
        return preco
    simbolo = f"{ativo}USDT"
    try:
        preco = await cliente.obter_preco_atual(simbolo)
    except Exception:
        LOG.warning("falha_preco_ativo_usdt", extra={"ativo": ativo})
        preco = 0.0
    cache[ativo] = preco
    return preco


def _consumir_lotes(lotes: list[dict[str, float]], quantidade: float) -> tuple[float, float]:
    restante = max(0.0, quantidade)
    custo = 0.0
    while restante > 1e-12 and lotes:
        lote = lotes[0]
        consumido = min(lote["quantidade"], restante)
        custo += consumido * lote["custo_unitario"]
        lote["quantidade"] -= consumido
        restante -= consumido
        if lote["quantidade"] <= 1e-12:
            lotes.pop(0)
    return custo, quantidade - restante


async def _historico_negociacoes(
    *,
    cliente: ClienteBinance,
    trades: list[dict[str, Any]],
    preco_atual: float,
    simbolo: str,
) -> dict[str, Any]:
    base_ativo = ativo_base(simbolo)
    quote_ativo = ativo_cotacao(simbolo)
    cache_precos: dict[str, float] = {"USDT": 1.0}
    if simbolo.upper() == "BTCUSDT" and preco_atual > 0.0:
        cache_precos["BTC"] = preco_atual
    lotes: list[dict[str, float]] = []
    historico: list[dict[str, Any]] = []
    taxas_totais = 0.0
    pnl_realizado_bruto = 0.0
    pnl_realizado_liquido = 0.0
    cobertura_fifo_incompleta = False

    for trade in sorted(trades, key=lambda item: (int(item.get("time", 0)), int(item.get("id", 0)))):
        preco = float(trade.get("price", 0.0) or 0.0)
        quantidade = float(trade.get("qty", 0.0) or 0.0)
        valor_quote = float(trade.get("quoteQty", 0.0) or (preco * quantidade))
        preco_quote_usdt = await _preco_ativo_usdt(
            cliente=cliente,
            ativo=quote_ativo,
            cache=cache_precos,
            preco_btcusdt=cache_precos.get("BTC", 0.0),
        )
        valor_usdt = valor_quote if quote_ativo == "USDT" else (valor_quote * preco_quote_usdt)
        taxa = float(trade.get("commission", 0.0) or 0.0)
        ativo_taxa = str(trade.get("commissionAsset") or "USDT").upper()
        taxa_usdt = taxa * await _preco_ativo_usdt(
            cliente=cliente,
            ativo=ativo_taxa,
            cache=cache_precos,
            preco_btcusdt=cache_precos.get("BTC", 0.0),
        )
        taxas_totais += taxa_usdt

        lado = "COMPRA" if bool(trade.get("isBuyer")) else "VENDA"
        lucro_bruto = None
        lucro_liquido = None
        custo_fifo = None
        pnl_confiavel = True

        if lado == "COMPRA":
            quantidade_liquida = quantidade - taxa if ativo_taxa == base_ativo else quantidade
            quantidade_liquida = max(0.0, quantidade_liquida)
            if quantidade_liquida > 1e-12:
                custo_total = valor_usdt + taxa_usdt
                lotes.append(
                    {
                        "quantidade": quantidade_liquida,
                        "custo_unitario": (custo_total / quantidade_liquida) if quantidade_liquida else preco,
                    }
                )
        else:
            custo_consumido, quantidade_coberta = _consumir_lotes(lotes, quantidade)
            restante = max(0.0, quantidade - quantidade_coberta)
            if restante > 1e-12:
                cobertura_fifo_incompleta = True
                pnl_confiavel = False
                custo_consumido += restante * preco
            custo_fifo = custo_consumido
            lucro_bruto = valor_usdt - custo_consumido
            lucro_liquido = lucro_bruto - taxa_usdt
            pnl_realizado_bruto += lucro_bruto
            pnl_realizado_liquido += lucro_liquido
            if ativo_taxa == base_ativo and taxa > 0:
                _consumir_lotes(lotes, taxa)

        historico.append(
            {
                "id_trade": int(trade.get("id", 0) or 0),
                "id_ordem": int(trade.get("orderId", 0) or 0),
                "horario": int(trade.get("time", 0) or 0),
                "lado": lado,
                "preco": preco,
                "quantidade_base": quantidade,
                "valor_usdt": valor_usdt,
                "valor_quote": valor_quote,
                "ativo_base": base_ativo,
                "ativo_quote": quote_ativo,
                "taxa": taxa,
                "ativo_taxa": ativo_taxa,
                "taxa_usdt": round(taxa_usdt, 8),
                "maker": bool(trade.get("isMaker")),
                "custo_fifo_usdt": round(custo_fifo, 8) if custo_fifo is not None else None,
                "lucro_bruto_usdt": round(lucro_bruto, 8) if lucro_bruto is not None else None,
                "lucro_liquido_usdt": round(lucro_liquido, 8) if lucro_liquido is not None else None,
                "pnl_confiavel": pnl_confiavel,
            }
        )

    inventario_base = sum(lote["quantidade"] for lote in lotes)
    custo_em_aberto = sum(lote["quantidade"] * lote["custo_unitario"] for lote in lotes)
    custo_medio_base = (custo_em_aberto / inventario_base) if inventario_base > 1e-12 else 0.0
    valor_base_atual_usdt = await _preco_ativo_usdt(
        cliente=cliente,
        ativo=base_ativo,
        cache=cache_precos,
        preco_btcusdt=cache_precos.get("BTC", 0.0),
    )
    pnl_nao_realizado = (inventario_base * valor_base_atual_usdt) - custo_em_aberto if valor_base_atual_usdt > 0 else 0.0

    return {
        "historico": historico[-120:],
        "taxas_totais_usdt": round(taxas_totais, 8),
        "pnl_realizado_bruto_usdt": round(pnl_realizado_bruto, 8),
        "pnl_realizado_liquido_usdt": round(pnl_realizado_liquido, 8),
        "inventario_base": round(inventario_base, 8),
        "custo_medio_base_usdt": round(custo_medio_base, 8),
        "pnl_nao_realizado_usdt": round(pnl_nao_realizado, 8),
        "cobertura_fifo_incompleta": cobertura_fifo_incompleta,
    }


def _ordens_binance(ordens: list[dict[str, Any]]) -> dict[str, Any]:
    historico: list[dict[str, Any]] = []
    resumo = {
        "abertas": 0,
        "parciais": 0,
        "executadas": 0,
        "canceladas": 0,
        "rejeitadas": 0,
        "expiradas": 0,
        "cancelando": 0,
    }

    for item in sorted(ordens, key=lambda ordem: (int(ordem.get("updateTime", 0) or ordem.get("time", 0)), int(ordem.get("orderId", 0)))):
        status_binance = str(item.get("status") or "NEW").upper()
        status_local = _MAPA_STATUS_ORDEM.get(status_binance, status_binance)
        chave_resumo = {
            "ABERTA": "abertas",
            "PARCIAL": "parciais",
            "EXECUTADA": "executadas",
            "CANCELADA": "canceladas",
            "REJEITADA": "rejeitadas",
            "EXPIRADA": "expiradas",
            "CANCELANDO": "cancelando",
        }.get(status_local)
        if chave_resumo:
            resumo[chave_resumo] += 1

        historico.append(
            {
                "id_ordem": int(item.get("orderId", 0) or 0),
                "cliente_id": item.get("clientOrderId"),
                "horario": int(item.get("updateTime", 0) or item.get("time", 0) or 0),
                "lado": "COMPRA" if str(item.get("side")).upper() == "BUY" else "VENDA",
                "tipo": str(item.get("type") or "MARKET").upper(),
                "status": status_local,
                "status_binance": status_binance,
                "preco": float(item.get("price", 0.0) or 0.0),
                "preco_stop": float(item.get("stopPrice", 0.0) or 0.0),
                "quantidade": float(item.get("origQty", 0.0) or 0.0),
                "executado": float(item.get("executedQty", 0.0) or 0.0),
                "valor_usdt": float(item.get("cummulativeQuoteQty", 0.0) or 0.0),
            }
        )

    return {
        "resumo": resumo,
        "historico": historico[-80:],
        "abertas": [item for item in historico if item["status"] in {"ABERTA", "PARCIAL", "CANCELANDO"}][-30:],
    }


async def montar_painel_conta(
    *,
    simbolo: str,
    sessao: dict[str, Any],
    loop_previsao_ativo: bool,
    db_path: str,
    ajustes_sinal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    simbolo = simbolo.upper()
    noticias_cache = await obter_noticias_para_peso(simbolo)
    noticias = list(noticias_cache.get("itens", []))

    try:
        await coletar_e_persistir(simbolo=simbolo, limit=120)
        await gerar_previsao_dados_persistidos(
            simbolo=simbolo,
            noticias=noticias,
            coletar_mercado=False,
            limite_klines=120,
            persistir=True,
            origem="painel_conta",
            ajustes_sinal=ajustes_sinal,
        )
    except Exception as exc:
        LOG.warning("falha_refresh_painel_conta", extra={"simbolo": simbolo, "erro": str(exc)})

    base = await montar_dashboard(
        simbolo=simbolo,
        usuario_id=None,
        loop_previsao_ativo=loop_previsao_ativo,
        db_path=db_path,
    )
    preco_atual = float((base.get("mercado") or {}).get("preco_atual") or 0.0)

    cliente = ClienteBinance(
        api_key=str(sessao["api_key"]),
        api_secret=str(sessao["api_secret"]),
        testnet=bool(sessao["modo_testnet"]),
    )
    binance_disponivel = True
    erro_binance = None
    conta_raw: dict[str, Any] = {}
    trades: list[dict[str, Any]] = []
    ordens_abertas: list[dict[str, Any]] = []
    ordens_todas: list[dict[str, Any]] = []
    negociacoes = {
        "historico": [],
        "taxas_totais_usdt": 0.0,
        "pnl_realizado_bruto_usdt": 0.0,
        "pnl_realizado_liquido_usdt": 0.0,
        "inventario_base": 0.0,
        "custo_medio_base_usdt": 0.0,
        "pnl_nao_realizado_usdt": 0.0,
        "cobertura_fifo_incompleta": False,
    }
    monitoramento_multiativo = {
        "ativos_monitorados": [],
        "pares_monitorados": [],
        "precos_usdt": {},
        "saldos_monitorados": {},
        "perfil_taxas": {},
        "capital_manager": {},
        "bnb_manager": {},
        "scanner": {"pares": [], "total_validas": 0, "sem_vantagem_real": True},
        "arbitragem_triangular": {"rotas": [], "oportunidades_validas": 0, "sem_vantagem_real": True},
        "noticias_contexto": {"itens": []},
        "sem_vantagem_estatistica": True,
    }
    try:
        conta_raw, trades, ordens_abertas, ordens_todas = await asyncio.gather(
            cliente.obter_conta_raw(),
            cliente.obter_trades_conta(simbolo=simbolo, limit=1000),
            cliente.obter_ordens_abertas(simbolo=simbolo),
            cliente.obter_todas_ordens(simbolo=simbolo, limit=1000),
        )
        if preco_atual <= 0.0:
            preco_atual = await cliente.obter_preco_atual(simbolo)
        negociacoes = await _historico_negociacoes(cliente=cliente, trades=trades, preco_atual=preco_atual, simbolo=simbolo)
        try:
            monitoramento_multiativo = await montar_monitoramento_multiativo(
                cliente=cliente,
                conta_raw=conta_raw,
                persistir_mercado=False,
                ajustes_sinal=ajustes_sinal,
            )
        except Exception as exc:
            LOG.warning("falha_monitoramento_multiativo", extra={"erro": str(exc)})
    except Exception as exc:
        binance_disponivel = False
        erro_binance = str(exc)
        ordens_abertas = []
        LOG.error("falha_consulta_conta_binance", extra={"simbolo": simbolo, "erro": erro_binance})
    finally:
        await cliente.fechar()

    ordens = _ordens_binance(ordens_todas if binance_disponivel else ordens_abertas)

    saldo_btc = _saldo_ativo(conta_raw, "BTC") if binance_disponivel else {"livre": 0.0, "travado": 0.0, "total": 0.0}
    saldo_base = _saldo_ativo(conta_raw, ativo_base(simbolo)) if binance_disponivel else {"livre": 0.0, "travado": 0.0, "total": 0.0}
    saldo_quote = _saldo_ativo(conta_raw, ativo_cotacao(simbolo)) if binance_disponivel else {"livre": 0.0, "travado": 0.0, "total": 0.0}
    saldo_usdt = _saldo_ativo(conta_raw, "USDT") if binance_disponivel else {"livre": 0.0, "travado": 0.0, "total": 0.0}
    saldo_total_estimado = float((monitoramento_multiativo.get("capital_manager") or {}).get("saldo_total_estimado_usdt", 0.0) or 0.0)
    if saldo_total_estimado <= 0.0:
        saldo_total_estimado = saldo_usdt["total"] + (saldo_btc["total"] * preco_atual)
    taxas = _taxas_conta(conta_raw) if binance_disponivel else {"maker_pct": 0.0, "taker_pct": 0.0, "compra_pct": 0.0, "venda_pct": 0.0}

    operacional = dict(base.get("operacional") or {})
    operacional["binance"] = "operacional" if binance_disponivel else "travado"
    operacional["conta"] = "operacional" if binance_disponivel else "travado"
    if erro_binance:
        operacional["erro_binance"] = erro_binance

    nome_exibicao = str(sessao.get("nome_exibicao") or "Conta SPOT Binance")
    id_conta = str(sessao.get("id_conta") or "nao_informado_pela_binance")
    if binance_disponivel:
        nome_exibicao = f"Conta {str(conta_raw.get('accountType') or 'SPOT').upper()} Binance"
        if conta_raw.get("uid") not in {None, ""}:
            id_conta = str(conta_raw["uid"])

    conta = {
        "disponivel": binance_disponivel,
        "nome_exibicao": nome_exibicao,
        "id_conta": id_conta,
        "modo_testnet": bool(sessao["modo_testnet"]),
        "api_key_mascarada": sessao["api_key_mascarada"],
        "permissoes": conta_raw.get("permissions", []) if binance_disponivel else [],
        "permite_trade": bool(conta_raw.get("canTrade")) if binance_disponivel else False,
        "ativo_base": ativo_base(simbolo),
        "ativo_quote": ativo_cotacao(simbolo),
        "saldo_base": saldo_base,
        "saldo_quote": saldo_quote,
        "saldo_btc": saldo_btc,
        "saldo_usdt": saldo_usdt,
        "saldos_monitorados": monitoramento_multiativo.get("saldos_monitorados", {}),
        "saldo_total_estimado_usdt": round(saldo_total_estimado, 8),
        "preco_simbolo": round(preco_atual, 8),
        "preco_btcusdt": round(float((monitoramento_multiativo.get("precos_usdt") or {}).get("BTC", preco_atual) or preco_atual), 8),
        "taxas": taxas,
        "taxas_efetivas": monitoramento_multiativo.get("perfil_taxas", {}),
        "erro": erro_binance,
    }

    pnl = {
        **negociacoes,
        "simbolo": simbolo,
        "ativo_base": ativo_base(simbolo),
        "ativo_quote": ativo_cotacao(simbolo),
        "inventario_btc": float(negociacoes.get("inventario_base", 0.0) or 0.0) if ativo_base(simbolo) == "BTC" else 0.0,
        "custo_medio_btc": float(negociacoes.get("custo_medio_base_usdt", 0.0) or 0.0) if ativo_base(simbolo) == "BTC" else 0.0,
        "pnl_total_liquido_usdt": round(
            float(negociacoes["pnl_realizado_liquido_usdt"]) + float(negociacoes["pnl_nao_realizado_usdt"]),
            8,
        ),
    }

    return {
        "simbolo": simbolo,
        "ts_atualizacao": base.get("ts_atualizacao"),
        "sessao": {
            "autenticado": True,
            "api_key_mascarada": sessao["api_key_mascarada"],
            "modo_testnet": bool(sessao["modo_testnet"]),
            "nome_exibicao": nome_exibicao,
            "id_conta": id_conta,
        },
        "operacional": operacional,
        "mercado": base.get("mercado"),
        "modelos": base.get("modelos"),
        "conta": conta,
        "pnl": pnl,
        "ordens": ordens,
        "noticias": noticias_cache,
        "multiativos": monitoramento_multiativo,
        "historico_negociacoes": negociacoes["historico"],
        "historico": base.get("historico"),
    }
