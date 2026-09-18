"""Contratos imutáveis para previsão direcional exclusivamente em sombra."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Mapping
from types import MappingProxyType

HORIZONTES_SEGUNDOS = frozenset({60, 300, 600, 900})
DIRECOES = ("subir", "estacionar", "descer")
VERSAO_SCHEMA_CONTEXTO = 1
VERSAO_LIMIAR_NEUTRO = "retorno_relativo_v1"
LIMIAR_NEUTRO = 0.0005
ATRASO_MAXIMO_CONTEXTO_SEGUNDOS = 5.0
ATRASO_MAXIMO_VELAS_SEGUNDOS = 60.0
ATRASO_MAXIMO_LIVRO_SEGUNDOS = 5.0
ATRASO_MAXIMO_RESULTADO_SEGUNDOS = 5.0


def _numero_finito(valor: float | int, nome: str, *, estritamente_positivo: bool = False) -> float:
    if isinstance(valor, bool):
        raise ValueError(f"{nome}_invalido")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as erro:
        raise ValueError(f"{nome}_invalido") from erro
    if not math.isfinite(numero) or (estritamente_positivo and numero <= 0.0):
        raise ValueError(f"{nome}_invalido")
    return numero


def hash_features(features: Mapping[str, float]) -> str:
    """Hash canônico dos valores que efetivamente entram no classificador."""
    if not isinstance(features, Mapping) or not features:
        raise ValueError("features_ausentes")
    normalizadas: dict[str, float] = {}
    for nome, valor in features.items():
        if not isinstance(nome, str) or not nome.strip():
            raise ValueError("nome_feature_invalido")
        normalizadas[nome] = _numero_finito(valor, f"feature_{nome}")
    serializado = json.dumps(normalizadas, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DadoExogeno:
    """Entrada externa com procedência; ausência explícita não é dado neutro."""

    fonte: str
    publicado_em: float | None
    ttl_segundos: int
    ausente: bool
    valores: Mapping[str, float]

    def validar(self, *, referencia_em: float) -> None:
        if not isinstance(self.fonte, str) or not self.fonte.strip() or len(self.fonte) > 100:
            raise ValueError("fonte_exogena_invalida")
        if type(self.ttl_segundos) is not int or self.ttl_segundos <= 0:
            raise ValueError("ttl_exogeno_invalido")
        if self.ausente:
            if self.publicado_em is not None or self.valores:
                raise ValueError("ausencia_exogena_inconsistente")
            return
        if self.publicado_em is None:
            raise ValueError("publicado_em_ausente")
        publicado_em = _numero_finito(self.publicado_em, "publicado_em")
        if publicado_em > referencia_em:
            raise ValueError("exogeno_futuro")
        if referencia_em - publicado_em > self.ttl_segundos:
            raise ValueError("exogeno_vencido")
        hash_features(self.valores)


@dataclass(frozen=True)
class ContextoDirecao:
    """Snapshot somente de velas fechadas, livro versionado e dados externos datados."""

    versao_schema: int
    simbolo: str
    horizonte_segundos: int
    referencia_em: float
    features: Mapping[str, float]
    hash_features: str
    velas_fechadas: bool
    velas_ate: float
    livro_as_of: float
    livro_sequencia: int
    dados_exogenos: tuple[DadoExogeno, ...] = ()

    def validar(self, *, agora: float) -> None:
        agora = _numero_finito(agora, "agora")
        if self.versao_schema != VERSAO_SCHEMA_CONTEXTO:
            raise ValueError("versao_schema_incompativel")
        if not isinstance(self.simbolo, str) or not self.simbolo.strip() or len(self.simbolo) > 30:
            raise ValueError("simbolo_invalido")
        if self.horizonte_segundos not in HORIZONTES_SEGUNDOS:
            raise ValueError("horizonte_invalido")
        referencia_em = _numero_finito(self.referencia_em, "referencia_em")
        if referencia_em > agora:
            raise ValueError("contexto_futuro")
        if agora - referencia_em > ATRASO_MAXIMO_CONTEXTO_SEGUNDOS:
            raise ValueError("contexto_vencido")
        if not self.velas_fechadas:
            raise ValueError("velas_abertas_nao_permitidas")
        velas_ate = _numero_finito(self.velas_ate, "velas_ate")
        if velas_ate > referencia_em:
            raise ValueError("velas_futuras")
        if referencia_em - velas_ate > ATRASO_MAXIMO_VELAS_SEGUNDOS:
            raise ValueError("velas_vencidas")
        livro_as_of = _numero_finito(self.livro_as_of, "livro_as_of")
        if type(self.livro_sequencia) is not int or self.livro_sequencia < 0:
            raise ValueError("livro_sem_sequencia")
        if livro_as_of > referencia_em:
            raise ValueError("livro_futuro")
        if referencia_em - livro_as_of > ATRASO_MAXIMO_LIVRO_SEGUNDOS:
            raise ValueError("livro_vencido")
        if not isinstance(self.hash_features, str) or self.hash_features != hash_features(self.features):
            raise ValueError("hash_features_invalido")
        fontes: set[str] = set()
        for dado in self.dados_exogenos:
            if dado.fonte in fontes:
                raise ValueError("fonte_exogena_duplicada")
            fontes.add(dado.fonte)
            dado.validar(referencia_em=referencia_em)


def congelar_contexto(contexto: ContextoDirecao) -> ContextoDirecao:
    """Copia dados mutáveis para que o rótulo use exatamente o snapshot previsto."""
    dados_exogenos = tuple(
        DadoExogeno(
            fonte=dado.fonte,
            publicado_em=dado.publicado_em,
            ttl_segundos=dado.ttl_segundos,
            ausente=dado.ausente,
            valores=MappingProxyType({nome: dado.valores[nome] for nome in sorted(dado.valores)}),
        )
        for dado in sorted(contexto.dados_exogenos, key=lambda item: item.fonte)
    )
    return ContextoDirecao(
        versao_schema=contexto.versao_schema,
        simbolo=contexto.simbolo,
        horizonte_segundos=contexto.horizonte_segundos,
        referencia_em=contexto.referencia_em,
        features=MappingProxyType({nome: contexto.features[nome] for nome in sorted(contexto.features)}),
        hash_features=contexto.hash_features,
        velas_fechadas=contexto.velas_fechadas,
        velas_ate=contexto.velas_ate,
        livro_as_of=contexto.livro_as_of,
        livro_sequencia=contexto.livro_sequencia,
        dados_exogenos=dados_exogenos,
    )


def rotular_direcao(preco_referencia: float, preco_observado: float) -> str:
    """Rótulo determinístico com limiar neutro versionado no contrato."""
    referencia = _numero_finito(preco_referencia, "preco_referencia", estritamente_positivo=True)
    observado = _numero_finito(preco_observado, "preco_observado", estritamente_positivo=True)
    retorno = observado / referencia - 1.0
    if abs(retorno) <= LIMIAR_NEUTRO:
        return "estacionar"
    return "subir" if retorno > 0.0 else "descer"
