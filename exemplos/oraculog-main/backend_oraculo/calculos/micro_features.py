"""
Motor Local de Micro-Features e Previsão Direcional (PT-BR)
Execução ultra-rápida (<1ms) para operar em janelas curtas de mercado (5s a 15s)
com alta sensibilidade a fluxo de ordens e micro-tendências.
"""
import math
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass

@dataclass
class MicroFeaturesMercado:
    par: str
    preco_atual: float
    retorno_15s: float
    retorno_1m: float
    desequilibrio_livro: float  # -1.0 (venda pesada) a +1.0 (compra pesada)
    pressao_compradora: float   # 0.0 a 1.0
    spread_pct: float
    volatilidade_atr_pct: float
    score_direcional_local: float  # -1.0 a +1.0
    confianca_sinal: float          # 0.0 a 1.0
    sugestao_direcao: str          # 'COMPRA', 'VENDA', 'NEUTRO'

class ExtratorMicroFeatures:
    def __init__(self):
        pass

    def extrair_e_prever(
        self,
        par: str,
        precos_recentes: List[float],
        bids_volume: float,
        asks_volume: float,
        melhor_bid: float,
        melhor_ask: float,
        peso_noticias_ia: float = 0.20,
        bias_noticias_ia: float = 0.0
    ) -> MicroFeaturesMercado:
        """
        Gera features e previsão direcional local imediata ponderando
        o viés macro de IA (atualizado a cada 2 horas) com o micro-fluxo de ordens.
        """
        if not precos_recentes:
            precos_recentes = [100.0, 100.0]

        preco_atual = precos_recentes[-1]
        
        # 1. Retornos de curto prazo
        p_antigo_15s = precos_recentes[-2] if len(precos_recentes) >= 2 else preco_atual
        p_antigo_1m = precos_recentes[0] if len(precos_recentes) >= 5 else p_antigo_15s

        retorno_15s = (preco_atual - p_antigo_15s) / p_antigo_15s if p_antigo_15s > 0 else 0.0
        retorno_1m = (preco_atual - p_antigo_1m) / p_antigo_1m if p_antigo_1m > 0 else 0.0

        # 2. Desequilíbrio do Livro de Ofertas (Order Book Imbalance)
        vol_total = bids_volume + asks_volume
        if vol_total > 0:
            desequilibrio_livro = (bids_volume - asks_volume) / vol_total
            pressao_compradora = bids_volume / vol_total
        else:
            desequilibrio_livro = 0.0
            pressao_compradora = 0.5

        # 3. Spread percentual
        preco_medio = (melhor_bid + melhor_ask) / 2.0 if (melhor_bid + melhor_ask) > 0 else preco_atual
        spread_absoluto = max(0.0, melhor_ask - melhor_bid)
        spread_pct = (spread_absoluto / preco_medio) if preco_medio > 0 else 0.0001

        # 4. Volatilidade local estimada
        variacoes = [
            abs(precos_recentes[i] - precos_recentes[i-1]) / precos_recentes[i-1]
            for i in range(1, len(precos_recentes))
        ] if len(precos_recentes) > 1 else [0.0005]
        volatilidade_atr_pct = sum(variacoes) / len(variacoes) if variacoes else 0.0005

        # 5. Previsão Direcional Ponderada Local
        # Componentes quantitativos (80% a 85% do peso na decisão ultra-rápida):
        score_momentum = (retorno_15s * 40.0) + (retorno_1m * 20.0)
        score_momentum = max(-1.0, min(1.0, score_momentum))

        score_livro = desequilibrio_livro  # -1.0 a +1.0

        # Fusão do motor local com o viés de IA de 2 horas:
        # Peso da IA (ex: 20%) + Peso do motor local (ex: 80%)
        peso_local = max(0.60, 1.0 - peso_noticias_ia)
        score_local = (score_livro * 0.55) + (score_momentum * 0.45)
        
        score_final = (score_local * peso_local) + (bias_noticias_ia * peso_noticias_ia)
        score_final = max(-1.0, min(1.0, score_final))

        # Confiança do sinal baseada em alinhamento de fatores
        fatores_alinhados = (
            (score_livro > 0 and score_momentum > 0 and bias_noticias_ia >= 0) or
            (score_livro < 0 and score_momentum < 0 and bias_noticias_ia <= 0)
        )
        confianca_base = abs(score_final)
        confianca = min(0.98, confianca_base * 1.2 if fatores_alinhados else confianca_base * 0.85)

        # Determinação da direção
        limiar_gatilho = 0.18
        if score_final >= limiar_gatilho and confianca >= 0.35:
            sugestao = 'COMPRA'
        elif score_final <= -limiar_gatilho and confianca >= 0.35:
            sugestao = 'VENDA'
        else:
            sugestao = 'NEUTRO'

        return MicroFeaturesMercado(
            par=par,
            preco_atual=round(preco_atual, 4),
            retorno_15s=round(retorno_15s, 6),
            retorno_1m=round(retorno_1m, 6),
            desequilibrio_livro=round(desequilibrio_livro, 4),
            pressao_compradora=round(pressao_compradora, 4),
            spread_pct=round(spread_pct, 6),
            volatilidade_atr_pct=round(volatilidade_atr_pct, 6),
            score_direcional_local=round(score_final, 4),
            confianca_sinal=round(confianca, 4),
            sugestao_direcao=sugestao
        )

EXTRATOR_FEATURES = ExtratorMicroFeatures()
