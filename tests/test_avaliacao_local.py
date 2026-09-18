"""Provas isoladas da avaliação prospectiva; nenhum banco de operação é usado."""

import sqlite3
from dataclasses import replace

import pytest

from src.intelligence.avaliacao_local import AvaliadorLocal, PrevisaoLocal


@pytest.fixture
def avaliador():
    with sqlite3.connect(":memory:") as conexao:
        instancia = AvaliadorLocal(conexao)
        instancia.preparar()
        yield instancia
    conexao.close()


def previsao(**ajustes):
    return replace(PrevisaoLocal("id-1", "BTCUSDT", "sklearn-v1", 1000, 60,
                                100.0, "subir", 0.8, 0.1, 0.1, 0.001), **ajustes)


def resumo(avaliador):
    return avaliador.relatorio(modelo_versao="sklearn-v1", simbolo="BTCUSDT", horizonte_segundos=60)


def test_previsao_imutavel_e_resultado_idempotente(avaliador):
    assert avaliador.registrar(previsao(), agora=1000)
    assert not avaliador.registrar(previsao(), agora=1100)
    with pytest.raises(ValueError, match="conflitante"):
        avaliador.registrar(previsao(preco_referencia=101), agora=1000)
    assert avaliador.avaliar("id-1", timestamp=1060, preco=101, agora=1060)
    assert not avaliador.avaliar("id-1", timestamp=1060, preco=101, agora=1070)
    with pytest.raises(ValueError, match="conflitante"):
        avaliador.avaliar("id-1", timestamp=1060, preco=102, agora=1070)
    assert resumo(avaliador)["subir"]["brier"] == pytest.approx(0.06)


@pytest.mark.parametrize("agora", [999, 1060, 2000, float("nan")])
def test_rejeita_previsao_futura_ou_retroativa(avaliador, agora):
    with pytest.raises(ValueError):
        avaliador.registrar(previsao(), agora=agora)


@pytest.mark.parametrize("ajuste", [
    {"preco_referencia": 0}, {"preco_referencia": float("nan")},
    {"prob_subir": float("inf")}, {"prob_subir": -0.1}, {"prob_subir": 1.1},
    {"prob_subir": 0.6}, {"timestamp": float("nan")}, {"horizonte_segundos": 0},
    {"horizonte_segundos": True}, {"direcao": "BUY"}, {"simbolo": ""},
    {"tolerancia": -1},
])
def test_rejeita_entrada_invalida(avaliador, ajuste):
    with pytest.raises(ValueError):
        avaliador.registrar(previsao(**ajuste), agora=1000)


@pytest.mark.parametrize("timestamp,preco,agora", [
    (1059, 101, 1100), (1066, 101, 1066), (1100, 101, 1099), (1060, 0, 1060),
    (1060, float("nan"), 1060), (float("nan"), 101, 1060),
])
def test_rejeita_outcome_antecipado_futuro_ou_invalido(avaliador, timestamp, preco, agora):
    avaliador.registrar(previsao(), agora=1000)
    with pytest.raises(ValueError):
        avaliador.avaliar("id-1", timestamp=timestamp, preco=preco, agora=agora)
    assert resumo(avaliador)["subir"]["amostras"] == 0


def test_resultado_exige_timestamp_observavel_no_horizonte(avaliador):
    avaliador.registrar(previsao(), agora=1005)

    with pytest.raises(ValueError, match="horizonte"):
        avaliador.avaliar("id-1", timestamp=999999, preco=101, agora=999999)


def test_sem_amostra_peso_zero_sem_amostragem_estocastica(avaliador):
    avaliador.registrar(previsao(), agora=1000)
    relatorio = resumo(avaliador)
    assert relatorio["subir"]["peso_sugerido"] == 0
    assert relatorio["subir"]["taxa_acerto"] is None
    assert relatorio["peso_aplicado"] == 0
    assert relatorio["amostragem_estocastica"] is False


def test_hold_nao_infla_direcoes_e_modelos_nao_se_misturam(avaliador):
    for i in range(30):
        item = previsao(identificador=str(i), direcao="estacionar")
        avaliador.registrar(item, agora=1000)
        avaliador.avaliar(str(i), timestamp=1060, preco=100, agora=1060)
    avaliador.registrar(previsao(modelo_versao="sklearn-v2"), agora=1000)
    avaliador.avaliar("id-1", timestamp=1060, preco=101, agora=1060)
    relatorio = resumo(avaliador)
    assert relatorio["estacionar"]["acertos"] == 30
    assert relatorio["estacionar"]["peso_sugerido"] == 0
    assert relatorio["subir"]["amostras"] == 0


def test_peso_por_direcao_com_amostra_minima_sem_execucao(avaliador):
    for i in range(30):
        avaliador.registrar(previsao(identificador=str(i)), agora=1000)
        avaliador.avaliar(str(i), timestamp=1060, preco=101, agora=1060)
        if i == 28:
            assert resumo(avaliador)["subir"]["peso_sugerido"] == 0
    relatorio = resumo(avaliador)
    assert 0 < relatorio["subir"]["peso_sugerido"] < 0.36
    assert relatorio["subir"]["wilson_inferior"] < 1.0
    assert relatorio["descer"]["peso_sugerido"] == 0
    assert relatorio["peso_aplicado"] == 0


def test_protecao_append_only_e_conexao_pertence_ao_chamador(avaliador):
    avaliador.registrar(previsao(), agora=1000)
    avaliador.avaliar("id-1", timestamp=1060, preco=101, agora=1060)
    for tabela in ("ia_local_previsoes", "ia_local_resultados"):
        with pytest.raises(sqlite3.IntegrityError, match="imutavel"):
            avaliador.conexao.execute(f"DELETE FROM {tabela}")
    tabelas = avaliador.conexao.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    assert {t[0] for t in tabelas} == {"ia_local_previsoes", "ia_local_resultados"}
    avaliador.conexao.rollback()
    assert resumo(avaliador)["subir"]["amostras"] == 0
