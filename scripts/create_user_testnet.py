from __future__ import annotations

import asyncio
import os

from src.persistencia.repositorio_usuarios import RepositorioUsuarios


async def main() -> None:
    api_key_secret_id = (os.getenv("TESTNET_API_KEY_SECRET_ID") or "TESTNET_API_KEY").strip().upper()
    api_secret_secret_id = (os.getenv("TESTNET_API_SECRET_SECRET_ID") or "TESTNET_API_SECRET").strip().upper()
    if not os.getenv(api_key_secret_id) or not os.getenv(api_secret_secret_id):
        print("missing_secret_refs")
        return

    uid = await RepositorioUsuarios.criar(
        nome="teste_e2e",
        api_key_secret_id=api_key_secret_id,
        api_secret_secret_id=api_secret_secret_id,
        testnet=True,
        ativo=True,
    )
    print(uid)


if __name__ == "__main__":
    asyncio.run(main())
