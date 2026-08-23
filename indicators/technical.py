=== 3. indicators/technical.py ===
"""
Módulo de Indicadores Técnicos (indicators/technical.py).
Calcula el set completo de indicadores que consume el motor de estrategias
(strategies/ensemble.py, trend_following.py, mean_reversion.py) sobre el
DataFrame de velas en vivo.

Usa la librería `ta`, la misma que usa features/feature_engineering.py en el
backtester, para que la señal en vivo y la que se valida en backtest sean
consistentes.
"""
import pandas as pd
import numpy as np
import ta


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Enriquece el DataFrame con todos los indicadores que necesita el ensemble."""
    # ADX/MACD/Bollinger necesitan más historial que el viejo mínimo de 14 velas
    if df.empty or len(df) < 50:
        return df

    df = df.copy()

    # 1. Medias móviles (para cruces normalizados por ATR)
    df["sma_fast"] = ta.trend.sma_indicator(df["close"], window=10)
    df["sma_slow"] = ta.trend.sma_indicator(df["close"], window=50)
    df["ema_fast"] = ta.trend.ema_indicator(df["close"], window=12)
    df["ema_slow"] = ta.trend.ema_indicator(df["close"], window=26)
    df["ema_trend"] = df["close"].ewm(span=200, adjust=False).mean()

    # Distancias entre medias (las usa strategies/trend_following.py)
    df["sma_cross"] = df["sma_fast"] - df["sma_slow"]
    df["ema_cross"] = df["ema_fast"] - df["ema_slow"]

    # 2. Momentum
    df["rsi"] = ta.momentum.rsi(df["close"], window=14)
    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_diff"] = macd.macd_diff()

    # 3. Volatilidad (ATR para riesgo, Bollinger para reversión a la media)
    bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["bb_high"] = bb.bollinger_hband()
    df["bb_low"] = bb.bollinger_lband()
    df["bb_pct"] = bb.bollinger_pband()
    df["atr"] = ta.volatility.average_true_range(df["high"], df["low"], df["close"], window=14)

    # 4. Fuerza de tendencia (filtro de régimen del ensemble: trend vs mean-reversion)
    df["adx"] = ta.trend.adx(df["high"], df["low"], df["close"], window=14)

    return df

Mostrar data/live_feed.py final
Resumen de qué pegar dónde (los 4 archivos de arriba, contenido completo, reemplazando cada uno entero):

Archivo	Qué arregla
app.py	Logging visible + conecta el cliente real de Binance
main.py	Usa el ensemble completo (tendencia+reversión+ADX) en vez de la señal binaria
indicators/technical.py	Calcula MACD, Bollinger, ADX, cruces — todo lo que el ensemble necesita
data/live_feed.py	Arregla el bug de la tupla que rompía cada mensaje del websocket
data/ws_listener.py no lo toqués, ya es compatible.

Pegalos los 4 en una sola tanda (con el lápiz ✏️, uno por uno, "Commit changes" en cada uno) antes de que dispares el deploy final — si Render hace un deploy a mitad de camino con solo alguno de los 4 actualizado, puede volver a romperse por incompatibilidad entre archivos, como pasó recién. Avisame cuando termines los 4 y reviso el deploy y los primeros logs en tiempo real.



