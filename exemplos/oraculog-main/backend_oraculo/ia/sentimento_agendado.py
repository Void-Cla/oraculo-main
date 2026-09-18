"""
Gerenciador de Inteligência Artificial em Intervalos de 2 Horas (PT-BR)
Define o peso diário/periódico das notícias a cada 2 horas e viés macro,
mantendo o motor local ultra-rápido durante as janelas de trading curtas.
"""
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

@dataclass
class EstadoSessaoIa2h:
    timestamp_ultima_analise: float
    timestamp_proxima_analise: float
    peso_noticias_ia: float          # Ex: 0.15 a 0.25
    bias_macro_direcional: float      # -1.0 (bearish) a +1.0 (bullish)
    regime_mercado: str               # 'TENDENCIA_ALTA', 'TENDENCIA_BAIXA', 'LATERAL_CONSOLIDACAO'
    intensidade_impacto_noticias: str # 'BAIXO', 'MEDIO', 'ALTO'
    resumo_executivo_ptbr: str
    fatores_chave: list
    modelo_utilizado: str = "Gemini 3.8 Flash"

class GerenciadorIaSentimento2h:
    def __init__(self, intervalo_segundos: int = 7200): # 2 horas = 7200s
        self.intervalo_segundos = intervalo_segundos
        agora = time.time()
        # Estado inicial calibrado
        self.estado = EstadoSessaoIa2h(
            timestamp_ultima_analise=agora,
            timestamp_proxima_analise=agora + self.intervalo_segundos,
            peso_noticias_ia=0.18,
            bias_macro_direcional=0.15,  # Leve viés positivo institucional
            regime_mercado="LATERAL_COM_PRESSAO_COMPRADORA",
            intensidade_impacto_noticias="MEDIO",
            resumo_executivo_ptbr=(
                "Fluxo institucional estável no par BTC/USDT. Liquidez saudável no livro de ofertas "
                "com baixa probabilidade de choques de cauda nas próximas 2 horas. "
                "Peso das notícias calibrado em 18% para priorizar micro-momentum local."
            ),
            fatores_chave=[
                "Estabilidade do spread e ausência de FUD imediato",
                "Entrada consistente de ordens a mercado no suporte de curto prazo",
                "Foco em capturar micro-ineficiências com validação de lucro líquido"
            ]
        )

    def precisa_atualizar(self) -> bool:
        """Verifica se já se passaram 2 horas desde a última atualização"""
        return time.time() >= self.estado.timestamp_proxima_analise

    def obter_tempo_restante_segundos(self) -> int:
        restante = int(self.estado.timestamp_proxima_analise - time.time())
        return max(0, restante)

    def atualizar_analise_ia(
        self,
        peso_noticias: float,
        bias_macro: float,
        regime: str,
        intensidade: str,
        resumo: str,
        fatores: list
    ) -> EstadoSessaoIa2h:
        """Registra a nova análise gerada pelo Gemini 3.8 Flash"""
        agora = time.time()
        self.estado = EstadoSessaoIa2h(
            timestamp_ultima_analise=agora,
            timestamp_proxima_analise=agora + self.intervalo_segundos,
            peso_noticias_ia=round(max(0.05, min(0.40, peso_noticias)), 3),
            bias_macro_direcional=round(max(-1.0, min(1.0, bias_macro)), 3),
            regime_mercado=regime,
            intensidade_impacto_noticias=intensidade,
            resumo_executivo_ptbr=resumo,
            fatores_chave=fatores,
            modelo_utilizado="Gemini 3.8 Flash"
        )
        return self.estado

    def gerar_prompt_analise_2h(self, dados_mercado_resumo: Dict[str, Any]) -> str:
        """Gera o prompt especializado em PT-BR para o Gemini 3.8 avaliar o ciclo de 2h"""
        return (
            f"Você é o Diretor Quantitativo e Estrategista Chefe do Oráculo Trading Bot (Binance Spot).\n"
            f"Avalie a janela macro e notícias para as próximas 2 HORAS com os seguintes dados de mercado:\n"
            f"{dados_mercado_resumo}\n\n"
            f"Responda estritamente em formato JSON estruturado com os seguintes campos:\n"
            f"{{\n"
            f'  "peso_noticias_ia": float entre 0.08 e 0.30,\n'
            f'  "bias_macro_direcional": float entre -1.0 (muito vendedor) e +1.0 (muito comprador),\n'
            f'  "regime_mercado": "TENDENCIA_ALTA" | "TENDENCIA_BAIXA" | "LATERAL_CONSOLIDACAO",\n'
            f'  "intensidade_impacto_noticias": "BAIXO" | "MEDIO" | "ALTO",\n'
            f'  "resumo_executivo_ptbr": "resumo claro de 2-3 frases em português sobre o contexto das próximas 2 horas",\n'
            f'  "fatores_chave": ["fator 1", "fator 2", "fator 3"]\n'
            f"}}"
        )

GERENCIADOR_IA = GerenciadorIaSentimento2h()
