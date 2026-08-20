"""
Estrategia de tendencia: combina cruce de medias (SMA/EMA) con MACD.
Devuelve una señal continua entre -1 (bajista fuerte) y 1 (alcista fuerte),
no una decisión binaria — así se puede combinar mejor en el ensemble.
"""
import numpy as np


def signal(row) -> float:
    score = 0.0
    weights_used = 0.0

    # Cruce de SMA
    if not np.isnan(row.get("sma_cross", np.nan)):
        sma_signal = np.tanh(row["sma_cross"] / (row["close"] * 0.01))  # normalizado
        score += sma_signal
        weights_used += 1

    # Cruce de EMA
    if not np.isnan(row.get("ema_cross", np.nan)):
        ema_signal = np.tanh(row["ema_cross"] / (row["close"] * 0.01))
        score += ema_signal
        weights_used += 1

    # MACD histograma
    if not np.isnan(row.get("macd_diff", np.nan)):
        macd_signal = np.tanh(row["macd_diff"] / (row["close"] * 0.005))
        score += macd_signal
        weights_used += 1

    if weights_used == 0:
        return 0.0

    return float(np.clip(score / weights_used, -1, 1))
