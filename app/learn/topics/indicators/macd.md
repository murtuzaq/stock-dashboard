+++
id = "macd"
title = "MACD"
category = "Indicators"
aliases = ["moving average convergence divergence", "MACD line"]
related = ["signal-line", "histogram", "crossovers", "sma"]
summary = "Momentum: how far a fast average has pulled away from a slow one, and whether that gap is growing."
+++
**MACD** (Moving Average Convergence Divergence) measures **momentum**. It is built from three lines:

1. The **MACD line**: a 12-period *exponential* average minus a 26-period one.
2. The [signal line](topic:signal-line): a 9-period average of the MACD line.
3. The [histogram](topic:histogram): the gap between the two.

## How to read it
- MACD **above** its signal line (bars above zero): momentum is rising.
- MACD **below** its signal line: momentum is falling.
- A **cross** of the two lines is a common buy or sell *confirmation* (see [crossovers](topic:crossovers)).
- MACD above **zero** means the fast average is above the slow one, which fits an uptrend.

## Limits
Like all averages it lags. It works best in trending markets and whipsaws in sideways ones.
