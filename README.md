# stock-dashboard

A personal dashboard for learning to trade stocks: search symbols, explore them in a tree,
and view TradingView-style charts.

Built with [NiceGUI](https://nicegui.io) (Python UI in the browser) and
[TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts).

## Setup (Git Bash)

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

## Run

```bash
python app/main.py
```

Then open http://localhost:8080.

## Layout

- **Top bar:** symbol search and candle size (1D, 1W, 2W, 1M, 3M).
- **Explorer (left):** each searched symbol is a parent node; its children are views (Candles for now).
- **Main area:** the selected view.

## Timeframes

Only daily candles will be downloaded. Larger candles are built from them:
open = first day's open, high = highest high, low = lowest low, close = last day's close.
1D, 1W and 1M are standard; 2W is our own; 3M is a quarterly candle.
