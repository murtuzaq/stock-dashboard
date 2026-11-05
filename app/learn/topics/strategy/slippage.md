+++
id = "slippage"
title = "Slippage"
category = "Strategy"
related = ["commission", "backtest"]
summary = "The gap between the price you expected and the price you actually got."
+++
**Slippage** is the difference between the price you expect and the price you actually get filled at, caused by the
spread between buyers and sellers and by your own order moving the price.

In a [backtest](topic:backtest) it is modelled as a percentage: every buy fills that much **higher** than the open and
every sell that much **lower**. Leaving it at zero makes results look better than they could be in real life.
