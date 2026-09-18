"""
Configurações e Parâmetros Centrais do Oráculo Trading Bot (PT-BR)
"""
import os
from dataclasses import dataclass

@dataclass
class ConfiguracaoOraculo:
    # Regra Mandatória de Lucro Líquido Real:
    # Todo trade deve cobrir todas as taxas (entrada + saída + slippage) + pelo menos 0,01 USD (1 centavo de dólar)
    LUCRO_MINIMO_LIQUIDO_USD: float = 0.01
    
    # Taxas padrão Binance Spot (0.10% taker por ponta = 0.20% round-trip)
    # Com BNB fee deduction cai para 0.075% por ponta
    TAXA_ENTRADA_PADRAO: float = 0.0010  # 0.10%
    TAXA_SAIDA_PADRAO: float = 0.0010   # 0.10%
    SLIPPAGE_ESTIMADO: float = 0.0003    # 0.03% de tolerância
    
    # Intervalo de IA para atualização de sentimento e notícias (em segundos = 2 horas)
    INTERVALO_IA_SEGUNDOS: int = 7200  # 2 horas = 7200s
    
    # Janela rápida de trading local (ciclos rápidos em segundos)
    JANELA_RAPIDA_SEGUNDOS: int = 15  # 15 segundos para micro-scalping com edge
    
    # Capital base de operação (modo conservador para crescimento consistente)
    CAPITAL_INICIAL_USDT: float = 100.0
    NOTIONAL_MINIMO_POR_ORDEM: float = 10.0  # Mínimo aceito na Binance
    
    # Pares monitorados primários
    PARES_ATIVOS: tuple = (
        'BTCUSDT',
        'ETHUSDT',
        'BNBUSDT',
        'SOLUSDT',
        'ETHBTC',
        'BNBBTC'
    )
    
    # Banco de dados SQLite
    DB_PATH: str = os.getenv('DB_PATH', 'oraculo_producao.db')
    
    # Modos de operação: 'SIMULACAO', 'TESTNET', 'CONTA_REAL'
    # Trava do Guardião: CONTA_REAL requer validação formal de edge
    MODO_OPERACAO: str = 'SIMULACAO'

CONFIG = ConfiguracaoOraculo()
