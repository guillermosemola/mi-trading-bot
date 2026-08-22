import os
import threading
from flask import Flask
from main import TradingBot

app = Flask(__name__)

# Endpoint que responderá a UptimeRobot con éxito
@app.route('/')
def health_check():
    return "Bot de Trading activo y ejecutándose.", 200

def run_trading_bot():
    """Ejecuta la instancia del bot en un hilo secundario."""
    bot = TradingBot()
    # Si tienes un método de bucle principal como bot.run(), conéctalo aquí
    print("Bot de trading ejecutándose en segundo plano...")

if __name__ == "__main__":
    # 1. Iniciar el bot de trading en un hilo paralelo para no bloquear Flask
    bot_thread = threading.Thread(target=run_trading_bot, daemon=True)
    bot_thread.start()

    # 2. Iniciar el servidor web Flask en el puerto que asigna Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
