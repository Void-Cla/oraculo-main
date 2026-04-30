"""Treinador online (wrapper) que ajusta o modelo incrementalmente.
"""
from typing import Dict, Any
from .gerenciador_modelo import GerenciadorModelo


def ajustar_online(simbolo: str, features: Dict[str, Any], y: float):
    gm = GerenciadorModelo(simbolo=simbolo)
    gm.partial_fit(features, y)
    gm.salvar()
