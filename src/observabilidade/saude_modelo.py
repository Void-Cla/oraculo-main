"""Saúde de modelo/treino em runtime (observabilidade) — alimenta as saídas de API.

Agrega o status do GerenciadorModelo (treino online, divergência, gate de amostras)
com a qualidade recente medida no banco (IC entre predição e realidade), permitindo
acompanhar AO VIVO se o aprendizado está saudável e se há sinal utilizável.
"""
from __future__ import annotations

from typing import Any

from src.modelagem.gerenciador_modelo import obter_gerenciador_modelo
from src.observabilidade.qualidade_sinal import calcular_ic
from src.persistencia.conexao import get_conexao

# Norma L2 de coeficientes acima da qual o modelo online é suspeito de ter divergido.
# O modelo saturado do run 13-18h tinha norma ~71; saudável fica bem abaixo disso.
_LIMIAR_COEF_DIVERGENTE: float = 10.0
# ms por minuto — alinha `ts_previsao` (instante da previsão) ao candle 1m que o contém.
_MS_POR_MINUTO: int = 60_000


async def resumo_qualidade_recente(simbolo: str, limite: int = 200) -> dict[str, Any]:
    """IC do RETORNO predito vs RETORNO real nos últimos N outcomes — a métrica de EDGE.

    ⚠️ Correlacionar PREÇO previsto vs PREÇO real dá IC ~1.0 espúrio (preço é persistente
    em nível); isso NÃO é sinal. O que importa é o RETORNO: (y_hat − ref)/ref vs
    (y_true − ref)/ref, onde `ref` é o close no instante da previsão (join com ohlcv_1m).
    """
    simbolo = str(simbolo or "").upper()
    limite = max(2, min(2000, int(limite)))
    ret_prev: list[float] = []
    ret_real: list[float] = []
    err: list[float] = []
    async with get_conexao() as con:
        # `ts_previsao` é o instante da previsão (meio do minuto); alinha ao candle 1m que o
        # contém via floor-ao-minuto, senão o join exato nunca casa (ts não é minute-aligned).
        cur = await con.execute(
            "SELECT o.y_hat, o.y_true, o.err_rel, c.close "
            "FROM outcomes o JOIN ohlcv_1m c "
            "  ON c.simbolo = o.simbolo AND c.ts = (o.ts_previsao / ?) * ? "
            "WHERE o.simbolo=? ORDER BY o.ts_previsao DESC LIMIT ?",
            (_MS_POR_MINUTO, _MS_POR_MINUTO, simbolo, limite),
        )
        linhas = await cur.fetchall()
    for yh, yt, er, ref in linhas:
        if yh is None or yt is None or ref is None or float(ref) <= 0.0:
            continue
        ref_f = float(ref)
        ret_prev.append((float(yh) - ref_f) / ref_f)   # retorno PREVISTO
        ret_real.append((float(yt) - ref_f) / ref_f)    # retorno REAL
        if er is not None:
            err.append(abs(float(er)))
    n = len(ret_prev)
    ic = calcular_ic(ret_prev, ret_real) if n >= 2 else 0.0
    erro_medio_rel = (sum(err) / len(err)) if err else None
    return {
        "simbolo": simbolo,
        "amostras": n,
        "ic_recente": round(ic, 4),          # IC de RETORNO (não de preço) — métrica de edge
        "ic_utilizavel": ic > 0.05,
        "erro_medio_rel": round(erro_medio_rel, 6) if erro_medio_rel is not None else None,
        "limite_consultado": limite,
    }


async def saude_modelo(simbolo: str, limite_qualidade: int = 200) -> dict[str, Any]:
    """Consolida status do treino online + qualidade recente para a API de runtime."""
    simbolo = str(simbolo or "").upper()
    status = obter_gerenciador_modelo(simbolo).status()
    qualidade = await resumo_qualidade_recente(simbolo, limite_qualidade)
    coef_norm = status.get("coef_norm")
    divergente = coef_norm is not None and float(coef_norm) > _LIMIAR_COEF_DIVERGENTE
    return {
        **status,
        "qualidade_recente": qualidade,
        "diagnostico": {
            "online_em_uso": bool(status.get("online_em_uso")),
            "online_divergente_suspeito": bool(divergente),
            "tem_sinal_recente": bool(qualidade.get("ic_utilizavel")),
        },
    }
