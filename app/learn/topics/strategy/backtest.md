+++
id = "backtest"
title = "Backtest"
category = "Strategy"
aliases = ["backtesting", "backtested"]
related = ["buy-and-hold", "max-drawdown", "win-rate", "slippage"]
summary = "Replaying a strategy over past prices to see what it would have done."
+++
A **backtest** replays a strategy's rules over past prices and records the trades it *would* have made.

## How this dashboard does it
- A signal is judged at a candle's **close**; the trade fills at the **next candle's open**.
- [Commission](topic:commission) and [slippage](topic:slippage) are charged on every fill.
- [Stops and targets](topic:stop-loss) are checked inside each candle. A gap fills at the open; if both are hit in one
  candle, the stop is assumed to hit first.
- One position at a time, using all the money.

## Read results with care
- The past does not predict the future.
- A strategy tuned until it fits history perfectly (*overfitting*) often fails on new data.
- Compare with [buy and hold](topic:buy-and-hold): a complicated strategy that does not beat it may not be worth it.

*For learning only; this is not investment advice.*
