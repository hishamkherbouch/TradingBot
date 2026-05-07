"""
Hand-rolled backtest of the 12-1 momentum strategy.

What makes this version more honest than the toy v1:
  - Universe is the current S&P 500 (from src.universe), not 20 hand-picks.
  - Rebalance is delta-based (no fake sell-and-rebuy of names we still hold)
    so transaction costs are charged on real turnover, not ritual churn.
  - Costs: 5 bps per side of every executed dollar — defensible slippage
    for liquid mega-caps; commissions on Alpaca paper are zero so this is
    pure slippage assumption.
  - Multi-window output: three disjoint test periods (no in-sample tuning,
    same parameters everywhere) so we can see whether the edge is consistent
    across regimes or only shows up in one.
"""

import os
from typing import Dict, List, Tuple

import pandas as pd
from dotenv import load_dotenv

from src import db, signals, metrics
from src.universe import get_sp500_at

load_dotenv()


INITIAL_CASH = 100_000.0
TOP_N = int(os.environ.get("TOP_N", 5))

# Slippage assumption per side. 5 bps = 0.05%. With monthly rebalance and
# delta-only trading, full-portfolio turnover years bleed roughly 60-120 bps
# to costs — in line with what real momentum strategies actually pay on
# liquid US equities.
COST_BPS_PER_SIDE = float(os.environ.get("COST_BPS_PER_SIDE", 5))


def _mark_to_market(cash: float, holdings: Dict[str, float], prices_today: pd.Series) -> float:
    return cash + sum(shares * float(prices_today[t]) for t, shares in holdings.items())


def _trade(date, ticker, action, price, shares, signal_value):
    """Record a trade row. Wrapper exists so the rebalance function reads cleanly."""
    db.insert_trade(
        ticker=ticker, date=date, action=action,
        price=price, shares=shares, signal_value=signal_value, source="backtest",
    )


def _rebalance(
    date,
    cash: float,
    holdings: Dict[str, float],
    prices_today: pd.Series,
    picks: List[str],
    scores: pd.Series,
) -> Tuple[float, Dict[str, float]]:
    """Delta rebalance toward an equal-weight target portfolio.

    Steps:
      1. Mark-to-market today's holdings → total equity.
      2. Liquidate names not in picks (one sell each).
      3. For each pick: compute target shares = (equity / N) / price,
         and trade only the delta vs. current shares (buy or sell).
      4. Charge slippage: cost = (sell_volume + buy_volume) * bps/10000,
         deducted from cash.

    A held name that's still in picks is *not* sold and rebought — that
    fake churn was a cost-modeling problem in the v1 backtest, and it'd
    also show up in live execution as needless taxable events / slippage.
    """
    total_equity = _mark_to_market(cash, holdings, prices_today)
    new_holdings: Dict[str, float] = {}
    sell_volume = 0.0
    buy_volume = 0.0

    def _signal(t):
        v = scores.get(t, float("nan"))
        return None if pd.isna(v) else float(v)

    # 1. Sell anything not in the new picks.
    for ticker, shares in list(holdings.items()):
        if ticker in picks:
            continue
        price = float(prices_today[ticker])
        gross = shares * price
        sell_volume += gross
        cash += gross
        _trade(date, ticker, "sell", price, shares, _signal(ticker))

    # 2. Resize each pick toward target dollar weight.
    if picks:
        target_dollar = total_equity / len(picks)
        for ticker in picks:
            price = float(prices_today[ticker])
            target_shares = target_dollar / price
            current = holdings.get(ticker, 0.0)
            delta = target_shares - current
            if delta > 1e-9:
                gross = delta * price
                buy_volume += gross
                cash -= gross
                _trade(date, ticker, "buy", price, delta, _signal(ticker))
            elif delta < -1e-9:
                gross = -delta * price
                sell_volume += gross
                cash += gross
                _trade(date, ticker, "sell", price, -delta, _signal(ticker))
            new_holdings[ticker] = target_shares

    # 3. Apply slippage on real traded volume.
    cash -= (sell_volume + buy_volume) * COST_BPS_PER_SIDE / 10_000.0

    return cash, new_holdings


