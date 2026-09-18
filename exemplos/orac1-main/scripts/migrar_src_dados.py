"""
Script seguro para migrar artefatos em `src/dados/` para a pasta oficial `dados/`.
Uso: python scripts/migrar_src_dados.py
"""
from __future__ import annotations

import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC_DADOS = ROOT / "src" / "dados"
DEST_DADOS = ROOT / "dados"


def migrar() -> None:
    if not SRC_DADOS.exists():
        print("src/dados não existe — nada a migrar.")
        return

    DEST_DADOS.mkdir(parents=True, exist_ok=True)

    moved = 0
    for item in SRC_DADOS.iterdir():
        target = DEST_DADOS / item.name
        if target.exists():
            backup = DEST_DADOS / f"legacy_{item.name}"
            print(f"Arquivo {item.name} já existe em dados/, movendo para {backup.name}")
            target = backup
        try:
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
            moved += 1
        except Exception as exc:
            print(f"falha_ao_migrar {item}: {exc}")

    print(f"migração concluída — itens copiados: {moved}")


if __name__ == "__main__":
    migrar()
