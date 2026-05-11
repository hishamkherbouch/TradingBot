"""
Universe definition + price-data fetching from two sources.

Two data sources are used by design:

  - Alpaca (StockHistoricalDataClient): live trading needs Alpaca anyway for
    submitting orders, and Alpaca is also the source of refresh data in live.py.
    Free-tier IEX feed only goes back to ~2016, so it's not enough for a
    long-history backtest.

  - yfinance (Yahoo Finance): free, goes back decades, has split + dividend
    adjustment. Used for the one-shot historical seed of the prices table.
    Quality is variable but adequate for a learning project.

For consistency, the backtest reads everything from the prices table — it
doesn't care which source put each row there.
"""

import os
from datetime import datetime
from typing import Iterable, List

import pandas as pd
from dotenv import load_dotenv

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment

from src import db

load_dotenv()


from src.universe import get_sp500, get_all_historical_tickers, get_sp500_at

# Span of our historical backtest (and therefore the price data we need).
HIST_START = "2008-01-01"
HIST_END = "2024-12-31"

# Universe of every ticker that was in the S&P 500 at any point during our
# backtest window. We need price data for all of them, even ones no longer
# in the index — otherwise we can't run an honest point-in-time strategy.
UNIVERSE = sorted(get_all_historical_tickers(HIST_START, HIST_END))

# Benchmark — fetched and stored alongside, but excluded from the strategy
# universe. The dashboard plots strategy equity vs. SPY buy-and-hold.
BENCHMARK = "SPY"

# Alpaca caps per-request symbol counts; chunk to be safe.
_FETCH_CHUNK = 50


def _client() -> StockHistoricalDataClient:
    return StockHistoricalDataClient(
        os.environ["ALPACA_API_KEY"],
        os.environ["ALPACA_SECRET_KEY"],
    )


def fetch_bars(tickers: Iterable[str], start, end) -> pd.DataFrame:
    """Fetch daily bars for `tickers` from Alpaca. Returns long-format
    DataFrame with columns: ticker, date, open, high, low, close, volume."""
    tickers = list(tickers)
    req = StockBarsRequest(
        symbol_or_symbols=tickers,
        timeframe=TimeFrame.Day,
        start=pd.Timestamp(start).to_pydatetime(),
        end=pd.Timestamp(end).to_pydatetime(),
        # 'all' applies both split AND dividend adjustments. Without this we'd
        # get raw prices: every split discontinuity (AAPL 4-for-1 in 2020,
        # NVDA 10-for-1 in 2024, TSLA 3-for-1 in 2022) becomes a fake "−75%
        # one-day return" that destroys the momentum signal across that date.
        # Total return (price + dividends) is also what we actually care about
        # for backtesting — strategies are evaluated on TR, not price-only.
        adjustment=Adjustment.ALL,
    )
    bars = _client().get_stock_bars(req)
    df = bars.df  # MultiIndex (symbol, timestamp), cols: open/high/low/close/volume/...
    if df.empty:
        return pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"])
    df = df.reset_index()
    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    df = df.rename(columns={"symbol": "ticker"})
    return df[["ticker", "date", "open", "high", "low", "close", "volume"]]


# --- yfinance path (historical seeding) ---------------------------------

def _yf_symbol(t: str) -> str:
    # Yahoo uses dashes for class shares (BRK.B → BRK-B). Our DB stores the
    # original (dot) form so the rest of the code matches Wikipedia.
    return t.replace(".", "-")


