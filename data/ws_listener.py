"""
Escuchador Asíncrono WebSocket (data/ws_listener.py).
Mantiene la conexión abierta y notifica al bot en cada cierre de vela.
"""
import asyncio
import json
import logging
import websockets
from data.live_feed import LiveDataFeed

logger = logging.getLogger(__name__)


async def start_kline_stream(bot_instance, symbol: str = "btcusdt", interval: str = "1m"):
    """Conecta al WebSocket de Binance Stream y pasa las velas al bot."""
    feed = LiveDataFeed(symbol=symbol.upper(), interval=interval)
    
    # 1. Cargar historial base
    feed.fetch_historical_klines()

    ws_url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@kline_{interval}"
    logger.info(f"Conectando a WebSocket: {ws_url}...")

    async with websockets.connect(ws_url) as ws:
        logger.info("🟢 WebSocket conectado exitosamente.")
        while True:
            try:
                message = await ws.recv()
                data = json.loads(message)
                
                # Actualizar Dataframe con el mensaje
                updated_df, is_closed = feed.update_candle_from_ws(data)
                
                # Evaluar mercado solo al cierre definitivo de la vela (evita falso ruido)
                if is_closed:
                    logger.info(f"📍 Vela {interval} cerrada. Evaluando estrategia...")
                    # Calcular indicadores en el DF antes de evaluar
                    # (aquí puedes invocar tus funciones de indicadores)
                    current_row = updated_df.iloc[-1]
                    bot_instance.evaluate_market(current_row)

            except Exception as e:
                logger.error(f"Error en recepción WebSocket: {e}")
                await asyncio.sleep(5)  # Reintento de reconexión
