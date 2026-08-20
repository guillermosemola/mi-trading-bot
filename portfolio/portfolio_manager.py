"""
Módulo de Gestión de Portafolio (PortfolioManager) con Trailing Stop y Persistencia en Disco.
Guarda y carga las posiciones abiertas en 'portfolio.json'.
El Stop Loss sube automáticamente a medida que el precio alcance nuevos máximos (Trailing Stop).
"""
import json
import logging
import os
import config

logger = logging.getLogger(__name__)

PORTFOLIO_FILE = "portfolio.json"


class PortfolioManager:
    def __init__(self):
        self.positions = {}
        self.load_state()

    def save_state(self):
        """Guarda las posiciones abiertas en un archivo JSON."""
        try:
            with open(PORTFOLIO_FILE, "w") as f:
                json.dump(self.positions, f, indent=4)
            logger.debug("Estado del portafolio guardado en %s", PORTFOLIO_FILE)
        except Exception as e:
            logger.error("Error al guardar el estado del portafolio: %s", e)

    def load_state(self):
        """Carga las posiciones abiertas guardadas previamente en disco."""
        if os.path.exists(PORTFOLIO_FILE):
            try:
                with open(PORTFOLIO_FILE, "r") as f:
                    self.positions = json.load(f)
                if self.positions:
                    logger.info("Posiciones activas recuperadas desde %s: %s", PORTFOLIO_FILE, list(self.positions.keys()))
            except Exception as e:
                logger.error("Error al cargar el estado del portafolio: %s", e)
                self.positions = {}
        else:
            self.positions = {}

    def has_position(self, symbol: str) -> bool:
        """Devuelve True si existe una posición abierta en el símbolo."""
        return symbol in self.positions

    def open_position(self, symbol: str, entry_price: float, quantity: float, stop_loss: float, take_profit: float):
        """Registra una posición abierta inicial en disco."""
        self.positions[symbol] = {
            "entry_price": entry_price,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "highest_price": entry_price  # Para seguimiento de Trailing Stop
        }
        self.save_state()
        logger.info(
            "Posición abierta registrada para %s: Qty=%.5f Entry=%.2f SL=%.2f TP=%.2f", 
            symbol, quantity, entry_price, stop_loss, take_profit
        )

    def close_position(self, symbol: str, exit_price: float) -> float:
        """Calcula el PnL, elimina la posición y actualiza el JSON."""
        if not self.has_position(symbol):
            return 0.0

        pos = self.positions.pop(symbol)
        self.save_state()

        pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
        logger.info("Posición cerrada en %s a precio %.2f. PnL: %.4f USDT", symbol, exit_price, pnl)
        return pnl

    def check_stop_take(self, symbol: str, current_price: float) -> str:
        """
        Evalúa Stop Loss, Take Profit y actualiza el Trailing Stop.
        Si el precio sube, desplaza el Stop Loss hacia arriba de forma proporcional.
        """
        if not self.has_position(symbol):
            return None

        pos = self.positions[symbol]
        sl = pos.get("stop_loss")
        tp = pos.get("take_profit")
        highest = pos.get("highest_price", pos["entry_price"])

        # LÓGICA DE TRAILING STOP:
        # Si alcanzamos un nuevo precio máximo en la posición
        if current_price > highest:
            delta = current_price - highest
            pos["highest_price"] = current_price
            # Subimos el Stop Loss en la misma magnitud del incremento
            pos["stop_loss"] = sl + delta
            self.save_state()
            logger.info(
                "📈 [%s] Trailing Stop actualizado! Nuevo máximo: %.2f | Nuevo SL: %.2f",
                symbol, current_price, pos["stop_loss"]
            )
            sl = pos["stop_loss"]

        # 1. Verificar si tocó el Stop Loss (inicial o desplazado por Trailing Stop)
        if sl and current_price <= sl:
            return "TRAILING_STOP" if highest > pos["entry_price"] else "STOP_LOSS"

        # 2. Verificar si tocó el Take Profit
        if tp and current_price >= tp:
            return "TAKE_PROFIT"

        return None

    def total_equity(self, current_prices: dict) -> float:
        """Calcula el capital total combinando las posiciones abiertas."""
        val = config.TOTAL_CAPITAL_USDT
        for sym, pos in self.positions.items():
            price = current_prices.get(sym, pos["entry_price"])
            pnl = (price - pos["entry_price"]) * pos["quantity"]
            val += pnl
        return val
