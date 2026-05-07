"""
Performance metrics on a daily equity curve.

A `pd.Series` indexed by date, value = total portfolio value, is the
canonical input. Trades-DataFrame round-trip pairing (for win rate and
per-stock contribution) lives here too so backtest.py and dashboard.py can
share one FIFO implementation.
"""

import numpy as np
import pandas as pd


# --- top-line metrics ----------------------------------------------------

def total_return(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 0.0
    return float(equity.iloc[-1] / equity.iloc[0] - 1)


def annualized_return(equity: pd.Series) -> float:
    """Geometric annualization assuming ~252 trading days per year."""
    n = len(equity)
    if n < 2:
        return 0.0
    growth = float(equity.iloc[-1] / equity.iloc[0])
    return growth ** (252.0 / n) - 1.0


def sharpe_ratio(equity: pd.Series, rf: float = 0.0) -> float:
    """sqrt(252) * mean(excess daily returns) / std(excess daily returns).

    --- What Sharpe measures -----------------------------------------------
    Risk-adjusted return: how much excess return you earn per unit of
    volatility, annualized. A Sharpe of 1 is decent, 2 is rare, 3+ is
    suspicious (often a sign of survivorship bias or a regime that won't
    last). It penalizes equity curves that get to the same endpoint via a
    bumpy ride more than smooth ones.
    ------------------------------------------------------------------------
    """
    returns = equity.pct_change().dropna()
    if returns.empty:
        return 0.0
    excess = returns - rf / 252.0
    sd = excess.std()
    if sd == 0 or np.isnan(sd):
        return 0.0
    return float(np.sqrt(252) * excess.mean() / sd)


def max_drawdown(equity: pd.Series) -> float:
    """Worst peak-to-trough loss along the curve, as a negative fraction.

    --- Why drawdown matters ----------------------------------------------
    Total return tells you where you ended; drawdown tells you what you had
    to live through to get there. A strategy with 12% CAGR and 50% max
    drawdown is one most humans will abandon at the bottom — making the
    realized return worse than a "worse" strategy with 8% CAGR and 15%
    drawdown they'd actually stick with.
    ------------------------------------------------------------------------
    """
    if equity.empty:
        return 0.0
    return float((equity / equity.cummax() - 1).min())


# --- trade pairing -------------------------------------------------------

def pair_trades(trades_df: pd.DataFrame) -> pd.DataFrame:
    """FIFO-pair buys and sells per ticker into round-trips.

    Returns a DataFrame with columns:
        ticker, buy_date, sell_date, shares, buy_price, sell_price, pnl
    """
    if trades_df.empty:
        return pd.DataFrame(columns=[
            "ticker", "buy_date", "sell_date",
            "shares", "buy_price", "sell_price", "pnl",
        ])

    rounds = []
    for ticker, group in trades_df.sort_values("date").groupby("ticker"):
        buys = []  # FIFO queue of [shares_remaining, price, date]
        for _, row in group.iterrows():
            shares = float(row["shares"])
            price = float(row["price"])
            if row["action"] == "buy":
                buys.append([shares, price, row["date"]])
            elif row["action"] == "sell":
                remaining = shares
                while remaining > 0 and buys:
                    b = buys[0]
                    matched = min(remaining, b[0])
                    rounds.append({
                        "ticker": ticker,
                        "buy_date": b[2],
                        "sell_date": row["date"],
                        "shares": matched,
                        "buy_price": b[1],
                        "sell_price": price,
                        "pnl": (price - b[1]) * matched,
                    })
                    b[0] -= matched
                    remaining -= matched
                    if b[0] <= 1e-12:
                        buys.pop(0)
    return pd.DataFrame(rounds)


def win_rate(trades_df: pd.DataFrame) -> float:
    """Fraction of FIFO-paired round-trips with positive PnL."""
    rounds = pair_trades(trades_df)
    if rounds.empty:
        return 0.0
    return float((rounds["pnl"] > 0).mean())


# --- pretty-printing -----------------------------------------------------

def print_metrics(equity: pd.Series, trades_df: pd.DataFrame, label: str) -> None:
    print(f"\n=== {label} ===")
    print(f"  period:           {equity.index[0].date()} → {equity.index[-1].date()}  ({len(equity)} trading days)")
    print(f"  total return:     {total_return(equity):>8.2%}")
    print(f"  annualized:       {annualized_return(equity):>8.2%}")
    print(f"  sharpe ratio:     {sharpe_ratio(equity):>8.2f}")
    print(f"  max drawdown:     {max_drawdown(equity):>8.2%}")
    print(f"  win rate:         {win_rate(trades_df):>8.2%}  ({len(pair_trades(trades_df))} round-trips)")
