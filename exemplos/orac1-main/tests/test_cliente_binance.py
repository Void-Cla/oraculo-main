import time

import pytest

from src.binance_api.cliente import ClienteBinance


class _ClienteAsyncFalso:
    def __init__(self):
        self.timestamp_offset = 0

    async def get_server_time(self):
        return {"serverTime": 110000}


@pytest.mark.asyncio
async def test_cliente_binance_sincroniza_timestamp_e_repete_operacao(monkeypatch):
    cliente = ClienteBinance()
    cliente._max_tentativas = 2
    cliente._timeout = 1
    cliente_falso = _ClienteAsyncFalso()
    chamadas = {"total": 0}

    async def _obter_cliente():
        return cliente_falso

    async def _callback():
        chamadas["total"] += 1
        if chamadas["total"] == 1:
            raise RuntimeError("APIError(code=-1021): Timestamp for this request was 1000ms ahead of the server's time.")
        return "ok"

    monkeypatch.setattr(cliente, "_obter_cliente", _obter_cliente)
    monkeypatch.setattr(time, "time", lambda: 100.0)

    resultado = await cliente._executar_com_retry("teste", _callback)

    assert resultado == "ok"
    assert chamadas["total"] == 2
    assert cliente_falso.timestamp_offset == 10000
