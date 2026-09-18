"""construir_contexto_analise_direcional_lote — payload único cobrindo N símbolos
(economia de RPM/TPM, ver src/intelligence/market_analyst.py). Repositórios vazios (DB de
teste isolado) — o alvo aqui é a FORMA do payload, não o conteúdo de mercado."""
import json
import os

import pytest


def _setup_db(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "context_builder_lote.sqlite")
    from src.persistencia.conexao import inicializar_db

    inicializar_db()


@pytest.mark.asyncio
async def test_contexto_lote_tem_um_item_por_simbolo_na_mesma_ordem(tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.context_builder import construir_contexto_analise_direcional_lote

    bruto = await construir_contexto_analise_direcional_lote(["BTCUSDT", "ETHUSDT", "BNBUSDT"], saldo=100.0)
    payload = json.loads(bruto)

    assert [item["simbolo"] for item in payload["simbolos"]] == ["BTCUSDT", "ETHUSDT", "BNBUSDT"]


@pytest.mark.asyncio
async def test_contexto_lote_nao_vaza_sinal_mecanico(tmp_path):
    """Mesma regra do caminho por-símbolo: contexto direcional nunca carrega decisão mecânica."""
    _setup_db(tmp_path)
    from src.intelligence.context_builder import construir_contexto_analise_direcional_lote

    bruto = await construir_contexto_analise_direcional_lote(["BTCUSDT"], saldo=100.0)
    assert "sinal_mecanico" not in bruto


@pytest.mark.asyncio
async def test_contexto_lote_respeita_noticias_por_simbolo(tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.context_builder import construir_contexto_analise_direcional_lote

    noticias = {"BTCUSDT": [{"titulo": "alta forte", "sentimento": 0.8}]}
    bruto = await construir_contexto_analise_direcional_lote(["BTCUSDT", "ETHUSDT"], saldo=100.0, noticias_por_simbolo=noticias)
    payload = json.loads(bruto)

    btc = next(item for item in payload["simbolos"] if item["simbolo"] == "BTCUSDT")
    eth = next(item for item in payload["simbolos"] if item["simbolo"] == "ETHUSDT")
    assert btc["noticias_recentes"] == [{"titulo": "alta forte", "sentimento": 0.8}]
    assert eth["noticias_recentes"] == []


@pytest.mark.asyncio
async def test_contexto_lote_vazio_retorna_lista_vazia(tmp_path):
    _setup_db(tmp_path)
    from src.intelligence.context_builder import construir_contexto_analise_direcional_lote

    bruto = await construir_contexto_analise_direcional_lote([], saldo=100.0)
    assert json.loads(bruto) == {"simbolos": []}


# ── Compactação do contexto (DA-32 — menos tokens, decisão mais rápida) ─────────
def test_velas_compactas_formato_array_e_janela():
    from src.intelligence.context_builder import _VELAS_IA, _velas_compactas

    velas = [
        {"ts": i, "open": 100.123456789, "high": 101.0, "low": 99.5, "close": 100.9876543, "volume": 12.3456789}
        for i in range(1, 21)  # 20 velas no banco
    ]
    compactas = _velas_compactas(velas)
    assert len(compactas) == _VELAS_IA                    # janela reduzida (12, não 20)
    assert compactas[-1] == [20, 100.123457, 101.0, 99.5, 100.987654, 12.346]  # array + arredondado
    assert compactas[0][0] == 20 - _VELAS_IA + 1          # pegou as ÚLTIMAS velas, não as primeiras


def test_historico_compacto_limita_e_filtra_campos():
    from src.intelligence.context_builder import _historico_compacto

    trades = [{"lado": "BUY", "lucro_usdt": 0.123456789, "regime": "RANGE", "estrategia": "momentum", "duracao_ms": 60000}] * 9
    compacto = _historico_compacto(trades)
    assert len(compacto) == 5                              # 5, não 9
    assert set(compacto[0].keys()) == {"resultado", "lado", "lucro_usdt", "regime"}  # sem estrategia/duração
    assert compacto[0]["lucro_usdt"] == 0.1235             # arredondado


def test_noticias_compactas_trunca_titulo_e_limita():
    from src.intelligence.context_builder import _noticias_compactas

    noticias = [{"titulo": "x" * 300, "sentimento": 0.123456}] * 8
    compactas = _noticias_compactas(noticias)
    assert len(compactas) == 5
    assert len(compactas[0]["titulo"]) == 90               # manchete truncada
    assert compactas[0]["sentimento"] == 0.123
