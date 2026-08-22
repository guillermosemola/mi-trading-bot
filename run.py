"""
Script de Arranque Principal del Bot de Trading (run.py).
Inicia el bot multi-activo y conecta las transmisiones WebSocket en paralelo.
"""
import asyncio
import logging
import config
from main import TradingBot
from data.ws_listener import start_multi_stream

# Configuración básica de registros (Logs)
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    ]
)

logger = logging.getLogger("Runner")


async def main():
    logger.info("Iniciando Bot Multi-Activo...")
    
    # 1. Instanciar el bot principal
    bot = TradingBot()
    
    # 2. Iniciar la escucha simultánea para todas las criptos del config.py
    await start_multi_stream(
        bot_instance=bot,
        symbols=config.SYMBOLS,
        interval=config.TIMEFRAME
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot detenido manualmente por el usuario.")
    except Exception as e:
        logger.critical(f"💥 Error fatal en la ejecución: {e}", exc_info=True)
