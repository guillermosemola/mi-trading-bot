"""
Estrategia de tendencia optimizada: 
Combina cruces de medias normalizados por ATR, histograma y pendiente del MACD,
y confirmación direccional de tendencia.
Devuelve un score continuo [-1, 1] representativo de la fuerza de la tendencia.
"""
import numpy as np


def signal(row) -> float:
    score = 0.0
    weights_used = 0.0

    close = row.get("close", 0.0)
    atr = row.get("atr", None)

    # Si no tenemos ATR disponible, usamos un 1% del precio como fallback
    volatility_scale = atr if (atr is not None and not np.isnan(atr) and atr > 0) else (close * 0.01)

    # 1. Cruce / Distancia de EMA (Normalizado por la volatilidad real del activo - ATR)
    ema_cross = row.get("ema_cross", np.nan)
    if not np.isnan(ema_cross):
        # Mapea la distancia en múltiplos de ATR a la curva [-1, 1]
        ema_signal = np.tanh(ema_cross / volatility_scale)
        score += ema_signal * 1.2  # Le damos mayor peso a la EMA por ser más reactiva
        weights_used += 1.2

    # 2. Cruce de SMA (Soporte tendencial de mayor plazo)
    sma_cross = row.get("sma_cross", np.nan)
    if not np.isnan(sma_cross):
        sma_signal = np.tanh(sma_cross / (volatility_scale * 1.5))
        score += sma_signal * 0.8
        weights_used += 0.8

    # 3. MACD Histograma y su Impulso
    macd_diff = row.get("macd_diff", np.nan)
    if not np.isnan(macd_diff):
        # Normalizado por la volatilidad del activo
        macd_signal = np.tanh(macd_diff / (volatility_scale * 0.5))
        score += macd_signal * 1.0
        weights_used += 1.0

    # 4. Confirmación de Volumen / Momentum (RSI / OBV slope si existen)
    rsi = row.get("rsi", np.nan)
    if not np.isnan(rsi):
        # Modificador de momentum: impulsa si RSI apoya la tendencia (entre 50 y 70 para LONG, 30 y 50 para SHORT)
        rsi_momentum = (rsi - 50.0) / 20.0  # Mapea 30->-1, 50->0, 70->1
        score += np.clip(rsi_momentum, -1.0, 1.0) * 0.5
        weights_used += 0.5

    if weights_used == 0:
        return 0.0

    final_score = score / weights_used
    return float(np.clip(final_score, -1.0, 1.0))
