"""
Módulo para conectarse a la API de Binance y obtener datos de velas (K-lines).
Incluye bypass automático de restricciones de ubicación por IP de servidor.
"""
import logging
import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException
import config

logger = logging.getLogger("data_fetcher")


def get_client() -> Client:
    """
    Inicializa y retorna el cliente de Binance configurado.
    Redirige las llamadas a dominios alternativos si detecta restricción regional.
    """
    client = Client(
        config.BINANCE_API_KEY,
        config.BINANCE_API_SECRET,
        requests_params={"timeout": 10}
    )

    # Forzar el uso de los endpoints alternativos de Binance para evitar bloqueos por IP de servidores en EE. UU.
    client.API_URL = "https://api1.binance.com/api"

    try:
        # Verificación rápida de conexión
        client.ping()
    except BinanceAPIException as e:
        if "restricted location" in str(e).lower():
            logger.warning("Conexión principal restringida por región. Cambiando a endpoint secundario api3.binance.com...")
            client.API_URL = "https://api3.binance.com/api"
            client.ping()
        else:
            raise e

    return client


def fetch_klines(client: Client, symbol: str, interval: str = None, limit: int = None) -> pd.DataFrame:
    """
    Obtiene velas históricas para un par dado y retorna un DataFrame procesado.
    """
    if interval is None:
        interval = config.TIMEFRAME
    if limit is None:
        limit = config.LIMIT_KLINES

    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)

    columns = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
    ]

    df = pd.DataFrame(klines, columns=columns)

    # Convertir columnas numéricas de texto a float
    numeric_cols = ["open", "high", "low", "close", "volume"]
    df[numeric_cols] = df[numeric_cols].astype(float)

    # Convertir timestamp a datetime
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df.set_index("open_time", inplace=True)

    return df
