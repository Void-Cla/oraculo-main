from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.persistencia.conexao import inicializar_db


if __name__ == "__main__":
    caminho = inicializar_db()
    print(f"Banco inicializado em: {caminho}")
