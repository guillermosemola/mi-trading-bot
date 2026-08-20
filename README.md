# Bot de trading multi-estrategia (Binance)

## ⚠️ Antes que nada

Este bot **no garantiza rentabilidad**. Ningún sistema de trading lo hace, sin importar
qué tan sofisticado sea (ni siquiera los que usan fondos institucionales con equipos de
cientos de personas). Lo que este proyecto sí ofrece:

- Una arquitectura seria y modular (estrategias, ML, riesgo, portfolio, ejecución separados)
- Modo `DRY_RUN` y `USE_TESTNET` activados **por defecto** — no manda órdenes reales hasta que vos lo cambies explícitamente
- Gestión de riesgo con circuit breakers (pérdida diaria máxima, drawdown máximo)
- Backtesting con validación temporal (walk-forward, no K-fold random, que filtraría información del futuro)

**Flujo recomendado, en este orden:**
1. `python main.py backtest` — validar con datos históricos
2. `python main.py run` con `DRY_RUN=true` y `USE_TESTNET=true` — correr en vivo sin arriesgar nada, comparar contra lo esperado
3. Recién ahí, si los resultados te convencen, pasar a `USE_TESTNET=false` con el capital chico que definiste — y aceptando que puede perderse.

## Instalación

```bash
cd trading_bot
python3 -m venv venv
source venv/bin/activate  # o venv\Scripts\activate en Windows
pip install -r requirements.txt
cp .env.example .env
```

Completá `.env` con tus API keys. Para arrancar sin ningún riesgo, generá keys de
**testnet** en https://testnet.binance.vision/ (no requiere fondos reales).

## Arquitectura

```
trading_bot/
├── config.py                    # toda la configuración vía variables de entorno
├── data/data_fetcher.py         # trae velas OHLCV de Binance (testnet/mainnet)
├── features/feature_engineering.py  # indicadores técnicos (RSI, MACD, Bollinger, ATR...)
├── models/ml_model.py           # clasificador Gradient Boosting, valida con walk-forward
├── strategies/
│   ├── trend_following.py       # señal por cruce de medias + MACD
│   ├── mean_reversion.py        # señal por RSI + posición en bandas de Bollinger
│   └── ensemble.py              # combina las 3 señales con pesos configurables
├── risk/risk_manager.py         # position sizing + stop loss/take profit + circuit breakers
├── portfolio/portfolio_manager.py  # estado de posiciones multi-símbolo
├── execution/binance_executor.py   # ejecución de órdenes (dry-run por defecto)
├── backtest/backtester.py       # backtest con comisiones y métricas (Sharpe, drawdown, win rate)
└── main.py                      # orquestador: backtest | train | run
```

## Cómo funciona la señal combinada

Cada estrategia devuelve un score continuo entre -1 y 1 (no una decisión binaria).
El ensemble los combina con pesos configurables (`WEIGHT_TREND`, `WEIGHT_MEAN_REVERSION`,
`WEIGHT_ML` en `.env`, deben sumar 1.0):

```
score_final = (trend * W_trend + mean_reversion * W_mr + ml * W_ml) / suma_pesos
```

Si `score_final >= ENTRY_THRESHOLD` → compra. Si `<= -ENTRY_THRESHOLD` y hay posición
abierta → cierra. Entre medio → no hace nada (`FLAT`). Podés ajustar los pesos y el
umbral en `.env` según qué tanto peso le querés dar a cada componente.

## Gestión de riesgo (la parte que más importa)

- **Position sizing por riesgo fijo**: cada trade arriesga `RISK_PER_TRADE_PCT` del
  capital total (no del capital libre), calculado según la distancia al stop loss.
- **Stop loss / take profit** fijos por trade (`STOP_LOSS_PCT`, `TAKE_PROFIT_PCT`).
- **Circuit breaker diario**: si la pérdida del día supera `MAX_DAILY_LOSS_PCT`, el bot
  deja de abrir posiciones nuevas hasta el día siguiente.
- **Circuit breaker de drawdown**: si el equity cae `MAX_DRAWDOWN_PCT` desde su pico
  histórico, el bot se detiene por completo (requiere intervención manual para reanudar).

Estos límites están para protegerte de vos mismo en una mala racha — no los saques
sin pensarlo mucho.

## Comandos

```bash
# Backtest sobre historial reciente de cada símbolo en SYMBOLS
python main.py backtest

# Entrena y guarda el modelo ML por símbolo
python main.py train

# Loop en vivo (dry-run/testnet según .env)
python main.py run --poll-seconds 60
```

## Limitaciones honestas

- El modelo ML es un **filtro de probabilidad**, no un oráculo. En el smoke test con
  datos sintéticos (random walk), el AUC ronda 0.5 — es decir, sin ninguna ventaja
  predictiva, como es esperable en datos puramente aleatorios. Con datos reales de
  mercado vas a tener que evaluar el AUC real y decidir si el modelo aporta algo o si
  conviene bajarle el peso (`WEIGHT_ML`) y apoyarte más en las reglas técnicas.
- El backtest no modela slippage ni impacto en el book — en un par líquido como
  BTCUSDT con montos chicos no debería ser grave, pero es una simplificación real.
- La estrategia "SHORT" en spot no abre posiciones cortas de verdad — solo cierra
  posiciones largas existentes. Para shortear de verdad hace falta cuenta de
  Margin/Futures, que trae riesgo de liquidación y no está implementado acá.
- Nunca corrí este bot contra el mercado real — lo que valida el smoke test es que
  el pipeline de código funciona sin errores, no que sea rentable. Esa validación
  la tenés que hacer vos con backtest sobre datos reales y después con testnet en vivo.

## Próximos pasos sugeridos

1. Correr `python main.py backtest` con tus símbolos y ver accuracy/AUC del ML real.
2. Si el AUC ronda 0.5, el ML no está aportando — considerá ampliar features
   (order book imbalance, funding rate si vas a futuros, features de otros timeframes)
   o directamente bajarle el peso en el ensemble.
3. Correr en testnet por al menos 2-4 semanas antes de considerar mainnet.
4. Empezar mainnet con el capital chico que ya definiste, y solo escalar si el
   comportamiento real coincide con lo esperado por el backtest.
