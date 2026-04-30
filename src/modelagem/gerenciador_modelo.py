from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.linear_model import SGDRegressor
from sklearn.preprocessing import StandardScaler

from src.core.settings import env_float, model_dir

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
        if not self._esta_ajustado():
            return None
        try:
            x = self._features_para_array(features)
            x_norm = self._scaler.transform(x)
            return self._normalizar_predicao_preco(features, float(self._modelo.predict(x_norm)[0]))
        except Exception:
            return None

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

    def status(self) -> dict[str, Any]:
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
        }
