import pytest

from src.executor.gerenciador_ordens import GerenciadorOrdens, NotionalTooSmall


@pytest.mark.asyncio
async def test_obter_filtros_simbolo_considera_filtro_notional(monkeypatch):
    ger = GerenciadorOrdens(api_key="x", api_secret="y", testnet=True)

    async def _info(_simbolo):
        return {
            "filters": [
                {"filterType": "LOT_SIZE", "stepSize": "0.00100000", "minQty": "0.01000000"},
                {"filterType": "MIN_NOTIONAL", "minNotional": "5.00000000"},
                {"filterType": "NOTIONAL", "minNotional": "10.00000000"},
            ]
        }

    monkeypatch.setattr(ger, "obter_info_simbolo", _info)

    filtros = await ger.obter_filtros_simbolo("ETHUSDT")

    assert filtros["step_size"] == pytest.approx(0.001)
    assert filtros["min_qty"] == pytest.approx(0.01)
    assert filtros["min_notional"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_criar_ordem_market_converte_erro_notional_em_excecao_controlada(monkeypatch):
    ger = GerenciadorOrdens(api_key="x", api_secret="y", testnet=True)

    async def _filtros(_simbolo):
        return {"step_size": 0.001, "min_qty": 0.001, "min_notional": 10.0}

    class _ClienteFalso:
        async def get_symbol_ticker(self, symbol):
            return {"symbol": symbol, "price": "100.0"}

        async def create_order(self, **payload):
            raise RuntimeError("APIError(code=-1013): Filter failure: NOTIONAL")

        async def close_connection(self):
            return None

    monkeypatch.setattr(ger, "obter_filtros_simbolo", _filtros)
    ger._cliente = _ClienteFalso()

    with pytest.raises(NotionalTooSmall):
        await ger.criar_ordem_market("ETHUSDT", "SELL", quantidade=0.1)
