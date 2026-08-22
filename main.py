"""
Módulo Principal del Bot de Trading (main.py)
Coordina la recolección de datos, generación de señales mediante ensamble,
gestión dinámica de posiciones, ejecución adaptativa de órdenes y alertas de Telegram.
"""
import logging
import time
import pandas as pd
import numpy as np

import config
from strategies import trend_following, mean_reversion
from risk.risk_manager import RiskManager
from execution.order_manager import OrderManager
from notifications.telegram_bot import send_telegram_message

# Configuración del registrador de eventos (Logging)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("TradingBot")


class TradingBot:
    def __init__(self, client=None):
        self.client = client
        self.symbol = getattr(config, "SYMBOL", "BTCUSDT")
        
        # Inicialización del Gestor de Riesgo y Gestor de Órdenes
        self.risk_manager = RiskManager(sl_atr_mult=1.8, tp_atr_mult=3.6)
        self.order_manager = OrderManager(client=self.client)
        self.active_position = None  # Almacena la posición abierta
        
        # Pesos para el Ensamble de Estrategias
        self.weight_trend = 0.6
        self.weight_reversion = 0.4
        self.entry_threshold = getattr(config, "ENTRY_THRESHOLD", 0.55)

        # Notificación inicial a Telegram
        dry_run_str = " (DRY RUN / SIMULACIÓN)" if self.order_manager.dry_run else " (LIVE / REAL)"
        send_telegram_message(
            f"🤖 *Bot de Trading Iniciado*{dry_run_str}\n"
            f"• *Símbolo:* `{self.symbol}`\n"
            f"• *Capital Inicial:* `{self.risk_manager.current_equity:.2f} USDT`"
        )

    def calculate_ensemble_signal(self, row: pd.Series) -> float:
        """Calcula la señal combinada ponderada de las estrategias."""
        sig_trend = trend_following.signal(row)
        sig_reversion = mean_reversion.signal(row)

        combined_score = (sig_trend * self.weight_trend) + (sig_reversion * self.weight_reversion)
        return float(np.clip(combined_score, -1.0, 1.0))

    def evaluate_market(self, current_row: pd.Series):
        """Evalúa las condiciones del mercado y gestiona entradas o salidas."""
        current_price = float(current_row["close"])
        current_atr = float(current_row.get("atr", current_price * 0.01))

        # 1. SI HAY UNA POSICIÓN ABIERTA: Gestionar Trailing Stop, Break-Even y Cierres
        if self.active_position is not None:
            self._manage_open_position(current_price, current_atr)
            return

        # 2. SI NO HAY POSICIÓN: Verificar Circuit Breakers del Gestor de Riesgo
        if not self.risk_manager.can_trade():
            msg = f"⚠️ *Trading Pausado por Gestor de Riesgo*\nMotivo: {self.risk_manager.halt_reason}"
            logger.warning(msg)
            send_telegram_message(msg)
            return

        # 3. Calcular la Señal del Ensamble
        ensemble_score = self.calculate_ensemble_signal(current_row)
        logger.info(f"Precio: {current_price:.2f} | Ensamble Score: {ensemble_score:.3f}")

        # 4. Evaluar Umbrales de Entrada
        if ensemble_score >= self.entry_threshold:
            self._open_position(side="LONG", entry_price=current_price, atr=current_atr)
        elif ensemble_score <= -self.entry_threshold:
            self._open_position(side="SHORT", entry_price=current_price, atr=current_atr)

    def _open_position(self, side: str, entry_price: float, atr: float):
        """Calcula el tamaño, ejecuta la orden de entrada y establece niveles de riesgo."""
        sl_price = self.risk_manager.stop_loss_price(entry_price, side, atr)
        raw_qty = self.risk_manager.position_size(entry_price, sl_price)

        # Precios estimados de Spread Bid/Ask
        bid_price = entry_price * 0.9999
        ask_price = entry_price * 1.0001

        # Ejecución inteligente vía OrderManager
        execution = self.order_manager.execute_smart_order(
            symbol=self.symbol,
            side=side,
            qty=raw_qty,
            current_bid=bid_price,
            current_ask=ask_price
        )

        if execution["status"] != "FILLED":
            logger.warning("No se pudo ejecutar la orden de entrada.")
            return

        real_entry_price = execution["filled_price"]
        actual_qty = execution["qty"]
        tp_price = self.risk_manager.take_profit_price(real_entry_price, side, atr)
        notional_usdt = actual_qty * real_entry_price

        self.active_position = {
            "symbol": self.symbol,
            "side": side,
            "entry_price": real_entry_price,
            "qty": actual_qty,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "best_price": real_entry_price
        }

        logger.info(
            f"=== POSICIÓN ABIERTA [{side}] ==="
            f"\n  Precio Ejecutado: {real_entry_price:.2f}"
            f"\n  Cantidad: {actual_qty:.4f}"
            f"\n  Tipo Orden: {execution['type']}"
            f"\n  Stop Loss: {sl_price:.2f}"
            f"\n  Take Profit: {tp_price:.2f}"
        )

        emoji = "🟢" if side == "LONG" else "🔴"
        send_telegram_message(
            f"{emoji} *NUEVA POSICIÓN ABIERTA [{side}]*\n\n"
            f"• *Activo:* `{self.symbol}`\n"
            f"• *Precio Entrada:* `{real_entry_price:.2f} USDT`\n"
            f"• *Cantidad:* `{actual_qty:.4f}` (~`{notional_usdt:.2f} USDT`)\n"
            f"• *Tipo:* `{execution['type']}`\n"
            f"• *Stop Loss:* `{sl_price:.2f} USDT`\n"
            f"• *Take Profit:* `{tp_price:.2f} USDT`"
        )

    def _manage_open_position(self, current_price: float, current_atr: float):
        """Ajusta Stop Loss dinámico y comprueba condiciones de salida."""
        pos = self.active_position

        new_sl, new_best = self.risk_manager.update_dynamic_stop(
            side=pos["side"],
            entry_price=pos["entry_price"],
            current_price=current_price,
            current_sl=pos["stop_loss"],
            best_price=pos["best_price"],
            atr=current_atr
        )

        pos["best_price"] = new_best

        if new_sl != pos["stop_loss"]:
            logger.info(f"Stop Loss actualizado: {pos['stop_loss']:.2f} -> {new_sl:.2f}")
            pos["stop_loss"] = new_sl

        # Comprobar salidas para LONG y SHORT
        if pos["side"] == "LONG":
            if current_price <= pos["stop_loss"]:
                self._close_position(current_price, reason="STOP_LOSS / TRAILING_STOP")
            elif current_price >= pos["take_profit"]:
                self._close_position(current_price, reason="TAKE_PROFIT")

        elif pos["side"] == "SHORT":
            if current_price >= pos["stop_loss"]:
                self._close_position(current_price, reason="STOP_LOSS / TRAILING_STOP")
            elif current_price <= pos["take_profit"]:
                self._close_position(current_price, reason="TAKE_PROFIT")

    def _close_position(self, market_price: float, reason: str):
        """Ejecuta la orden de cierre en Binance, registra PnL y envía alerta."""
        pos = self.active_position
        close_side = "SELL" if pos["side"] == "LONG" else "BUY"

        bid_price = market_price * 0.9999
        ask_price = market_price * 1.0001

        # Ejecutar cierre vía OrderManager
        execution = self.order_manager.execute_smart_order(
            symbol=pos["symbol"],
            side=close_side,
            qty=pos["qty"],
            current_bid=bid_price,
            current_ask=ask_price
        )

        exit_price = execution["filled_price"] if execution["status"] == "FILLED" else market_price

        # Cálculo de PnL
        if pos["side"] == "LONG":
            pnl = (exit_price - pos["entry_price"]) * pos["qty"]
        else:
            pnl = (pos["entry_price"] - exit_price) * pos["qty"]

        pnl_pct = (pnl / (pos["entry_price"] * pos["qty"])) * 100

        # Registro en el gestor de riesgo
        self.risk_manager.register_trade_pnl(pnl)
        self.risk_manager.update_equity(self.risk_manager.current_equity + pnl)

        logger.info(
            f"=== POSICIÓN CERRADA [{reason}] ==="
            f"\n  Precio Salida: {exit_price:.2f}"
            f"\n  PnL Operación: {pnl:+.2f} USDT"
            f"\n  Equidad Actual: {self.risk_manager.current_equity:.2f} USDT"
        )

        outcome_emoji = "✅" if pnl >= 0 else "❌"
        send_telegram_message(
            f"{outcome_emoji} *POSICIÓN CERRADA [{reason}]*\n\n"
            f"• *Activo:* `{pos['symbol']}` ({pos['side']})\n"
            f"• *Precio Entrada:* `{pos['entry_price']:.2f} USDT`\n"
            f"• *Precio Salida:* `{exit_price:.2f} USDT`\n"
            f"• *PnL Operación:* `{pnl:+.2f} USDT` (`{pnl_pct:+.2f}%`)\n"
            f"• *Balance Cuenta:* `{self.risk_manager.current_equity:.2f} USDT`"
        )

        self.active_position = None


if __name__ == "__main__":
    bot = TradingBot()
    logger.info("Bot de Trading iniciado correctamente.")
