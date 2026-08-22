"""
Core Principal del Bot de Trading (main.py).
Gestiona el análisis, evaluación de señales y ejecución de órdenes.
"""
import logging
import pandas as pd
import config
from notifications.telegram_bot import send_telegram_message
from risk.risk_manager import RiskManager
from execution.order_manager import OrderManager

logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self, client=None):
        self.client = client
        
        # 1. Cargar configuración global
        self.symbols = config.SYMBOLS
        self.timeframe = config.TIMEFRAME
        self.entry_threshold = getattr(config, "ENTRY_THRESHOLD", 0.45)
        
        # 2. Inicializar Gestores de Riesgo y Órdenes
        self.risk_manager = RiskManager()
        self.order_manager = OrderManager(client=self.client)
        
        # 3. Estado de las posiciones activas por cada criptomoneda
        self.active_positions = {symbol: None for symbol in self.symbols}
        
        # 4. Notificación de inicio a Telegram
        dry_run_str = " (SIMULACIÓN)" if getattr(config, "DRY_RUN", True) else " (REAL)"
        symbols_str = "\n• ".join(self.symbols)
        
        send_telegram_message(
            f"🤖 *Bot Multi-Activo Iniciado*{dry_run_str}\n\n"
            f"• *Timeframe:* `{self.timeframe}`\n"
            f"• *Activos Monitoreados ({len(self.symbols)}):*\n• {symbols_str}"
        )

    def evaluate_market(self, symbol: str, current_row: pd.Series):
        """Evalúa las condiciones del mercado al cierre de cada vela para un activo."""
        current_price = float(current_row["close"])
        current_atr = float(current_row.get("atr", current_price * 0.01))

        # A. Si ya hay una operación abierta, gestionamos el SL/TP y salimos
        if self.active_positions[symbol] is not None:
            self._manage_open_position(symbol, current_price, current_atr)
            return

        # B. Comprobar si el gestor de riesgo permite operar
        if not self.risk_manager.can_trade():
            msg = f"⚠️ *Trading Pausado ({symbol})*\nMotivo: {self.risk_manager.halt_reason}"
            logger.warning(msg)
            send_telegram_message(msg)
            return

        # C. Calcular el Score de la Estrategia (Trend + RSI)
        ensemble_score = self.calculate_ensemble_signal(current_row)
        logger.info(f"[{symbol}] Precio: {current_price:.2f} | Score Estrategia: {ensemble_score:.3f}")

        # D. Ejecutar orden si supera el umbral configurado
        if ensemble_score >= self.entry_threshold:
            self._open_position(symbol=symbol, side="LONG", entry_price=current_price, atr=current_atr)
        elif ensemble_score <= -self.entry_threshold:
            self._open_position(symbol=symbol, side="SHORT", entry_price=current_price, atr=current_atr)

    def calculate_ensemble_signal(self, current_row: pd.Series) -> float:
        """
        Combina indicadores técnicos para generar una señal ponderada de -1.0 a +1.0.
        """
        rsi = float(current_row.get("rsi", 50.0))
        ema_fast = float(current_row.get("ema_fast", 0.0))
        ema_slow = float(current_row.get("ema_slow", 0.0))

        # Estrategia 1: Tendencia (Cruce de EMAs)
        trend_score = 0.0
        if ema_fast > ema_slow and ema_slow > 0:
            trend_score = 1.0
        elif ema_fast < ema_slow and ema_slow > 0:
            trend_score = -1.0

        # Estrategia 2: Reversión (RSI Sobrecompra/Sobreventa)
        reversion_score = 0.0
        if rsi < 30:
            reversion_score = 1.0
        elif rsi > 70:
            reversion_score = -1.0

        # Extraer pesos configurados (o usar valores por defecto)
        weight_trend = getattr(config, "WEIGHT_TREND", 0.65)
        weight_reversion = getattr(config, "WEIGHT_MEAN_REVERSION", 0.35)

        # Cálculo final ponderado
        score = (trend_score * weight_trend) + (reversion_score * weight_reversion)
        return score

    def _open_position(self, symbol: str, side: str, entry_price: float, atr: float):
        """Calcula el riesgo, ejecuta la orden en Binance y notifica a Telegram."""
        sl_price = self.risk_manager.stop_loss_price(entry_price, side, atr)
        raw_qty = self.risk_manager.position_size(entry_price, sl_price)

        # Envío de la orden al OrderManager
        execution = self.order_manager.execute_smart_order(
            symbol=symbol, side=side, qty=raw_qty, current_bid=entry_price, current_ask=entry_price
        )

        if execution.get("status") != "FILLED":
            return

        # Recuperar datos reales de la ejecución (slippage)
        real_price = execution.get("filled_price", entry_price)
        actual_qty = execution.get("qty", raw_qty)
        tp_price = self.risk_manager.take_profit_price(real_price, side, atr)

        # Guardar la posición en memoria
        self.active_positions[symbol] = {
            "symbol": symbol,
            "side": side,
            "entry_price": real_price,
            "qty": actual_qty,
            "stop_loss": sl_price,
            "take_profit": tp_price
        }

        emoji = "🟢" if side == "LONG" else "🔴"
        send_telegram_message(
            f"{emoji} *NUEVA POSICIÓN [{symbol} - {side}]*\n\n"
            f"• *Entrada:* `{real_price:.2f} USDT`\n"
            f"• *Cantidad:* `{actual_qty:.4f}`\n"
            f"• *Stop Loss:* `{sl_price:.2f} USDT`\n"
            f"• *Take Profit:* `{tp_price:.2f} USDT`"
        )

    def _manage_open_position(self, symbol: str, current_price: float, atr: float):
        """Gestiona el Stop Loss / Take Profit para la posicion de esta moneda."""
        pos = self.active_positions[symbol]
        if not pos:
            return

        # 1. Chequeo de Stop Loss
        if (pos["side"] == "LONG" and current_price <= pos["stop_loss"]) or \
           (pos["side"] == "SHORT" and current_price >= pos["stop_loss"]):
            send_telegram_message(f"🛑 *STOP LOSS ACTIVADO en {symbol}* @ `{current_price:.2f} USDT`")
            self.active_positions[symbol] = None

        # 2. Chequeo de Take Profit
        elif (pos["side"] == "LONG" and current_price >= pos["take_profit"]) or \
             (pos["side"] == "SHORT" and current_price <= pos["take_profit"]):
            send_telegram_message(f"🎯 *TAKE PROFIT ALCANZADO en {symbol}* @ `{current_price:.2f} USDT`")
            self.active_positions[symbol] = None
