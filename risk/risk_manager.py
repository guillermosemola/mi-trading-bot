"""
Módulo de Gestión de Riesgo (Risk Manager) Optimizado con Trailing Stop & Break-Even.
Garantiza el cálculo dinámico de posición, niveles adaptativos por ATR y gestión
en tiempo real de posiciones abiertas para asegurar ganancias.
"""
import logging
import config

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, sl_atr_mult: float = 1.8, tp_atr_mult: float = 3.6):
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult
        self.initial_equity = getattr(config, "TOTAL_CAPITAL_USDT", 1000.0)
        self.current_equity = self.initial_equity
        self.peak_equity = self.initial_equity
        self.daily_pnl = 0.0
        self.halt_reason = None

        # Umbral para mover a Break-Even (múltiplo de ATR)
        self.be_atr_mult = 1.5

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
        """Reinicia el contador de PnL diario (llamar al inicio de cada día UTC)."""
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
        """Calcula el Stop Loss inicial basado en ATR o porcentaje por defecto."""
        stop_loss_pct = getattr(config, "STOP_LOSS_PCT", 0.02)
        dist = atr * self.sl_atr_mult if (atr and atr > 0) else entry_price * stop_loss_pct

        if side == "LONG":
            return max(0.0, entry_price - dist)
        else:
            return entry_price + dist

    def take_profit_price(self, entry_price: float, side: str, atr: float = None) -> float:
        """Calcula el Take Profit inicial basado en ATR o porcentaje por defecto."""
        take_profit_pct = getattr(config, "TAKE_PROFIT_PCT", 0.04)
        dist = atr * self.tp_atr_mult if (atr and atr > 0) else entry_price * take_profit_pct

        if side == "LONG":
            return entry_price + dist
        else:
            return max(0.0, entry_price - dist)

    def position_size(self, current_price: float, stop_loss_price: float = None) -> float:
        """Calcula la cantidad exacta a operar según el riesgo asignado por trade."""
        min_usdt_notional = 10.5
        if current_price <= 0:
            return 0.0

        risk_per_trade_pct = getattr(config, "RISK_PER_TRADE_PCT", 0.02)
        max_capital_to_risk = self.current_equity * risk_per_trade_pct

        if stop_loss_price and stop_loss_price > 0 and stop_loss_price != current_price:
            risk_per_unit = abs(current_price - stop_loss_price)
            target_qty = max_capital_to_risk / risk_per_unit
            notional_value = target_qty * current_price

            if notional_value < min_usdt_notional:
                target_qty = min_usdt_notional / current_price

            max_qty_allowed = self.current_equity / current_price
            return min(target_qty, max_qty_allowed)

        return min_usdt_notional / current_price

    def update_dynamic_stop(
        self,
        side: str,
        entry_price: float,
        current_price: float,
        current_sl: float,
        best_price: float,
        atr: float
    ) -> tuple[float, float]:
        """
        Calcula la actualización del Stop Loss en vivo aplicando Break-Even y Trailing Stop por ATR.
        
        Retorna:
            tuple: (nuevo_stop_loss, nuevo_best_price)
        """
        if atr is None or atr <= 0:
            return current_sl, best_price

        updated_sl = current_sl
        updated_best_price = best_price

        if side == "LONG":
            # Actualizar el precio máximo alcanzado desde la entrada
            if current_price > best_price:
                updated_best_price = current_price

            profit_dist = updated_best_price - entry_price

            # 1. Break-Even Check: si alcanzamos el umbral (BE_ATR), movemos SL a precio de entrada
            if profit_dist >= (atr * self.be_atr_mult):
                updated_sl = max(updated_sl, entry_price)

            # 2. Trailing Stop Check: trailing a distancia fija del precio máximo
            trailing_sl = updated_best_price - (atr * self.sl_atr_mult)
            updated_sl = max(updated_sl, trailing_sl)

        elif side == "SHORT":
            # Actualizar el precio mínimo alcanzado desde la entrada
            if current_price < best_price or best_price == 0.0:
                updated_best_price = current_price

            profit_dist = entry_price - updated_best_price

            # 1. Break-Even Check
            if profit_dist >= (atr * self.be_atr_mult):
                updated_sl = min(updated_sl, entry_price)

            # 2. Trailing Stop Check
            trailing_sl = updated_best_price + (atr * self.sl_atr_mult)
            if updated_sl == 0.0:
                updated_sl = trailing_sl
            else:
                updated_sl = min(updated_sl, trailing_sl)

        return updated_sl, updated_best_price
