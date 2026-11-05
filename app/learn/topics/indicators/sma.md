+++
id = "sma"
title = "SMA"
category = "Indicators"
aliases = ["simple moving average", "moving average"]
related = ["macd", "crossovers", "candlestick"]
summary = "The average closing price over the last N candles: a smoothed line that shows the trend."
+++
The **simple moving average (SMA)** adds up the last *N* closing prices and divides by *N*. Each new candle drops the
oldest price and adds the newest, so the line "moves" along with the chart.

## Why traders use it
- It smooths out day-to-day noise, so the **trend** is easier to see.
- Price **above a rising** average usually means an uptrend; **below a falling** one, a downtrend.
- Longer averages react more slowly: the 50-day shows the medium-term trend, the 200-day the long-term trend.

## In this dashboard
The SMA view draws the **50, 150 and 200-day** averages. On weekly or monthly candles the same number of *days* is
converted into candles (50 days is about 10 weekly candles). Many swing traders only buy when
price > 50 > 150 > 200.

## Limits
An average is a **lagging** indicator: it confirms a trend after it has started, and it gives many false signals when
the market moves sideways.
