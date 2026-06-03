"""
Pure functions on price DataFrames. No DB, no API.

This is the file that gets the most teaching comments — these are the ideas a
learner most needs to internalize:

  * 12-1 momentum: trailing 12-month return, EXCLUDING the most recent month.
  * Equal weight: a deliberately humble portfolio construction.
  * Trading-day arithmetic: months are weird, indexes lie, use the actual index.
"""

import os

import pandas as pd

LOOKBACK_MONTHS = int(os.environ.get("LOOKBACK_MONTHS", 12))
SKIP_MONTHS = int(os.environ.get("SKIP_MONTHS", 1))
REBALANCE_FREQUENCY = os.environ.get("REBALANCE_FREQUENCY", "bi-monthly").lower()
TOP_N = int(os.environ.get("TOP_N", 10))


def compute_momentum(prices_wide: pd.DataFrame, as_of) -> pd.Series:
    """Score each ticker by its 12-1 momentum as of `as_of`.

    The score is:
        price[as_of - 1mo]  /  price[as_of - 13mo]  -  1

    --- Why exclude the most recent month? --------------------------------
    Stocks that ran up sharply in the last few weeks tend to mean-revert in
    the next few weeks (microstructure, profit-taking, liquidity). Pure
    12-month momentum gets contaminated by this short-term reversal effect.
    Skipping the most recent month — the "1" in "12-1" — removes that noise
    and leaves the slower, more persistent trend that academic studies
    (Jegadeesh & Titman, 1993; Asness et al.) find is actually predictive.
    -----------------------------------------------------------------------

    "1 month" and "13 months" are resolved against the actual trading-day
    index via Index.asof(...), so weekends, holidays, and missing bars don't
    break the signal.
    """
    as_of = pd.Timestamp(as_of)
    skip_target = as_of - pd.DateOffset(months=SKIP_MONTHS)
    look_target = as_of - pd.DateOffset(months=LOOKBACK_MONTHS + SKIP_MONTHS)

    skip_idx = prices_wide.index.asof(skip_target)
    look_idx = prices_wide.index.asof(look_target)
    if pd.isna(skip_idx) or pd.isna(look_idx):
        return pd.Series(dtype=float)

    skip_prices = prices_wide.loc[skip_idx]
    look_prices = prices_wide.loc[look_idx]
    return (skip_prices / look_prices) - 1


def rank_and_select(scores: pd.Series, top_n: int = TOP_N) -> list:
    """Drop NaN, sort descending, take top N tickers.

    --- Why equal weight, not score-weighted? -----------------------------
    The momentum score is a noisy ranking signal. Score-weighted portfolios
    pretend the spread between rank 1 and rank 5 is meaningful — but it
    isn't, really. Equal weight says: "I trust the *order* (these are the
    five strongest trends I see) more than the *magnitudes*." It's robust
    to small ranking errors, simple to implement, and historically holds up
    against fancier weighting schemes.
    -----------------------------------------------------------------------
    """
    return scores.dropna().sort_values(ascending=False).head(top_n).index.tolist()


def month_start_rebalance_dates(index: pd.DatetimeIndex, start, end) -> list:
    """First trading day of each month within [start, end], drawn from the
    actual price index — so we never schedule a rebalance on a weekend or
    market holiday.
    """
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    sliced = index[(index >= start_ts) & (index <= end_ts)]
    if len(sliced) == 0:
        return []
    s = pd.Series(sliced)
    return s.groupby([s.dt.year, s.dt.month]).min().tolist()

def rebalance_dates(index, start, end, frequency=None):
    if frequency is None:
        frequency = REBALANCE_FREQUENCY
    # ... (full function would go here, but simplified for now)
