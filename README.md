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

## Search

Type a symbol (`AAPL`), a company name or part of one (`apple`, `bank of am`), or a group
(`nasdaq`, `s&p`, `etf`). Use ↑/↓ and Enter, or click.

Choosing a group (Nasdaq-100, S&P 500, an exchange, or ETFs) turns it into a blue filter chip:
the list then shows that group's members, and typing searches only inside it.
Backspace on an empty search (or clicking the chip) removes the filter.

Symbol lists are downloaded on first run into `cache/` and refreshed weekly:
all US-listed stocks and ETFs from Nasdaq Trader, Nasdaq-100 members from Nasdaq,
and S&P 500 members from Wikipedia. Code lives in [app/search/](app/search/).

## Timeframes

Only daily candles will be downloaded. Larger candles are built from them:
open = first day's open, high = highest high, low = lowest low, close = last day's close.
1D, 1W and 1M are standard; 2W is our own; 3M is a quarterly candle.