def fetch_bars_yfinance(tickers: List[str], start, end) -> pd.DataFrame:
    """Bulk fetch from Yahoo Finance, auto-adjusted for splits AND dividends.

    yfinance is occasionally flaky (rate limits, transient network issues);
    callers should be prepared to retry or skip empty chunks.
    """
    import yfinance as yf
    if not tickers:
        return pd.DataFrame()
    yf_to_orig = {_yf_symbol(t): t for t in tickers}
    raw = yf.download(
        tickers=list(yf_to_orig.keys()),
        start=str(start),
        end=str(pd.Timestamp(end) + pd.Timedelta(days=1))[:10],  # yf 'end' is exclusive
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="ticker",
    )
    if raw is None or raw.empty:
        return pd.DataFrame()

    rows = []
    if len(yf_to_orig) == 1:
        # Single-ticker shape: flat columns.
        only_yt = next(iter(yf_to_orig))
        for ts, r in raw.iterrows():
            if pd.isna(r.get("Close")):
                continue
            rows.append((
                yf_to_orig[only_yt], ts.date(),
                float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"]),
                int(r["Volume"]) if pd.notna(r.get("Volume")) else 0,
            ))
    else:
        top = set(raw.columns.get_level_values(0))
        for yt, orig in yf_to_orig.items():
            if yt not in top:
                continue
            sub = raw[yt]
            for ts, r in sub.iterrows():
                if pd.isna(r.get("Close")):
                    continue
                rows.append((
                    orig, ts.date(),
                    float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"]),
                    int(r["Volume"]) if pd.notna(r.get("Volume")) else 0,
                ))
    return pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close", "volume"])


def seed_yfinance(start=HIST_START, end=HIST_END, only_missing: bool = False) -> int:
    """Historical seed of the prices table from yfinance.

    Uses the full historical universe (every ticker that was ever in the S&P
    500 between HIST_START and HIST_END). Auto-adjusted for splits and
    dividends. Idempotent — ON CONFLICT DO NOTHING in insert_prices means
    re-running won't dupe rows.
    """
    tickers = list(UNIVERSE) + [BENCHMARK]
    if only_missing:
        with db.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT ticker FROM prices")
            existing = {row[0] for row in cur.fetchall()}
            cur.close()
        tickers = [t for t in tickers if t not in existing]
        print(f"Skipping {len(existing)} tickers already in DB; fetching {len(tickers)} new ones.")

    total = 0
    for i in range(0, len(tickers), _FETCH_CHUNK):
        batch = tickers[i:i + _FETCH_CHUNK]
        try:
            df = fetch_bars_yfinance(batch, start, end)
        except Exception as exc:
            print(f"  [{i:3d}-{i+len(batch):3d}] FETCH FAILED ({type(exc).__name__}): {exc}")
            continue
        if df.empty:
            print(f"  [{i:3d}-{i+len(batch):3d}] no bars returned")
            continue
        db.insert_prices(df)
        total += len(df)
        print(f"  [{i:3d}-{i+len(batch):3d}] {len(df):>6d} bars across {df['ticker'].nunique()} tickers")
    print(f"Seeded ~{total} price rows for {len(tickers)} tickers ({start} → {end}) via yfinance.")
    return total


# --- Alpaca path (still used by live.py for incremental refresh) --------

def seed_database(start, end, only_missing: bool = False) -> int:
    """Chunked fetch of UNIVERSE + BENCHMARK from Alpaca, inserted into prices.

    Some tickers may have no data on the IEX feed (recently listed names,
    delisted-then-relisted, ticker reuses). Empty chunks are skipped.

    With only_missing=True, skip any ticker that's already in the prices
    table — useful for incrementally extending coverage to historical S&P
    500 members without re-downloading what we already have.
    """
    tickers = list(UNIVERSE) + [BENCHMARK]
    if only_missing:
        with db.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT ticker FROM prices")
            existing = {row[0] for row in cur.fetchall()}
            cur.close()
        tickers = [t for t in tickers if t not in existing]
        print(f"Skipping {len(existing)} tickers already in DB; fetching {len(tickers)} new ones.")

    total = 0
    for i in range(0, len(tickers), _FETCH_CHUNK):
        batch = tickers[i:i + _FETCH_CHUNK]
        try:
            df = fetch_bars(batch, start, end)
        except Exception as exc:
            print(f"  [{i:3d}-{i+len(batch):3d}] FETCH FAILED ({type(exc).__name__}): {exc}")
            continue
        if df.empty:
            print(f"  [{i:3d}-{i+len(batch):3d}] no bars returned")
            continue
        db.insert_prices(df)
        total += len(df)
        print(f"  [{i:3d}-{i+len(batch):3d}] {len(df):>6d} bars across {df['ticker'].nunique()} tickers")
    print(f"Seeded ~{total} price rows for {len(tickers)} tickers ({start} → {end}).")
    return total


if __name__ == "__main__":
    # Convenience: `python -m src.data 2018-12-01 2024-12-31`
    import sys
    s, e = sys.argv[1], sys.argv[2]
    seed_database(s, e)
