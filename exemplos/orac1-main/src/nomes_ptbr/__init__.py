"""
Alias PT-BR para símbolos públicos do projeto.

Este módulo não altera implementações; apenas reexporta nomes
com documentação em português para facilitar leitura e adoção.
Use `from src.nomes_ptbr import GerenciadorModelo` por clareza PT-BR.
"""

from src.binance_api.cliente import ClienteBinance
from src.modelagem.gerenciador_modelo import GerenciadorModelo
from src.modelagem.preditor import preditor_end_to_end
from src.persistencia.repositorio_ohlcv import RepositorioOhlcv
from src.persistencia.repositorio_livro_topo import RepositorioLivroTopo
from src.persistencia.repositorio_features import RepositorioFeatures
from src.probabilidade.probabilistic_engine import ProbabilisticTradeEngine
from src.probabilidade.ev_calculator import EVCalculator
from src.probabilidade.probability_calibrator import ProbabilityCalibrator
from src.probabilidade.trade_selector import TradeSelector
from src.sinais.signal_engine import gerar_sinal_orquestrado
from src.executor.gerenciador_ordens import GerenciadorOrdens

__all__ = [
    "ClienteBinance",
    "GerenciadorModelo",
    "preditore2e",
    "RepositorioOhlcv",
    "RepositorioLivroTopo",
    "RepositorioFeatures",
    "ProbabilisticTradeEngine",
    "EVCalculator",
    "ProbabilityCalibrator",
    "TradeSelector",
    "gerar_sinal_orquestrado",
    "GerenciadorOrdens",
]

# Compatibilidade: pequenos aliases/renames em PT-BR
preditore2e = preditor_end_to_end
