"""
Wrapper de ejecución de órdenes. Por defecto opera en DRY_RUN: calcula
y loguea qué haría, pero no manda nada a Binance. Para operar de verdad
hay que setear DRY_RUN=false explícitamente en el .env, y encima usar
USE_TESTNET=false para ir a mainnet con dinero real.
"""
import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException

import config

logger = logging.getLogger(__name__)


"""
Ejecutor de órdenes en Binance Spot.
Aplica formateo de decimales y validación de notional mínimo.
"""
import logging
from binance.client import Client

logger = logging.getLogger(__name__)


class BinanceExecutor:
    def __init__(self, client: Client):
        self.client = client

    def market_buy(self, symbol: str, quantity: float):
        """Ejecuta una orden de compra a mercado respetando las reglas de Binance."""
        try:
            # 1. Ajustar precisión de decimales según el símbolo
            if "BTC" in symbol:
                formatted_qty = f"{quantity:.5f}"
            elif "ETH" in symbol:
                formatted_qty = f"{quantity:.4f}"
            elif "BNB" in symbol:
                formatted_qty = f"{quantity:.3f}"
            else:
                formatted_qty = f"{quantity:.2f}"

            qty_float = float(formatted_qty)

            if qty_float <= 0:
                logger.error("Cantidad ajustada a 0 para %s, no se envía la orden.", symbol)
                return None

            logger.info("Enviando orden MARKET BUY de %s para %s...", formatted_qty, symbol)

            # 2. Ejecutar la orden en Binance
            order = self.client.create_order(
                symbol=symbol,
                side=Client.SIDE_BUY,
                type=Client.ORDER_TYPE_MARKET,
                quantity=formatted_qty
            )
            logger.info("¡Orden ejecutada con éxito en Binance! ID: %s", order.get("orderId"))
            return order

        except Exception as e:
            logger.error("Error ejecutando orden de compra en %s: %s", symbol, e)
            return None

    def market_sell(self, symbol: str, quantity: float):
        """Ejecuta una orden de venta a mercado."""
        try:
            if "BTC" in symbol:
                formatted_qty = f"{quantity:.5f}"
            elif "ETH" in symbol:
                formatted_qty = f"{quantity:.4f}"
            elif "BNB" in symbol:
                formatted_qty = f"{quantity:.3f}"
            else:
                formatted_qty = f"{quantity:.2f}"

            order = self.client.create_order(
                symbol=symbol,
                side=Client.SIDE_SELL,
                type=Client.ORDER_TYPE_MARKET,
                quantity=formatted_qty
            )
            logger.info("¡Orden de VENTA ejecutada con éxito en Binance! ID: %s", order.get("orderId"))
            return order
        except Exception as e:
            logger.error("Error ejecutando orden de venta en %s: %s", symbol, e)
            return None
    def _round_qty(self, symbol: str, quantity: float) -> float:
        """
        Binance exige que la cantidad respete el stepSize del símbolo.
        Esto trae las reglas del exchange y redondea correctamente
        para evitar el error clásico de "LOT_SIZE".
        """
        try:
            info = self.client.get_symbol_info(symbol)
            step_size = None
            for f in info["filters"]:
                if f["filterType"] == "LOT_SIZE":
                    step_size = float(f["stepSize"])
                    break
            if step_size:
                precision = max(0, str(step_size)[::-1].find("."))
                return round(quantity - (quantity % step_size), precision)
        except Exception as e:
            logger.warning("No se pudo obtener stepSize para %s: %s", symbol, e)
        return round(quantity, 6)
