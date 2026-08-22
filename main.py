"""
Core Principal del Bot de Trading (main.py).
"""
import logging
import pandas as pd
import config
from notifications.telegram_bot import send_telegram_message
# CORRECTO:
from risk.risk_manager import RiskManager
from execution.order_manager import OrderManager

logger = logging.getLogger(__name__)


class TradingBot:
    def __init__(self, client=None):
        self.client = client
        
        # Cargar configuración desde config.py
        self.symbols = config.SYMBOLS
        self.timeframe = config.TIMEFRAME
        self.entry_threshold = config.ENTRY_THRESHOLD
        
        # Gestores de riesgo y órdenes
        self.risk_manager = RiskManager()
        self.order_manager = OrderManager(client=self.client)
        
        # Mantener el estado de posiciones abiertas de forma independiente por activo
        self.active_positions = {symbol: None for symbol in self.symbols}
        
        # Notificación inicial en Telegram
        dry_run_str = " (SIMULACIÓN)" if config.DRY_RUN else " (REAL)"
        symbols_str = "\n• ".join(self.symbols)
        
        send_telegram_message(
            f"🤖 *Bot Multi-Activo Iniciado*{dry_run_str}\n\n"
            f"• *Timeframe:* `{self.timeframe}`\n"
            f"• *Capital Configurado:* `{config.TOTAL_CAPITAL_USDT} USDT`\n"
            f"• *Activos Monitoreados ({len(self.symbols)}):*\n• {symbols_str}"
        )

    def evaluate_market(self, symbol: str, current_row: pd.Series):
        """Evalúa las condiciones del mercado para una moneda específica."""
        current_price = float(current_row["close"])
        current_atr = float(current_row.get("atr", current_price * 0.01))

        # 1. Gestionar si ya hay una posición abierta para ESTE símbolo
        if self.active_positions[symbol] is not None:
            self._manage_open_position(symbol, current_price, current_atr)
            return

        # 2. Verificar límites globales de riesgo
        if not self.risk_manager.can_trade():
            msg = f"⚠️ *Trading Pausado ({symbol})*\nMotivo: {self.risk_manager.halt_reason}"
            logger.warning(msg)
            send_telegram_message(msg)
            return

        # 3. Señal de la estrategia
        ensemble_score = self.calculate_ensemble_signal(current_row)
        logger.info(f"[{symbol}] Precio: {current_price:.2f} | Score: {ensemble_score:.3f}")

        # 4. Evaluación de Entrada
        if ensemble_score >= self.entry_threshold:
            self._open_position(symbol=symbol, side="LONG", entry_price=current_price, atr=current_atr)
        elif ensemble_score <= -self.entry_threshold:
            self._open_position(symbol=symbol, side="SHORT", entry_price=current_price, atr=current_atr)

    def calculate_ensemble_signal(self, current_row: pd.Series) -> float:
        """Aquí se combinan las señales de tu ensamble de estrategias."""
        # Coloca aquí la llamada a tus estrategias existentes (ej. trend_following + mean_reversion)
        # Retorna un float entre -1.0 y 1.0
        return 0.0  # Placeholder

    def _open_position(self, symbol: str, side: str, entry_price: float, atr: float):
        """Abre la posición y actualiza el diccionario del activo correspondiente."""
        sl_price = self.risk_manager.stop_loss_price(entry_price, side, atr)
        raw_qty = self.risk_manager.position_size(entry_price, sl_price)

        execution = self.order_manager.execute_smart_order(
            symbol=symbol, side=side, qty=raw_qty, current_bid=entry_price, current_ask=entry_price
        )

        if execution.get("status") != "FILLED":
            return

        real_price = execution["filled_price"]
        actual_qty = execution["qty"]
        tp_price = self.risk_manager.take_profit_price(real_price, side, atr)

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
        """Gestiona el Stop Loss / Take Profit para la posición de esta moneda."""
        pos = self.active_positions[symbol]
        if not pos:
            return

        # Ejemplo de cierre por Stop Loss
        if (pos["side"] == "LONG" and current_price <= pos["stop_loss"]) or \
           (pos["side"] == "SHORT" and current_price >= pos["stop_loss"]):
            send_telegram_message(f"🛑 *STOP LOSS ACTIVADO en {symbol}* @ `{current_price:.2f} USDT`")
            self.active_positions[symbol] = None

        # Ejemplo de cierre por Take Profit
        elif (pos["side"] == "LONG" and current_price >= pos["take_profit"]) or \
             (pos["side"] == "SHORT" and current_price <= pos["take_profit"]):
            send_telegram_message(f"🎯 *TAKE PROFIT ALCANZADO en {symbol}* @ `{current_price:.2f} USDT`")
            self.active_positions[symbol] = None
