+++
id = "candle-size"
title = "Candle size"
category = "Charts"
aliases = ["timeframe"]
related = ["candlestick", "range"]
summary = "How much time each candle covers: 1D, 1W, 2W, 1M or 3M. Bigger candles show the bigger picture."
+++
The **candle size** is how much time one [candle](topic:candlestick) covers: **1D** (a day), **1W**, **2W**, **1M** or
**3M**.

Only daily prices are downloaded. Bigger candles are *built from them*: the open of the first day, the highest high,
the lowest low, the close of the last day and the total volume.

## Candle size vs. range
Candle size is the *detail* of the picture; the [range](topic:range) is how *far back* it goes. Daily candles over a
month show every day; monthly candles over ten years show the long-term shape.

Indicator lengths given in days are converted: a 50-day [SMA](topic:sma) on weekly candles uses 10 candles.
