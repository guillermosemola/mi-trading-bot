"""
Servidor Web para mantener vivo el bot en Render (app.py)
"""
import threading
import asyncio
from flask import Flask
import config

# Importamos tu bot y el listener
from main import TradingBot
from data.ws_listener import start_multi_stream

app = Flask(__name__)

@app.route('/')
def health_check():
    return "🚀 El Bot de Trading Multi-Activo está funcionando correctamente."

def run_trading_bot():
    """Esta función correrá el bot en un hilo separado con su propio loop asíncrono."""
    # Crear un nuevo event loop para este hilo
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    bot = TradingBot()
    
    # Arrancar la escucha de todas las criptos
    loop.run_until_complete(
        start_multi_stream(bot_instance=bot, symbols=config.SYMBOLS, interval=config.TIMEFRAME)
    )

if __name__ == '__main__':
    # 1. Iniciar el bot en segundo plano (daemon=True hace que se cierre si Flask se cierra)
    bot_thread = threading.Thread(target=run_trading_bot, daemon=True)
    bot_thread.start()
    
    # 2. Iniciar el servidor web en el puerto que Render necesita (por defecto 10000)
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