def run_period(prices_wide: pd.DataFrame, start: str, end: str, label: str) -> pd.Series:
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    period_index = prices_wide.index[(prices_wide.index >= start_ts) & (prices_wide.index <= end_ts)]
    if len(period_index) == 0:
        print(f"[{label}] no price data in [{start}, {end}], skipping.")
        return pd.Series(dtype=float)

    rebal_dates = set(signals.month_start_rebalance_dates(prices_wide.index, start, end))

    cash = INITIAL_CASH
    holdings: Dict[str, float] = {}
    equity_curve: List[Tuple[pd.Timestamp, float]] = []

    for date in period_index:
        prices_today = prices_wide.loc[date]

        if date in rebal_dates:
            # Point-in-time eligibility: only tickers that were actually in
            # the S&P 500 on this rebalance date are candidates. This is what
            # kills the "added because it 10x'd" survivorship bias.
            eligible_at_date = get_sp500_at(date) & set(prices_wide.columns)
            scores = signals.compute_momentum(prices_wide[list(eligible_at_date)], date)
            picks = signals.rank_and_select(scores, TOP_N)

            ranked = scores.dropna().sort_values(ascending=False)
            db.insert_signals([
                (date.date(), tkr, float(score), rank)
                for rank, (tkr, score) in enumerate(ranked.items(), start=1)
            ])

            cash, holdings = _rebalance(date.date(), cash, holdings, prices_today, picks, scores)

        total_value = _mark_to_market(cash, holdings, prices_today)
        equity_curve.append((date, total_value))
        db.upsert_snapshot(date.date(), "backtest", total_value, cash, holdings)

    equity = pd.Series(
        [v for _, v in equity_curve],
        index=pd.DatetimeIndex([d for d, _ in equity_curve]),
        name="equity",
    )
    trades_df = db.get_trades("backtest")
    period_trades = trades_df[(trades_df["date"] >= start_ts) & (trades_df["date"] <= end_ts)]
    metrics.print_metrics(equity, period_trades, label)
    return equity


def _spy_buy_and_hold(prices_wide: pd.DataFrame, start: str, end: str) -> pd.Series:
    """Buy-and-hold SPY benchmark over [start, end], normalized so we can
    eyeball strategy CAGR against the index over the same window."""
    if "SPY" not in prices_wide.columns:
        return pd.Series(dtype=float)
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    spy = prices_wide["SPY"]
    spy = spy[(spy.index >= start_ts) & (spy.index <= end_ts)].dropna()
    if spy.empty:
        return spy
    return INITIAL_CASH * (spy / spy.iloc[0])


def main():
    prices_wide = db.get_prices_wide("2018-12-01", "2024-12-31")
    if prices_wide.empty:
        raise SystemExit("No prices in DB. Run setup_db.py and seed_database first.")

    # Wipe prior backtest state so reruns don't leave orphan trades/snapshots
    # mixing across windows.
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM trades WHERE source='backtest'")
        cur.execute("DELETE FROM portfolio_snapshots WHERE source='backtest'")
        cur.execute("DELETE FROM signals")

    # Three disjoint regimes. No parameter tuning between windows — same
    # 12-1 momentum, top-5, equal-weight, monthly rebalance, 5 bps per side
    # everywhere. We're asking: is the edge consistent, or did one window
    # carry the whole result?
    windows = [
        ("Window A (2020-2021, growth/COVID)",        "2020-01-01", "2021-12-31"),
        ("Window B (2022-2023, rate-hike whipsaw)",   "2022-01-01", "2023-12-31"),
        ("Window C (2024, trending mega-cap)",        "2024-01-01", "2024-12-31"),
        ("Full sample (2020-2024)",                   "2020-01-01", "2024-12-31"),
    ]
    for label, start, end in windows:
        run_period(prices_wide, start, end, label)
        spy = _spy_buy_and_hold(prices_wide, start, end)
        if not spy.empty:
            spy_cagr = (spy.iloc[-1] / spy.iloc[0]) ** (252.0 / len(spy)) - 1
            print(f"  SPY buy-hold CAGR ({start[:4]}–{end[:4]}): {spy_cagr:.2%}")


if __name__ == "__main__":
    main()
