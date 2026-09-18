from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


RAIZ = Path(__file__).resolve().parents[2]
SEMGREP = RAIZ / ".ferramentas/mcp/python/.venv/Scripts/semgrep.exe"
TIMEOUT_SEGUNDOS = 180
CONFIGS_PERMITIDAS = {"auto", "p/python", "p/secrets", "p/owasp-top-ten"}

mcp = FastMCP("oraculo-semgrep-local")


def resolver_alvo(alvo: str) -> str:
    caminho = (RAIZ / alvo).resolve()
    if not str(caminho).startswith(str(RAIZ)):
        raise ValueError(f"alvo fora do repositorio: {alvo}")
    return str(caminho)


@mcp.tool()
def semgrep_version() -> str:
    """Retorna a versao do Semgrep local."""
    saida = subprocess.run(
        [str(SEMGREP), "--version"],
        cwd=RAIZ,
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    return saida.stdout.strip()


@mcp.tool()
def semgrep_scan(
    alvos: list[str] | None = None,
    config: str = "p/python",
) -> dict[str, Any]:
    """Executa scan Semgrep JSON em alvos relativos ao repositorio."""
    if config not in CONFIGS_PERMITIDAS:
        raise ValueError(f"config Semgrep nao permitido: {config}")

    caminhos = [resolver_alvo(alvo) for alvo in (alvos or ["src", "tests"])]
    comando = [
        str(SEMGREP),
        "scan",
        "--json",
        "--quiet",
        "--metrics",
        "off",
        "--config",
        config,
        *caminhos,
    ]
    execucao = subprocess.run(
        comando,
        cwd=RAIZ,
        text=True,
        capture_output=True,
        timeout=TIMEOUT_SEGUNDOS,
        check=False,
    )
    bruto = execucao.stdout or "{}"
    dados = json.loads(bruto)
    achados = dados.get("results", [])
    return {
        "returncode": execucao.returncode,
        "config": config,
        "total": len(achados),
        "achados": achados[:50],
        "stderr": execucao.stderr[-4000:],
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
