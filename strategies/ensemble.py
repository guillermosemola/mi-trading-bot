import numpy as np
import config
from strategies import trend_following, mean_reversion


def combined_signal(row, ml_prob_up: float = 0.5) -> dict:
    # 1. Obtener o calcular puntajes de las sub-estrategias
    trend_score = row.get("trend_score", None)
    mr_score = row.get("mean_reversion_score", None)

    if (trend_score is None or np.isnan(trend_score)) and hasattr(trend_following, "signal"):
        trend_score = trend_following.signal(row)
    if (mr_score is None or np.isnan(mr_score)) and hasattr(mean_reversion, "signal"):
        mr_score = mean_reversion.signal(row)

    # Sanitización de entradas nulas
    trend_score = 0.0 if trend_score is None or np.isnan(trend_score) else float(trend_score)
    mr_score = 0.0 if mr_score is None or np.isnan(mr_score) else float(mr_score)

    # Score de ML escalado de [-1, 1]
    ml_prob_up = 0.5 if np.isnan(ml_prob_up) else ml_prob_up
    ml_score = (ml_prob_up - 0.5) * 2.0

    # 2. Leer ADX (con fallback en caso de NaN)
    adx_val = row.get("adx", 20.0)
    if adx_val is None or np.isnan(adx_val):
        adx_val = 20.0

    # 3. Aplicar Filtro de Régimen de Mercado
    if adx_val >= 30.0:
        w_trend = config.WEIGHT_TREND + (config.WEIGHT_MEAN_REVERSION * 0.8)
        w_mr = config.WEIGHT_MEAN_REVERSION * 0.2
        w_ml = config.WEIGHT_ML
    elif adx_val <= 20.0:
        w_trend = config.WEIGHT_TREND * 0.2
        w_mr = config.WEIGHT_MEAN_REVERSION + (config.WEIGHT_TREND * 0.8)
        w_ml = config.WEIGHT_ML
    else:
        w_trend = config.WEIGHT_TREND
        w_mr = config.WEIGHT_MEAN_REVERSION
        w_ml = config.WEIGHT_ML

    # Normalizar pesos
    total_w = w_trend + w_mr + w_ml
    if total_w > 0:
        w_trend /= total_w
        w_mr /= total_w
        w_ml /= total_w

    # 4. Calcular Score Combinado Final
    combined = (trend_score * w_trend) + (mr_score * w_mr) + (ml_score * w_ml)

    # 5. Determinar la decisión final del bot
    decision = "FLAT"
    threshold = getattr(config, "ENTRY_THRESHOLD", 0.5)

    if combined >= threshold:
        decision = "LONG"
    elif combined <= -threshold:
        decision = "SHORT"

    return {
        "decision": decision,
        "combined_score": round(combined, 3),
        "trend_score": round(trend_score, 2),
        "mean_reversion_score": round(mr_score, 2),
        "ml_score": round(ml_score, 2),
        "adx": round(adx_val, 1)
    }
