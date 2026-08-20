import os
import logging
import requests

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv(8877719410:AAFtK7df1KijAoVsdWHgPYcYWCy_tEFGkVQ, "")
TELEGRAM_CHAT_ID = os.getenv(297700822, "")

def send_telegram_message(message: str):
    """Envía un mensaje formateado a tu chat de Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("Telegram no configurado. Mensaje omitido.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.error("Error enviando mensaje por Telegram: %s", e)