"""
Punto de entrada del bot con Notificaciones por Telegram,
Filtro de Tendencia Global (SMA 200 de BTC) y Machine Learning Activo.

Modos de uso:
  python main.py backtest        -> corre backtest sobre datos históricos
  python main.py train           -> entrena y guarda el modelo ML con datos actuales
  python main.py run             -> loop en vivo (respeta DRY_RUN/USE_TESTNET del config)
"""
import argparse
import logging
import sys
import time
import os
import requests
from dotenv import load_dotenv

# Cargar variables del archivo .env al entorno de Python
load_dotenv()

import config
from data.data_fetcher import get_client, fetch_klines
from features.feature_engineering import build_features
from models.ml_model import MLSignalModel
from strategies.ensemble import combined_signal
from risk.risk_manager import RiskManager
from portfolio.portfolio_manager import PortfolioManager
from execution.binance_executor import BinanceExecutor
from backtest.backtester import run_backtest

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(config.LOG_FILE)],
)
logger = logging.getLogger("main")


def send_telegram(msg: str):
    """Envía un mensaje a Telegram si el token y chat_id están configurados."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.error("Error enviando notificación a Telegram: %s", e)


def is_btc_bullish(client) -> bool:
    """
    FILTRO DE TENDENCIA GLOBAL:
    Verifica si BTCUSDT cotiza por encima de su media móvil de 200 períodos (SMA 200).
    """
    try:
        df_btc = fetch_klines(client, "BTCUSDT")
        df_feat = build_features(df_btc).dropna()
        if len(df_feat) < 200:
            logger.warning("Velas insuficientes para SMA 200 de BTC. Permitiendo operaciones por defecto.")
            return True

        sma200 = df_feat["close"].rolling(window=200).mean().iloc[-1]
        btc_price = df_feat["close"].iloc[-1]
        is_bull = btc_price > sma200
        logger.info("Filtro BTC SMA 200: Precio=%.2f | SMA200=%.2f | Alcista=%s", btc_price, sma200, is_bull)
        return is_bull
    except Exception as e:
        logger.error("Error calculando SMA 200 de BTC: %s", e)
        return True


def cmd_backtest():
    client = get_client()
    for symbol in config.SYMBOLS:
        logger.info("=== Backtest: %s ===", symbol)
        df = fetch_klines(client, symbol)
        try:
            results = run_backtest(df)
        except ValueError as e:
            logger.error(str(e))
            continue
        print(f"\n--- Resultados {symbol} ---")
        for k, v in results.items():
            if k not in ("equity_curve", "trades", "ml_metrics"):
                print(f"  {k}: {v}")
        if "ml_metrics" in results and "accuracy" in results["ml_metrics"]:
            print(f"  ml_accuracy: {results['ml_metrics']['accuracy']:.3f}")
            print(f"  ml_auc: {results['ml_metrics']['auc']:.3f}")


def cmd_train():
    client = get_client()
    for symbol in config.SYMBOLS:
        logger.info("Entrenando modelo para %s", symbol)
        df = fetch_klines(client, symbol)
        df_feat = build_features(df).dropna()
        model = MLSignalModel(model_path=f"models/artifacts/ml_model_{symbol}.joblib")
        metrics = model.train(df_feat)
        logger.info("%s -> accuracy=%.3f auc=%.3f", symbol, metrics["accuracy"], metrics["auc"])


def cmd_run(poll_seconds: int = 60):
    if not config.DRY_RUN and not config.USE_TESTNET:
        logger.warning(
            "*** ATENCIÓN: DRY_RUN=false y USE_TESTNET=false. "
            "El bot va a operar con DINERO REAL en mainnet. ***"
        )
        confirm = input("Escribí 'CONFIRMO' para continuar: ")
        if confirm.strip() != "CONFIRMO":
            logger.info("Cancelado por el usuario.")
            return

    client = get_client()
    executor = BinanceExecutor(client)
    portfolio = PortfolioManager()
    risk_manager = RiskManager()

    models = {}
    for symbol in config.SYMBOLS:
        model = MLSignalModel(model_path=f"models/artifacts/ml_model_{symbol}.joblib")
        try:
            model.load()
        except FileNotFoundError:
            logger.warning("No hay modelo entrenado para %s, entrenando ahora...", symbol)
            df = fetch_klines(client, symbol)
            df_feat = build_features(df).dropna()
            model.train(df_feat)
        models[symbol] = model

    logger.info("Bot iniciado. DRY_RUN=%s USE_TESTNET=%s", config.DRY_RUN, config.USE_TESTNET)
    send_telegram("🤖 *Bot de Trading Iniciado*\nMonitoreando en vivo: " + ", ".join(config.SYMBOLS))

    while True:
        current_prices = {}
        
        # Evaluar el filtro de mercado global sobre BTC antes de analizar entradas
        btc_bullish = is_btc_bullish(client)

        for symbol in config.SYMBOLS:
            try:
                df = fetch_klines(client, symbol)
                df_feat = build_features(df).dropna()
                last_row = df_feat.iloc[-1]
                price = last_row["close"]
                current_prices[symbol] = price

                # 1. Gestión de posición abierta (Verificar Stop Loss / Trailing Stop / Take Profit)
                if portfolio.has_position(symbol):
                    hit = portfolio.check_stop_take(symbol, price)
                    if hit:
                        pos_qty = portfolio.positions.get(symbol, {}).get("quantity", 0)
                        pnl = portfolio.close_position(symbol, price)
                        executor.market_sell(symbol, pos_qty)
                        pnl_val = pnl or 0.0
                        risk_manager.register_trade_pnl(pnl_val)
                        
                        emoji = "🟢" if pnl_val >= 0 else "🔴"
                        msg_sell = (
                            f"{emoji} *OPERACIÓN CERRADA ({hit})*\n"
                            f"📌 *Par:* `{symbol}`\n"
                            f"💵 *Precio Salida:* `{price:.2f} USDT`\n"
                            f"📊 *PnL:* `{pnl_val:+.4f} USDT`"
                        )
                        send_telegram(msg_sell)
                        logger.info("%s cerrado por %s, PnL=%.4f", symbol, hit, pnl_val)
                    continue

                # 2. Control de riesgo del portafolio
                if not risk_manager.can_trade():
                    logger.warning("Trading pausado: %s", risk_manager.halt_reason)
                    continue

                # 3. Bloqueo de compras si el mercado general es bajista
                if not btc_bullish:
                    logger.info("Mercado en tendencia bajista (BTC < SMA200). Se omiten compras para %s", symbol)
                    continue

                # 4. Evaluación de Señal de Entrada
                ml_prob_up = models[symbol].predict_proba_up(last_row)
                sig = combined_signal(last_row, ml_prob_up)
                logger.info(
                    "%s señal=%s score=%.3f (trend=%.2f mr=%.2f ml=%.2f)",
                    symbol, sig["decision"], sig["combined_score"],
                    sig["trend_score"], sig["mean_reversion_score"], sig["ml_score"]
                )

                if sig["decision"] == "LONG":
                    atr_val = last_row.get("atr", None)
                    sl = risk_manager.stop_loss_price(price, "LONG", atr_val)
                    tp = risk_manager.take_profit_price(price, "LONG", atr_val)
                    qty = risk_manager.position_size(price, sl)
                    
                    if qty > 0:
                        order = executor.market_buy(symbol, qty)
                        if order:
                            portfolio.open_position(symbol, price, qty, sl, tp)
                            
                            msg_buy = (
                                f"🚀 *COMPRA EJECUTADA*\n"
                                f"📌 *Par:* `{symbol}`\n"
                                f"💵 *Precio Entrada:* `{price:.2f} USDT`\n"
                                f"📦 *Cantidad:* `{qty}`\n"
                                f"🔴 *Stop Loss:* `{sl:.2f} USDT`\n"
                                f"🟢 *Take Profit:* `{tp:.2f} USDT`"
                            )
                            send_telegram(msg_buy)

            except Exception as e:
                logger.error("Error procesando %s: %s", symbol, e, exc_info=True)

        equity = portfolio.total_equity(current_prices)
        risk_manager.update_equity(equity)
        logger.info("Equity actual: %.2f USDT", equity)

        time.sleep(poll_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bot de trading multi-estrategia con ML")
    parser.add_argument("mode", choices=["backtest", "train", "run"])
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args()

    if args.mode == "backtest":

import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot OK")

def run_health_check_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# Iniciar servidor web en un hilo secundario
threading.Thread(target=run_health_check_server, daemon=True).start()
        cmd_backtest()
    elif args.mode == "train":
        cmd_train()
    elif args.mode == "run":
        cmd_run(args.poll_seconds)
