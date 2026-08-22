"""
Módulo de Ejecución de Órdenes (execution/order_manager.py)
Administra la ejecución en Binance con soporte para DRY_RUN,
formateo dinámico de LOT_SIZE y órdenes Límite Adaptativas (Maker/Taker).
"""
import logging
import time
import math
import config
from binance.client import Client

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(self, client: Client = None, timeout_seconds: int = 12, max_spread_pct: float = 0.0008):
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.max_spread_pct = max_spread_pct
        self.dry_run = getattr(config, "DRY_RUN", True)

    def _get_step_size_and_precision(self, symbol: str) -> tuple[float, int]:
        """Obtiene el stepSize del símbolo en Binance para evitar errores LOT_SIZE."""
        if not self.client or self.dry_run:
            return 0.00001, 5  # Precisión por defecto en Dry Run

        try:
            info = self.client.get_symbol_info(symbol)
            for f in info.get("filters", []):
                if f["filterType"] == "LOT_SIZE":
                    step_size = float(f["stepSize"])
                    precision = max(0, str(step_size)[::-1].find("."))
                    return step_size, precision
        except Exception as e:
            logger.warning(f"No se pudo consultar LOT_SIZE para {symbol}: {e}")
        
        return 0.00001, 5

    def _round_qty(self, symbol: str, quantity: float) -> float:
        """Ajusta la cantidad al múltiplo exacto permitido por Binance."""
        step_size, precision = self._get_step_size_and_precision(symbol)
        if step_size > 0:
            # Redondeo hacia abajo para evitar pedir más de lo que se tiene en balance
            factor = 1 / step_size
            return round(math.floor(quantity * factor) / factor, precision)
        return round(quantity, precision)

    def check_spread_ok(self, bid: float, ask: float) -> bool:
        """Verifica que el spread no supere el umbral seguro."""
        if bid <= 0 or ask <= 0:
            return False
        spread = (ask - bid) / ask
        if spread > self.max_spread_pct:
            logger.warning(f"Spread elevado: {spread * 100:.3f}% > {self.max_spread_pct * 100:.3f}%.")
            return False
        return True

    def execute_smart_order(self, symbol: str, side: str, qty: float, current_bid: float, current_ask: float) -> dict:
        """
        Ejecuta la orden según el entorno:
        1. Si DRY_RUN es True: Simula la operación sin tocar la API real.
        2. Si DRY_RUN es False: Ejecuta una orden Límite Maker con fallback a Mercado Taker.
        """
        formatted_qty = self._round_qty(symbol, qty)
        if formatted_qty <= 0:
            logger.error(f"Cantidad ajustada a 0 para {symbol}, cancelación de orden.")
            return {"status": "CANCELLED", "reason": "ZERO_QTY", "filled_price": 0.0, "qty": 0.0}

        if not self.check_spread_ok(current_bid, current_ask):
            return {"status": "CANCELLED", "reason": "HIGH_SPREAD", "filled_price": 0.0, "qty": 0.0}

        limit_price = current_bid if side in ["BUY", "LONG"] else current_ask

        # Modo DRY_RUN (Simulación local)
        if self.dry_run or self.client is None:
            logger.info(f"🧪 [DRY_RUN] Orden {side} simulada: {formatted_qty} {symbol} a {limit_price:.2f}")
            return {
                "status": "FILLED",
                "type": "DRY_RUN_MAKER",
                "filled_price": limit_price,
                "qty": formatted_qty
            }

        # Modo PRODUCCIÓN (Dinero Real o Testnet)
        try:
            order_side = Client.SIDE_BUY if side in ["BUY", "LONG"] else Client.SIDE_SELL
            
            logger.info(f"Colocando orden LÍMITE [{order_side}] {formatted_qty} {symbol} a {limit_price:.2f}...")
            order = self.client.create_order(
                symbol=symbol,
                side=order_side,
                type=Client.ORDER_TYPE_LIMIT,
                timeInForce=Client.TIME_IN_FORCE_GTC,
                quantity=f"{formatted_qty}",
                price=f"{limit_price:.2f}"
            )
            order_id = order["orderId"]

            # Esperar llenado como Maker
            start_time = time.time()
            while time.time() - start_time < self.timeout_seconds:
                time.sleep(2)
                check = self.client.get_order(symbol=symbol, orderId=order_id)
                if check["status"] == "FILLED":
                    filled_price = float(check["price"])
                    logger.info(f"✅ Orden LÍMITE ejecutada como MAKER a {filled_price:.2f}")
                    return {"status": "FILLED", "type": "LIMIT_MAKER", "filled_price": filled_price, "qty": formatted_qty}

            # Fallback a Mercado (Taker)
            logger.warning(" Timeout en orden Límite. Cancelando y ejecutando a MERCADO (Taker)...")
            self.client.cancel_order(symbol=symbol, orderId=order_id)

            market_order = self.client.create_order(
                symbol=symbol,
                side=order_side,
                type=Client.ORDER_TYPE_MARKET,
                quantity=f"{formatted_qty}"
            )
            filled_price = float(market_order.get("fills", [{}])[0].get("price", current_ask if order_side == "BUY" else current_bid))
            
            return {"status": "FILLED", "type": "MARKET_TAKER", "filled_price": filled_price, "qty": formatted_qty}

        except Exception as e:
            logger.error(f"Error crítico en ejecución de órdenes: {e}")
            return {"status": "ERROR", "reason": str(e), "filled_price": 0.0, "qty": 0.0}
