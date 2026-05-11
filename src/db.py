"""
Thin DB wrapper with Postgres and SQLite support.

Postgres remains the default/primary path. SQLite exists so the project can run
in lightweight local environments where a Postgres service is not available.
"""

import json
import os
import sqlite3
from datetime import date as date_type
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import unquote, urlparse

import pandas as pd
from dotenv import load_dotenv

load_dotenv()


def _db_url() -> str:
    return os.environ["DATABASE_URL"]


def _backend() -> str:
    url = _db_url()
    if url.startswith("sqlite://"):
        return "sqlite"
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return "postgres"
    raise ValueError(f"Unsupported DATABASE_URL: {url}")


def _sqlite_path() -> str:
    url = _db_url()
    parsed = urlparse(url)
    path = unquote(parsed.path or "")
    if not path:
        raise ValueError("SQLite DATABASE_URL is missing a path")
    if parsed.netloc and parsed.netloc not in ("", "localhost"):
        # sqlite:////abs/path form keeps abs path in parsed.path. If netloc is
        # used unusually, preserve it.
        path = f"//{parsed.netloc}{path}"
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path)


def get_conn():
    """Open a DB connection from DATABASE_URL."""
    if _backend() == "sqlite":
        conn = sqlite3.connect(_sqlite_path())
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    import psycopg2
    return psycopg2.connect(_db_url())


def _query_df(sql: str, params=()) -> pd.DataFrame:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close()
    return pd.DataFrame(rows, columns=cols)


def _placeholder(n: int) -> str:
    return "(" + ", ".join(["?"] * n) + ")"


# --- prices ---------------------------------------------------------------

def insert_prices(rows) -> int:
    if isinstance(rows, pd.DataFrame):
        cols = ["ticker", "date", "open", "high", "low", "close", "volume"]
        rows = list(rows[cols].itertuples(index=False, name=None))
    rows = list(rows)
    if not rows:
        return 0

    if _backend() == "sqlite":
        sql = (
            "INSERT OR IGNORE INTO prices (ticker, date, open, high, low, close, volume) "
            f"VALUES {_placeholder(7)}"
        )
        with get_conn() as conn:
            cur = conn.cursor()
            cur.executemany(sql, rows)
            conn.commit()
            count = cur.rowcount
            cur.close()
            return count

    from psycopg2.extras import execute_values
    sql = (
        "INSERT INTO prices (ticker, date, open, high, low, close, volume) "
        "VALUES %s ON CONFLICT (ticker, date) DO NOTHING"
    )
    with get_conn() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows)
        count = cur.rowcount
        conn.commit()
        cur.close()
        return count


def get_prices_wide(start, end) -> pd.DataFrame:
    sql = (
        "SELECT date, ticker, close FROM prices "
        "WHERE date >= %s AND date <= %s ORDER BY date"
    )
    if _backend() == "sqlite":
        sql = sql.replace("%s", "?")
        params = (
            pd.Timestamp(start).date().isoformat(),
            pd.Timestamp(end).date().isoformat(),
        )
    else:
        params = (start, end)
    long = _query_df(sql, params)
    if long.empty:
        return pd.DataFrame()
    long["date"] = pd.to_datetime(long["date"])
    wide = long.pivot(index="date", columns="ticker", values="close").sort_index()
    return wide.astype(float)


def latest_price_date(ticker: str) -> Optional[date_type]:
    sql = "SELECT MAX(date) FROM prices WHERE ticker = %s"
    params = (ticker,)
    if _backend() == "sqlite":
        sql = sql.replace("%s", "?")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        cur.close()
        return pd.to_datetime(row[0]).date() if row and row[0] else None


# --- trades ---------------------------------------------------------------

def insert_trade(ticker, date, action, price, shares, signal_value, source) -> None:
    sql = (
        "INSERT INTO trades (ticker, date, action, price, shares, signal_value, source) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
    )
    params = (ticker, date, action, price, shares, signal_value, source)
    if _backend() == "sqlite":
        sql = sql.replace("%s", "?")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        cur.close()


def get_trades(source: str) -> pd.DataFrame:
    sql = (
        "SELECT id, ticker, date, action, price, shares, signal_value, source "
        "FROM trades WHERE source = %s ORDER BY date, id"
    )
    params = (source,)
    if _backend() == "sqlite":
        sql = sql.replace("%s", "?")
    df = _query_df(sql, params)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        for c in ("price", "shares", "signal_value"):
            df[c] = pd.to_numeric(df[c])
    return df


# --- snapshots ------------------------------------------------------------

def upsert_snapshot(date, source, total_value, cash, holdings: dict) -> None:
    if _backend() == "sqlite":
        sql = """
            INSERT INTO portfolio_snapshots (date, source, total_value, cash, holdings)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date, source) DO UPDATE SET
                total_value = excluded.total_value,
                cash        = excluded.cash,
                holdings    = excluded.holdings
        """
        params = (date, source, total_value, cash, json.dumps(holdings))
    else:
        sql = """
            INSERT INTO portfolio_snapshots (date, source, total_value, cash, holdings)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (date, source) DO UPDATE SET
                total_value = EXCLUDED.total_value,
                cash        = EXCLUDED.cash,
                holdings    = EXCLUDED.holdings
        """
        params = (date, source, total_value, cash, json.dumps(holdings))

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        cur.close()


def get_snapshots(source: str) -> pd.DataFrame:
    sql = (
        "SELECT date, source, total_value, cash, holdings "
        "FROM portfolio_snapshots WHERE source = %s ORDER BY date"
    )
    params = (source,)
    if _backend() == "sqlite":
        sql = sql.replace("%s", "?")
    df = _query_df(sql, params)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df["total_value"] = pd.to_numeric(df["total_value"])
        df["cash"] = pd.to_numeric(df["cash"])
    return df


# --- signals --------------------------------------------------------------

def insert_signals(rows: Iterable) -> int:
    rows = list(rows)
    if not rows:
        return 0

    if _backend() == "sqlite":
        sql = (
            "INSERT INTO signals (date, ticker, momentum_score, rank) "
            f"VALUES {_placeholder(4)} "
            "ON CONFLICT(date, ticker) DO UPDATE SET "
            "momentum_score = excluded.momentum_score, "
            "rank = excluded.rank"
        )
        with get_conn() as conn:
            cur = conn.cursor()
            cur.executemany(sql, rows)
            conn.commit()
            count = cur.rowcount
            cur.close()
            return count

    from psycopg2.extras import execute_values
    sql = """
        INSERT INTO signals (date, ticker, momentum_score, rank) VALUES %s
        ON CONFLICT (date, ticker) DO UPDATE SET
            momentum_score = EXCLUDED.momentum_score,
            rank           = EXCLUDED.rank
    """
    with get_conn() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows)
        count = cur.rowcount
        conn.commit()
        cur.close()
        return count
