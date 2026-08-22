"""
Escuchador Asíncrono Multi-Símbolo (data/ws_listener.py).
Mantiene conexiones paralelas para notificar al bot en cada cierre de vela.
"""
import asyncio
import json
import logging
import websockets
from data.live_feed import LiveDataFeed
from indicators.technical import add_technical_indicators

logger = logging.getLogger(__name__)


async def listen_single_symbol(bot_instance, symbol: str, interval: str = "1h"):
    """Mantiene la conexión WebSocket independiente para un único activo."""
    feed = LiveDataFeed(symbol=symbol, interval=interval)
    feed.fetch_historical_klines()

    ws_url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@kline_{interval}"
    logger.info(f"Conectando WebSocket para [{symbol}]...")

    async with websockets.connect(ws_url) as ws:
        logger.info(f"🟢 Stream de [{symbol}] conectado.")
        while True:
            try:
                message = await ws.recv()
                data = json.loads(message)
                
                updated_df, is_closed = feed.update_candle_from_ws(data)
                
                if is_closed:
                    df_with_indicators = add_technical_indicators(updated_df)
                    current_row = df_with_indicators.iloc[-1]
                    # Envía la vela indicando qué símbolo es
                    bot_instance.evaluate_market(symbol, current_row)

            except Exception as e:
                logger.error(f"Error en WebSocket [{symbol}]: {e}")
                await asyncio.sleep(5)


async def start_multi_stream(bot_instance, symbols: list, interval: str = "1h"):
    """Lanza en paralelo los procesos de escucha para todas las criptos."""
    tasks = [
        listen_single_symbol(bot_instance, symbol, interval)
        for symbol in symbols
    ]
    await asyncio.gather(*tasks)
