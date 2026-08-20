"""
Módulo de Configuración Global del Bot de Trading.
Lee las variables de entorno desde el archivo .env.
"""
import os
from dotenv import load_dotenv

# Cargar variables del .env
load_dotenv()

# --- Modo de Operación ---
USE_TESTNET = os.getenv("USE_TESTNET", "false").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# --- Credenciales de Binance ---
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# --- Universo y Timeframe ---
SYMBOLS_RAW = os.getenv(
    "SYMBOLS",
    "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,AVAXUSDT,LINKUSDT"
)
SYMBOLS = [s.strip() for s in SYMBOLS_RAW.split(",") if s.strip()]

TIMEFRAME = os.getenv("TIMEFRAME", "1h")
LOOKBACK_CANDLES = int(os.getenv("LOOKBACK_CANDLES", "1000"))

# --- Capital y Riesgo ---
TOTAL_CAPITAL_USDT = float(os.getenv("TOTAL_CAPITAL_USDT", "100.0"))
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "0.01"))
MAX_POSITION_PCT_PER_SYMBOL = float(os.getenv("MAX_POSITION_PCT_PER_SYMBOL", "0.20"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.02"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.04"))
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.05"))
MAX_DRAWDOWN_PCT = float(os.getenv("MAX_DRAWDOWN_PCT", "0.15"))

# --- Pesos de la Estrategia y Umbral ---
WEIGHT_TREND = float(os.getenv("WEIGHT_TREND", "0.65"))
WEIGHT_MEAN_REVERSION = float(os.getenv("WEIGHT_MEAN_REVERSION", "0.35"))
WEIGHT_ML = float(os.getenv("WEIGHT_ML", "0.00"))
ENTRY_THRESHOLD = float(os.getenv("ENTRY_THRESHOLD", "0.45"))

# --- Machine Learning ---
ML_PREDICTION_HORIZON = int(os.getenv("ML_PREDICTION_HORIZON", "3"))
ML_MIN_TRAIN_ROWS = int(os.getenv("ML_MIN_TRAIN_ROWS", "300"))

# --- Logging ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "trading_bot.log")