"""
Módulo de Alimentación de Datos (data/live_feed.py).
Gestiona la descarga de historiales y la conexión en vivo con Binance.
"""
import os
import logging
import pandas as pd
from binance.client import Client  # <--- ESTA ES LA LÍNEA QUE FALTABA
from strategies.indicators.technical import add_technical_indicators

logger = logging.getLogger(__name__)

class LiveDataFeed:
    def __init__(self, symbol: str, interval: str = "1m"):
        self.symbol = symbol.upper()
        self.interval = interval
        
        # Cargar credenciales desde variables de entorno
        api_key = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_API_SECRET", "")
        
        # Inicializar el cliente REST de Binance para historiales
        self.rest_client = Client(api_key, api_secret)

    def fetch_historical_klines(self) -> pd.DataFrame:
        """Descarga el historial reciente de velas para calcular los indicadores iniciales."""
        try:
            klines = self.rest_client.get_klines(
                symbol=self.symbol,
                interval=self.interval,
                limit=100
            )
            
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'get_buy_quote_volume', 'ignore'
            ])
            
            # Convertir tipos de datos a numéricos
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Aplicar indicadores técnicos
            df = add_technical_indicators(df)
            return df
            
        except Exception as e:
            logger.error(f"[{self.symbol}] Error al obtener klines historicas: {e}")
            return pd.DataFrame()
