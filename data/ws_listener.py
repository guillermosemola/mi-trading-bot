1	"""
     2	Escuchador Asíncrono Multi-Símbolo (data/ws_listener.py).
     3	Mantiene conexiones estables con ping/pong y reconexión automática.
     4	"""
     5	import asyncio
     6	import json
     7	import logging
     8	import websockets
     9	from data.live_feed import LiveDataFeed
    10	from indicators.technical import add_technical_indicators
    11	
    12	logger = logging.getLogger(__name__)
    13	
    14	
    15	async def listen_single_symbol(bot_instance, symbol: str, interval: str = "1m"):
    16	    """Mantiene la conexión WebSocket estable para un único activo con reconexión automática."""
    17	    feed = LiveDataFeed(symbol=symbol, interval=interval)
    18	    ws_url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@kline_{interval}"
    19	
    20	    while True:
    21	        try:
    22	            logger.info(f"Conectando WebSocket para [{symbol}]...")
    23	            # Configuramos ping_interval y ping_timeout para evitar el error de timeout
    24	            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
    25	                logger.info(f"🟢 Stream de [{symbol}] conectado exitosamente.")
    26	                
    27	                while True:
    28	                    message = await ws.recv()
    29	                    data = json.loads(message)
    30	                    
    31	                    # Actualizar la vela en el feed
    32	                    updated_df = feed.update_candle_from_ws(data)
    33	                    
    34	                    if not updated_df.empty:
    35	                        # Validar si la última vela cerró
    36	                        kline = data.get('k', {})
    37	                        is_closed = kline.get('x', False)
    38	                        
    39	                        if is_closed:
    40	                            current_row = updated_df.iloc[-1]
    41	                            bot_instance.evaluate_market(symbol, current_row)
    42	
    43	        websockets.exceptions.ConnectionClosedError as e:
    44	            logger.warning(f"⚠️ Conexión cerrada para [{symbol}] ({e}). Reconectando en 5 segundos...")
    45	            await asyncio.sleep(5)
    46	        except Exception as e:
    47	            logger.error(f"❌ Error en WebSocket [{symbol}]: {e}. Reconectando en 5 segundos...")
    48	            await asyncio.sleep(5)
    49	
    50	
    51	async def start_multi_stream(bot_instance, symbols: list, interval: str = "1m"):
    52	    """Lanza en paralelo los procesos de escucha para todas las criptos."""
    53	    tasks = [
    54	        listen_single_symbol(bot_instance, symbol, interval)
    55	        for symbol in symbols
    56	    ]
    57	    await asyncio.gather(*tasks)
