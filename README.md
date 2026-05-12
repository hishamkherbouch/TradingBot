# Equity Momentum Research System

**A Python research system for testing 12-1 momentum across S&P 500 equities, with database-backed market data, transaction-cost-aware backtesting, SPY benchmarking, and paper-trading infrastructure through Alpaca.**

---

## What Is 12-1 Momentum?

Momentum investing is the idea that stocks that have performed well over the recent past tend to keep performing well, and stocks that have performed poorly tend to keep performing poorly. The academic literature (Jegadeesh & Titman, 1993; Carhart, 1997; Asness et al.) has documented this effect across decades and markets.

The "12-1" variant measures a stock's trailing 12-month return but **excludes the most recent month**. Here's why that one-month gap matters:

Stocks that have surged or crashed in the last few weeks often experience a short-term reversal — profit-taking, liquidity effects, or microstructure noise pulls them back in the opposite direction. If you include that final month, you contaminate the slower, more persistent trend signal with a burst of mean-reverting noise. Skipping it gives you a cleaner look at the underlying momentum that — historically — has been the predictive part.

### How the strategy works

1. **Signal construction (monthly):** On the first trading day of each month, compute the 12-1 return for every stock currently in the S&P 500.
2. **Rank and select:** Rank stocks by that score and take the top N (default: 5).
3. **Equal-weight:** Buy each selected stock at an equal dollar weight (e.g., 20% each for N=5). Equal-weight is deliberately simple — it says "I trust the *order* of the rankings more than the *magnitudes*."
4. **Delta rebalancing:** Stocks that remain in the top N from one month to the next are kept, not sold and rebought. Only the difference is traded, minimizing churn and transaction costs.
5. **Benchmark comparison:** Strategy returns are compared against SPY buy-and-hold over the same windows to separate alpha from broad-market beta.

This is not an attempt to build a profitable trading system. It is a research pipeline for understanding how signal construction, universe selection, transaction costs, and market regimes interact in a momentum backtest.

---

## Repository Map

| File | Purpose |
|------|---------|
| `backtest.py` | Main entry point: runs the full historical simulation across three regime windows plus the full sample |
| `live.py` | Daily cron script: refreshes prices from Alpaca, checks for rebalance days, and pushes target portfolio to Alpaca paper trading |
| `dashboard.py` | Generates three matplotlib charts from stored backtest results and saves them to `charts/` |
| `setup_db.py` | Creates or recreates all database tables (PostgreSQL or SQLite) |
| `src/signals.py` | Pure functions: 12-1 momentum scoring, ranking/selection, rebalance-date calendar |
| `src/universe.py` | S&P 500 membership reconstruction: scrapes Wikipedia for current constituents and change log, reconstructs point-in-time membership |
| `src/data.py` | Data fetching layer: Alpaca historical bars (live refresh) and yfinance (historical seed), with bulk chunking and DB inserts |
| `src/db.py` | Database access layer: PostgreSQL and SQLite support for prices, trades, portfolio snapshots, and signals tables |
| `src/metrics.py` | Performance analytics: total return, annualized return (CAGR), Sharpe ratio, max drawdown, FIFO trade pairing, win rate |
| `src/execution.py` | Alpaca paper-trading execution: reads current positions and submits notional market orders to move toward target portfolio |
| `data/sp500.csv` | Cached current S&P 500 constituent list |
| `data/sp500_changes.csv` | Cached S&P 500 change log (additions, removals, dates) |
| `charts/` | Generated output: equity curve, monthly heatmap, per-stock contribution |
| `tests/` | Unit tests for signals.py and metrics.py (pytest) |
| `docs/` | Research report and project documentation |

