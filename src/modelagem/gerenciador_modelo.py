from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.linear_model import SGDRegressor
from sklearn.preprocessing import StandardScaler

from src.core.settings import env_float, env_int, model_dir

FEATURE_ORDER = [
    "r_1m",
    "r_3m",
    "r_5m",
    "r_15m",
    "ma3",
    "ma6",
    "ma10",
    "ema5",
    "ema10",
    "vol5",
    "vol10",
    "amplitude_rel",
    "volume_ratio",
    "book_imb",
    "spread_rel",
    "microprice",
    "pressao_rel",
    "ret_log_1m",
    "ret_log_cum_3m",
    "diff_close_micro_rel",
    "slope_ma",
    "hora_sin",
    "hora_cos",
    "dia_sin",
    "dia_cos",
    "sent_score",
]

MODEL_DIR = model_dir()
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def _clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


class GerenciadorModelo:
    def __init__(self, simbolo: str = "BTCUSDT") -> None:
        self.simbolo = simbolo.upper()
        self._diretorio = MODEL_DIR / self.simbolo
        self._diretorio.mkdir(parents=True, exist_ok=True)
        self._modelo_path = self._diretorio / "modelo_online.joblib"
        self._meta_path = self._diretorio / "meta.json"
        self._modelo_batch_path = self._diretorio / "modelo_batch.joblib"
        self._meta_batch_path = self._diretorio / "meta_batch.json"
        self._modelo: SGDRegressor = SGDRegressor(
            loss="huber",
            penalty="l2",
            alpha=1e-4,
            learning_rate="optimal",
            random_state=42,
        )
        self._scaler: StandardScaler = StandardScaler()
        self._modelo_batch: Any | None = None
        self._feature_cols_batch: list[str] = list(FEATURE_ORDER)
        self._amostras_ajustadas = 0
        self._versao = "cold-start"
        self._versao_batch = "ausente"
        self._carregar()

    def _carregar(self) -> None:
        if self._modelo_path.exists():
            dados = joblib.load(self._modelo_path)
            self._modelo = dados.get("modelo", self._modelo)
            self._scaler = dados.get("scaler", self._scaler)
            self._amostras_ajustadas = int(dados.get("amostras_ajustadas", 0))
            self._versao = str(dados.get("versao", self._versao))
        self._carregar_batch()

    def _carregar_batch(self) -> None:
        caminho = self._resolver_modelo_batch()
        if caminho is None:
            return
        dados = joblib.load(caminho)
        self._modelo_batch = dados.get("modelo")
        self._feature_cols_batch = list(dados.get("feature_cols") or FEATURE_ORDER)
        self._versao_batch = str(dados.get("versao", caminho.stem))

    def _resolver_modelo_batch(self) -> Path | None:
        if self._modelo_batch_path.exists():
            return self._modelo_batch_path
        candidatos = sorted(self._diretorio.glob("batch-*.joblib"))
        if candidatos:
            return candidatos[-1]
        return None

    def _features_para_array(self, features: dict[str, Any], feature_order: list[str] | None = None) -> np.ndarray:
        valores = []
        for chave in list(feature_order or FEATURE_ORDER):
            try:
                valores.append(float(features.get(chave, 0.0) or 0.0))
            except (TypeError, ValueError):
                valores.append(0.0)
        return np.asarray(valores, dtype=float).reshape(1, -1)

    def _esta_ajustado(self) -> bool:
        return hasattr(self._modelo, "coef_") and self._amostras_ajustadas > 0

    def _predicao_fallback(self, features: dict[str, Any]) -> float:
        close = float(features.get("close", 0.0) or 0.0)
        if close <= 0.0:
            return 0.0
        score = (
            (float(features.get("r_1m", 0.0) or 0.0) * 0.40)
            + (float(features.get("r_3m", 0.0) or 0.0) * 0.20)
            + (float(features.get("r_5m", 0.0) or 0.0) * 0.15)
            + (float(features.get("diff_close_micro_rel", 0.0) or 0.0) * 0.15)
            + (float(features.get("sent_score", 0.0) or 0.0) * 0.10)
        )
        variacao = _clamp(score, -0.015, 0.015)
        return close * (1.0 + variacao)

    def _normalizar_predicao_preco(self, features: dict[str, Any], predicao: float) -> float:
        close = float(features.get("close", 0.0) or 0.0)
        if close <= 0.0:
            return float(predicao)
        limite = env_float("MAX_VARIACAO_PREVISTA", 0.02, minimo=0.001)
        variacao = _clamp((float(predicao) - close) / close, -limite, limite)
        return close * (1.0 + variacao)

    def _predicao_online(self, features: dict[str, Any]) -> float | None:
        # Gate de confiabilidade: um modelo sub-treinado (poucas amostras) com SGD pode
        # divergir e cravar predições extremas, dominando o sinal. Só usa o online após
        # um aquecimento mínimo (MIN_AMOSTRAS_ONLINE). Abaixo disso, vale o fallback são.
        min_amostras = env_int("MIN_AMOSTRAS_ONLINE", 200, minimo=1)
        if not self._esta_ajustado() or self._amostras_ajustadas < min_amostras:
            return None
        try:
            x = self._features_para_array(features)
            x_norm = self._scaler.transform(x)
            norm = self._normalizar_predicao_preco(features, float(self._modelo.predict(x_norm)[0]))
        except Exception:
            return None
        # Guarda de divergência: se a predição satura o clamp de variação, o modelo
        # provavelmente explodiu os coeficientes → descartar (não poluir o consenso com ±máximo).
        close = float(features.get("close", 0.0) or 0.0)
        limite = env_float("MAX_VARIACAO_PREVISTA", 0.02, minimo=0.001)
        if close > 0.0 and abs((norm - close) / close) >= (limite - 1e-9):
            return None
        return norm

    def _predicao_batch(self, features: dict[str, Any]) -> float | None:
        if self._modelo_batch is None:
            return None
        try:
            x = self._features_para_array(features, self._feature_cols_batch)
            return self._normalizar_predicao_preco(features, float(self._modelo_batch.predict(x)[0]))
        except Exception:
            return None

    def predict(self, features: dict[str, Any]) -> float:
        predicao_heuristica = self._predicao_fallback(features)
        predicoes: list[tuple[float, float]] = [(predicao_heuristica, 0.25)]

        predicao_batch = self._predicao_batch(features)
        if predicao_batch is not None:
            predicoes.append((predicao_batch, 0.35))

        predicao_online = self._predicao_online(features)
        if predicao_online is not None:
            peso_online_base = env_float("PESO_MODELO_ONLINE", 0.40, minimo=0.10)
            fator_online = min(1.0, max(0.25, self._amostras_ajustadas / 50.0))
            predicoes.append((predicao_online, peso_online_base * fator_online))

        soma_pesos = sum(peso for _, peso in predicoes) or 1.0
        predicao_final = sum(predicao * peso for predicao, peso in predicoes) / soma_pesos
        return self._normalizar_predicao_preco(features, predicao_final)

    def partial_fit(self, features: dict[str, Any], y: float) -> None:
        x = self._features_para_array(features)
        self._scaler.partial_fit(x)
        self._modelo.partial_fit(self._scaler.transform(x), np.asarray([float(y)], dtype=float))
        self._amostras_ajustadas += 1
        self._versao = f"online-{int(time.time())}"

    def salvar(self, versao: str | None = None) -> None:
        if versao:
            self._versao = versao
        joblib.dump(
            {
                "modelo": self._modelo,
                "scaler": self._scaler,
                "amostras_ajustadas": self._amostras_ajustadas,
                "versao": self._versao,
            },
            self._modelo_path,
        )
        with self._meta_path.open("w", encoding="utf-8") as arquivo:
            json.dump(self.status(), arquivo, ensure_ascii=False, indent=2)

    def _coef_norm(self) -> float | None:
        """Norma L2 dos coeficientes do modelo online — indicador de divergência.
        Saudável: pequeno. O modelo saturado do run 13-18h tinha norma ~71."""
        coef = getattr(self._modelo, "coef_", None)
        if coef is None:
            return None
        try:
            return float(np.linalg.norm(np.asarray(coef, dtype=float)))
        except Exception:
            return None

    def status(self) -> dict[str, Any]:
        min_amostras = env_int("MIN_AMOSTRAS_ONLINE", 200, minimo=1)
        return {
            "simbolo": self.simbolo,
            "versao": self._versao,
            "versao_batch": self._versao_batch,
            "feature_order": FEATURE_ORDER,
            "feature_order_batch": self._feature_cols_batch,
            "amostras_ajustadas": self._amostras_ajustadas,
            "modelo_path": str(self._modelo_path),
            "meta_path": str(self._meta_path),
            "modelo_batch_path": str(self._resolver_modelo_batch() or self._modelo_batch_path),
            "meta_batch_path": str(self._meta_batch_path),
            "esta_ajustado": self._esta_ajustado(),
            "batch_carregado": self._modelo_batch is not None,
            # Saúde do treino online em runtime (observabilidade):
            "min_amostras_online": min_amostras,
            "gate_amostras_ok": self._amostras_ajustadas >= min_amostras,
            "online_em_uso": self._esta_ajustado() and self._amostras_ajustadas >= min_amostras,
            "coef_norm": self._coef_norm(),
            "max_variacao_prevista": env_float("MAX_VARIACAO_PREVISTA", 0.02, minimo=0.001),
        }


