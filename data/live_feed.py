"""
Módulo de Ingesta de Datos en Vivo (data/live_feed.py).
Combina REST API para precargar historial y WebSockets de Binance
para recibir klines en tiempo real con latencia mínima.
"""
import logging
import asyncio
import pandas as pd
from binance.client import Client
from binance.async_client import AsyncClient
from binance.ws.spot_web_socket_api import SpotWebSocketAPIClient

import config

logger = logging.getLogger(__name__)


class LiveDataFeed:
    def __init__(self, symbol: str = "BTCUSDT", interval: str = "1m", limit_history: int = 200):
        self.symbol = symbol.upper()
        self.interval = interval
        self.limit_history = limit_history
        self.df = pd.DataFrame()
        
        # Cliente REST para descarga inicial
        api_key = getattr(config, "BINANCE_API_KEY", "")
        api_secret = getattr(config, "BINANCE_API_SECRET", "")
        self.rest_client = Client(api_key, api_secret)

    def fetch_historical_klines((self) -> pd.DataFrame:
        """Descarga velas históricas vía REST API para inicializar indicadores."""
        logger.info(f"Descargando últimas {self.limit_history} velas ({self.interval}) para {self.symbol}...")
        try:
            klines = self.rest_client.get_klines(
                symbol=self.symbol,
                interval=self.interval,
                limit=self.limit_history
            )
            data = []
            for k in klines:
                data.append({
                    "timestamp": pd.to_datetime(k[0], unit="ms"),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5])
                })
            
            self.df = pd.DataFrame(data)
            logger.info(f"Historial cargado con éxito. Último precio de cierre: {self.df['close'].iloc[-1]:.2f}")
            return self.df
        except Exception as e:
            logger.error(f"Error al descargar historial vía REST API: {e}")
            return pd.DataFrame()

    def update_candle_from_ws(self, kline_data: dict) -> tuple[pd.DataFrame, bool]:
        """
        Procesa el payload recibido por WebSocket.
        Retorna la estructura de datos actualizada y un flag que indica si la vela ya cerró.
        """
        k = kline_data.get("k", {})
        is_candle_closed = k.get("x", False) # 'x' es True cuando la vela ha finalizado

        candle_timestamp = pd.to_datetime(k.get("t"), unit="ms")
        new_row = {
            "timestamp": candle_timestamp,
            "open": float(k.get("o", 0)),
            "high": float(k.get("h", 0)),
            "low": float(k.get("l", 0)),
            "close": float(k.get("c", 0)),
            "volume": float(k.get("v", 0))
        }

        # Actualizar la última vela en progreso o agregar una nueva si cerró la previa
        if not self.df.empty and self.df.iloc[-1]["timestamp"] == candle_timestamp:
            self.df.iloc[-1] = new_row
        else:
            self.df = pd.concat([self.df, pd.DataFrame([new_row])], ignore_index=True)
            if len(self.df) > self.limit_history:
                self.df = self.df.iloc[-self.limit_history:].reset_index(drop=True)

        return self.df, is_candle_closed
