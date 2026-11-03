# stock-dashboard

A personal desktop dashboard for learning to trade stocks: search symbols, explore them in a tree,
and view trading-platform-style charts.

Built with [PySide6](https://doc.qt.io/qtforpython-6/) (Qt desktop UI) and
[pyqtgraph](https://www.pyqtgraph.org/) (fast interactive charts).

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

The dashboard opens in its own window.

## Layout

- **Top bar:** symbol search and candle size (1D, 1W, 2W, 1M, 3M).
- **Explorer (left):** each searched symbol is a parent node; its children are views (Candles for now).
- **Main area:** the selected view.

## Timeframes

Only daily candles will be downloaded. Larger candles are built from them:
open = first day's open, high = highest high, low = lowest low, close = last day's close.
1D, 1W and 1M are standard; 2W is our own; 3M is a quarterly candle.
