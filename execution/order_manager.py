"""
Módulo de Ejecución de Órdenes (execution/order_manager.py)
Administra la ejecución en Binance con soporte para DRY_RUN,
formateo dinámico (LOT_SIZE, PRICE_FILTER), prevención de desfase de reloj (recvWindow)
y órdenes Límite Adaptativas (Maker/Taker).
"""
import logging
import time
import math
from decimal import Decimal
import config
from binance.client import Client
from binance.exceptions import BinanceAPIException

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(self, client: Client = None, timeout_seconds: int = 12, max_spread_pct: float = 0.0008):
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.max_spread_pct = max_spread_pct
        self.dry_run = getattr(config, "DRY_RUN", True)
        self._rules_cache = {}

    def _get_symbol_filters(self, symbol: str) -> tuple[float, int, float, int]:
        """Obtiene y almacena en caché las reglas de precisión (LOT_SIZE y PRICE_FILTER)."""
        if symbol in self._rules_cache:
            return self._rules_cache[symbol]

        default_rules = (0.00001, 5, 0.01, 2)
        if not self.client or self.dry_run:
            return default_rules

        try:
            info = self.client.get_symbol_info(symbol)
            step_size, qty_precision = 0.00001, 5
            tick_size, price_precision = 0.01, 2

            for f in info.get("filters", []):
                if f["filterType"] == "LOT_SIZE":
                    step_size = float(f["stepSize"])
                    qty_precision = Decimal(f["stepSize"]).normalize().as_tuple().exponent * -1
                elif f["filterType"] == "PRICE_FILTER":
                    tick_size = float(f["tickSize"])
                    price_precision = Decimal(f["tickSize"]).normalize().as_tuple().exponent * -1

            rules = (step_size, max(0, qty_precision), tick_size, max(0, price_precision))
            self._rules_cache[symbol] = rules
            return rules
        except Exception as e:
            logger.warning(f"Error consultando filtros Binance para {symbol}: {e}")
            return default_rules

    def _format_qty_and_price(self, symbol: str, quantity: float, price: float) -> tuple[str, str]:
        """Ajusta cantidad y precio según las reglas estrictas de Binance."""
        step_size, qty_prec, tick_size, price_prec = self._get_symbol_filters(symbol)
        
        factor_qty = 1 / step_size
        rounded_qty = math.floor(quantity * factor_qty) / factor_qty
        
        factor_price = 1 / tick_size
        rounded_price = round(price * factor_price) / factor_price

        return f"{rounded_qty:.{qty_prec}f}", f"{rounded_price:.{price_prec}f}"

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
        limit_price = current_bid if side in ["BUY", "LONG"] else current_ask
        str_qty, str_price = self._format_qty_and_price(symbol, qty, limit_price)
        formatted_qty = float(str_qty)

        if formatted_qty <= 0:
            logger.error(f"Cantidad ajustada a 0 para {symbol}, cancelación de orden.")
            return {"status": "CANCELLED", "reason": "ZERO_QTY", "filled_price": 0.0, "qty": 0.0}

        if not self.check_spread_ok(current_bid, current_ask):
            return {"status": "CANCELLED", "reason": "HIGH_SPREAD", "filled_price": 0.0, "qty": 0.0}

        # Modo DRY_RUN (Simulación)
        if self.dry_run or self.client is None:
            logger.info(f"🧪 [DRY_RUN] Orden {side} simulada: {str_qty} {symbol} a {str_price}")
            return {
                "status": "FILLED",
                "type": "DRY_RUN_MAKER",
                "filled_price": float(str_price),
                "qty": formatted_qty
            }

        # Modo PRODUCCIÓN
        try:
            order_side = Client.SIDE_BUY if side in ["BUY", "LONG"] else Client.SIDE_SELL
            
            logger.info(f"Colocando orden LÍMITE [{order_side}] {str_qty} {symbol} a {str_price}...")
            order = self.client.create_order(
                symbol=symbol,
                side=order_side,
                type=Client.ORDER_TYPE_LIMIT,
                timeInForce=Client.TIME_IN_FORCE_GTC,
                quantity=str_qty,
                price=str_price,
                recvWindow=10000
            )
            order_id = order["orderId"]

            # Esperar llenado como Maker
            start_time = time.time()
            while time.time() - start_time < self.timeout_seconds:
                time.sleep(1.5)
                check = self.client.get_order(symbol=symbol, orderId=order_id, recvWindow=10000)
                if check["status"] == "FILLED":
                    filled_price = float(check.get("price") or str_price)
                    logger.info(f"✅ Orden LÍMITE ejecutada como MAKER a {filled_price}")
                    return {"status": "FILLED", "type": "LIMIT_MAKER", "filled_price": filled_price, "qty": formatted_qty}

            # Cancelación con protección ante llenados de último segundo o errores de API
            try:
                self.client.cancel_order(symbol=symbol, orderId=order_id, recvWindow=10000)
                time.sleep(0.5)
                check_final = self.client.get_order(symbol=symbol, orderId=order_id, recvWindow=10000)
                if check_final["status"] == "FILLED":
                    filled_price = float(check_final.get("price") or str_price)
                    return {"status": "FILLED", "type": "LIMIT_MAKER", "filled_price": filled_price, "qty": formatted_qty}
            except BinanceAPIException as e:
                if e.code == -2011:  # La orden ya fue llenada completamente y no puede cancelarse
                    check_final = self.client.get_order(symbol=symbol, orderId=order_id, recvWindow=10000)
                    filled_price = float(check_final.get("price") or str_price)
                    return {"status": "FILLED", "type": "LIMIT_MAKER", "filled_price": filled_price, "qty": formatted_qty}

            # Fallback a Mercado (Taker)
            logger.warning("Timeout en orden Límite. Cancelada con éxito, ejecutando a MERCADO (Taker)...")
            market_order = self.client.create_order(
                symbol=symbol,
                side=order_side,
                type=Client.ORDER_TYPE_MARKET,
                quantity=str_qty,
                recvWindow=10000
            )

            # Cálculo del precio medio real (VWAP) en caso de ejecuciones parciales
            fills = market_order.get("fills", [])
            if fills:
                total_cost = sum(float(f["price"]) * float(f["qty"]) for f in fills)
                total_qty = sum(float(f["qty"]) for f in fills)
                filled_price = total_cost / total_qty if total_qty > 0 else limit_price
            else:
                filled_price = limit_price
            
            return {"status": "FILLED", "type": "MARKET_TAKER", "filled_price": filled_price, "qty": formatted_qty}

        except Exception as e:
            logger.error(f"Error crítico en ejecución de órdenes: {e}")
            return {"status": "ERROR", "reason": str(e), "filled_price": 0.0, "qty": 0.0}
