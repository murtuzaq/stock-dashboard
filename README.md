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
- **Explorer (left):** each searched symbol is a parent node. **Click the stock's name** for its company overview
  (see below); its children are views:
  - **Price** (opens first): closing prices as an area chart, like Google Finance (one point per candle,
    so on 1D it is daily closes). Green if up over the selected range, red if down. Hover for date and close.
  - **Candles**: open/high/low/close as a candlestick chart.
  - **SMA 50/150/200**: the 50, 150 and 200-day simple moving averages (long-term trend). Alone, drawn over a
    faint price line; **Ctrl+click it with Price or Candles and the lines are drawn on that chart instead**.
    On bigger candles the days are converted (50/150/200 days = 10/30/40 weekly candles).
  - **Volume**: shares traded per candle as bars (green = closed up, red = closed down), with a yellow
    20-candle average. The legend shows the latest volume as a multiple of that average (e.g. "0.63× average").
    Big bars on a price move suggest conviction; stack it under Candles to read them together.
  - **Stoch RSI**: the Stochastic RSI indicator (standard settings 14, 14, 3, 3). Above 80 = overbought,
    below 20 = oversold; K is the fast line, D its average. Indicator math lives in [app/indicators/](app/indicators/).
  - **MACD (12, 26, 9)**: MACD line, signal line and histogram (momentum confirmation).
  - **ATR (14)**: Average True Range, the typical move per candle in dollars and % of price (risk, stop sizing).
  - **Rel. Strength**: stock ÷ S&P 500 (Yahoo `^GSPC`), set to 100 at the start of the range. Above 100 = beating
    the market since then. The legend compares both returns.
  - **Revenue/EPS Growth**: quarterly and annual revenue and diluted EPS with QoQ/YoY growth (business health).
    Yahoo provides only ~5 quarters and ~4 years; figures are stored in `data/prices.db` (table `financials`)
    and refreshed weekly, so the history grows over time.
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

## Company overview

Click a stock's **name** in the Explorer (the row above Price) to see:

- **What the company does** (Yahoo's description) and key numbers: price, market value, P/E, dividend, 52-week range,
  beta, employees, website.
- **What investors like / don't like**, worked out from the numbers with simple, stated rules (growth, profit margin,
  P/E and PEG, debt, cash, dividend, analyst ratings and price targets, short interest, trend, and performance vs the
  S&P 500). Every point quotes its number and says in one line what the measure means; a missing figure just gives
  no point. The thresholds are constants at the top of [app/company/assessment.py](app/company/assessment.py).
- **Best strategy for this stock:** every strategy that can run on it (its own and the library templates) is
  backtested on daily candles over the past 5 years and compared with simply buying and holding. The verdict says
  plainly when buy & hold won. Click a strategy's row to open its full backtest.

The profile is stored in `data/prices.db` (table `documents`) and refreshed weekly. Past results don't guarantee
future ones, and the best of several strategies is partly luck: use it as a starting point.

## Library menu

**Library > Stocks…** (Ctrl+Shift+S) opens the Stock Library on the right: every stock whose prices are stored on this
computer, with company name, last close, day change, how far back its prices go, and when they were last updated.
A stock joins the library the first time its prices are downloaded (searching it anywhere does that); use the
panel's search box to add more. **Right-click** a stock to open it or *Add to portfolio >* any saved portfolio (or a
new one); **double-click** to open it.

**Library > Strategies…** (Ctrl+Shift+T) opens the Strategy Library: library templates first, then each stock's own
strategies. Pick one to read its rules and act on it: *Backtest on <the stock on screen>* (another stock's strategy
is copied first), *Copy to another stock…*, *Save to Library*, *Edit…*, *Delete…*. **+ New template…** opens the
Strategy Builder for a template that works on any stock; when you save or cancel, you are back in the library.

Each library strategy says **what it does**, its **style** (trend following, mean reversion ...), **why it can work**,
what to **watch out for**, and **references** (books and peer-reviewed papers). Built-in templates:

