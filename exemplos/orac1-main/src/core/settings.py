from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]


def env_str(nome: str, padrao: str = "") -> str:
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    valor = str(valor).strip()
    return valor if valor else padrao


def env_bool(nome: str, padrao: bool = False) -> bool:
    bruto = os.getenv(nome)
    if bruto is None:
        return padrao
    return str(bruto).strip().lower() in {"1", "true", "yes", "on"}


def env_int(nome: str, padrao: int, *, minimo: int | None = None) -> int:
    try:
        valor = int(str(os.getenv(nome, padrao)).strip())
    except (TypeError, ValueError):
        valor = padrao
    if minimo is not None:
        valor = max(minimo, valor)
    return valor


def env_float(nome: str, padrao: float, *, minimo: float | None = None) -> float:
    try:
        valor = float(str(os.getenv(nome, padrao)).strip())
    except (TypeError, ValueError):
        valor = padrao
    if minimo is not None:
        valor = max(minimo, valor)
    return valor


def env_csv(nome: str, padrao: str = "") -> list[str]:
    bruto = env_str(nome, padrao)
    return [item.strip() for item in bruto.split(",") if item.strip()]


def resolve_runtime_path(nome_env: str, padrao_relativo: str) -> Path:
    bruto = env_str(nome_env, padrao_relativo)
    caminho = Path(bruto).expanduser()
    if not caminho.is_absolute():
        caminho = ROOT_DIR / caminho
    return caminho.resolve()


def db_path() -> Path:
    return resolve_runtime_path("DB_PATH", "./dados/oraculo.sqlite")


def model_dir() -> Path:
    return resolve_runtime_path("MODEL_DIR", "./dados/modelos")
