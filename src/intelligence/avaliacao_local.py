"""Avaliação prospectiva do modelo sklearn em sombra, sem execução financeira.

O chamador fornece conexão, relógio confiável e preços observados. Ele também
possui a transação (commit/rollback) e a validação da origem dos dados.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import astuple, dataclass
from typing import Any

DIRECOES = ("subir", "estacionar", "descer")
MINIMO_AMOSTRAS = 30  # Piso exploratório por direção; não comprova lucro.
PESO_MAXIMO_SOMBRA = 0.36  # Teto nominal da fonte IA já existente.
Z_WILSON = 1.959963984540054  # Intervalo bilateral de 95%.
ATRASO_MAXIMO_REGISTRO_SEGUNDOS = 5.0  # Evita sinal com preço de referência vencido.
ATRASO_MAXIMO_RESULTADO_SEGUNDOS = 5.0  # Exige observação próxima ao horizonte.


def _numero(valor: float, nome: str, minimo: float = 0.0) -> None:
    if isinstance(valor, bool) or not math.isfinite(valor) or valor < minimo:
        raise ValueError(f"{nome}_invalido")


@dataclass(frozen=True)
class PrevisaoLocal:
    """Probabilidades na ordem subir/estacionar/descer; tempos Unix segundos."""

    identificador: str
    simbolo: str
    modelo_versao: str
    timestamp: float
    horizonte_segundos: int
    preco_referencia: float
    direcao: str
    prob_subir: float
    prob_estacionar: float
    prob_descer: float
    tolerancia: float

    def validar(self) -> None:
        for nome in ("identificador", "simbolo", "modelo_versao"):
            valor = getattr(self, nome)
            if not isinstance(valor, str) or not valor.strip() or len(valor) > 200:
                raise ValueError(f"{nome}_invalido")
        _numero(self.timestamp, "timestamp")
        if type(self.horizonte_segundos) is not int or self.horizonte_segundos <= 0:
            raise ValueError("horizonte_invalido")
        _numero(self.preco_referencia, "preco_referencia")
        if self.preco_referencia == 0 or self.direcao not in DIRECOES:
            raise ValueError("preco_ou_direcao_invalido")
        probabilidades = (self.prob_subir, self.prob_estacionar, self.prob_descer)
        for valor in probabilidades:
            _numero(valor, "probabilidade")
            if valor > 1:
                raise ValueError("probabilidade_invalida")
        if not math.isclose(sum(probabilidades), 1.0, abs_tol=1e-9, rel_tol=0):
            raise ValueError("soma_probabilidades_invalida")
        _numero(self.tolerancia, "tolerancia")
        if self.tolerancia >= 1:
            raise ValueError("tolerancia_invalida")


def limite_wilson(acertos: int, total: int) -> float:
    """Limite inferior; amostras correlacionadas ainda exigem validação temporal."""
    if total == 0:
        return 0.0
    proporcao = acertos / total
    z2 = Z_WILSON**2
    margem = Z_WILSON * math.sqrt(proporcao * (1 - proporcao) / total + z2 / (4 * total**2))
    return max(0.0, (proporcao + z2 / (2 * total) - margem) / (1 + z2 / total))


class AvaliadorLocal:
    """Registro append-only. Conexão e transação pertencem ao chamador."""

    def __init__(self, conexao: sqlite3.Connection) -> None:
        self.conexao = conexao

    def preparar(self) -> None:
        self.conexao.execute("""CREATE TABLE IF NOT EXISTS ia_local_previsoes (
            identificador TEXT PRIMARY KEY, simbolo TEXT NOT NULL,
            modelo_versao TEXT NOT NULL, timestamp REAL NOT NULL,
            horizonte_segundos INTEGER NOT NULL, preco_referencia REAL NOT NULL,
            direcao TEXT NOT NULL, prob_subir REAL NOT NULL,
            prob_estacionar REAL NOT NULL, prob_descer REAL NOT NULL,
            tolerancia REAL NOT NULL, temperatura REAL NOT NULL,
            registrado_em REAL NOT NULL)""")
        self.conexao.execute("""CREATE TABLE IF NOT EXISTS ia_local_resultados (
            identificador TEXT PRIMARY KEY REFERENCES ia_local_previsoes(identificador),
            timestamp REAL NOT NULL, preco REAL NOT NULL, direcao TEXT NOT NULL,
            brier REAL NOT NULL)""")
        self.conexao.execute("""CREATE INDEX IF NOT EXISTS ia_local_grupo
            ON ia_local_previsoes(modelo_versao, simbolo, horizonte_segundos)""")
        for tabela in ("ia_local_previsoes", "ia_local_resultados"):
            for operacao in ("UPDATE", "DELETE"):
                self.conexao.execute(f"""CREATE TRIGGER IF NOT EXISTS {tabela}_{operacao}
                    BEFORE {operacao} ON {tabela} BEGIN
                    SELECT RAISE(ABORT, 'registro_ia_imutavel'); END""")

    def registrar(self, previsao: PrevisaoLocal, *, agora: float) -> bool:
        """Retorna False para retry idêntico; rejeita backfill e ID conflitante."""
        previsao.validar()
        _numero(agora, "agora")
        valores = astuple(previsao)
        anterior = self.conexao.execute(
            "SELECT * FROM ia_local_previsoes WHERE identificador = ?", (previsao.identificador,)
        ).fetchone()
        if anterior is not None:
            if tuple(anterior)[0:11] != valores:
                raise ValueError("identificador_conflitante")
            return False
        atraso = agora - previsao.timestamp
        if atraso < 0 or atraso > ATRASO_MAXIMO_REGISTRO_SEGUNDOS:
            raise ValueError("previsao_futura_ou_horizonte_encerrado")
        self.conexao.execute(
            "INSERT INTO ia_local_previsoes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (*valores, 0.0, agora),
        )
        return True

    def avaliar(self, identificador: str, *, timestamp: float, preco: float, agora: float) -> bool:
        """Registra preço ao vencer horizonte; timestamp futuro é inválido."""
        for nome, valor in (("timestamp", timestamp), ("preco", preco), ("agora", agora)):
            _numero(valor, nome)
        if preco == 0 or timestamp > agora:
            raise ValueError("preco_ou_timestamp_invalido")
        registro = self.conexao.execute(
            "SELECT * FROM ia_local_previsoes WHERE identificador = ?", (identificador,)
        ).fetchone()
        if registro is None:
            raise ValueError("previsao_inexistente")
        previsao = PrevisaoLocal(*tuple(registro)[0:11])
        alvo = previsao.timestamp + previsao.horizonte_segundos
        if timestamp < alvo or timestamp > alvo + ATRASO_MAXIMO_RESULTADO_SEGUNDOS:
            raise ValueError("horizonte_nao_encerrado")
        anterior = self.conexao.execute(
            "SELECT timestamp, preco FROM ia_local_resultados WHERE identificador = ?", (identificador,)
        ).fetchone()
        if anterior is not None:
            if tuple(anterior) != (timestamp, preco):
                raise ValueError("resultado_conflitante")
            return False
        retorno = preco / previsao.preco_referencia - 1
        direcao = "estacionar" if abs(retorno) <= previsao.tolerancia else "subir" if retorno > 0 else "descer"
        probs = (previsao.prob_subir, previsao.prob_estacionar, previsao.prob_descer)
        brier = sum((p - int(d == direcao)) ** 2 for p, d in zip(probs, DIRECOES))
        self.conexao.execute(
            "INSERT INTO ia_local_resultados VALUES (?, ?, ?, ?, ?)",
            (identificador, timestamp, preco, direcao, brier),
        )
        return True

    def relatorio(self, *, modelo_versao: str, simbolo: str, horizonte_segundos: int) -> dict[str, Any]:
        """Métricas descritivas; peso proposto não autoriza execução ou lucro."""
        linhas = self.conexao.execute("""SELECT p.direcao, COUNT(*),
                SUM(p.direcao = r.direcao), AVG(r.brier)
            FROM ia_local_previsoes p JOIN ia_local_resultados r USING (identificador)
            WHERE p.modelo_versao = ? AND p.simbolo = ? AND p.horizonte_segundos = ?
            GROUP BY p.direcao""", (modelo_versao, simbolo, horizonte_segundos)).fetchall()
        grupos = {linha[0]: linha[1:] for linha in linhas}
        resultado: dict[str, Any] = {
            "modo": "sombra", "peso_aplicado": 0.0,
            "validacao_temporal_independente": False,
            "aviso": "estatisticas_descritivas_nao_comprovam_edge_ou_independencia",
        }
        for direcao in DIRECOES:
            total, acertos, brier = grupos.get(direcao, (0, 0, None))
            limite = limite_wilson(acertos, total)
            peso = PESO_MAXIMO_SOMBRA * max(0.0, 2 * limite - 1)
            resultado[direcao] = {
                "amostras": total, "acertos": acertos,
                "taxa_acerto": acertos / total if total else None,
                "wilson_inferior": limite, "brier": brier,
                "peso_sugerido": peso if total >= MINIMO_AMOSTRAS and direcao != "estacionar" else 0.0,
            }
        resultado["amostragem_estocastica"] = False
        return resultado
