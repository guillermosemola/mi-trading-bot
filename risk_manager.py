"""
Módulo de Gestión de Riesgo (Risk Manager).
Calcula tamaños de posición, Stop Loss y Take Profit dinámicos por ATR,
y controla los circuit breakers del portafolio.
"""
import logging
import config

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, sl_atr_mult: float = 1.0, tp_atr_mult: float = 3.0):
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult
        self.initial_equity = config.TOTAL_CAPITAL_USDT
        self.current_equity = config.TOTAL_CAPITAL_USDT
        self.peak_equity = config.TOTAL_CAPITAL_USDT
        self.daily_pnl = 0.0
        self.halt_reason = None

    def update_equity(self, current_equity: float):
        """Actualiza la equidad actual y rastrea el máximo histórico (peak) para drawdown."""
        self.current_equity = current_equity
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

    def register_trade_pnl(self, pnl: float):
        """Registra el PnL de una operación cerrada para controlar pérdida diaria."""
        self.daily_pnl += pnl

    def can_trade(self) -> bool:
        """Verifica los circuit breakers de pérdida diaria y max drawdown."""
        # 1. Pérdida Máxima Diaria
        max_daily_loss = self.initial_equity * config.MAX_DAILY_LOSS_PCT
        if self.daily_pnl <= -max_daily_loss:
            self.halt_reason = f"Límite de pérdida diaria alcanzado (-{abs(self.daily_pnl):.2f} USDT)"
            return False

        # 2. Max Drawdown desde el máximo de equidad
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - self.current_equity) / self.peak_equity
            if drawdown >= config.MAX_DRAWDOWN_PCT:
                self.halt_reason = f"Max Drawdown superado ({drawdown * 100:.2f}%)"
                return False

        self.halt_reason = None
        return True

    def stop_loss_price(self, entry_price: float, side: str, atr: float = None) -> float:
        """Calcula el precio de Stop Loss basado en ATR o porcentaje por defecto."""
        if atr and atr > 0:
            dist = atr * self.sl_atr_mult
        else:
            dist = entry_price * config.STOP_LOSS_PCT

        if side == "LONG":
            return entry_price - dist
        else:
            return entry_price + dist

    def take_profit_price(self, entry_price: float, side: str, atr: float = None) -> float:
        """Calcula el precio de Take Profit basado en ATR o porcentaje por defecto."""
        if atr and atr > 0:
            dist = atr * self.tp_atr_mult
        else:
            dist = entry_price * config.TAKE_PROFIT_PCT

        if side == "LONG":
            return entry_price + dist
        else:
            return entry_price - dist

    def position_size(self, current_price: float, stop_loss_price: float = None) -> float:
        """
        Calcula la cantidad de cripto a comprar.
        Asegura un notional mínimo de ~10.5 USDT para cumplir la regla de Binance Spot.
        """
        min_usdt_notional = 10.5
        if current_price <= 0:
            return 0.0

        raw_qty = min_usdt_notional / current_price
        return raw_qty