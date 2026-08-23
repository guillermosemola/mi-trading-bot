"""
Escuchador Asíncrono de Stream Combinado (data/ws_listener.py).
Mantiene una única conexión WebSocket estable para múltiples símbolos en Binance.
"""
import asyncio
import json
import logging
import websockets
from data.live_feed import LiveDataFeed
from indicators.technical import add_technical_indicators

logger = logging.getLogger(__name__)


async def start_multi_stream(bot_instance, symbols: list, interval: str = "1m"):
    """
    Abre una única conexión WebSocket combinada para todos los símbolos configurados.
    """
    # 1. Inicializar los feeds de datos históricos para cada símbolo
    feeds = {symbol.upper(): LiveDataFeed(symbol=symbol, interval=interval) for symbol in symbols}

    # 2. Construir la URL del Combined Stream
    streams_str = "/".join([f"{s.lower()}@kline_{interval}" for s in symbols])
    ws_url = f"wss://stream.binance.com:9443/stream?streams={streams_str}"

    while True:
        try:
            logger.info(f"Conectando al Stream Combinado de Binance para {len(symbols)} activos...")
            
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                logger.info("🟢 Stream Combinado conectado exitosamente.")
                
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    
                    payload = data.get("data", {})
                    if not payload:
                        continue
                        
                    kline = payload.get("k", {})
                    if not kline:
                        continue
                        
                    symbol = payload.get("s", "").upper()
                    is_closed = kline.get("x", False)
                    
                    if symbol in feeds:
                        updated_df = feeds[symbol].update_candle_from_ws(payload)
                        
                        if is_closed and not updated_df.empty:
                            current_row = updated_df.iloc[-1]
                            bot_instance.evaluate_market(symbol, current_row)

        except websockets.exceptions.ConnectionClosedError as e:
            logger.warning(f"⚠️ Stream Combinado cerrado ({e}). Reconectando en 5 segundos...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"❌ Error en Stream Combinado: {e}. Reconectando en 5 segundos...")
            await asyncio.sleep(5)
