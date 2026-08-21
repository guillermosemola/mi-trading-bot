import logging
import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException
import config

logger = logging.getLogger(__name__)


def get_client() -> Client:
    """Inicializa y retorna el cliente oficial de Binance utilizando las claves de configuración."""
    try:
        client = Client(
            config.BINANCE_API_KEY,
            config.BINANCE_API_SECRET,
            requests_params={"timeout": 10},
        )
        return client
    except Exception as e:
        logger.error(f"Error al inicializar el cliente de Binance: {e}")
        raise


def fetch_klines(
    client: Client, symbol: str, interval: str, limit: int = 200
) -> pd.DataFrame:
    """Obtiene las velas (klines) de Binance para un par e intervalo dado.

    Retorna un DataFrame de Pandas estructurado.
    """
    try:
        raw_klines = client.get_klines(
            symbol=symbol, interval=interval, limit=limit
        )

        # Estructurar los datos devueltos por la API de Binance
        columns = [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume",
            "ignore",
        ]

        df = pd.DataFrame(raw_klines, columns=columns)

        # Convertir tipos de datos a numéricos
        numeric_columns = ["open", "high", "low", "close", "volume"]
        df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, axis=1)

        # Convertir timestamp a formato datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        return df[["timestamp", "open", "high", "low", "close", "volume"]]

    except BinanceAPIException as e:
        logger.error(
            f"Error de API de Binance al obtener klines para {symbol}: {e}"
        )
        return pd.DataFrame()
    except Exception as e:
        logger.error(
            f"Error inesperado al procesar klines para {symbol}: {e}"
        )
        return pd.DataFrame()


def get_account_balance(client: Client, asset: str = "USDT") -> float:
    """Obtiene el balance disponible para un activo específico (por defecto USDT)."""
    try:
        balance_info = client.get_asset_balance(asset=asset)
        if balance_info and "free" in balance_info:
            return float(balance_info["free"])
        return 0.0
    except Exception as e:
        logger.error(f"Error al consultar balance de {asset}: {e}")
        return 0.0
