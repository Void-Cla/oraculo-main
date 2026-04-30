import asyncio
import os

from fastapi.testclient import TestClient

from src.main import app
from src.persistencia.conexao import inicializar_db
from src.servicos.noticias import obter_noticias_para_peso


async def _coletar_falso(simbolo):
    itens = []
    for idx in range(20):
        itens.append(
            {
                "titulo": f"Noticia {idx}",
                "descricao": "Impacto em bitcoin",
                "link": f"https://fonte{idx}.example/noticia",
                "fonte": f"Fonte {idx}",
                "dominio": f"fonte{idx}.example",
                "publicado_em": "Sat, 15 Mar 2026 00:00:00 GMT",
            }
        )
    return itens, {
        "fontes_monitoradas": 30,
        "fontes_minimas_exigidas": 10,
        "fontes_com_retorno": 20,
        "fontes_utilizadas": [f"Fonte {idx}" for idx in range(20)],
    }


async def _classificar_falso(itens):
    return {
        "sentimento_geral": 0.4,
        "confianca": 0.7,
        "resumo": "Fluxo de noticias levemente positivo para BTC.",
        "itens": [
            {"id": idx, "sentimento": 0.25, "impacto": "medio", "tags": ["cripto"], "resumo": "positivo"}
            for idx, _ in enumerate(itens)
        ],
    }


def test_noticias_respeita_limite_diario(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "noticias.sqlite")
    inicializar_db()
    chamadas = {"coleta": 0}

    async def _coletar_contando(simbolo):
        chamadas["coleta"] += 1
        return await _coletar_falso(simbolo)

    monkeypatch.setattr("src.servicos.noticias._coletar_noticias_fontes", _coletar_contando)
    monkeypatch.setattr("src.servicos.noticias._classificar_com_openai", _classificar_falso)

    for _ in range(6):
        resultado = asyncio.run(obter_noticias_para_peso("BTCUSDT", forcar_atualizacao=True))

    assert chamadas["coleta"] == 5
    assert resultado["meta"]["buscas_hoje"] == 5
    assert resultado["meta"]["max_buscas_dia"] == 5
    assert resultado["meta"]["limite_busca_atingido"] is True
    assert len(resultado["itens"]) == 20


def test_endpoint_noticias_retorna_cache(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "noticias_api.sqlite")
    inicializar_db()
    monkeypatch.setattr("src.servicos.noticias._coletar_noticias_fontes", _coletar_falso)
    monkeypatch.setattr("src.servicos.noticias._classificar_com_openai", _classificar_falso)

    with TestClient(app) as client:
        resposta = client.get("/v1/noticias?simbolo=BTCUSDT&atualizar=true")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["simbolo"] == "BTCUSDT"
        assert corpo["meta"]["fontes_monitoradas"] >= 10
        assert corpo["meta"]["status_classificacao"] == "openai_responses_api"
        assert len(corpo["meta"]["fontes_detalhadas"]) == 10


def test_endpoint_noticias_multi_retorna_pares(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "noticias_multi.sqlite")
    inicializar_db()
    monkeypatch.setattr("src.servicos.noticias._coletar_noticias_fontes", _coletar_falso)
    monkeypatch.setattr("src.servicos.noticias._classificar_com_openai", _classificar_falso)

    with TestClient(app) as client:
        resposta = client.get("/v1/noticias/multi?simbolos=BTCUSDT,ETHUSDT,BNBUSDT")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["simbolos"] == ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        assert len(corpo["itens"]) == 3
        assert all(len(item["meta"]["fontes_detalhadas"]) == 10 for item in corpo["itens"])


def test_endpoint_frame_noticias_retorna_html(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "noticias_frame.sqlite")
    inicializar_db()
    monkeypatch.setattr("src.servicos.noticias._coletar_noticias_fontes", _coletar_falso)
    monkeypatch.setattr("src.servicos.noticias._classificar_com_openai", _classificar_falso)

    with TestClient(app) as client:
        resposta = client.get("/v1/noticias/frame?simbolo=BTCUSDT&fonte=Fonte%200")
        assert resposta.status_code == 200
        assert "text/html" in resposta.headers["content-type"]
        assert "Fonte 0" in resposta.text
        assert "BTCUSDT" in resposta.text


def test_endpoint_noticias_multi_degrada_sem_quebrar_lote(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "noticias_multi_falha.sqlite")
    inicializar_db()

    async def _obter_com_falha(simbolo, forcar_atualizacao=False):
        if simbolo == "ETHUSDT":
            raise RuntimeError("fonte_instavel")
        return await obter_noticias_para_peso(simbolo=simbolo, forcar_atualizacao=forcar_atualizacao)

    monkeypatch.setattr("src.servicos.noticias._coletar_noticias_fontes", _coletar_falso)
    monkeypatch.setattr("src.servicos.noticias._classificar_com_openai", _classificar_falso)
    monkeypatch.setattr("src.main.obter_noticias_para_peso", _obter_com_falha)

    with TestClient(app) as client:
        resposta = client.get("/v1/noticias/multi?simbolos=BTCUSDT,ETHUSDT")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert len(corpo["itens"]) == 2
        item_falha = next(item for item in corpo["itens"] if item["simbolo"] == "ETHUSDT")
        assert item_falha["meta"]["status_classificacao"] == "falha_coleta"
        assert item_falha["itens"] == []


def test_endpoint_frame_noticias_degrada_para_html_seguro(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "noticias_frame_falha.sqlite")
    inicializar_db()

    async def _obter_falhando(simbolo, forcar_atualizacao=False):
        raise RuntimeError("feed_indisponivel")

    monkeypatch.setattr("src.servicos.noticias.obter_noticias_para_peso", _obter_falhando)

    with TestClient(app) as client:
        resposta = client.get("/v1/noticias/frame?simbolo=BTCUSDT&fonte=Reuters")
        assert resposta.status_code == 200
        assert "Falha temporaria" in resposta.text
        assert "feed_indisponivel" in resposta.text
