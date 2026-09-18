from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


RAIZ = Path(__file__).resolve().parents[2]
CONFIG = RAIZ / ".mcp.json"
TIMEOUT_SEGUNDOS = 75


def carregar_config() -> dict[str, Any]:
    with CONFIG.open("r", encoding="utf-8") as arquivo:
        bruto = json.load(arquivo)
    return bruto["mcpServers"]


def montar_parametros(nome: str, cfg: dict[str, Any]) -> StdioServerParameters:
    ambiente = os.environ.copy()
    ambiente.update({str(k): str(v) for k, v in cfg.get("env", {}).items()})
    return StdioServerParameters(
        command=cfg["command"],
        args=[str(arg) for arg in cfg.get("args", [])],
        env=ambiente,
        cwd=RAIZ,
    )


async def validar_servidor(nome: str, cfg: dict[str, Any]) -> tuple[str, bool, str]:
    parametros = montar_parametros(nome, cfg)
    try:
        async with stdio_client(parametros) as (leitura, escrita):
            async with ClientSession(leitura, escrita) as sessao:
                await asyncio.wait_for(sessao.initialize(), timeout=TIMEOUT_SEGUNDOS)
                ferramentas = await asyncio.wait_for(
                    sessao.list_tools(), timeout=TIMEOUT_SEGUNDOS
                )
                nomes = [ferramenta.name for ferramenta in ferramentas.tools]
                return nome, True, ", ".join(nomes[:10]) or "sem ferramentas"
    except Exception as exc:
        return nome, False, f"{type(exc).__name__}: {exc}"


async def main() -> int:
    parser = argparse.ArgumentParser()
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--todos", action="store_true")
    grupo.add_argument("--servidor")
    args = parser.parse_args()

    servidores = carregar_config()
    alvo = servidores if args.todos else {args.servidor: servidores[args.servidor]}
    resultados = await asyncio.gather(
        *(validar_servidor(nome, cfg) for nome, cfg in alvo.items())
    )

    falhou = False
    for nome, ok, detalhe in resultados:
        estado = "OK" if ok else "FALHA"
        print(f"{estado} {nome}: {detalhe}")
        falhou = falhou or not ok
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
