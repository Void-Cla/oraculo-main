"""Repositório base e utilitários comuns em PT-BR.
Fornece abstrações leves para os repositórios específicos.
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseRepositorio(ABC):
    """Classe base para repositórios.

    Métodos concretos podem usar `self.conn` ou `self.pool` conforme injeção.
    """

    def __init__(self, conn: Any = None, pool: Any = None):
        self.conn = conn
        self.pool = pool

    @abstractmethod
    async def criar_tabelas(self) -> None:
        """Cria tabelas necessárias para o repositório."""
        raise NotImplementedError()