# ── Cache de instâncias por símbolo (PERF-01) ───────────────────────────────
# Evita o joblib.load() a cada ciclo de predição. A invalidação é por assinatura de
# disco (mtime do modelo online + mtime do diretório): quando o treinador salva um novo
# modelo, a assinatura muda e o preditor recarrega — o aprendizado online não é perdido.
_CACHE_GERENCIADORES: dict[str, tuple[tuple[float, float], "GerenciadorModelo"]] = {}


def _assinatura_disco(simbolo: str) -> tuple[float, float]:
    diretorio = MODEL_DIR / simbolo.upper()

    def _mtime(caminho: Path) -> float:
        try:
            return caminho.stat().st_mtime
        except OSError:
            return 0.0

    # Assinatura por mtime dos ARQUIVOS de modelo (não do diretório, cujo mtime muda ao criá-lo):
    # online cobre o aprendizado online; batch resolvido cobre re-treinos batch.
    online = _mtime(diretorio / "modelo_online.joblib")
    batch_path = diretorio / "modelo_batch.joblib"
    if not batch_path.exists():
        candidatos = sorted(diretorio.glob("batch-*.joblib"))
        batch_path = candidatos[-1] if candidatos else batch_path
    return (online, _mtime(batch_path))


def obter_gerenciador_modelo(simbolo: str) -> "GerenciadorModelo":
    """Retorna um GerenciadorModelo cacheado por símbolo, recarregando só se o disco mudou."""
    chave = simbolo.upper()
    assinatura = _assinatura_disco(chave)
    cacheado = _CACHE_GERENCIADORES.get(chave)
    if cacheado is not None and cacheado[0] == assinatura:
        return cacheado[1]
    gerenciador = GerenciadorModelo(simbolo=chave)
    _CACHE_GERENCIADORES[chave] = (assinatura, gerenciador)
    return gerenciador
