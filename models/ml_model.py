"""
Modelo de Machine Learning: clasificador que estima la probabilidad
de que el precio suba en los próximos N períodos.

Usamos Gradient Boosting porque maneja bien relaciones no lineales
entre indicadores técnicos sin requerir mucho preprocesamiento,
y es razonablemente robusto con datasets chicos/medianos.

IMPORTANTE: esto es un filtro de señal, no un oráculo. Su output
es una probabilidad, se combina con las otras estrategias en el
ensemble, y de ninguna manera garantiza aciertos.
"""
import logging
import os
import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, roc_auc_score

import config
from features.feature_engineering import build_ml_dataset

logger = logging.getLogger(__name__)


class MLSignalModel:
    def __init__(self, model_path: str = None):
        self.model_path = model_path or config.ML_MODEL_PATH
        self.model = None
        self.feature_cols = None

    def train(self, df_features, horizon: int = None):
        X, y, feature_cols = build_ml_dataset(df_features, horizon)
        self.feature_cols = feature_cols

        if len(X) < config.ML_MIN_TRAIN_ROWS:
            logger.warning(
                "Dataset chico (%d filas) para entrenar de forma confiable. "
                "Se recomienda >= %d filas.", len(X), config.ML_MIN_TRAIN_ROWS
            )

        # Validación temporal (nunca usar K-fold random en series de tiempo:
        # eso filtra información del futuro al pasado)
        tscv = TimeSeriesSplit(n_splits=5)
        scores = []
        for train_idx, test_idx in tscv.split(X):
            model = GradientBoostingClassifier(
                n_estimators=150, max_depth=3, learning_rate=0.05, random_state=42
            )
            model.fit(X.iloc[train_idx], y.iloc[train_idx])
            preds = model.predict(X.iloc[test_idx])
            probs = model.predict_proba(X.iloc[test_idx])[:, 1]
            acc = accuracy_score(y.iloc[test_idx], preds)
            try:
                auc = roc_auc_score(y.iloc[test_idx], probs)
            except ValueError:
                auc = float("nan")
            scores.append((acc, auc))

        avg_acc = np.mean([s[0] for s in scores])
        avg_auc = np.nanmean([s[1] for s in scores])
        logger.info("Validación walk-forward: accuracy=%.3f AUC=%.3f", avg_acc, avg_auc)

        # Entrenamos el modelo final con todos los datos disponibles
        self.model = GradientBoostingClassifier(
            n_estimators=150, max_depth=3, learning_rate=0.05, random_state=42
        )
        self.model.fit(X, y)

        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        joblib.dump({"model": self.model, "feature_cols": self.feature_cols}, self.model_path)
        logger.info("Modelo guardado en %s", self.model_path)

        return {"accuracy": avg_acc, "auc": avg_auc}

    def load(self):
        payload = joblib.load(self.model_path)
        self.model = payload["model"]
        self.feature_cols = payload["feature_cols"]

    def predict_proba_up(self, df_features_row) -> float:
        """
        Recibe la última fila de features (Series o DataFrame de 1 fila)
        y devuelve la probabilidad estimada de que el precio suba.
        """
        if self.model is None:
            raise RuntimeError("El modelo no está entrenado ni cargado.")
        import pandas as pd
        X = pd.DataFrame([df_features_row[self.feature_cols].astype(float)], columns=self.feature_cols)
        if X.isnull().values.any():
            return 0.5  # sin suficiente info, señal neutra
        prob_up = self.model.predict_proba(X)[0, 1]
        return float(prob_up)