| Strategy | Style | Main sources |
|---|---|---|
| Golden Cross (50/200-day) | Trend following | Murphy (1999); Brock, Lakonishok & LeBaron (1992); Sullivan, Timmermann & White (1999) |
| 200-Day Trend Filter (Faber) | Trend following, risk control (use Candle 1M) | Faber (2007); Siegel (2014); Moskowitz, Ooi & Pedersen (2012) |
| Turtle Breakout (20/10-day) | Breakout | Faith (2007); Covel (2007) |
| 52-Week High Breakout | Momentum / breakout | George & Hwang (2004); O'Neil (2009) |
| Minervini Trend Template (simplified) | Growth / momentum | Minervini (2013, 2017); O'Neil (2009) |
| RSI(2) Pullback (Connors) | Mean reversion (daily candles) | Connors & Alvarez (2009) |
| MACD Crossover with Trend Filter | Momentum | Appel (2005); Murphy (1999) |
| Bollinger Band Bounce | Mean reversion | Bollinger (2001) |
| Relative Strength Momentum | Momentum | Jegadeesh & Titman (1993); Antonacci (2014); Daniel & Moskowitz (2016) |
| Long-Term Trend, MACD + Stoch RSI, ATR Swing Trade | Dashboard examples (not published systems) | — |

None of these is guaranteed to work: each is a documented starting point to backtest on your stocks (the company
overview compares them all). The Strategy Builder's **Description** box adds a summary to your own strategies; a
copied strategy keeps its source's reasoning and references.

## Portfolios

A portfolio is a named set of stocks, saved as `portfolios/<name>.json` (commit them like the strategies). Every
change is saved at once, so there is no Save step.

- **File > New Portfolio** (Ctrl+N) adds a node called "Portfolio 1" and lets you type a better name. Rename
  later with double-click or F2 (names must be unique, ignoring case).
- **File > Load Portfolio...** (Ctrl+O) lists the saved portfolios that are not open and opens the one you pick.
  Open portfolios are not remembered between runs; load them again.
- **Right-click a portfolio:** *Add Stock...* opens the Add Stock panel on the right: search, pick as many stocks
  as you like (each is added immediately), press **Done**. Also *Rename...*, *Close Portfolio* (keeps the file) and
  *Delete Portfolio...* (removes the file; the stocks and their strategies are untouched).
- **Right-click any stock** (on its own, or inside another portfolio): *Add to portfolio >* copies it into another
  open portfolio (or a new one). Inside a portfolio, *Remove from portfolio* takes it out of that portfolio only.
- The search bar in the top bar still works as before: a searched stock appears as its own top-level node.
- A stock inside a portfolio has the same views as any other. Strategies belong to the ticker, so the same
  strategies show under every copy of it. Portfolio-wide strategies and backtests are planned.

## Info Wizard (learn the lingo)

**View > Info Wizard** (Ctrl+I) turns on a teaching mode. While it is on, every word, row or column title that has
an explanation is **underlined**. **Double-click** one and the **Info** panel opens on the right (below the strategy
builder if that is open) with a short explanation, a diagram where it helps, and links to related topics. Use the
arrows to go back, and close the panel with its X; the next double-click opens it again.

- It covers the Explorer rows, indicator legends, strategy summaries and rule text, the History and Growth column
  titles, and labels such as Range and Candle.
- While it is on, double-clicking a portfolio opens its explanation instead of renaming it; use F2 or the
  right-click menu to rename.
- **Not underlined?** Right-click the word and choose *Request info on...*. The request is saved in
  `info_requests.json` (with where you saw it) so a topic can be written for it. Send that file to the developer.
- Turned off, nothing is underlined and everything behaves as before. The setting is remembered between runs.

The explanations are Markdown files in [app/learn/topics/](app/learn/topics/); see
[app/learn/README.md](app/learn/README.md) for how to add one.

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

## Strategies and backtesting

Each stock has a **Strategies** folder in the Explorer: the stock's own strategies, then the library
templates (grey, "· library"), which you can try on any stock.

- **Click a strategy** to backtest it over the selected Range and Candle size: a summary (return vs buy & hold,
  trades, win rate, max drawdown, time in market), an equity curve against buy & hold, and every trade
  (signal and fill dates, prices, P/L, exit reason; an open position is shown as unrealized).
  Capital, commission and slippage are editable on the panel and saved with the strategy.
- **Ctrl+click Candles, MACD, etc.** to stack them with the strategy: every chart shows the trades
  (▲ BUY / ▼ SELL at the signal candle, fill dots, entry line, stop/target levels, green/red shading).