---

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL (recommended) or SQLite
- An [Alpaca](https://alpaca.markets/) account (free tier is sufficient; paper trading is free)

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd TradingBot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Copy the example and fill in your credentials:

```bash
cp .env.example .env
```

Required variables:

```env
# Alpaca paper trading credentials
ALPACA_API_KEY=your_paper_api_key
ALPACA_SECRET_KEY=your_paper_secret_key

# Database connection
# PostgreSQL (recommended):
DATABASE_URL=postgresql://user:pass@localhost:5432/tradingbot
# SQLite (lightweight fallback):
# DATABASE_URL=sqlite:////absolute/path/to/tradingbot.db

# Strategy parameters (these defaults match the research)
LOOKBACK_MONTHS=12
SKIP_MONTHS=1
TOP_N=5
COST_BPS_PER_SIDE=5
```

### 3. Initialize the database

```bash
python setup_db.py
```

### 4. Seed historical price data

This downloads daily OHLCV data from Yahoo Finance for every ticker that was in the S&P 500 between 2008 and 2024 (~500+ tickers). Expect 10-30 minutes depending on network speed.

```bash
python -c "from src.data import seed_yfinance; seed_yfinance()"
```

### 5. Run tests

```bash
python -m pytest tests/ -v
```

### 6. Run the backtest

```bash
python backtest.py
```

### 7. Generate charts

```bash
python dashboard.py
```

Charts are saved to `charts/01_equity_vs_spy.png`, `charts/02_monthly_heatmap.png`, and `charts/03_per_stock_contribution.png`.

### 8. (Optional) Start live paper trading

```bash
python live.py
```

Designed to run as a weekday cron job. Use `--force` to force a rebalance on non-rebalance days during testing.

---

## Running the Project End-to-End

A minimal run from a fresh clone:

```bash
cp .env.example .env
# edit .env with your Alpaca paper credentials
python setup_db.py
python -m pytest tests/ -v      # verify core logic
python backtest.py              # run backtest
python dashboard.py             # generate charts
python live.py --force          # test live paper-trading (optional)
```

---

## Backtest Results

All results use: 12-1 momentum signal, top-5 stocks, equal-weight portfolio, monthly rebalance, 5 bps slippage per side, point-in-time S&P 500 membership.

| Period | Strategy CAGR | SPY CAGR | Sharpe | Max Drawdown | Win Rate |
|--------|--------------|----------|--------|--------------|----------|
| 2020–2021 (growth/COVID) | 28.87% | 22.80% | 0.75 | −42.47% | 60.75% |
| 2022–2023 (rate hikes) | 0.57% | 1.32% | 0.19 | −30.74% | 59.82% |
| 2024 (mega-cap trend) | 58.02% | 25.59% | 1.38 | −25.28% | 66.00% |
| **Full 2020–2024** | **21.64%** | **14.27%** | **0.67** | **−44.57%** | **62.35%** |

### Regime notes

- **2020–2021 (COVID/growth):** The strategy outperformed SPY by roughly 6 percentage points annualized. Momentum worked well in the growth-fueled recovery, but the −42% drawdown during the March 2020 crash was severe — a momentum portfolio loaded with cyclical names got hit harder than the broad index.
- **2022–2023 (rate hikes):** This was a momentum-killing environment. Rapid sector rotation, whipsaw reversals, and value-over-growth leadership meant the trend-following signal produced essentially flat returns. The strategy underperformed SPY by roughly 75 bps annualized.
- **2024 (mega-cap trend):** A strong trending year — mega-cap tech names dominated and momentum signals captured the move. The 58% CAGR is exceptional and should be viewed as a single-year anomaly, not a sustainable expectation.
- **Full sample:** Over the full five years, the strategy's CAGR exceeded SPY by about 7 percentage points annualized with a Sharpe of 0.67 — decent, but the price was a −44.57% max drawdown.

**Important:** These are backtest results, not live trading performance. See Limitations below.

---

## Live Trading Status

An Alpaca paper-trading account has been running live since May 2026, starting with a $100K notional balance. The `live.py` script runs daily and rebalances monthly to the top-5 momentum picks from the current S&P 500.

This is an experimental live execution designed to test:

- Whether the signal pipeline functions correctly outside of a historical backtest
- How Alpaca notional orders behave with real market fills (bid-ask spread, partial fills)
- Whether the delta-rebalance logic is practical for a live account

Live performance should not be compared head-to-head against backtest results — paper fills differ from real fills, and a few months is too short to draw any conclusions.

---

## Charts

Generated by `dashboard.py` and saved to the `charts/` directory:

| Chart | File | Description |
|-------|------|-------------|
| Equity curve vs. SPY | `charts/01_equity_vs_spy.png` | Strategy and SPY buy-and-hold, both normalized to 1.0 starting value |
| Monthly returns heatmap | `charts/02_monthly_heatmap.png` | Year × month grid showing strategy monthly returns, color-coded green (positive) to red (negative) |
| Per-stock contribution | `charts/03_per_stock_contribution.png` | Horizontal bar chart of cumulative FIFO-paired round-trip PnL by ticker |

---

## Limitations

An honest project acknowledges what it does not do. The following limitations should be understood before drawing conclusions from these results:

- **Past returns ≠ future returns.** Historical backtest performance is not a prediction. Momentum strategies can and do underperform for extended periods.
- **Estimated slippage, not actual fills.** The backtest assumes a flat 5 bps per side of traded volume. Real execution costs vary with liquidity, volatility, and order size. During market stress — the COVID crash, for example — actual slippage would almost certainly be higher.
- **No taxes, borrow costs, or market impact modeled.** These are non-trivial in a real portfolio. Short-term capital gains from monthly rebalancing would reduce after-tax returns significantly. Market impact from buying/selling concentrated positions in less liquid names is not captured.
- **Survivorship bias reduction, not elimination.** Point-in-time S&P 500 reconstruction (walking the Wikipedia change log backward from today's constituents) is a substantial improvement over using today's index membership for the entire history. However, tickers that fully delisted (bankruptcy, going private) are absent from Alpaca's price feed and silently drop out of the eligible universe — a form of delisting bias. Ticker renames and corporate actions can create edge cases in the historical membership reconstruction.
- **Data quality.** yfinance data occasionally has gaps, stale prices, or adjustment anomalies. Individual stock-level bars can be noisy. The aggregate portfolio-level results should be directionally informative but not precise to the basis point.
- **Experimental live execution.** The Alpaca paper-trading integration has been running for weeks, not years. Paper fills are indicative, not identical to live fills (no competition for liquidity, no market impact). Live execution is a learning exercise, not a validated trading system.
- **No out-of-sample forward testing.** The backtest covers 2020–2024. Parameters (12-1 lookback, top-5, 5 bps) were chosen based on prior academic literature, not optimized on this data, but they have not been tested on truly unseen forward data beyond the current paper-trading experiment.
- **Concentrated portfolio risk.** A top-5 equal-weight portfolio is highly concentrated. A single stock's drawdown can dominate monthly returns, and sector clustering (e.g., all five picks being tech) is common in trending markets.

---

## Interview Preparation

If you're discussing this project in a finance-tech, quant, or software engineering interview, you should be able to answer these questions without referencing the code:

1. **What is 12-1 momentum?** Trailing 12-month return, excluding the most recent month. The 1-month skip removes short-term reversal noise, leaving the cleaner, more persistent trend component identified in academic momentum research.

2. **Why skip the most recent month?** Short-term reversal — stocks that surged or crashed in the last few weeks tend to mean-revert due to profit-taking, liquidity effects, and microstructure. Including that month contaminates the signal.

3. **What is survivorship bias, and how does this project address it?** Survivorship bias is the distortion that occurs when you backtest using only stocks that survived to the present — you implicitly select for winners. This project reconstructs point-in-time S&P 500 membership by walking the Wikipedia change log backward, so the universe on each rebalance date reflects what the index actually contained then, not what it contains today.

4. **How does the monthly rebalance work?** On the first trading day of each month, the system computes momentum scores for all eligible stocks, selects the top N, and uses a delta-based adjustment: held positions still in the top N are kept (no sell-and-rebuy churn), new positions are bought, and dropped positions are sold. Transaction costs are applied only to executed dollar volume.

5. **What do Sharpe ratio and max drawdown mean?** Sharpe ratio is annualized excess return divided by annualized volatility — a measure of risk-adjusted return. A Sharpe of 1 is decent; 2+ is rare. Max drawdown is the worst peak-to-trough loss along the equity curve. It measures not just where you ended up, but what you had to survive to get there. A −44% drawdown means the portfolio lost nearly half its value from peak to trough at some point.

6. **What assumptions in this backtest are most unreliable?** Estimated slippage (flat 5 bps doesn't reflect stress periods), absence of taxes and borrow costs, and delisting bias from stocks that disappeared entirely from price feeds. The 2024 58% CAGR window is also a single-year result that should not be extrapolated.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.10+ |
| Data processing | pandas, NumPy |
| Database | PostgreSQL (primary), SQLite (fallback) |
| Market data | yfinance (historical seed), Alpaca API (live refresh) |
| Execution | Alpaca Trading API (paper trading) |
| Visualization | matplotlib |
| Environment | python-dotenv |

---

## License

This project is an educational/research tool. Use at your own risk. Nothing in this repository constitutes financial advice.
