"""
Módulo de Indicadores Técnicos (indicators/technical.py).
Calcula indicadores clave (EMA, ATR, RSI) sobre el DataFrame de velas.
"""
import pandas as pd
import numpy as np


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Enriquece el DataFrame con indicadores para el ensamble de estrategias."""
    if df.empty or len(df) < 14:
        return df

    df = df.copy()

    # 1. Medias Móviles Exponenciales (EMA)
    df["ema_fast"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema_trend"] = df["close"].ewm(span=200, adjust=False).mean()

    # 2. Average True Range (ATR) para la gestión de riesgo
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = tr.rolling(window=14).mean()

    # 3. Relative Strength Index (RSI)
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    
    rs = gain / (loss + 1e-9)
    df["rsi"] = 100 - (100 / (1 + rs))

    return df
