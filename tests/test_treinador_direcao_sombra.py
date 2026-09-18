from __future__ import annotations

import math

import numpy as np
import pytest

from src.modelagem.contrato_direcao import (
    DadoExogeno,
    ContextoDirecao,
    VERSAO_SCHEMA_CONTEXTO,
    hash_features,
)
from src.modelagem.treinador_direcao_sombra import TreinadorDirecaoSombra


def _contexto(
    *,
    horizonte: int = 60,
    referencia: float = 1000.0,
    feature: float = 1.0,
    exogeno: DadoExogeno | None = None,
) -> ContextoDirecao:
    features = {"r_1m": feature, "book_imb": feature / 10}
    return ContextoDirecao(
        versao_schema=VERSAO_SCHEMA_CONTEXTO,
        simbolo="BTCUSDT",
        horizonte_segundos=horizonte,
        referencia_em=referencia,
        features=features,
        hash_features=hash_features(features),
        velas_fechadas=True,
        velas_ate=referencia - 1,
        livro_as_of=referencia - 1,
        livro_sequencia=9,
        dados_exogenos=() if exogeno is None else (exogeno,),
    )


def test_contexto_rejeita_vela_aberta_hash_e_valor_nao_finito() -> None:
    contexto = _contexto()
    with pytest.raises(ValueError, match="velas_abertas"):
        ContextoDirecao(**{**contexto.__dict__, "velas_fechadas": False}).validar(agora=1001)
    with pytest.raises(ValueError, match="hash_features"):
        ContextoDirecao(**{**contexto.__dict__, "hash_features": "x"}).validar(agora=1001)
    invalido = _contexto()
    invalido = ContextoDirecao(**{**invalido.__dict__, "features": {"r_1m": math.nan}})
    with pytest.raises(ValueError):
        invalido.validar(agora=1001)


def test_contexto_rejeita_livro_stale_futuro_e_ia_vencida() -> None:
    contexto = _contexto()
    with pytest.raises(ValueError, match="livro_vencido"):
        ContextoDirecao(**{**contexto.__dict__, "livro_as_of": 990}).validar(agora=1001)
    with pytest.raises(ValueError, match="livro_futuro"):
        ContextoDirecao(**{**contexto.__dict__, "livro_as_of": 1001}).validar(agora=1001)
    ia_vencida = DadoExogeno("ia_diaria", 900.0, 60, False, {"sentimento": 0.2})
    with pytest.raises(ValueError, match="exogeno_vencido"):
        _contexto(exogeno=ia_vencida).validar(agora=1001)


def test_ausencia_ia_explicita_e_aceita_sem_fingir_neutralidade() -> None:
    ausente = DadoExogeno("ia_diaria", None, 86400, True, {})
    _contexto(exogeno=ausente).validar(agora=1001)
    with pytest.raises(ValueError, match="ausencia_exogena"):
        DadoExogeno("ia_diaria", 999.0, 86400, True, {"sentimento": 0.0}).validar(referencia_em=1000)


def test_horizontes_ficam_isolados_e_modelo_abstem_ate_aquecimento() -> None:
    treinador = TreinadorDirecaoSombra(minimo_amostras_aquecimento=1)
    p60 = treinador.prever("p60", _contexto(horizonte=60), preco_referencia=100, agora=1001)
    p300 = treinador.prever("p300", _contexto(horizonte=300), preco_referencia=100, agora=1001)
    assert p60.direcao is None and p300.direcao is None
    assert treinador.maturar("p60", preco_observado=101, observado_em=1060, agora=1060)
    seguinte = treinador.prever("p60-2", _contexto(horizonte=60, referencia=1060), preco_referencia=101, agora=1061)
    assert seguinte.direcao in {"subir", "estacionar", "descer"}
    assert treinador.diagnostico(_contexto(horizonte=300))["amostras_treinadas"] == 0


