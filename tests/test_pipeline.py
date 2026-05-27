import pytest
import asyncio
from src.servicos.fluxo_usuario_sinais import executar_fluxo_usuario_sinal
from src.persistencia.repositorio_ordens import RepositorioOrdens
from src.sinais.fila_sinais import fila_sinais_global

@pytest.mark.asyncio
async def test_pipeline():
    # Configurações iniciais
    usuario_id = 1
    payload = {
        "simbolo": "BTCUSDT",
        "publicar_fila": True,
        "saldo": {"BTC": 0.1, "USDT": 1000},
        "noticias": [],
    }

    # Executa o fluxo
    resultado = await executar_fluxo_usuario_sinal(usuario_id, payload)

    # Verifica se a ordem foi criada
    ordem_id = resultado.get("ordem_id")
    assert ordem_id is not None, "Ordem não foi criada"

    ordem = await RepositorioOrdens.obter(ordem_id)
    assert ordem is not None, "Ordem não encontrada no banco de dados"

    # Verifica se o sinal foi publicado na fila
    fila_snapshot = await fila_sinais_global.snapshot()
    assert any(item["ordem_id"] == ordem_id for item in fila_snapshot), "Sinal não foi publicado na fila"

    print("Teste do pipeline completo passou com sucesso!")