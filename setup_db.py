"""
Drop and recreate all tables. Idempotent — safe to re-run.

Tables:
  prices              raw daily bars, one row per (ticker, date)
  trades              every buy/sell, tagged source='backtest' or 'live'
  portfolio_snapshots one row per (date, source) holding total equity + composition
  signals             ranked momentum scores per rebalance date
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

SCHEMA = """
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


def main():
    url = os.environ["DATABASE_URL"]
    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        cur.execute(SCHEMA)
    print("Schema created (or recreated).")


if __name__ == "__main__":
    main()