- **Right-click** a stock or the folder: *New Strategy…*. Right-click a strategy: *Edit…, Duplicate,
  Copy to another stock…, Save to Library, Delete…* (library templates: *Copy to this stock and customise…*).
- **Strategy Builder** (opens on the right): Start (new, or copy any existing strategy) → Name →
  BUY rules → SELL rules and exits (stop-loss %, ATR stop, take-profit %) → Review → Save & Backtest.
  Indicators include Close/Open/High/Low, SMA, MACD, Stoch RSI, RSI, ATR, Volume, Rel. Strength, **Donchian channel**
  (highest high / lowest low of the previous N days, for breakouts) and **Bollinger Bands**.
  Each rule is *[indicator] [is above / is below / crosses above / crosses below] [indicator or number]*,
  combined with ALL (AND) or ANY (OR). *Is above/below* holds on every candle; *crosses* happens on one candle
  (optionally "within the last N candles").

**Backtest assumptions:** signals are judged at a candle's close and trades fill at the next candle's open
(no look-ahead); fills include slippage and commission; whole shares, all available cash, long only, one position
at a time; stops and targets are checked inside each candle (gaps fill at the open; if both are hit in one candle,
the stop is assumed first). Indicators warm up on the full stored history, so SMA 200 is ready from day one of
the range.

**Files:** strategies are JSON in [strategies/](strategies/) (commit them): `strategies/library/*.json` for
templates, `strategies/<SYMBOL>/*.json` per stock. A copy is independent of its original and records it in
`origin_id`. Code: engine in [app/strategy/](app/strategy/) (no GUI: `model`, `catalog`, `signals`, `backtest`,
`describe`, `repository`); GUI in `app/qtrender/dashboard/panels/strategy_view.py`, `dashboard/trade_overlay.py` and
`builder/wizard.py` (the rules behind them are in `app/core/strategies/` and `app/core/builder/`).

## Architecture: GUI and logic are separate

Code is grouped by feature (screen area). Each feature has its logic in `core/` and its widgets in `qtrender/`
under the same name, so everything about, say, the Explorer is in `core/explorer/` and `qtrender/explorer/`.

```
app/
  prices/ indicators/ strategy/ search/   data, calculations, strategy engine (no GUI)
  portfolio/                              saved portfolios: model + JSON files (no GUI)
  company/                                company profiles from Yahoo (cached) and the like/dislike rules (no GUI)
  learn/                                  the teaching library: topic files, loader/validator, linker, requests (no GUI)
  core/                                   application logic (no GUI: tests/test_boundary.py enforces it)
    common/        colours, text formatting, background loading
    dashboard/     DashboardController + DashboardView, view layout, the models each panel draws
    explorer/      ExplorerController + ExplorerTreeView, selection rules, what the tree lists
    builder/       WizardController + WizardView, step rules, condition-row rules
    strategies/    StrategyController (actions), strategy service, results as text
    searchbar/     SearchController + SearchView, catalogue state and filter
    portfolios/    PortfolioController (File menu, rename, right-click actions), AddStockController, service
    overview/      the company overview model (facts, likes/dislikes, strategy comparison and verdict)
    library/       StockLibraryController and StrategyLibraryController (the Library menu's panels)
    learn/         InfoController (Info Wizard on/off, history, requests), UI-to-topic map, text linking
  qtrender/                               the only Qt / pyqtgraph code
    dashboard/     view area, chart building blocks, trade overlay, panels/ (one widget per view)
    explorer/ builder/ searchbar/ portfolios/ library/ learn/   the widgets for those features
    header.py menu_bar.py side_panel.py dialogs.py style.py gui_thread.py richtext.py    window-level pieces
                                          (side_panel.py = the right-hand dock: Strategy Builder, Add Stock, Stock and Strategy Library;
                                          the Info dock is in learn/; layouts.py = small layout helpers)
  main.py                                 composition root: builds controllers and widgets, connects them
```

A widget only draws and reports what the user did. Its controller decides what that means and drives the widget
back through a small protocol (`DashboardView`, `ExplorerTreeView`, `WizardView`, `SearchView`, `AddStockView`, `InfoView`, `Dialogs`), so
another toolkit only has to implement those protocols and the drawing. Slow work goes through
`core.common.background.BackgroundLoader` (Qt supplies the "run on the GUI thread" function).

## Tests

```bash
pytest
```
