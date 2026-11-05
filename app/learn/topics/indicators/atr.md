+++
id = "atr"
title = "ATR"
category = "Indicators"
aliases = ["Average True Range"]
related = ["atr-stop", "stop-loss"]
summary = "Average True Range: the typical size of one candle's move, in price units."
+++
**ATR** (Average True Range) measures **volatility**: how far the price typically moves in one candle.

Each candle's *true range* is the largest of:
- high minus low,
- the distance from the previous close to the high,
- the distance from the previous close to the low

(so overnight gaps count). ATR is the average of that over 14 candles. It is in **dollars**, not percent, so a stock
with ATR 2.00 usually moves about two dollars per candle.

## Uses
- A rising ATR means a more volatile stock.
- Placing a stop-loss 1.5 to 2 times ATR away means normal swings are less likely to trigger it (see
  [ATR stop](topic:atr-stop)).
- Dividing your risk by ATR is a common way to size a position.
