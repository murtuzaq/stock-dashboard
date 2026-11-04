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
- **Explorer (left):** each searched symbol is a parent node; its children are views:
  - **Price** (opens first): closing prices as an area chart, like Google Finance (one point per candle,
    so on 1D it is daily closes). Green if up over the selected range, red if down. Hover for date and close.
  - **Candles**: open/high/low/close as a candlestick chart.
  - **Stoch RSI**: the Stochastic RSI indicator (standard settings 14, 14, 3, 3). Above 80 = overbought,
    below 20 = oversold; K is the fast line, D its average. Indicator math lives in [app/indicators/](app/indicators/).
  - **History**: the same data as a table, newest first (Date, Open, High, Low, Close, Change, Volume),
    with a summary line for the range (high, low). Hover a column header for what it means.
- **Header:** latest close, then the change over the selected range (e.g. "−14.22% (−41.46) year to date",
  measured from the first close in the range, as Google Finance does), then today's change.
- **Main area:** the selected views. **Click** a view to show it alone; **Ctrl+click** to add or remove views,
  **Shift+click** to select a run of them. Selected views stack top to bottom in Explorer order, share one
  time axis (scroll and zoom together, dates shown once at the bottom), and can be resized by dragging
  the dividers. All views follow the candle size and range.

## Search

Type a symbol (`AAPL`), a company name or part of one (`apple`, `bank of am`), or a group
(`nasdaq`, `s&p`, `etf`). Use ↑/↓ and Enter, or click.

Choosing a group (Nasdaq-100, S&P 500, an exchange, or ETFs) turns it into a blue filter chip:
the list then shows that group's members, and typing searches only inside it.
Backspace on an empty search (or clicking the chip) removes the filter.

Symbol lists are downloaded on first run into `cache/` and refreshed weekly:
all US-listed stocks and ETFs from Nasdaq Trader, Nasdaq-100 members from Nasdaq,
and S&P 500 members from Wikipedia. Code lives in [app/search/](app/search/).

## Candle size vs. range

- **Candle** (top bar: 1D, 1W, 2W, 1M, 3M): how much time *one candle* covers.
- **Range** (under the chart: 1M, 3M, 6M, YTD, 1Y, 5Y, 10Y, Max): how much history *the chart* shows.
  Default is 1Y. Drag or scroll the chart to move through time; the price axis fits what's in view.

Candles are placed one per trading session, so weekends and holidays don't leave gaps
(the same as trading platforms).

Price history comes from Yahoo Finance (via `yfinance`), adjusted for stock splits (not dividends,
matching Google Finance and TradingView). Code lives in [app/prices/](app/prices/).

## Stored price data

Every daily row downloaded is kept in a local SQLite database, `data/prices.db` (not in git),
so the data is available for backtesting and charts open instantly.

- First time a symbol is opened: its full history is downloaded once.
- After that, at most every 6 hours: only the last ~2 weeks are fetched and added.
- Those 2 weeks overlap rows already stored. If they disagree (a stock split, or Yahoo corrected
  its data), the symbol's full history is downloaded again so everything stays consistent.
- Dividends and splits are stored too (`dividend`, `split` columns), for total-return backtests later.

Tables: `daily(symbol, date, open, high, low, close, volume, dividend, split)` and
`symbols(symbol, checked_at)`. To read it in your own scripts:

```python
import sqlite3, pandas as pd
with sqlite3.connect('data/prices.db') as db:
    ibm = pd.read_sql_query("SELECT * FROM daily WHERE symbol = 'IBM'", db, parse_dates=['date'])
```

## Timeframes

Only daily candles are downloaded. Larger candles are built from them:
open = first day's open, high = highest high, low = lowest low, close = last day's close.
1D, 1W and 1M are standard; 2W is our own; 3M is a quarterly candle.
