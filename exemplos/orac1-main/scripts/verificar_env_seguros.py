"""
Verificador simples para variáveis sensíveis em `.env`.
Imprime chaves que parecem conter segredos (ex.: API keys) para ajudar a limpar antes de commitar.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

SUSPEITAS = [
    re.compile(r"(api|secret|key|token)", re.IGNORECASE),
]


def verificar() -> None:
    if not ENV_PATH.exists():
        print(".env não encontrado — nada a verificar.")
        return

    with ENV_PATH.open("r", encoding="utf-8") as fh:
        for i, linha in enumerate(fh, start=1):
            texto = linha.strip()
            if not texto or texto.startswith("#"):
                continue
            if "=" not in texto:
                continue
            chave, valor = texto.split("=", 1)
            chave = chave.strip()
            valor = valor.strip()
            for padrao in SUSPEITAS:
                if padrao.search(chave) and len(valor) > 6:
                    print(f"Possivel segredo em .env: linha {i}: {chave}")


if __name__ == "__main__":
    verificar()
