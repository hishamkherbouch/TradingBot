"""
Thin functional wrapper over psycopg2. No ORM.

Everything that touches the DB lives here so the strategy code in signals.py
and metrics.py stays pure and unit-testable on bare DataFrames.
"""

import json
import os
from datetime import date as date_type
from typing import Iterable, Optional

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()


def get_conn():
    """Open a new psycopg2 connection from DATABASE_URL.

    Caller is responsible for closing (or using `with` — psycopg2 connections
    support the context-manager protocol and auto-commit on exit).
    """
    url = os.environ["DATABASE_URL"]
    return psycopg2.connect(url)


def _query_df(sql: str, params=()) -> pd.DataFrame:
    """Run a SELECT and return a DataFrame. We avoid pandas.read_sql here
    because pandas 3.x emits a UserWarning when passed a raw DBAPI connection
    (it wants SQLAlchemy). Sticking to psycopg2 keeps the no-ORM goal clean.
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


# --- prices ---------------------------------------------------------------

def insert_prices(rows) -> int:
    """Bulk insert daily bars. Accepts a DataFrame or an iterable of tuples
    in the order (ticker, date, open, high, low, close, volume).

    Conflicts on (ticker, date) are silently dropped — re-running a fetch
    that overlaps existing data is safe.
    """
    if isinstance(rows, pd.DataFrame):
        cols = ["ticker", "date", "open", "high", "low", "close", "volume"]
        rows = list(rows[cols].itertuples(index=False, name=None))
    rows = list(rows)
    if not rows:
        return 0
    sql = (
        "INSERT INTO prices (ticker, date, open, high, low, close, volume) "
        "VALUES %s ON CONFLICT (ticker, date) DO NOTHING"
    )
    with get_conn() as conn, conn.cursor() as cur:
        execute_values(cur, sql, rows)
        return cur.rowcount


def get_prices_wide(start, end) -> pd.DataFrame:
    """Return a wide-format DataFrame:
      index   = trading dates (DatetimeIndex)
      columns = ticker
      values  = close

    This is the canonical shape consumed by signals.compute_momentum and the
    backtest loop. Pivoting once here keeps the rest of the code framework-free.
    """
    sql = (
        "SELECT date, ticker, close FROM prices "
        "WHERE date >= %s AND date <= %s ORDER BY date"
    )
    long = _query_df(sql, (start, end))
    if long.empty:
        return pd.DataFrame()
    long["date"] = pd.to_datetime(long["date"])
    wide = long.pivot(index="date", columns="ticker", values="close").sort_index()
    return wide.astype(float)


def latest_price_date(ticker: str) -> Optional[date_type]:
    """Most recent date we have for this ticker, or None. Drives incremental
    fetches in live.py — we only ask Alpaca for bars we don't already have."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT MAX(date) FROM prices WHERE ticker = %s", (ticker,))
        row = cur.fetchone()
        return row[0] if row else None


# --- trades ---------------------------------------------------------------

def insert_trade(ticker, date, action, price, shares, signal_value, source) -> None:
    sql = (
        "INSERT INTO trades (ticker, date, action, price, shares, signal_value, source) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
    )
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, (ticker, date, action, price, shares, signal_value, source))


def get_trades(source: str) -> pd.DataFrame:
    """Read all trades for a given source ('backtest' or 'live')."""
    sql = (
        "SELECT id, ticker, date, action, price, shares, signal_value, source "
        "FROM trades WHERE source = %s ORDER BY date, id"
    )
    df = _query_df(sql, (source,))
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        for c in ("price", "shares", "signal_value"):
            df[c] = pd.to_numeric(df[c])
    return df


# --- snapshots ------------------------------------------------------------

def upsert_snapshot(date, source, total_value, cash, holdings: dict) -> None:
    sql = """
        INSERT INTO portfolio_snapshots (date, source, total_value, cash, holdings)
        VALUES (%s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (date, source) DO UPDATE SET
            total_value = EXCLUDED.total_value,
            cash        = EXCLUDED.cash,
            holdings    = EXCLUDED.holdings
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, (date, source, total_value, cash, json.dumps(holdings)))


def get_snapshots(source: str) -> pd.DataFrame:
    sql = (
        "SELECT date, source, total_value, cash, holdings "
        "FROM portfolio_snapshots WHERE source = %s ORDER BY date"
    )
    df = _query_df(sql, (source,))
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df["total_value"] = pd.to_numeric(df["total_value"])
        df["cash"] = pd.to_numeric(df["cash"])
    return df


# --- signals --------------------------------------------------------------

def insert_signals(rows: Iterable) -> int:
    """rows: iterable of (date, ticker, momentum_score, rank)."""
    rows = list(rows)
    if not rows:
        return 0
    sql = """
        INSERT INTO signals (date, ticker, momentum_score, rank) VALUES %s
        ON CONFLICT (date, ticker) DO UPDATE SET
            momentum_score = EXCLUDED.momentum_score,
            rank           = EXCLUDED.rank
    """
    with get_conn() as conn, conn.cursor() as cur:
        execute_values(cur, sql, rows)
        return cur.rowcount
