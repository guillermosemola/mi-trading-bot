"""
Escuchador Asíncrono Multi-Símbolo (data/ws_listener.py).
Mantiene conexiones estables con ping/pong y reconexión automática.
"""
import asyncio
import json
import logging
import websockets
from data.live_feed import LiveDataFeed
from indicators.technical import add_technical_indicators

logger = logging.getLogger(__name__)


async def listen_single_symbol(bot_instance, symbol: str, interval: str = "1m"):
    """Mantiene la conexión WebSocket estable para un único activo con reconexión automática."""
    feed = LiveDataFeed(symbol=symbol, interval=interval)
    ws_url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@kline_{interval}"

    while True:
        try:
            logger.info(f"Conectando WebSocket para [{symbol}]...")
            # Configuramos ping_interval y ping_timeout para evitar el error de timeout
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                logger.info(f"🟢 Stream de [{symbol}] conectado exitosamente.")
                
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    
                    # Actualizar la vela en el feed
                    updated_df = feed.update_candle_from_ws(data)
                    
                    if not updated_df.empty:
                        # Validar si la última vela cerró
                        kline = data.get('k', {})
                        is_closed = kline.get('x', False)
                        
                        if is_closed:
                            current_row = updated_df.iloc[-1]
                            bot_instance.evaluate_market(symbol, current_row)

        websockets.exceptions.ConnectionClosedError as e:
            logger.warning(f"⚠️ Conexión cerrada para [{symbol}] ({e}). Reconectando en 5 segundos...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"❌ Error en WebSocket [{symbol}]: {e}. Reconectando en 5 segundos...")
            await asyncio.sleep(5)


async def start_multi_stream(bot_instance, symbols: list, interval: str = "1m"):
    """Lanza en paralelo los procesos de escucha para todas las criptos."""
    tasks = [
        listen_single_symbol(bot_instance, symbol, interval)
        for symbol in symbols
    ]
    await asyncio.gather(*tasks)
