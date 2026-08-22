"""
Módulo de Gestión de Riesgo (Risk Manager) Optimizado.
Calcula tamaños de posición basados en el riesgo por operación y distancia al Stop Loss (ATR),
gestiona niveles dinámicos de SL/TP, y controla circuit breakers del portafolio.
"""
import logging
import config

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, sl_atr_mult: float = 1.8, tp_atr_mult: float = 3.6):
        # Multiplicadores de ATR optimizados para absorber ruido de mercado
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult
        self.initial_equity = getattr(config, "TOTAL_CAPITAL_USDT", 1000.0)
        self.current_equity = self.initial_equity
        self.peak_equity = self.initial_equity
        self.daily_pnl = 0.0
        self.halt_reason = None

    def update_equity(self, current_equity: float):
        """Actualiza la equidad actual y rastrea el máximo histórico (peak) para drawdown."""
        if current_equity <= 0:
            return
        self.current_equity = current_equity
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

    def register_trade_pnl(self, pnl: float):
        """Registra el PnL de una operación cerrada para controlar pérdida diaria."""
        self.daily_pnl += pnl

    def reset_daily_pnl(self):
        """Llamar a esta función al inicio de cada día UTC para reiniciar el circuit breaker diario."""
        self.daily_pnl = 0.0
        logger.info("PnL diario reiniciado a 0.0 USDT.")

    def can_trade(self) -> bool:
        """Verifica los circuit breakers de pérdida diaria y max drawdown."""
        max_daily_loss_pct = getattr(config, "MAX_DAILY_LOSS_PCT", 0.05)
        max_drawdown_pct = getattr(config, "MAX_DRAWDOWN_PCT", 0.15)

        # 1. Pérdida Máxima Diaria
        max_daily_loss = self.current_equity * max_daily_loss_pct
        if self.daily_pnl <= -max_daily_loss:
            self.halt_reason = f"Límite de pérdida diaria alcanzado (-{abs(self.daily_pnl):.2f} USDT)"
            return False

        # 2. Max Drawdown desde el máximo de equidad (Peak)
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - self.current_equity) / self.peak_equity
            if drawdown >= max_drawdown_pct:
                self.halt_reason = f"Max Drawdown superado ({drawdown * 100:.2f}%)"
                return False

        self.halt_reason = None
        return True

    def stop_loss_price(self, entry_price: float, side: str, atr: float = None) -> float:
        """Calcula el precio de Stop Loss basado en ATR o porcentaje por defecto."""
        stop_loss_pct = getattr(config, "STOP_LOSS_PCT", 0.02)
        if atr and atr > 0:
            dist = atr * self.sl_atr_mult
        else:
            dist = entry_price * stop_loss_pct

        if side == "LONG":
            return max(0.0, entry_price - dist)
        else:
            return entry_price + dist

    def take_profit_price(self, entry_price: float, side: str, atr: float = None) -> float:
        """Calcula el precio de Take Profit basado en ATR o porcentaje por defecto."""
        take_profit_pct = getattr(config, "TAKE_PROFIT_PCT", 0.04)
        if atr and atr > 0:
            dist = atr * self.tp_atr_mult
        else:
            dist = entry_price * take_profit_pct

        if side == "LONG":
            return entry_price + dist
        else:
            return max(0.0, entry_price - dist)

    def position_size(self, current_price: float, stop_loss_price: float = None) -> float:
        """
        Calcula la cantidad exacta de activos a operar basada en el riesgo por trade.
        Usa RISK_PER_TRADE_PCT de config.py (ej. 1% o 2% del capital).
        Asegura además cumplir con el notional mínimo de Binance (~10.5 USDT).
        """
        min_usdt_notional = 10.5
        if current_price <= 0:
            return 0.0

        risk_per_trade_pct = getattr(config, "RISK_PER_TRADE_PCT", 0.02) # Default: 2% del capital
        max_capital_to_risk = self.current_equity * risk_per_trade_pct

        # Si tenemos un Stop Loss válido, calculamos el tamaño exacto por gestión de riesgo
        if stop_loss_price and stop_loss_price > 0 and stop_loss_price != current_price:
            risk_per_unit = abs(current_price - stop_loss_price)
            target_qty = max_capital_to_risk / risk_per_unit
            notional_value = target_qty * current_price

            # Si la posición por riesgo es menor al mínimo de Binance, ajustamos al mínimo
            if notional_value < min_usdt_notional:
                target_qty = min_usdt_notional / current_price

            # No permitir que una sola posición supere el capital total asignado
            max_qty_allowed = self.current_equity / current_price
            return min(target_qty, max_qty_allowed)

        # Fallback si no hay Stop Loss: usar mínimo nocional
        return min_usdt_notional / current_price
