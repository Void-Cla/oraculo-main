import os

import pytest
from fastapi.testclient import TestClient


def _setup_db(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "obs.sqlite")
    from src.persistencia.conexao import inicializar_db
    inicializar_db()


# Base alinhada ao minuto (divisível por 60_000); ts_previsao fica no meio do minuto.
_BASE_MIN = 1_782_000_000_000


async def _seed_ohlcv(con, ts, simbolo, close):
    await con.execute(
        "INSERT INTO ohlcv_1m (ts, simbolo, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
        (ts, simbolo, close, close, close, close, 1.0),
    )


@pytest.mark.asyncio
async def test_resumo_qualidade_recente_calcula_ic_de_retorno(tmp_path):
    _setup_db(tmp_path)
    from src.persistencia.conexao import get_conexao
    from src.observabilidade.saude_modelo import resumo_qualidade_recente

    ref = 100.0
    async with get_conexao() as con:
        for i in range(10):
            # retorno PREVISTO e REAL monotônicos com i → IC de retorno máximo (precisa do ref/close)
            minuto = _BASE_MIN + i * 60_000          # candle alinhado ao minuto
            ts_prev = minuto + 1234                   # previsão no meio do minuto
            r_prev = 0.001 * (i + 1)
            r_real = 0.0009 * (i + 1)
            await _seed_ohlcv(con, minuto, "BTCUSDT", ref)
            await con.execute(
                "INSERT INTO outcomes (ts_previsao, ts_target, simbolo, y_true, y_hat, err_rel) "
                "VALUES (?,?,?,?,?,?)",
                (ts_prev, ts_prev + 60_000, "BTCUSDT", ref * (1 + r_real), ref * (1 + r_prev), 0.01),
            )
        await con.commit()

    r = await resumo_qualidade_recente("BTCUSDT", 50)
    assert r["amostras"] == 10
    assert r["ic_recente"] > 0.9
    assert r["ic_utilizavel"] is True


@pytest.mark.asyncio
async def test_ic_usa_retorno_nao_preco_evita_falso_sinal(tmp_path):
    # Regressão do bug: preço previsto vs real seria IC~1 (preço persistente), mas se a
    # PREDIÇÃO é sempre "sem mudança" (retorno previsto=0), o IC de RETORNO deve ser ~0.
    _setup_db(tmp_path)
    from src.persistencia.conexao import get_conexao
    from src.observabilidade.saude_modelo import resumo_qualidade_recente

    async with get_conexao() as con:
        for i in range(20):
            minuto = _BASE_MIN + i * 60_000
            ts_prev = minuto + 1234
            close = 100.0 + i  # preço em tendência (alta correlação de NÍVEL)
            await _seed_ohlcv(con, minuto, "BTCUSDT", close)
            await con.execute(
                "INSERT INTO outcomes (ts_previsao, ts_target, simbolo, y_true, y_hat, err_rel) "
                "VALUES (?,?,?,?,?,?)",
                (ts_prev, ts_prev + 60_000, "BTCUSDT", close * 1.0005, close, 0.0005),  # y_hat=ref → r_prev=0
            )
        await con.commit()

    r = await resumo_qualidade_recente("BTCUSDT", 50)
    assert r["amostras"] == 20
    assert r["ic_recente"] == 0.0          # sem sinal de retorno (predição flat)
    assert r["ic_utilizavel"] is False


@pytest.mark.asyncio
async def test_resumo_qualidade_sem_dados_e_seguro(tmp_path):
    _setup_db(tmp_path)
    from src.observabilidade.saude_modelo import resumo_qualidade_recente
    r = await resumo_qualidade_recente("ETHUSDT", 50)
    assert r["amostras"] == 0
    assert r["ic_recente"] == 0.0
    assert r["ic_utilizavel"] is False


@pytest.mark.asyncio
async def test_saude_modelo_expoe_status_e_diagnostico(tmp_path):
    _setup_db(tmp_path)
    from src.observabilidade.saude_modelo import saude_modelo
    r = await saude_modelo("BTCUSDT")
    assert r["simbolo"] == "BTCUSDT"
    for chave in ("coef_norm", "min_amostras_online", "online_em_uso", "qualidade_recente", "diagnostico"):
        assert chave in r
    assert {"online_em_uso", "online_divergente_suspeito", "tem_sinal_recente"} <= set(r["diagnostico"])


@pytest.mark.asyncio
async def test_saude_llm_modo_fallback_sem_chave(tmp_path, monkeypatch):
    _setup_db(tmp_path)
    monkeypatch.setattr("src.servicos.ai_advisor._GPT_KEY", "")
    from src.servicos.ai_advisor import saude_llm
    r = await saude_llm("BTCUSDT")
    assert r["gpt_chave_presente"] is False
    assert r["modo_fallback_ativo"] is True
    assert r["modelo_configurado"] == "heuristica_local"
    assert r["fonte_ultimo_insight"] == "heuristica_local"


def test_endpoint_modelos_treino(tmp_path):
    _setup_db(tmp_path)
    from src.main import app
    with TestClient(app) as client:
        resp = client.get("/v1/modelos/treino", params={"simbolo": "BTCUSDT"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["simbolo"] == "BTCUSDT"
        assert "qualidade_recente" in body
        assert "diagnostico" in body


def test_endpoint_ai_saude(tmp_path):
    _setup_db(tmp_path)
    from src.main import app
    with TestClient(app) as client:
        resp = client.get("/v1/ai/saude")
        assert resp.status_code == 200
        assert "modo_fallback_ativo" in resp.json()


def test_endpoint_diagnostico_consolida_tudo(tmp_path):
    _setup_db(tmp_path)
    from src.main import app
    with TestClient(app) as client:
        resp = client.get("/v1/diagnostico", params={"simbolo": "BTCUSDT"})
        assert resp.status_code == 200
        body = resp.json()
        assert "health" in body
        assert "modelo_treino" in body
        assert "llm" in body
        assert "edge" in body


def test_endpoint_edge_default_fechado(tmp_path):
    # Registro vazio (sem edge validado) ⇒ nenhum símbolo aprovado p/ conta real (fail-safe).
    _setup_db(tmp_path)
    from src.main import app
    with TestClient(app) as client:
        resp = client.get("/v1/edge")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ha_edge_para_real"] is False
        assert body["simbolos_aprovados_para_real"] == []
        assert "validade_dias" in body
