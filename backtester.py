"""
Backtester: corre la estrategia ensemble sobre datos históricos y
calcula métricas de performance realistas (incluyendo comisiones).

Esto NO predice el futuro. Un buen backtest es condición necesaria
pero no suficiente — el mercado real tiene slippage, liquidez limitada
y regímenes que cambian. Tratar cualquier resultado acá como un piso
mínimo de confianza, nunca como una garantía.
"""
import logging
import numpy as np
import pandas as pd

import config
from features.feature_engineering import build_features
from models.ml_model import MLSignalModel
from strategies.ensemble import combined_signal
from risk.risk_manager import RiskManager

logger = logging.getLogger(__name__)

BINANCE_TAKER_FEE = 0.001  # 0.1%, valor típico spot sin descuentos


def run_backtest(df_raw: pd.DataFrame, train_fraction: float = 0.6, verbose: bool = True):
    """
    df_raw: OHLCV crudo de un símbolo.
    train_fraction: qué porción de los datos se usa para entrenar el modelo ML
                    (el resto es el período de test, fuera de muestra).
    """
    df_feat = build_features(df_raw).dropna().reset_index()

    split_idx = int(len(df_feat) * train_fraction)
    train_df = df_feat.iloc[:split_idx]
    test_df = df_feat.iloc[split_idx:].reset_index(drop=True)

    if len(train_df) < config.ML_MIN_TRAIN_ROWS:
        raise ValueError(
            f"No hay suficientes datos para entrenar de forma confiable "
            f"({len(train_df)} filas, se recomiendan {config.ML_MIN_TRAIN_ROWS}+). "
            f"Traé más historial (aumentá LOOKBACK_CANDLES)."
        )

    ml_model = MLSignalModel()
    metrics = ml_model.train(train_df)
    if verbose:
        logger.info("ML entrenado — accuracy=%.3f AUC=%.3f", metrics["accuracy"], metrics["auc"])

    risk_manager = RiskManager()
    cash = risk_manager.total_capital
    position_qty = 0.0
    entry_price = None
    stop_loss = None
    take_profit = None

    equity_curve = []
    trades = []

    for i, row in test_df.iterrows():
        price = row["close"]
        atr_val = row["atr"] if "atr" in row else None

        # Actualiza equity y chequea circuit breakers
        equity = cash + position_qty * price
        risk_manager.update_equity(equity)
        equity_curve.append({"time": row["open_time"], "equity": equity})

        # Gestión de posición abierta: stop / take profit
        if position_qty > 0:
            hit = None
            if price <= stop_loss:
                hit = "STOP_LOSS"
            elif price >= take_profit:
                hit = "TAKE_PROFIT"
            if hit:
                proceeds = position_qty * price * (1 - BINANCE_TAKER_FEE)
                pnl = proceeds - (position_qty * entry_price)
                cash += proceeds
                risk_manager.register_trade_pnl(pnl)
                trades.append({"time": row["open_time"], "type": hit, "price": price, "pnl": pnl})
                position_qty = 0.0
                entry_price = None
                continue

        if not risk_manager.can_trade():
            continue

        ml_prob_up = ml_model.predict_proba_up(row)
        sig = combined_signal(row, ml_prob_up)

        if sig["decision"] == "LONG" and position_qty == 0:
            # Pasa atr_val al risk manager para obtener Stop Loss y Take Profit dinámicos
            sl = risk_manager.stop_loss_price(price, "LONG", atr_val)
            qty = risk_manager.position_size(price, sl)
            cost = qty * price * (1 + BINANCE_TAKER_FEE)
            if qty > 0 and cost <= cash:
                cash -= cost
                position_qty = qty
                entry_price = price
                stop_loss = sl
                take_profit = risk_manager.take_profit_price(price, "LONG", atr_val)
                trades.append({"time": row["open_time"], "type": "ENTRY", "price": price, "pnl": 0})

        elif sig["decision"] == "SHORT" and position_qty > 0:
            # En spot, señal bajista fuerte con posición abierta = cerrar
            proceeds = position_qty * price * (1 - BINANCE_TAKER_FEE)
            pnl = proceeds - (position_qty * entry_price)
            cash += proceeds
            risk_manager.register_trade_pnl(pnl)
            trades.append({"time": row["open_time"], "type": "EXIT_SIGNAL", "price": price, "pnl": pnl})
            position_qty = 0.0
            entry_price = None

    # Cierre forzado al final del período si quedó posición abierta
    if position_qty > 0:
        final_price = test_df.iloc[-1]["close"]
        proceeds = position_qty * final_price * (1 - BINANCE_TAKER_FEE)
        pnl = proceeds - (position_qty * entry_price)
        cash += proceeds
        trades.append({"time": test_df.iloc[-1]["open_time"], "type": "FORCED_EXIT", "price": final_price, "pnl": pnl})

    equity_df = pd.DataFrame(equity_curve).set_index("time")
    trades_df = pd.DataFrame(trades)

    results = compute_metrics(equity_df, trades_df, risk_manager.total_capital)
    results["ml_metrics"] = metrics
    results["equity_curve"] = equity_df
    results["trades"] = trades_df
    return results


def compute_metrics(equity_df, trades_df, initial_capital):
    # Validación para evitar el KeyError cuando no hay operaciones:
    if trades_df.empty or "type" not in trades_df.columns:
        return {
            "total_trades": 0,
            "final_equity": initial_capital,
            "return_pct": 0.0,
            "win_rate": 0.0,
            "max_drawdown": 0.0
        }

    final_equity = equity_df["equity"].iloc[-1]
    total_return_pct = (final_equity / initial_capital - 1) * 100

    returns = equity_df["equity"].pct_change().dropna()
    sharpe = 0.0
    if returns.std() > 0:
        # Asumiendo velas horarias -> anualizamos con sqrt(24*365)
        sharpe = (returns.mean() / returns.std()) * np.sqrt(24 * 365)

    running_max = equity_df["equity"].cummax()
    drawdown = (equity_df["equity"] - running_max) / running_max
    max_drawdown_pct = drawdown.min() * 100

    closed_trades = trades_df[trades_df["type"].isin(["STOP_LOSS", "TAKE_PROFIT", "EXIT_SIGNAL", "FORCED_EXIT"])]
    n_trades = len(closed_trades)
    win_rate = (closed_trades["pnl"] > 0).mean() * 100 if n_trades > 0 else 0.0
    avg_pnl = closed_trades["pnl"].mean() if n_trades > 0 else 0.0

    return {
        "initial_capital": initial_capital,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return_pct, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "n_trades": n_trades,
        "win_rate_pct": round(win_rate, 2),
        "avg_pnl_per_trade": round(avg_pnl, 2),
    }