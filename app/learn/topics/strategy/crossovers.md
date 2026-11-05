+++
id = "crossovers"
title = "Crossovers: states vs events"
category = "Strategy"
aliases = ["crosses above", "crosses below", "crossover", "crossovers"]
related = ["macd", "signal-line", "sma"]
summary = "\"Is above\" is true on every candle it holds; \"crosses above\" is true only on the candle where it happens."
+++
Rules in the strategy builder compare two lines, and there are two kinds of comparison:

- **States** (*is above*, *is below*): true on **every** candle where the condition holds.
- **Events** (*crosses above*, *crosses below*): true **only on the candle where the cross happens**.

## Combining them
An event is true for just one candle, so it rarely lines up exactly with other conditions. Use
**within N candles** to say the cross counts if it happened in the last N candles, e.g. "MACD crosses above its
signal line within the last 3 candles AND price is above the 200-day average".
