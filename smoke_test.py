"""
Test de humo: genera OHLCV sintético (random walk con algo de tendencia)
y corre todo el pipeline para verificar que no hay errores de código.
Esto NO valida rentabilidad, solo que el sistema funciona end-to-end.
"""
import logging
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from backtest.backtester import run_backtest

np.random.seed(42)
n = 2000
dates = pd.date_range("2024-01-01", periods=n, freq="h")
returns = np.random.normal(0.0002, 0.01, n)
prices = 30000 * np.exp(np.cumsum(returns))

df = pd.DataFrame({
    "open": prices * (1 + np.random.normal(0, 0.001, n)),
    "high": prices * (1 + np.abs(np.random.normal(0, 0.003, n))),
    "low": prices * (1 - np.abs(np.random.normal(0, 0.003, n))),
    "close": prices,
    "volume": np.random.uniform(100, 1000, n),
}, index=dates)
df.index.name = "open_time"

print("Corriendo backtest de prueba con datos sintéticos...")
results = run_backtest(df)

print("\n=== RESULTADOS (datos sintéticos, solo validación de pipeline) ===")
for k, v in results.items():
    if k not in ("equity_curve", "trades", "ml_metrics"):
        print(f"  {k}: {v}")
print(f"  ml_accuracy: {results['ml_metrics']['accuracy']:.3f}")
print(f"  ml_auc: {results['ml_metrics']['auc']:.3f}")
print(f"  n filas equity_curve: {len(results['equity_curve'])}")
print(f"  n trades: {len(results['trades'])}")
print("\nOK: el pipeline completo corrió sin errores.")
