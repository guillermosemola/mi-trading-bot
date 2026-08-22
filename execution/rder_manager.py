"""
Módulo de Ejecución de Órdenes (Order Manager).
Implementa órdenes Límite Adaptativas (Maker) con timeout y fallback a Mercado (Taker),
además de verificar el Bid-Ask Spread para minimizar el slippage.
"""
import logging
import time
import config

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(self, client=None, timeout_seconds: int = 12, max_spread_pct: float = 0.0008):
        self.client = client  # Instancia de Binance API / CCXT client
        self.timeout_seconds = timeout_seconds  # Tiempo de espera para orden Límite
        self.max_spread_pct = max_spread_pct    # Máximo Spread Bid-Ask permitido (0.08%)

    def check_spread_ok(self, bid: float, ask: float) -> bool:
        """Verifica que el spread no sea excesivo para evitar deslices."""
        if bid <= 0 or ask <= 0:
            return False
        spread = (ask - bid) / ask
        if spread > self.max_spread_pct:
            logger.warning(f"Spread excesivo: {spread * 100:.3f}% > {self.max_spread_pct * 100:.3f}%. Entrada cancelada.")
            return False
        return True

    def execute_smart_order(self, symbol: str, side: str, qty: float, current_bid: float, current_ask: float) -> dict:
        """
        Ejecuta una orden de entrada adaptativa:
        1. Filtra por spread.
        2. Intenta orden Límite al precio Bid (para BUY) o Ask (para SELL) para ganar comisión Maker.
        3. Si no se llena en 'timeout_seconds', cancela y ejecuta orden Mercado (Taker).
        """
        if not self.check_spread_ok(current_bid, current_ask):
            return {"status": "CANCELLED", "reason": "HIGH_SPREAD", "filled_price": 0.0, "qty": 0.0}

        # Precio límite competitivo (Maker)
        limit_price = current_bid if side == "BUY" or side == "LONG" else current_ask
        
        logger.info(f"Colocando orden LÍMITE [{side}] de {qty:.4f} {symbol} a {limit_price:.2f} (Esperando {self.timeout_seconds}s Maker)...")

        # --- SIMULACIÓN / API EXECUTION ---
        # Si no hay cliente API conectado (Modo Paper Trading / Dry Run)
        if self.client is None:
            time.sleep(1) # Simular tiempo de procesamiento
            logger.info(f" [Paper Trading] Orden LÍMITE ejecutada con éxito como Maker a {limit_price:.2f}")
            return {"status": "FILLED", "type": "LIMIT_MAKER", "filled_price": limit_price, "qty": qty}

        # --- MODO PRODUCCIÓN CON API REAL (Binance / CCXT) ---
        try:
            # 1. Enviar orden Límite
            order_side = "BUY" if side in ["BUY", "LONG"] else "SELL"
            order = self.client.create_limit_order(symbol, order_side, qty, limit_price)
            order_id = order["id"]

            start_time = time.time()
            while time.time() - start_time < self.timeout_seconds:
                time.sleep(2)
                order_status = self.client.fetch_order(order_id, symbol)
                
                if order_status["status"] == "closed":
                    logger.info(f"✅ Orden LÍMITE llenada como MAKER a {order_status['price']:.2f}")
                    return {
                        "status": "FILLED",
                        "type": "LIMIT_MAKER",
                        "filled_price": float(order_status["price"]),
                        "qty": float(order_status["filled"])
                    }

            # 2. Fallback: Cancelar Límite y ejecutar a Mercado
            logger.warning(" Timeout alcanzado para orden Límite. Ejecutando Fallback a MERCADO (Taker)...")
            self.client.cancel_order(order_id, symbol)
            
            market_order = self.client.create_market_order(symbol, order_side, qty)
            filled_price = float(market_order.get("price", current_ask if order_side == "BUY" else current_bid))
            
            return {
                "status": "FILLED",
                "type": "MARKET_TAKER",
                "filled_price": filled_price,
                "qty": qty
            }

        except Exception as e:
            logger.error(f"Error durante la ejecución de la orden: {e}")
            return {"status": "ERROR", "reason": str(e), "filled_price": 0.0, "qty": 0.0}
