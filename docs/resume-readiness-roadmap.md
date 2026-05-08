# TradingBot Resume Readiness Roadmap

## Purpose

TradingBot should be repositioned as an equity momentum research system, not as a finished trading bot or a promise of profitable trading. The goal is to make the project credible for finance-tech, analyst, business operations, and technical recruiting conversations by showing clear research logic, honest assumptions, and explainable engineering.

## Current State

TradingBot is an in-progress Python prototype that tests a 12-1 equity momentum strategy across S&P 500 stocks. It includes:

- Historical price storage in PostgreSQL
- 12-1 momentum signal generation
- Monthly top-N portfolio selection
- Equal-weight portfolio rebalancing
- Estimated transaction costs
- SPY benchmark comparison
- Performance metrics such as return, Sharpe ratio, max drawdown, and win rate
- Chart generation for equity curve, monthly returns, and per-stock contribution
- Experimental Alpaca paper-trading integration

This is a useful learning and research foundation, but it is not resume-ready until the project can be explained clearly and reproduced by another person.

## Positioning Target

Use this name in resume or portfolio contexts:

**Equity Momentum Research System**

Avoid these names or claims:

- Trading bot
- AI trading bot
- Profitable bot
- Stock predictor
- Automated money-making system

The stronger framing is:

> A Python research system for testing 12-1 momentum across S&P 500 equities, with database-backed market data, transaction-cost-aware backtesting, SPY benchmarking, and paper-trading infrastructure.

## Resume-Ready Bar

The project is resume-ready when all of the following are true:

- [ ] README explains the strategy in plain English
- [ ] README includes architecture, setup, and commands
- [ ] Backtest results are shown in a table
- [ ] Charts are included or linked from the README
- [ ] Limitations are clearly stated
- [ ] Core logic has basic tests
- [ ] The project can be explained in a 60-second interview answer
- [ ] The repo can be cloned and run from setup instructions

## Phase 1: Make The Project Understandable

### 1. Rename the story

Update README title and description to focus on research:

```md
# Equity Momentum Research System

A Python research system for testing 12-1 momentum across S&P 500 equities with PostgreSQL-backed market data, monthly rebalancing, transaction cost assumptions, SPY benchmarking, and paper-trading infrastructure through Alpaca.
```

### 2. Add a simple strategy explanation

Include this explanation in the README:

```md
The strategy ranks stocks by 12-1 momentum: trailing 12-month return excluding the most recent month. Each rebalance date, the system selects the top N eligible S&P 500 stocks, weights them equally, and compares the resulting portfolio against SPY.
```

### 3. Add a repo map

Document the main files:

```text
backtest.py           Runs historical strategy simulation
live.py               Experimental Alpaca paper-trading runner
dashboard.py          Generates charts from stored results
setup_db.py           Creates PostgreSQL schema
src/signals.py        Momentum scoring and rebalance date logic
src/universe.py       S&P 500 universe reconstruction
src/data.py           Market data fetching and storage helpers
src/db.py             PostgreSQL access layer
src/metrics.py        Performance metrics and trade analysis
src/execution.py      Alpaca paper-trading execution helpers
```

## Phase 2: Add Real Research Output

### 1. Run the backtest

Run the project locally with a configured database and data source.

Target output table:

```text
Period | Strategy CAGR | SPY CAGR | Sharpe | Max Drawdown | Notes
2020-2021 | TBD | TBD | TBD | TBD | Growth/COVID regime
2022-2023 | TBD | TBD | TBD | TBD | Rate-hike regime
2024 | TBD | TBD | TBD | TBD | Mega-cap trend regime
Full sample | TBD | TBD | TBD | TBD | 2020-2024
```

### 2. Save results

Create:

```text
docs/research-report.md
```

Include:

- Research question
- Data sources
- Methodology
- Results table
- Chart screenshots or chart links
- Interpretation
- Limitations
- Next steps

### 3. Add chart references

The repo already has charts under `charts/`. The README should reference:

- `charts/01_equity_vs_spy.png`
- `charts/02_monthly_heatmap.png`
- `charts/03_per_stock_contribution.png`

## Phase 3: Make It Technically Credible

### 1. Add tests

Add tests for core pure logic before testing API/database code.

Recommended test files:

```text
tests/test_signals.py
tests/test_metrics.py
```

Test cases:

- `compute_momentum` calculates the expected return from known prices
- `rank_and_select` returns the highest scores in order
- `month_start_rebalance_dates` returns first trading day per month
- `max_drawdown` returns expected peak-to-trough loss
- `annualized_return` handles a simple equity curve correctly

### 2. Add reproducible commands

Add this to README after tests exist:

```bash
python -m pytest
python setup_db.py
python backtest.py
python dashboard.py
```

### 3. Add environment documentation

Document required variables without secrets:

```env
DATABASE_URL=postgresql://...
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
TOP_N=5
LOOKBACK_MONTHS=12
SKIP_MONTHS=1
COST_BPS_PER_SIDE=5
```

## Phase 4: Strengthen Finance Credibility

### 1. Add a limitations section

Use honest limitations. This makes the project look more mature.

Include:

- Historical returns do not imply future returns
- Backtest uses estimated slippage, not actual fills
- Taxes, borrow costs, and market impact are not modeled
- Point-in-time S&P 500 reconstruction reduces survivorship bias but does not fully eliminate delisting/data bias
- Paper-trading execution is experimental
- Strategy may underperform in sideways or mean-reverting markets

### 2. Add one sensitivity analysis

Test at least one parameter variation:

- Top 5 vs top 10 stocks
- 5 bps vs 10 bps transaction costs
- Monthly vs quarterly rebalance

Do not overbuild this. One small sensitivity table is enough.

### 3. Add a concise interpretation

Example:

```md
The goal of this project is not to claim a profitable live strategy. The goal is to build a transparent research pipeline and understand how signal construction, universe selection, transaction costs, and risk metrics change backtest results.
```

## Interview Ownership Checklist

Before putting this project on a resume, be able to answer these questions without reading code:

1. What is 12-1 momentum?
2. Why skip the most recent month?
3. Why compare against SPY?
4. What is survivorship bias?
5. How does the monthly rebalance work?
6. What do Sharpe ratio and max drawdown mean?
7. What assumptions make the backtest unreliable?
8. What would you improve if you had another week?

## Suggested Final Resume Bullet

Use this only after README, results, limitations, and basic tests exist:

- Built an equity momentum research system in Python with PostgreSQL, pandas, Alpaca, and yfinance, implementing 12-1 momentum signals, transaction-cost-aware backtesting, SPY benchmarking, performance analytics, and paper-trading infrastructure.

## Immediate Next Three Tasks

1. Write the main README with strategy explanation, repo map, setup instructions, and limitations.
2. Add `docs/research-report.md` with backtest results and charts.
3. Add tests for `signals.py` and `metrics.py`.

If only one thing gets done next, write the README. It is the highest leverage upgrade because it forces the project to become explainable.
