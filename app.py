Servidor Web para mantener vivo el bot en Render (app.py)
"""
import logging
import threading
import asyncio
from flask import Flask
import config

from main import TradingBot
from data.ws_listener import start_multi_stream
from binance.client import Client

# --- Logging: sin esto, todos los logger.info(...) del bot quedan mudos ---
logging.basicConfig(
    level=getattr(logging, str(config.LOG_LEVEL).upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route('/')
def health_check():
    return "🚀 El Bot de Trading Multi-Activo está funcionando correctamente."


def build_binance_client():
    """
    Crea el cliente REAL de Binance (mainnet o testnet según config.USE_TESTNET).
    Si faltan credenciales, devuelve None y el bot cae en modo simulación forzada
    (OrderManager trata client=None igual que DRY_RUN=true, ver execution/order_manager.py).
    """
    if not config.BINANCE_API_KEY or not config.BINANCE_API_SECRET:
        logger.error(
            "Faltan BINANCE_API_KEY / BINANCE_API_SECRET en las variables de entorno. "
            "El bot va a correr SIN cliente real (simulación forzada, no manda órdenes)."
        )
        return None

    try:
        # Client() hace ping automáticamente al crearse (ping=True por defecto):
        # si las credenciales son inválidas, esto tira excepción acá mismo.
        client = Client(
            config.BINANCE_API_KEY,
            config.BINANCE_API_SECRET,
            testnet=config.USE_TESTNET,
        )
        account_type = "TESTNET (dinero ficticio)" if config.USE_TESTNET else "MAINNET (⚠️ DINERO REAL)"
        logger.info(f"✅ Cliente de Binance conectado correctamente en modo {account_type}.")
        return client
    except Exception as e:
        logger.error(f"❌ No se pudo conectar el cliente de Binance: {e}")
        return None


def run_trading_bot():
    """Corre el bot en un hilo separado con su propio loop asíncrono."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    client = build_binance_client()
    bot = TradingBot(client=client)

    loop.run_until_complete(
        start_multi_stream(bot_instance=bot, symbols=config.SYMBOLS, interval=config.TIMEFRAME)
    )


if __name__ == '__main__':
    mode = "SIMULACIÓN (DRY_RUN=true)" if config.DRY_RUN else "⚠️ OPERANDO CON DINERO REAL (DRY_RUN=false)"
    net = "TESTNET" if config.USE_TESTNET else "MAINNET"
    logger.info(f"Arrancando bot | Modo: {mode} | Red: {net} | Símbolos: {', '.join(config.SYMBOLS)}")

    bot_thread = threading.Thread(target=run_trading_bot, daemon=True)
    bot_thread.start()

    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
