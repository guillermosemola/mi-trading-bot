"""
Módulo de Alimentación de Datos (data/live_feed.py).
Gestiona la descarga de historiales y la conexión en vivo con Binance.
"""
import os
import logging
import pandas as pd
from binance.client import Client
from indicators.technical import add_technical_indicators

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
        self.df = self.fetch_historical_klines()

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
            
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            df = add_technical_indicators(df)
            return df
            
        except Exception as e:
            logger.error(f"[{self.symbol}] Error al obtener klines historicas: {e}")
            return pd.DataFrame()

    def update_candle_from_ws(self, kline_data: dict):
        """
        Actualiza el DataFrame interno con los datos de la vela del WebSocket.
        Devuelve una tupla: (DataFrame actualizado, booleano indicando si la vela cerró).
        """
        try:
            kline = kline_data.get('k', {})
            open_time = pd.to_datetime(kline.get('t'), unit='ms')
            o = float(kline.get('o', 0))
            h = float(kline.get('h', 0))
            l = float(kline.get('l', 0))
            c = float(kline.get('c', 0))
            v = float(kline.get('v', 0))
            is_closed = kline.get('x', False)

            if self.df.empty:
                return self.df, is_closed

            if self.df.iloc[-1]['timestamp'] == open_time:
                self.df.loc[self.df.index[-1], ['open', 'high', 'low', 'close', 'volume']] = [o, h, l, c, v]
            elif is_closed:
                new_row = pd.DataFrame([{
                    'timestamp': open_time, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v
                }])
                self.df = pd.concat([self.df, new_row], ignore_index=True)

            self.df = add_technical_indicators(self.df)
            return self.df, is_closed
            
        except Exception as e:
            logger.error(f"[{self.symbol}] Error actualizando vela desde WS: {e}")
            return self.df, False
