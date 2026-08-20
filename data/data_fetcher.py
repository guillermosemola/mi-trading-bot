"""
Módulo de conexión con Binance API.
Descarga datos históricos (klines) y aplica corrección automática 
de desfasaje de reloj (timestamp sync).
"""
import time
import logging
import pandas as pd
from binance.client import Client
import config

logger = logging.getLogger(__name__)


def get_client() -> Client:
    """Inicializa y devuelve el cliente de Binance con sincronización nativa de tiempo."""
    if config.USE_TESTNET:
        client = Client(config.BINANCE_API_KEY, config.BINANCE_API_SECRET, testnet=True)
    else:
       client = Client(
    config.BINANCE_API_KEY,
    config.BINANCE_API_SECRET,
    requests_params={"timeout": 10}
)
# Redirigir llamadas de API a endpoints globales no bloqueados
client.API_URL = 'https://api1.binance.com/api'

    # 1. Ampliar la ventana de recepción a 60 segundos
    client.RECV_WINDOW = 60000

    # 2. Sincronizar el reloj y aplicar el desfase nativo en python-binance
    try:
        res = client.get_server_time()
        server_time = res["serverTime"]
        local_time = int(time.time() * 1000)
        offset = server_time - local_time
        
        # Asignar el offset en las dos propiedades donde la librería lo requiere
        client.TIME_OFFSET = offset
        client.timestamp_offset = offset
        
        logger.info(
            "Reloj sincronizado con Binance. Offset local vs servidor: %d ms",
            offset,
        )
    except Exception as e:
        logger.warning("No se pudo sincronizar el tiempo automáticamente: %s", e)

    return client


def fetch_klines(client: Client, symbol: str, interval: str = None, limit: int = None) -> pd.DataFrame:
    """Descarga velas de Binance y las devuelve en formato pandas DataFrame."""
    if interval is None:
        interval = config.TIMEFRAME
    if limit is None:
        limit = config.LOOKBACK_CANDLES

    raw_klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)

    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
    ]
    df = pd.DataFrame(raw_klines, columns=cols)

    # Convertir tipos numéricos
    numeric_cols = ["open", "high", "low", "close", "volume"]
    for col in numeric_cols:
        df[col] = df[col].astype(float)

    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
    
    return df
