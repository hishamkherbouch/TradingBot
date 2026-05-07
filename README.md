# TradingBot

Educational Python trading bot for researching and paper-trading a monthly
12-1 momentum strategy on the S&P 500.

The project has four main workflows:

- Build a local Postgres database for prices, trades, snapshots, and signals.
- Seed historical adjusted price data for a point-in-time S&P 500 universe.
- Backtest an equal-weight top-N momentum portfolio against SPY.
- Run a daily Alpaca paper-trading rebalance and generate performance charts.

This is a learning project, not investment advice. Use paper trading first and
review the assumptions before risking real capital.

## Strategy

The strategy ranks eligible S&P 500 stocks by 12-1 momentum:

- Look back 12 months.
- Skip the most recent month to reduce short-term reversal noise.
- Select the top `TOP_N` tickers.
- Hold them equal-weighted.
- Rebalance on the first trading day of each month.

The backtest uses point-in-time index membership reconstructed from Wikipedia's
S&P 500 constituent and change tables. This avoids the worst survivorship bias
from testing only today's index members.

Backtest assumptions include:

- Initial capital: `$100,000`
- Default selection count: `TOP_N=5`
- Slippage: `5` basis points per side by default
- Benchmark: SPY buy-and-hold
- Test windows: 2020-2021, 2022-2023, 2024, and full sample 2020-2024

## Project Structure

```text
.
|-- backtest.py          # Runs the historical backtest
|-- dashboard.py         # Generates charts from backtest results
|-- live.py              # Daily Alpaca paper-trading entry point
|-- setup_db.py          # Drops and recreates the Postgres schema
|-- requirements.txt     # Python dependencies
|-- .env.example         # Required environment variables
|-- data/
|   |-- sp500.csv
|   `-- sp500_changes.csv
|-- charts/
|   |-- 01_equity_vs_spy.png
|   |-- 02_monthly_heatmap.png
|   `-- 03_per_stock_contribution.png
`-- src/
    |-- data.py          # Price fetching and historical seeding
    |-- db.py            # Postgres access helpers
    |-- execution.py     # Alpaca paper-trading rebalance helpers
    |-- metrics.py       # Performance metrics and trade pairing
    |-- signals.py       # Momentum scoring and rebalance dates
    `-- universe.py      # Point-in-time S&P 500 universe logic
```

## Requirements

- Python 3.10+
- PostgreSQL
- Alpaca paper-trading credentials for `live.py` and Alpaca data fetching
- Internet access for yfinance, Wikipedia cache refreshes, and Alpaca APIs

Python dependencies are listed in `requirements.txt`:

- `alpaca-py`
- `pandas`
- `numpy`
- `matplotlib`
- `psycopg2-binary`
- `python-dotenv`
- `lxml`
- `yfinance`

## Setup

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_BASE_URL=https://paper-api.alpaca.markets

DATABASE_URL=postgresql://user:pass@localhost:5432/tradingbot

LOOKBACK_MONTHS=12
SKIP_MONTHS=1
TOP_N=5
```

Create the Postgres database if it does not exist yet:

```bash
createdb tradingbot
```

Then create the schema:

```bash
python setup_db.py
```

Warning: `setup_db.py` drops and recreates all project tables.

## Seed Historical Data

The recommended historical seed path uses yfinance because it provides adjusted
daily data over a longer history than the free Alpaca IEX feed:

```bash
python -c "from src.data import seed_yfinance; seed_yfinance()"
```

This fills the `prices` table for every ticker that was in the S&P 500 at any
point in the configured historical window, plus `SPY`.

To seed from Alpaca instead:

```bash
python -m src.data 2018-12-01 2024-12-31
```

The Alpaca path requires `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`.

## Run a Backtest

After the schema and price data are in place:

```bash
python backtest.py
```

The script clears prior `backtest` trades, snapshots, and signals, then prints
metrics for each test window:

- Total return
- Annualized return
- Sharpe ratio
- Max drawdown
- FIFO-paired win rate
- SPY buy-and-hold CAGR

Backtest results are persisted in Postgres:

- `trades`
- `portfolio_snapshots`
- `signals`

## Generate Charts

After running a backtest:

```bash
python dashboard.py
```

The dashboard writes:

- `charts/01_equity_vs_spy.png`
- `charts/02_monthly_heatmap.png`
- `charts/03_per_stock_contribution.png`

To display charts interactively as well:

```bash
DASHBOARD_SHOW=1 python dashboard.py
```

## Run Live Paper Trading

`live.py` is intended as a daily cron entry point for Alpaca paper trading. It:

1. Refreshes missing recent daily bars.
2. Checks whether the latest trading day is the first trading day of the month.
3. Computes the current top momentum picks.
4. Closes positions that are no longer selected.
5. Submits notional market buy orders for new selected positions.
6. Records live trades and a portfolio snapshot.

Run it manually:

```bash
python live.py
```

Example cron entry for weekdays around one hour before the US market close:

```cron
0 14 * * 1-5  cd /path/to/TradingBot && .venv/bin/python live.py >> live.log 2>&1
```

The code constructs the Alpaca `TradingClient` with `paper=True`, so this entry
point targets paper trading.

## Configuration

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ALPACA_API_KEY` | none | Alpaca API key |
| `ALPACA_SECRET_KEY` | none | Alpaca secret key |
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` in example | Included in `.env.example`; current code uses Alpaca `paper=True` instead |
| `DATABASE_URL` | none | Postgres connection string |
| `LOOKBACK_MONTHS` | `12` | Momentum lookback window |
| `SKIP_MONTHS` | `1` | Recent months excluded from momentum |
| `TOP_N` | `5` | Number of tickers selected each rebalance |
| `COST_BPS_PER_SIDE` | `5` | Backtest slippage per side |
| `DASHBOARD_SHOW` | `0` | Set to `1` to show matplotlib windows |

## Data Notes

- `data/sp500.csv` caches current S&P 500 constituents.
- `data/sp500_changes.csv` caches index additions and removals.
- Run `python -m src.universe --refresh` to refresh both files from Wikipedia.
- Yahoo Finance symbols use dashes for class shares, but the database stores
  the original dot form used by Wikipedia, such as `BRK.B`.
- Delisted or renamed tickers may have incomplete data from public/free data
  sources. The code skips tickers with unavailable price data.

## Development

There is no dedicated test suite yet. A quick syntax check is:

```bash
python -m py_compile setup_db.py backtest.py dashboard.py live.py src/*.py
```

For deeper verification, run the full workflow against a local Postgres
database:

```bash
python setup_db.py
python -c "from src.data import seed_yfinance; seed_yfinance()"
python backtest.py
python dashboard.py
```
