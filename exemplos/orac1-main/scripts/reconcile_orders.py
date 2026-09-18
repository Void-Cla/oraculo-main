from __future__ import annotations

import asyncio
import os
from typing import Any

from src.executor.gerenciador_ordens import GerenciadorOrdens


async def listar_e_cancelar_abertas(simbolo: str | None = None) -> None:
    g = GerenciadorOrdens()
    cliente = await g._obter_cliente()
    try:
        if simbolo:
            ords = await cliente.get_open_orders(symbol=simbolo.upper())
        else:
            ords = await cliente.get_open_orders()
    except Exception as exc:
        print(f"falha_ao_listar_ordens: {exc}")
        return

    if not ords:
        print("sem_ordens_abertas")
        return

    for o in ords:
        try:
            sid = o.get("symbol")
            oid = o.get("orderId")
            print(f"cancelando {sid} #{oid}")
            await g.cancelar_ordem(sid, oid)
        except Exception as exc:
            print(f"falha_cancelar_ordem {o.get('orderId')}: {exc}")


if __name__ == "__main__":
    sym = os.getenv("RECONCILE_SYMBOL")
    asyncio.run(listar_e_cancelar_abertas(sym))
