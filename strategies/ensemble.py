"""
Combina trend_following + mean_reversion + señal ML en una única
señal ponderada adaptativa mediante el Filtro de Régimen de Mercado (ADX).
Este es el "cerebro" que decide si comprar, vender o quedarse afuera.
"""
import numpy as np
import config
from strategies import trend_following, mean_reversion


def combined_signal(row, ml_prob_up: float = 0.5) -> dict:
    # 1. Obtener o calcular puntajes de las sub-estrategias
    trend_score = row.get("trend_score", 0.0)
    mr_score = row.get("mean_reversion_score", 0.0)
    
    # Si las sub-estrategias son funciones directas en tus módulos, 
    # se evalúan si no vienen precargadas en la fila:
    if "trend_score" not in row and hasattr(trend_following, "signal"):
        trend_score = trend_following.signal(row)
    if "mean_reversion_score" not in row and hasattr(mean_reversion, "signal"):
        mr_score = mean_reversion.signal(row)

    # Score de ML escalado de [-1, 1]
    ml_score = (ml_prob_up - 0.5) * 2.0

    # 2. Leer ADX (si no existe en las features, asigna 20.0 por defecto)
    adx_val = row.get("adx", 20.0)

    # 3. Aplicar Filtro de Régimen de Mercado (Adaptación Dinámica de Pesos)
    # Exigir ADX > 30 (en lugar de 25) para confirmar tendencias sólidas
    if adx_val >= 30.0:
        w_trend = config.WEIGHT_TREND + (config.WEIGHT_MEAN_REVERSION * 0.8)
        w_mr = config.WEIGHT_MEAN_REVERSION * 0.2
        w_ml = config.WEIGHT_ML
    elif adx_val <= 20.0:
        # MERCADO EN RANGO / LATERAL: Se prioriza Reversión a la Media
        w_trend = config.WEIGHT_TREND * 0.2
        w_mr = config.WEIGHT_MEAN_REVERSION + (config.WEIGHT_TREND * 0.8)
        w_ml = config.WEIGHT_ML
    else:
        # MERCADO EN TRANSICIÓN: Pesos estándar de config.py
        w_trend = config.WEIGHT_TREND
        w_mr = config.WEIGHT_MEAN_REVERSION
        w_ml = config.WEIGHT_ML

    # Normalizar pesos para asegurar que la suma sea exactamente 1.0
    total_w = w_trend + w_mr + w_ml
    if total_w > 0:
        w_trend /= total_w
        w_mr /= total_w
        w_ml /= total_w

    # 4. Calcular Score Combinado Final
    combined = (trend_score * w_trend) + (mr_score * w_mr) + (ml_score * w_ml)

    # 5. Determinar la decisión final del bot
    decision = "FLAT"
    if combined >= config.ENTRY_THRESHOLD:
        decision = "LONG"
    elif combined <= -config.ENTRY_THRESHOLD:
        decision = "SHORT"

    return {
        "decision": decision,
        "combined_score": round(combined, 3),
        "trend_score": round(trend_score, 2),
        "mean_reversion_score": round(mr_score, 2),
        "ml_score": round(ml_score, 2),
        "adx": round(adx_val, 1)
    }