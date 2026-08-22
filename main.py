"""
Módulo Principal del Bot de Trading (main.py)
Coordina la recolección de datos, generación de señales mediante ensamble,
y la gestión dinámica de posiciones y riesgo con Trailing Stop y Break-Even.
"""
import logging
import time
import pandas as pd
import numpy as np

import config
from strategies import trend_following, mean_reversion
from risk.risk_manager import RiskManager

# Configuración del registrador de eventos (Logging)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("TradingBot")


class TradingBot:
    def __init__(self):
        # Inicializamos el gestor de riesgo
        self.risk_manager = RiskManager(sl_atr_mult=1.8, tp_atr_mult=3.6)
        self.active_position = None  # Almacena la posición abierta
        self.symbol = getattr(config, "SYMBOL", "BTCUSDT")
        
        # Pesos para el Ensamble de Estrategias
        self.weight_trend = 0.6
        self.weight_reversion = 0.4
        self.entry_threshold = getattr(config, "ENTRY_THRESHOLD", 0.55)

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

        # 2. SI NO HAY POSICIÓN: Verificar Circuit Breakers antes de buscar entradas
        if not self.risk_manager.can_trade():
            logger.warning(f"Trading pausado por Gestor de Riesgo: {self.risk_manager.halt_reason}")
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
        """Calcula el tamaño, niveles de riesgo y abre la posición."""
        sl_price = self.risk_manager.stop_loss_price(entry_price, side, atr)
        tp_price = self.risk_manager.take_profit_price(entry_price, side, atr)
        qty = self.risk_manager.position_size(entry_price, sl_price)

        self.active_position = {
            "symbol": self.symbol,
            "side": side,
            "entry_price": entry_price,
            "qty": qty,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "best_price": entry_price  # Necesario para el Trailing Stop
        }

        logger.info(
            f"=== POSICIÓN ABIERTA [{side}] ==="
            f"\n  Precio Entrada: {entry_price:.2f}"
            f"\n  Cantidad: {qty:.4f}"
            f"\n  Stop Loss Inicial: {sl_price:.2f}"
            f"\n  Take Profit Inicial: {tp_price:.2f}"
        )

    def _manage_open_position(self, current_price: float, current_atr: float):
        """Ajusta el Stop Loss dinámicamente y verifica condiciones de salida."""
        pos = self.active_position

        # Actualizar Stop Loss dinámico (Break-Even / Trailing Stop)
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
            logger.info(f" Stop Loss actualizado dinámicamente: {pos['stop_loss']:.2f} -> {new_sl:.2f}")
            pos["stop_loss"] = new_sl

        # Comprobar condiciones de salida
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

    def _close_position(self, exit_price: float, reason: str):
        """Cierra la posición activa y registra el resultado PnL."""
        pos = self.active_position
        if pos["side"] == "LONG":
            pnl = (exit_price - pos["entry_price"]) * pos["qty"]
        else:
            pnl = (pos["entry_price"] - exit_price) * pos["qty"]

        # Registrar PnL en el gestor de riesgo
        self.risk_manager.register_trade_pnl(pnl)
        self.risk_manager.update_equity(self.risk_manager.current_equity + pnl)

        logger.info(
            f"=== POSICIÓN CERRADA [{reason}] ==="
            f"\n  Precio Salida: {exit_price:.2f}"
            f"\n  PnL Operación: {pnl:+.2f} USDT"
            f"\n  Equidad Actual: {self.risk_manager.current_equity:.2f} USDT"
        )

        self.active_position = None


# --- EJEMPLO DE BUCLE DE SIMULACIÓN / RUNNER ---
if __name__ == "__main__":
    bot = TradingBot()
    logger.info("Bot de Trading iniciado correctamente.")
    
    # En producción aquí se conecta el websocket de Binance o el loop de velas.
