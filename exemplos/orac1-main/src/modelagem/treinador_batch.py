from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from .gerenciador_modelo import FEATURE_ORDER, MODEL_DIR


def treinar_batch(
    simbolo: str,
    df: pd.DataFrame,
    feature_cols: Iterable[str] | None = None,
    target_col: str = "y",
) -> str:
    colunas = list(feature_cols or FEATURE_ORDER)
    if target_col not in df.columns:
        raise ValueError(f"coluna alvo '{target_col}' nao encontrada no dataframe")

    simbolo = simbolo.upper()
    diretorio = Path(MODEL_DIR) / simbolo
    diretorio.mkdir(parents=True, exist_ok=True)

    X = df[colunas].fillna(0.0).to_numpy()
    y = df[target_col].astype(float).to_numpy()
    pipeline = Pipeline(
        [
            ("scaler", RobustScaler()),
            ("est", HistGradientBoostingRegressor(random_state=42)),
        ]
    )
    pipeline.fit(X, y)

    versao = f"batch-{int(pd.Timestamp.utcnow().timestamp())}"
    path = diretorio / f"{versao}.joblib"
    payload = {"modelo": pipeline, "feature_cols": colunas, "versao": versao}
    joblib.dump(payload, path)
    joblib.dump(payload, diretorio / "modelo_batch.joblib")

    meta = diretorio / "meta_batch.json"
    with meta.open("w", encoding="utf-8") as arquivo:
        json.dump(
            {
                "simbolo": simbolo,
                "versao": versao,
                "feature_cols": colunas,
                "arquivo_canonico": str(diretorio / "modelo_batch.joblib"),
                "arquivo_versao": str(path),
            },
            arquivo,
            ensure_ascii=False,
            indent=2,
        )

    return str(path)
