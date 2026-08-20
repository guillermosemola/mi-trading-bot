"""
Construye features técnicos a partir de OHLCV para alimentar tanto
las estrategias basadas en reglas como el modelo ML.
"""
import numpy as np
import pandas as pd
import ta

import config


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Recibe OHLCV, devuelve el mismo DataFrame con columnas de features agregadas.
    No modifica el original.
    """
    out = df.copy()

    # Medias móviles
    out["sma_fast"] = ta.trend.sma_indicator(out["close"], window=10)
    out["sma_slow"] = ta.trend.sma_indicator(out["close"], window=50)
    out["ema_fast"] = ta.trend.ema_indicator(out["close"], window=12)
    out["ema_slow"] = ta.trend.ema_indicator(out["close"], window=26)

    # Momentum
    out["rsi"] = ta.momentum.rsi(out["close"], window=14)
    macd = ta.trend.MACD(out["close"])
    out["macd"] = macd.macd()
    out["macd_signal"] = macd.macd_signal()
    out["macd_diff"] = macd.macd_diff()

    # Volatilidad
    bb = ta.volatility.BollingerBands(out["close"], window=20, window_dev=2)
    out["bb_high"] = bb.bollinger_hband()
    out["bb_low"] = bb.bollinger_lband()
    out["bb_pct"] = bb.bollinger_pband()  # posición del precio dentro de la banda (0..1)
    out["atr"] = ta.volatility.average_true_range(out["high"], out["low"], out["close"], window=14)

    # Volumen
    out["volume_sma"] = out["volume"].rolling(20).mean()
    out["volume_ratio"] = out["volume"] / out["volume_sma"]

    # Retornos
    out["return_1"] = out["close"].pct_change(1)
    out["return_5"] = out["close"].pct_change(5)

    # Derivadas
    out["sma_cross"] = out["sma_fast"] - out["sma_slow"]
    out["ema_cross"] = out["ema_fast"] - out["ema_slow"]

    return out


def build_ml_dataset(df_features: pd.DataFrame, horizon: int = None):
    """
    Construye X, y para entrenamiento supervisado.
    y = 1 si el retorno a `horizon` velas es positivo, 0 si no.
    """
    horizon = horizon or config.ML_PREDICTION_HORIZON
    data = df_features.copy()
    data["future_return"] = data["close"].shift(-horizon) / data["close"] - 1
    data["target"] = (data["future_return"] > 0).astype(int)

    feature_cols = [
        "sma_cross", "ema_cross", "rsi", "macd", "macd_signal", "macd_diff",
        "bb_pct", "atr", "volume_ratio", "return_1", "return_5",
    ]
    data = data.dropna(subset=feature_cols + ["target"])
    X = data[feature_cols]
    y = data["target"]
    return X, y, feature_cols
def add_features(df):
    # ... otros indicadores (RSI, SMA, etc.) ...
    
    # Cálculo de ATR (14 periodos)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pandas.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()
    
    return df
def add_adx(df, window=14):
    df = df.copy()
    df['up_move'] = df['high'] - df['high'].shift(1)
    df['down_move'] = df['low'].shift(1) - df['low']
    
    df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0.0)
    df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0.0)
    
    # True Range ya calculado para el ATR
    tr = df['atr'] * window # o recalculado si no lo tienes a mano
    
    plus_di = 100 * (df['plus_dm'].ewm(alpha=1/window).mean() / df['atr'])
    minus_di = 100 * (df['minus_dm'].ewm(alpha=1/window).mean() / df['atr'])
    
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
    df['adx'] = dx.ewm(alpha=1/window).mean()
    return df
