from __future__ import annotations

import asyncio
import os
import signal
import time
from typing import Any

from src.persistencia.conexao import inicializar_db
from src.persistencia.repositorio_usuarios import RepositorioUsuarios
from src.persistencia.repositorio_auditoria import RepositorioAuditoria
from src.servicos.sessoes import criar_sessao_binance
from src.servicos.testnet_auto_trader import TestnetAutoTrader


DEFAULT_DURATION = int(os.getenv("E2E_DURATION_SECONDS", "600"))


async def _criar_usuario_testnet_se_nao_existir() -> None:
    api_key = os.getenv("TESTNET_API_KEY")
    api_secret = os.getenv("TESTNET_API_SECRET")
    if not api_key or not api_secret:
        print("TESTNET_API_KEY or TESTNET_API_SECRET not set; aborting user creation")
        return
    # Use RepositorioUsuarios.criar to register a test user (idempotent check by name)
    usuarios = []
    if hasattr(RepositorioUsuarios, "listar"):
        usuarios = await RepositorioUsuarios.listar()
    existe = any(str(u.get("nome") or "").startswith("teste_e2e") for u in usuarios)
    if existe:
        print("usuario teste_e2e ja existe; skipping create")
        return
    uid = await RepositorioUsuarios.criar(
        nome="teste_e2e",
        api_key_secret_id="TESTNET_API_KEY",
        api_secret_secret_id="TESTNET_API_SECRET",
        testnet=True,
        ativo=True,
    )
    print(f"usuario criado: {uid}")


async def main(duration: int = DEFAULT_DURATION) -> None:
    inicializar_db()
    await _criar_usuario_testnet_se_nao_existir()

    api_key = os.getenv("TESTNET_API_KEY")
    api_secret = os.getenv("TESTNET_API_SECRET")
    if not api_key or not api_secret:
        print("E2E Runner requires TESTNET_API_KEY and TESTNET_API_SECRET environment variables.")
        return

    sessao = await criar_sessao_binance(api_key, api_secret, testnet=True)
    token = sessao.get("token")
    if not token:
        print("failed_to_create_session")
        return

    trader = TestnetAutoTrader()
    ajustes = {"simbolo": os.getenv("E2E_SYMBOL", "BTCUSDT"), "intervalo_segundos": int(os.getenv("E2E_INTERVAL_SECONDS", "30")), "notional_usdt": float(os.getenv("E2E_NOTIONAL_USDT", "5.0"))}
    print("iniciando testnet auto trader...")
    await trader.iniciar(token, {**sessao, "api_key": api_key, "api_secret": api_secret}, ajustes)

    stop = asyncio.Event()

    def _sig(_n, _f):
        stop.set()

    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, lambda: _sig(None, None))
        loop.add_signal_handler(signal.SIGTERM, lambda: _sig(None, None))
    except Exception:
        pass

    inicio = time.time()
    try:
        while not stop.is_set() and (time.time() - inicio) < duration:
            status = trader.status(token)
            ts = int(time.time() * 1000)
            try:
                await RepositorioAuditoria.registrar(simbolo=ajustes["simbolo"], tipo="e2e_status", payload={"ts": ts, "status": status})
            except Exception:
                # auditoria pode nao estar implementada em alguns ambientes; ignore
                pass
            print(f"[E2E] {time.strftime('%H:%M:%S')} status ativo={status.get('ativo')} ciclo_ativo={status.get('ciclo_ativo')} ultimo_motivo={status.get('ultimo_motivo')}")
            await asyncio.sleep(max(1, int(ajustes.get("intervalo_segundos", 30) or 30)))
    finally:
        print("parando testnet auto trader...")
        await trader.parar(token)
        await trader.encerrar_todos()
        print("testnet run complete")


if __name__ == "__main__":
    dur = int(os.getenv("E2E_DURATION_SECONDS", "600"))
    asyncio.run(main(dur))
