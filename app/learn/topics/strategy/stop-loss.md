+++
id = "stop-loss"
title = "Stop-loss"
category = "Strategy"
aliases = ["stop loss", "stop-loss order"]
related = ["take-profit", "atr-stop"]
summary = "An exit that sells automatically if the price falls a set percentage below what you paid."
+++
A **stop-loss** sells automatically when the price falls a set percentage below your entry price. It limits how much a
single trade can lose.

For example, an 8% stop on a stock bought at $100 sells if it reaches $92.

## Things to know
- A stop does not guarantee that exact price: if a stock **gaps** down overnight, you are sold at the lower open.
- Too tight a stop gets triggered by normal swings; too loose a stop lets losses grow.
- See [ATR stop](topic:atr-stop) for a volatility-based way to choose the distance.
