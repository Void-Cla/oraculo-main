"""Classificador direcional sklearn em sombra, sem dependência operacional."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler

from src.modelagem.contrato_direcao import (
    ATRASO_MAXIMO_RESULTADO_SEGUNDOS,
    DIRECOES,
    ContextoDirecao,
    congelar_contexto,
    rotular_direcao,
)

MINIMO_AMOSTRAS_AQUECIMENTO = 200
MINIMO_AMOSTRAS_DIAGNOSTICO = 30
JANELA_DIAGNOSTICO = 100
LIMIAR_ACERTO_DIAGNOSTICO = 0.50
VERSAO_MODELO_SOMBRA = "sgd_direcao_sombra_v1"
_CLASSES = np.asarray(DIRECOES, dtype=object)
_ChaveEstado = tuple[str, int, int, tuple[str, ...]]


@dataclass(frozen=True)
class PrevisaoDirecaoSombra:
    """Snapshot prequential. ``direcao=None`` significa abstenção, não HOLD."""

    identificador: str
    contexto: ContextoDirecao
    preco_referencia: float
    criada_em: float
    direcao: str | None
    probabilidades: tuple[float, float, float] | None
    modelo_versao: str = VERSAO_MODELO_SOMBRA


@dataclass
class _Resultado:
    direcao_real: str
    observado_em: float


@dataclass
class _EstadoHorizonte:
    scaler: StandardScaler = field(default_factory=StandardScaler)
    modelo: SGDClassifier = field(
        default_factory=lambda: SGDClassifier(
            loss="log_loss", penalty="l2", alpha=0.0001, learning_rate="optimal", random_state=42,
            shuffle=False,
        )
    )
    nomes_features: tuple[str, ...] | None = None
    amostras_treinadas: int = 0


class TreinadorDirecaoSombra:
    """Estado volátil de pesquisa; não salva, não vota e não libera operações."""

    def __init__(
        self,
        *,
        minimo_amostras_aquecimento: int = MINIMO_AMOSTRAS_AQUECIMENTO,
        minimo_amostras_diagnostico: int = MINIMO_AMOSTRAS_DIAGNOSTICO,
        janela_diagnostico: int = JANELA_DIAGNOSTICO,
        limiar_acerto_diagnostico: float = LIMIAR_ACERTO_DIAGNOSTICO,
    ) -> None:
        if minimo_amostras_aquecimento <= 0 or minimo_amostras_diagnostico <= 0:
            raise ValueError("minimo_amostras_invalido")
        if janela_diagnostico < minimo_amostras_diagnostico:
            raise ValueError("janela_diagnostico_invalida")
        if not 0.0 < limiar_acerto_diagnostico <= 1.0:
            raise ValueError("limiar_acerto_invalido")
        self._aquecimento = minimo_amostras_aquecimento
        self._minimo_diagnostico = minimo_amostras_diagnostico
        self._janela = janela_diagnostico
        self._limiar = limiar_acerto_diagnostico
        self._estados: dict[_ChaveEstado, _EstadoHorizonte] = {}
        self._previsoes: dict[str, PrevisaoDirecaoSombra] = {}
        self._resultados: dict[str, _Resultado] = {}

    @staticmethod
    def _numero(valor: float | int, nome: str, *, positivo: bool = False) -> float:
        if isinstance(valor, bool):
            raise ValueError(f"{nome}_invalido")
        try:
            numero = float(valor)
        except (TypeError, ValueError) as erro:
            raise ValueError(f"{nome}_invalido") from erro
        if not math.isfinite(numero) or (positivo and numero <= 0.0):
            raise ValueError(f"{nome}_invalido")
        return numero

    @staticmethod
    def _identificador(identificador: str) -> str:
        if not isinstance(identificador, str) or not identificador.strip() or len(identificador) > 200:
            raise ValueError("identificador_invalido")
        return identificador

    @staticmethod
    def _chave_estado(contexto: ContextoDirecao) -> _ChaveEstado:
        return (
            contexto.simbolo.upper(),
            contexto.horizonte_segundos,
            contexto.versao_schema,
            tuple(sorted(contexto.features)),
        )

    def _estado(self, contexto: ContextoDirecao) -> _EstadoHorizonte:
        chave = self._chave_estado(contexto)
        estado = self._estados.setdefault(chave, _EstadoHorizonte())
        nomes = chave[-1]
        if estado.nomes_features is None:
            estado.nomes_features = nomes
        elif estado.nomes_features != nomes:
            raise ValueError("schema_features_incompativel")
        return estado

    @staticmethod
    def _vetor(contexto: ContextoDirecao, nomes_features: tuple[str, ...]) -> np.ndarray:
        return np.asarray([[float(contexto.features[nome]) for nome in nomes_features]], dtype=float)

    def prever(
        self,
        identificador: str,
        contexto: ContextoDirecao,
        *,
        preco_referencia: float,
        agora: float,
    ) -> PrevisaoDirecaoSombra:
        """Registra o snapshot antes de qualquer rótulo; frio resulta em abstenção."""
        identificador = self._identificador(identificador)
        agora = self._numero(agora, "agora")
        preco_referencia = self._numero(preco_referencia, "preco_referencia", positivo=True)
        snapshot = congelar_contexto(contexto)
        snapshot.validar(agora=agora)
        anterior = self._previsoes.get(identificador)
        if anterior is not None:
            if anterior.contexto != snapshot or anterior.preco_referencia != preco_referencia:
                raise ValueError("identificador_conflitante")
            return anterior
        estado = self._estado(snapshot)
        direcao: str | None = None
        probabilidades: tuple[float, float, float] | None = None
        if estado.amostras_treinadas >= self._aquecimento:
            vetor = self._vetor(snapshot, estado.nomes_features or ())
            probs_array = estado.modelo.predict_proba(estado.scaler.transform(vetor))[0]
            classes = tuple(str(classe) for classe in estado.modelo.classes_)
            if len(probs_array) != len(DIRECOES) or set(classes) != set(DIRECOES):
                raise RuntimeError("classes_modelo_incompativeis")
            por_direcao = {direcao: float(probabilidade) for direcao, probabilidade in zip(classes, probs_array)}
            probabilidades = (
                por_direcao["subir"],
                por_direcao["estacionar"],
                por_direcao["descer"],
            )
            direcao = max(DIRECOES, key=por_direcao.__getitem__)
        previsao = PrevisaoDirecaoSombra(
            identificador=identificador,
            contexto=snapshot,
            preco_referencia=preco_referencia,
            criada_em=agora,
            direcao=direcao,
            probabilidades=probabilidades,
        )
        self._previsoes[identificador] = previsao
        return previsao

    def maturar(
        self,
        identificador: str,
        *,
        preco_observado: float,
        observado_em: float,
        agora: float,
    ) -> bool:
        """Aceita somente resultado vencido; treina após a previsão já persistida em memória."""
        identificador = self._identificador(identificador)
        preco_observado = self._numero(preco_observado, "preco_observado", positivo=True)
        observado_em = self._numero(observado_em, "observado_em")
        agora = self._numero(agora, "agora")
        if observado_em > agora:
            raise ValueError("resultado_futuro")
        previsao = self._previsoes.get(identificador)
        if previsao is None:
            raise ValueError("previsao_inexistente")
        vencimento = previsao.contexto.referencia_em + previsao.contexto.horizonte_segundos
        if observado_em < vencimento or observado_em > vencimento + ATRASO_MAXIMO_RESULTADO_SEGUNDOS:
            raise ValueError("resultado_fora_do_horizonte")
        direcao_real = rotular_direcao(previsao.preco_referencia, preco_observado)
        anterior = self._resultados.get(identificador)
        if anterior is not None:
            if anterior != _Resultado(direcao_real=direcao_real, observado_em=observado_em):
                raise ValueError("resultado_conflitante")
            return False
        estado = self._estado(previsao.contexto)
        vetor = self._vetor(previsao.contexto, estado.nomes_features or ())
        estado.scaler.partial_fit(vetor)
        estado.modelo.partial_fit(estado.scaler.transform(vetor), [direcao_real], classes=_CLASSES)
        estado.amostras_treinadas += 1
        self._resultados[identificador] = _Resultado(direcao_real=direcao_real, observado_em=observado_em)
        return True

    def diagnostico(self, contexto: ContextoDirecao) -> dict[str, Any]:
        """Relata queda; não recalibra peso, consenso, gate ou artefato servido."""
        chave = self._chave_estado(contexto)
        estado = self._estados.get(chave)
        resultados: list[tuple[PrevisaoDirecaoSombra, _Resultado]] = []
        for identificador, resultado in self._resultados.items():
            previsao = self._previsoes[identificador]
            if self._chave_estado(previsao.contexto) == chave and previsao.direcao in ("subir", "descer"):
                resultados.append((previsao, resultado))
        resultados.sort(key=lambda item: (item[0].criada_em, item[0].identificador))
        janela = resultados[-self._janela :]
        acertos = sum(previsao.direcao == resultado.direcao_real for previsao, resultado in janela)
        total = len(janela)
        acuracia = acertos / total if total else None
        candidato = total >= self._minimo_diagnostico and (acuracia or 0.0) < self._limiar
        return {
            "modo": "sombra",
            "simbolo": chave[0],
            "horizonte_segundos": chave[1],
            "versao_schema": chave[2],
            "schema_features": chave[3],
            "modelo_versao": VERSAO_MODELO_SOMBRA,
            "amostras_treinadas": estado.amostras_treinadas if estado else 0,
            "aquecido": bool(estado and estado.amostras_treinadas >= self._aquecimento),
            "amostras_direcionais_janela": total,
            "acertos_direcionais_janela": acertos,
            "acuracia_direcional_janela": acuracia,
            "solicitar_artefato_candidato": candidato,
            "artefato_candidato_servido": False,
            "validacao_oos_comprovada": False,
            "promocao_permitida": False,
            "peso_aplicado": 0.0,
            "altera_consenso": False,
            "altera_gate": False,
            "amostragem_estocastica": False,
        }
