"""
Estrategia de reversión a la media optimizada:
Filtra el "ruido" alrededor de la media usando funciones no lineales (tanh) 
para que la señal solo sea fuerte en verdaderos extremos de volatilidad/sobrecompra.
Devuelve un score continuo [-1, 1].
"""
import numpy as np

def signal(row) -> float:
    score = 0.0
    weights_used = 0.0

    # 1. RSI (Índice de Fuerza Relativa)
    rsi = row.get("rsi", np.nan)
    if not np.isnan(rsi):
        # Mapeo no lineal: divisor 12 aplana la curva en el centro.
        # RSI = 50 -> tanh(0) = 0.00 (Neutral)
        # RSI = 30 -> tanh(20/12) = tanh(1.66) = +0.93 (Alcista Fuerte)
        # RSI = 70 -> tanh(-20/12) = tanh(-1.66) = -0.93 (Bajista Fuerte)
        rsi_signal = np.tanh((50 - rsi) / 12.0)
        score += rsi_signal * 1.0
        weights_used += 1.0

    # 2. Porcentaje de Bandas de Bollinger (BB Pct)
    bb_pct = row.get("bb_pct", np.nan)
    if not np.isnan(bb_pct):
        # Mapeo no lineal: multiplicador 4 acentúa los extremos.
        # bb_pct = 0.50 (banda media) -> tanh(0) = 0.00
        # bb_pct = 0.00 (banda inferior) -> tanh(0.5 * 4) = +0.96 (Alcista Fuerte)
        # bb_pct = 1.00 (banda superior) -> tanh(-0.5 * 4) = -0.96 (Bajista Fuerte)
        # bb_pct = 1.20 (rotura por encima) -> tanh(-0.7 * 4) = -0.99 (Reversión Inminente)
        bb_signal = np.tanh((0.5 - bb_pct) * 4.0)
        
        # Le damos más peso a las BB porque se adaptan a la volatilidad del mercado
        score += bb_signal * 1.5 
        weights_used += 1.5

    if weights_used == 0:
        return 0.0

    final_score = score / weights_used

    # 3. Zona muerta (Deadzone Penalty)
    # Si la señal combinada es mediocre (ej. menor a 0.3), le quitamos fuerza 
    # para evitar que el Ensemble tome trades aburridos en zonas sin confirmación.
    if abs(final_score) < 0.3:
        final_score *= 0.3  # Reduce drásticamente el score

    return float(np.clip(final_score, -1.0, 1.0))
