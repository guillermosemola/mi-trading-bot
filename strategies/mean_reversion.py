"""
Estrategia de reversión a la media: usa RSI y posición dentro de
las bandas de Bollinger. Señal alcista cuando el precio está
"sobrevendido", bajista cuando está "sobrecomprado".
Igual que trend_following, devuelve un score continuo -1..1.
"""
import numpy as np


def signal(row) -> float:
    score = 0.0
    weights_used = 0.0

    rsi = row.get("rsi", np.nan)
    if not np.isnan(rsi):
        # RSI < 30 -> señal alcista (comprar), RSI > 70 -> señal bajista (vender)
        rsi_signal = (50 - rsi) / 50  # rango aprox -1..1
        score += np.clip(rsi_signal, -1, 1)
        weights_used += 1

    bb_pct = row.get("bb_pct", np.nan)
    if not np.isnan(bb_pct):
        # bb_pct cerca de 0 -> precio en banda baja -> alcista
        # bb_pct cerca de 1 -> precio en banda alta -> bajista
        bb_signal = (0.5 - bb_pct) * 2
        score += np.clip(bb_signal, -1, 1)
        weights_used += 1

    if weights_used == 0:
        return 0.0

    return float(np.clip(score / weights_used, -1, 1))