def test_prequential_idempotente_e_resultado_so_depois_do_horizonte() -> None:
    treinador = TreinadorDirecaoSombra(minimo_amostras_aquecimento=2)
    contexto = _contexto()
    previsao = treinador.prever("id", contexto, preco_referencia=100, agora=1001)
    assert treinador.prever("id", contexto, preco_referencia=100, agora=1001) == previsao
    with pytest.raises(ValueError, match="fora_do_horizonte"):
        treinador.maturar("id", preco_observado=101, observado_em=1059, agora=1059)
    assert treinador.maturar("id", preco_observado=101, observado_em=1060, agora=1060)
    assert not treinador.maturar("id", preco_observado=101, observado_em=1060, agora=1060)


def test_queda_so_sinaliza_candidato_sem_peso_ou_acao_operacional() -> None:
    treinador = TreinadorDirecaoSombra(
        minimo_amostras_aquecimento=1,
        minimo_amostras_diagnostico=1,
        janela_diagnostico=2,
        limiar_acerto_diagnostico=1.0,
    )
    treinador.prever("frio", _contexto(), preco_referencia=100, agora=1001)
    treinador.maturar("frio", preco_observado=101, observado_em=1060, agora=1060)
    previsao = treinador.prever("errada", _contexto(referencia=1060, feature=-1), preco_referencia=100, agora=1061)
    assert previsao.direcao in {"subir", "estacionar", "descer"}
    treinador.maturar("errada", preco_observado=99, observado_em=1120, agora=1120)
    diagnostico = treinador.diagnostico(_contexto())
    assert diagnostico["peso_aplicado"] == 0.0
    assert not diagnostico["artefato_candidato_servido"]
    assert not diagnostico["altera_consenso"] and not diagnostico["altera_gate"]
    assert diagnostico["amostragem_estocastica"] is False
    assert "temperatura" not in diagnostico


def test_predict_proba_mapeia_pela_classe_do_modelo_e_nao_pela_ordem() -> None:
    treinador = TreinadorDirecaoSombra(minimo_amostras_aquecimento=1)
    contexto = _contexto()
    treinador.prever("base", contexto, preco_referencia=100, agora=1001)
    treinador.maturar("base", preco_observado=101, observado_em=1060, agora=1060)

    class ModeloAssimetrico:
        classes_ = np.asarray(["descer", "subir", "estacionar"])

        def predict_proba(self, _: object) -> np.ndarray:
            return np.asarray([[0.05, 0.80, 0.15]])

    setattr(treinador._estado(contexto), "modelo", ModeloAssimetrico())
    previsao = treinador.prever("mapeada", _contexto(referencia=1060), preco_referencia=100, agora=1061)
    assert previsao.direcao == "subir"
    assert previsao.probabilidades == (0.80, 0.15, 0.05)


def test_estado_nao_contamina_simbolos_e_snapshot_congela_entradas_mutaveis() -> None:
    treinador = TreinadorDirecaoSombra(minimo_amostras_aquecimento=1)
    features = {"r_1m": 1.0, "book_imb": 0.1}
    valores_ia = {"sentimento": 0.2}
    exogeno = DadoExogeno("ia_diaria", 999.0, 86400, False, valores_ia)
    contexto_btc = ContextoDirecao(
        **{**_contexto(exogeno=exogeno).__dict__, "features": features, "hash_features": hash_features(features)}
    )
    previsao = treinador.prever("btc", contexto_btc, preco_referencia=100, agora=1001)
    features["r_1m"] = 999.0
    valores_ia["sentimento"] = -999.0
    assert previsao.contexto.features["r_1m"] == 1.0
    assert previsao.contexto.dados_exogenos[0].valores["sentimento"] == 0.2
    treinador.maturar("btc", preco_observado=101, observado_em=1060, agora=1060)
    contexto_eth = ContextoDirecao(**{**_contexto(referencia=1060).__dict__, "simbolo": "ETHUSDT"})
    assert treinador.diagnostico(contexto_eth)["amostras_treinadas"] == 0
    assert treinador.diagnostico(contexto_btc)["amostras_treinadas"] == 1
