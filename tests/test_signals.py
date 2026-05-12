"""Unit tests for src/signals.py — momentum, ranking, and rebalance dates."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.signals import compute_momentum, rank_and_select, month_start_rebalance_dates


# ---------------------------------------------------------------------------
# compute_momentum
# ---------------------------------------------------------------------------

def test_compute_momentum_basic():
    """12-1 momentum for two tickers with known prices at exactly the right
    asof anchor points.

    Index (month-end snapshots):
        2020-01-31, 2020-06-30, 2020-12-31, 2021-01-31, 2021-06-30, 2021-07-31
    as_of = 2021-08-15
      → skip_target = 2021-07-15   → index.asof → 2021-06-30
      → look_target = 2020-07-15   → index.asof → 2020-06-30

    By hand:
      AAPL  = 150 / 100 - 1 = 0.5
      MSFT  = 240 / 200 - 1 = 0.2
    """
    dates = pd.DatetimeIndex([
        "2020-01-31", "2020-06-30", "2020-12-31",
        "2021-01-31", "2021-06-30", "2021-07-31",
    ])
    prices = pd.DataFrame(
        {
            "AAPL": [50.0, 100.0, 120.0, 125.0, 150.0, 160.0],
            "MSFT": [150.0, 200.0, 210.0, 220.0, 240.0, 250.0],
        },
        index=dates,
    )

    result = compute_momentum(prices, as_of="2021-08-15")

    assert isinstance(result, pd.Series)
    assert result["AAPL"] == pytest.approx(0.5)
    assert result["MSFT"] == pytest.approx(0.2)


def test_compute_momentum_missing_tail():
    """When the lookback target falls before the first available date,
    asof returns NaN and the function should return an empty Series."""
    dates = pd.DatetimeIndex(["2021-01-31", "2021-06-30", "2021-07-31"])
    prices = pd.DataFrame(
        {"TICK": [100.0, 150.0, 160.0]},
        index=dates,
    )
    result = compute_momentum(prices, as_of="2021-08-15")
    assert len(result) == 0


# ---------------------------------------------------------------------------
# rank_and_select
# ---------------------------------------------------------------------------

def test_rank_and_select_basic():
    """Returns top 3 tickers by score, sorted descending, and skips NaN."""
    scores = pd.Series(
        {"A": 0.1, "B": 0.5, "C": -0.1, "D": 0.3},
        name="momentum",
    )
    result = rank_and_select(scores, top_n=3)
    assert result == ["B", "D", "A"]


def test_rank_and_select_with_nan():
    """NaN scores are dropped before ranking; they never appear in output."""
    scores = pd.Series(
        {"X": 0.2, "Y": np.nan, "Z": 0.8, "W": np.nan},
    )
    result = rank_and_select(scores, top_n=2)
    assert result == ["Z", "X"]
    assert "Y" not in result
    assert "W" not in result


def test_rank_and_select_top_n_larger_than_available():
    """When top_n exceeds the number of valid scores, all are returned."""
    scores = pd.Series({"P": 0.4, "Q": 0.6})
    result = rank_and_select(scores, top_n=5)
    assert result == ["Q", "P"]


def test_rank_and_select_all_nan():
    """All-NaN input returns an empty list."""
    scores = pd.Series({"A": np.nan, "B": np.nan})
    result = rank_and_select(scores, top_n=3)
    assert result == []


# ---------------------------------------------------------------------------
# month_start_rebalance_dates
# ---------------------------------------------------------------------------

def test_month_start_rebalance_dates():
    """First trading day of each month in [2020-01-15, 2020-03-15].

    Index = business days Jan–Mar 2020.
    Jan starts on 2020-01-15 (the first business day ≥ start),
    Feb starts on 2020-02-03 (first Mon–Fri day in Feb),
    Mar starts on 2020-03-02 (first Mon–Fri day in Mar).
    """
    index = pd.bdate_range("2020-01-01", "2020-03-31")
    result = month_start_rebalance_dates(index, start="2020-01-15", end="2020-03-15")

    expected = [
        pd.Timestamp("2020-01-15"),
        pd.Timestamp("2020-02-03"),
        pd.Timestamp("2020-03-02"),
    ]
    assert result == expected


def test_month_start_rebalance_dates_empty_range():
    """Empty range (start after end) returns an empty list."""
    index = pd.bdate_range("2020-01-01", "2020-03-31")
    result = month_start_rebalance_dates(index, start="2020-03-15", end="2020-01-15")
    assert result == []


def test_month_start_rebalance_dates_no_dates_in_range():
    """When no index entries fall in [start, end], result is empty."""
    index = pd.bdate_range("2020-01-01", "2020-01-31")
    result = month_start_rebalance_dates(index, start="2020-02-01", end="2020-02-28")
    assert result == []
