"""
Drop and recreate all tables. Idempotent — safe to re-run.

Supports both:
- PostgreSQL (original/default path)
- SQLite (lightweight local fallback for reproducible local runs)
"""

import os
import sqlite3
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

load_dotenv()

POSTGRES_SCHEMA = """
DROP TABLE IF EXISTS prices, trades, portfolio_snapshots, signals CASCADE;

CREATE TABLE prices (
    ticker  TEXT    NOT NULL,
    date    DATE    NOT NULL,
    open    NUMERIC,
    high    NUMERIC,
    low     NUMERIC,
    close   NUMERIC,
    volume  BIGINT,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX prices_date_idx ON prices(date);

CREATE TABLE trades (
    id            SERIAL PRIMARY KEY,
    ticker        TEXT    NOT NULL,
    date          DATE    NOT NULL,
    action        TEXT    NOT NULL CHECK (action IN ('buy', 'sell')),
    price         NUMERIC NOT NULL,
    shares        NUMERIC NOT NULL,
    signal_value  NUMERIC,
    source        TEXT    NOT NULL CHECK (source IN ('backtest', 'live'))
);
CREATE INDEX trades_ticker_date_idx ON trades(ticker, date);
CREATE INDEX trades_source_idx ON trades(source);

CREATE TABLE portfolio_snapshots (
    date         DATE    NOT NULL,
    source       TEXT    NOT NULL CHECK (source IN ('backtest', 'live')),
    total_value  NUMERIC NOT NULL,
    cash         NUMERIC NOT NULL,
    holdings     JSONB   NOT NULL,
    PRIMARY KEY (date, source)
);

CREATE TABLE signals (
    date            DATE    NOT NULL,
    ticker          TEXT    NOT NULL,
    momentum_score  NUMERIC,
    rank            INT,
    PRIMARY KEY (date, ticker)
);
CREATE INDEX signals_date_idx ON signals(date);
"""

SQLITE_SCHEMA = """
DROP TABLE IF EXISTS prices;
DROP TABLE IF EXISTS trades;
DROP TABLE IF EXISTS portfolio_snapshots;
DROP TABLE IF EXISTS signals;

CREATE TABLE prices (
    ticker  TEXT    NOT NULL,
    date    TEXT    NOT NULL,
    open    REAL,
    high    REAL,
    low     REAL,
    close   REAL,
    volume  INTEGER,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX prices_date_idx ON prices(date);

CREATE TABLE trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT    NOT NULL,
    date          TEXT    NOT NULL,
    action        TEXT    NOT NULL CHECK (action IN ('buy', 'sell')),
    price         REAL    NOT NULL,
    shares        REAL    NOT NULL,
    signal_value  REAL,
    source        TEXT    NOT NULL CHECK (source IN ('backtest', 'live'))
);
CREATE INDEX trades_ticker_date_idx ON trades(ticker, date);
CREATE INDEX trades_source_idx ON trades(source);

CREATE TABLE portfolio_snapshots (
    date         TEXT    NOT NULL,
    source       TEXT    NOT NULL CHECK (source IN ('backtest', 'live')),
    total_value  REAL    NOT NULL,
    cash         REAL    NOT NULL,
    holdings     TEXT    NOT NULL,
    PRIMARY KEY (date, source)
);

CREATE TABLE signals (
    date            TEXT    NOT NULL,
    ticker          TEXT    NOT NULL,
    momentum_score  REAL,
    rank            INTEGER,
    PRIMARY KEY (date, ticker)
);
CREATE INDEX signals_date_idx ON signals(date);
"""


def _db_url() -> str:
    return os.environ["DATABASE_URL"]


def _sqlite_path() -> str:
    parsed = urlparse(_db_url())
    path = unquote(parsed.path or "")
    if not path:
        raise ValueError("SQLite DATABASE_URL is missing a path")
    if parsed.netloc and parsed.netloc not in ("", "localhost"):
        path = f"//{parsed.netloc}{path}"
    return path


def main():
    url = _db_url()
    if url.startswith("sqlite://"):
        conn = sqlite3.connect(_sqlite_path())
        try:
            conn.executescript(SQLITE_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        print("SQLite schema created (or recreated).")
        return

    import psycopg2
    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        cur.execute(POSTGRES_SCHEMA)
    print("Postgres schema created (or recreated).")


if __name__ == "__main__":
    main()
