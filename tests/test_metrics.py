"""Unit tests for src/metrics.py — performance metrics and trade pairing."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.metrics import (
    total_return,
    annualized_return,
    sharpe_ratio,
    max_drawdown,
    pair_trades,
    win_rate,
)


# ---------------------------------------------------------------------------
# total_return
# ---------------------------------------------------------------------------

def test_total_return_basic():
    """100 → 150 over 5 days should return 0.5 (50%)."""
    equity = pd.Series(
        [100.0, 110.0, 120.0, 130.0, 150.0],
        index=pd.bdate_range("2020-01-01", periods=5),
    )
    assert total_return(equity) == pytest.approx(0.50)


def test_total_return_loss():
    """100 → 75 should return -0.25 (-25%)."""
    equity = pd.Series(
        [100.0, 90.0, 80.0, 75.0],
        index=pd.bdate_range("2020-01-01", periods=4),
    )
    assert total_return(equity) == pytest.approx(-0.25)


def test_total_return_too_short():
    """Single-point series has no return."""
    equity = pd.Series([100.0], index=[pd.Timestamp("2020-01-01")])
    assert total_return(equity) == 0.0


# ---------------------------------------------------------------------------
# annualized_return
# ---------------------------------------------------------------------------

def test_annualized_return_one_year():
    """100 → 121 over exactly 252 days → 21% annualized."""
    equity = pd.Series(
        [100.0] + [None] * 250 + [121.0],
        index=pd.bdate_range("2020-01-01", periods=252),
    )
    equity = equity.ffill()
    assert annualized_return(equity) == pytest.approx(0.21, abs=1e-6)


def test_annualized_return_two_years():
    """100 → 144 over 504 days (2 years) → 20% annualized."""
    equity = pd.Series(
        [100.0] + [None] * 502 + [144.0],
        index=pd.bdate_range("2020-01-01", periods=504),
    )
    equity = equity.ffill()
    assert annualized_return(equity) == pytest.approx(0.20, abs=1e-6)


def test_annualized_return_too_short():
    """Single point returns 0.0."""
    equity = pd.Series([100.0], index=[pd.Timestamp("2020-01-01")])
    assert annualized_return(equity) == 0.0


# ---------------------------------------------------------------------------
# sharpe_ratio
# ---------------------------------------------------------------------------

def test_sharpe_ratio_flat():
    """Zero-volatility equity curve has undefined Sharpe → returns 0.0."""
    equity = pd.Series(
        [100.0] * 10,
        index=pd.bdate_range("2020-01-01", periods=10),
    )
    assert sharpe_ratio(equity) == 0.0


def test_sharpe_ratio_known_returns():
    """Construct a curve with known daily returns and verify Sharpe.

    With perfectly consistent 0.5% daily returns, std is effectively zero
    but pandas gives a tiny non-zero std. Sharpe should be very large (>1000).
    """
    equity = pd.Series(
        [100.0, 100.5, 101.0, 101.5, 102.0],  # 0.5% daily, perfectly consistent
        index=pd.bdate_range("2020-01-01", periods=5),
    )
    sr = sharpe_ratio(equity)
    # With near-perfect consistency, Sharpe is extremely high
    assert sr > 100.0
    # sqrt(252) * 0.005 / tiny_std → should be well over 1000
    assert sr < 10000.0  # Sanity upper bound


def test_sharpe_ratio_with_volatility():
    """Equity curve with some volatility should produce a positive Sharpe."""
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.01, 252)  # 0.1% mean, 1% vol daily
    equity = 100.0 * np.cumprod(1 + returns)
    equity = pd.Series(equity, index=pd.bdate_range("2020-01-01", periods=252))
    sr = sharpe_ratio(equity)
    assert sr > 0.0  # Should be positive with positive mean returns
    # sqrt(252) * 0.001 / 0.01 ≈ 1.58 theoretically, but with sampling noise
    assert sr < 3.0  # Sanity upper bound


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------

def test_max_drawdown_simple():
    """100 → 150 → 90 → 120. Max drawdown = 90/150 - 1 = -0.4 (-40%)."""
    equity = pd.Series(
        [100.0, 150.0, 90.0, 120.0],
        index=pd.bdate_range("2020-01-01", periods=4),
    )
    assert max_drawdown(equity) == pytest.approx(-0.40, abs=1e-6)


def test_max_drawdown_no_drawdown():
    """Monotonically increasing equity has 0 drawdown."""
    equity = pd.Series(
        [100.0, 110.0, 120.0, 130.0],
        index=pd.bdate_range("2020-01-01", periods=4),
    )
    assert max_drawdown(equity) == 0.0


def test_max_drawdown_empty():
    """Empty series returns 0.0."""
    equity = pd.Series(dtype=float)
    assert max_drawdown(equity) == 0.0


# ---------------------------------------------------------------------------
# pair_trades
# ---------------------------------------------------------------------------

def test_pair_trades_simple_buy_sell():
    """One buy then one sell for the same ticker."""
    trades = pd.DataFrame({
        "ticker": ["AAPL", "AAPL"],
        "date": [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01")],
        "action": ["buy", "sell"],
        "price": [100.0, 120.0],
        "shares": [10.0, 10.0],
    })
    rounds = pair_trades(trades)
    assert len(rounds) == 1
    assert rounds.iloc[0]["ticker"] == "AAPL"
    assert rounds.iloc[0]["buy_price"] == 100.0
    assert rounds.iloc[0]["sell_price"] == 120.0
    assert rounds.iloc[0]["shares"] == 10.0
    assert rounds.iloc[0]["pnl"] == pytest.approx(200.0)


def test_pair_trades_partial_sell():
    """Buy 10, sell 5, then sell 5 more."""
    trades = pd.DataFrame({
        "ticker": ["AAPL", "AAPL", "AAPL"],
        "date": [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01"), pd.Timestamp("2020-03-01")],
        "action": ["buy", "sell", "sell"],
        "price": [100.0, 120.0, 110.0],
        "shares": [10.0, 5.0, 5.0],
    })
    rounds = pair_trades(trades)
    assert len(rounds) == 2
    # First sell: 5 shares @ 120
    assert rounds.iloc[0]["pnl"] == pytest.approx(100.0)
    # Second sell: 5 shares @ 110
    assert rounds.iloc[1]["pnl"] == pytest.approx(50.0)


def test_pair_trades_multiple_tickers():
    """Trades for two tickers should be paired separately."""
    trades = pd.DataFrame({
        "ticker": ["AAPL", "MSFT", "AAPL", "MSFT"],
        "date": [
            pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-01"),
            pd.Timestamp("2020-02-01"), pd.Timestamp("2020-02-01"),
        ],
        "action": ["buy", "buy", "sell", "sell"],
        "price": [100.0, 200.0, 110.0, 180.0],
        "shares": [10.0, 5.0, 10.0, 5.0],
    })
    rounds = pair_trades(trades)
    assert len(rounds) == 2
    aapl = rounds[rounds["ticker"] == "AAPL"].iloc[0]
    msft = rounds[rounds["ticker"] == "MSFT"].iloc[0]
    assert aapl["pnl"] == pytest.approx(100.0)
    assert msft["pnl"] == pytest.approx(-100.0)


def test_pair_trades_empty():
    """Empty DataFrame returns empty DataFrame with correct columns."""
    trades = pd.DataFrame(columns=["ticker", "date", "action", "price", "shares"])
    rounds = pair_trades(trades)
    assert len(rounds) == 0
    assert list(rounds.columns) == ["ticker", "buy_date", "sell_date", "shares", "buy_price", "sell_price", "pnl"]


# ---------------------------------------------------------------------------
# win_rate
# ---------------------------------------------------------------------------

def test_win_rate_all_winners():
    """All round-trips are profitable → 100% win rate."""
    trades = pd.DataFrame({
        "ticker": ["AAPL", "AAPL"],
        "date": [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01")],
        "action": ["buy", "sell"],
        "price": [100.0, 120.0],
        "shares": [10.0, 10.0],
    })
    assert win_rate(trades) == 1.0


def test_win_rate_mixed():
    """One winner, one loser → 50% win rate."""
    trades = pd.DataFrame({
        "ticker": ["AAPL", "AAPL", "MSFT", "MSFT"],
        "date": [
            pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01"),
            pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01"),
        ],
        "action": ["buy", "sell", "buy", "sell"],
        "price": [100.0, 120.0, 200.0, 180.0],
        "shares": [10.0, 10.0, 5.0, 5.0],
    })
    assert win_rate(trades) == 0.5


def test_win_rate_all_losers():
    """All round-trips are losses → 0% win rate."""
    trades = pd.DataFrame({
        "ticker": ["AAPL", "AAPL"],
        "date": [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01")],
        "action": ["buy", "sell"],
        "price": [100.0, 80.0],
        "shares": [10.0, 10.0],
    })
    assert win_rate(trades) == 0.0


def test_win_rate_empty():
    """No trades → 0% win rate."""
    trades = pd.DataFrame(columns=["ticker", "date", "action", "price", "shares"])
    assert win_rate(trades) == 0.0
