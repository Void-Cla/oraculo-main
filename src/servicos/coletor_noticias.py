"""
Coletor de notícias e calculador de peso por símbolo.
Esta implementação é um scaffold seguro: lê `SYMBOLS` do ambiente,
fornece interface assíncrona para buscar e calcular `sentiment_weight`.
"""
from __future__ import annotations

import os
import asyncio
from typing import Dict, List
from src.observabilidade.logger import get_logger
from src.servicos.noticias import obter_noticias_para_peso

LOG = get_logger("coletor_noticias")


def simbolos_monitorados() -> List[str]:
    from src.multiativo.config import pares_monitorados
    return list(pares_monitorados())


async def buscar_noticias_para_simbolo(simbolo: str) -> List[dict]:
    """Tenta usar o coletor principal (`noticias.obter_noticias_para_peso`).
    Retorna a lista de itens coletados (pode ser vazia).
    """
    try:
        payload = await obter_noticias_para_peso(simbolo, forcar_atualizacao=False)
        return payload.get("itens", [])
    except Exception as exc:
        LOG.warning("buscar_noticias_falha_integracao", extra={"simbolo": simbolo, "erro": str(exc)})
        return []


def calcular_peso_sentimento(artigos: List[dict]) -> float:
    """Recebe artigos e retorna score entre -1.0 .. +1.0.
    Aqui apenas stub que retorna 0.0 (neutro).
    """
    return 0.0


async def varrer_e_pesos() -> Dict[str, float]:
    resultados: Dict[str, float] = {}
    simbolos = simbolos_monitorados()
    for s in simbolos:
        artigos = await buscar_noticias_para_simbolo(s)
        peso = calcular_peso_sentimento(artigos)
        resultados[s] = peso
    LOG.info("pesos_noticias_atualizados", extra={"itens": len(resultados)})
    return resultados


if __name__ == "__main__":
    # Execução simples para desenvolvimento
    import asyncio

    print(asyncio.run(varrer_e_pesos()))
