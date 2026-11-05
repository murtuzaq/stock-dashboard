+++
id = "stoch-rsi"
title = "Stoch RSI"
category = "Indicators"
aliases = ["Stochastic RSI", "StochRSI"]
related = ["overbought-oversold", "crossovers"]
summary = "A 0-100 oscillator that shows how stretched the RSI is: above 80 overbought, below 20 oversold."
+++
**Stochastic RSI** applies the stochastic formula to the **RSI** (Relative Strength Index, a 0-100 measure of recent
gains versus losses). It shows where the RSI sits within its own recent range, so it reacts faster than RSI alone.

- **K** is the fast line; **D** is a smoothed average of K.
- Above **80**: [overbought](topic:overbought-oversold). Below **20**: [oversold](topic:overbought-oversold).
- K crossing D can signal a turn.

The panel uses the common settings (14, 14, 3, 3).

## Limits
It swings between extremes quickly, so it gives many signals. Traders usually combine it with a trend filter, such as
price above the 200-day [SMA](topic:sma).
