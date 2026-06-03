"""
Daily cron entry point: refresh prices, decide whether today is a rebalance
day, and (if it is) push the strategy's target portfolio to Alpaca paper.

Recommended cron line (weekdays, 14:00 — about an hour before US close so
notional orders fill same-session):

    0 14 * * 1-5  cd /path/to/repo && .venv/bin/python live.py >> live.log 2>&1
"""

import argparse
import os
from datetime import date, timedelta

import pandas as pd
from dotenv import load_dotenv

from alpaca.trading.client import TradingClient

from src import db, signals, execution
from src.data import BENCHMARK, fetch_bars
from src.universe import get_sp500_at

_FETCH_CHUNK = 50

load_dotenv()


TOP_N = int(os.environ.get("TOP_N", 10))


def _live_universe(today: date):
    """Current live-trading universe.

    Live trading should use the current S&P 500 membership, not the full
    historical backtest union that includes delisted or long-removed names.
    """
    return sorted(get_sp500_at(today))



def _refresh_prices(today: date, universe) -> None:
    """Fetch any missing bars for the live universe in batches.

    We bucket tickers by missing-data start date, then batch-fetch symbols
    together. Re-downloading a small overlap is fine because inserts are
    conflict-safe, and this is much faster than one API call per ticker.
    """
    buckets = {}
    for ticker in list(universe) + [BENCHMARK]:
        last = db.latest_price_date(ticker)
        start = (last + timedelta(days=1)) if last else (today - timedelta(days=400))
        if start >= today:
            continue
        buckets.setdefault(start, []).append(ticker)

    for start in sorted(buckets):
        tickers = buckets[start]
        for i in range(0, len(tickers), _FETCH_CHUNK):
            batch = tickers[i:i + _FETCH_CHUNK]
            df = fetch_bars(batch, start, today)
            if not df.empty:
                db.insert_prices(df)


def _parse_args():
    parser = argparse.ArgumentParser(description="Run the TradingBot live paper-trading flow.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force a rebalance even if today is not the month's first trading day.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    today = date.today()
    print(f"[live] {today}: starting daily run")

    api_key = os.environ.get("ALPACA_API_KEY", "").strip()
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "").strip()
    if not api_key or not secret_key:
        raise SystemExit(
            "Missing Alpaca credentials. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env before running live.py."
        )
    trading_client = TradingClient(api_key, secret_key, paper=True)

    live_universe = _live_universe(today)

    # 1-2. Refresh prices and reload the wide frame (need a long history so
    # 13 months of lookback is always available on rebalance days).
    _refresh_prices(today, live_universe)
    prices_wide = db.get_prices_wide(
        (today - timedelta(days=500)).isoformat(),
        today.isoformat(),
    )
    if prices_wide.empty:
        print("[live] no prices in DB after refresh — aborting.")
        return

    # 3. Is today a rebalance day? Use the actual price index (last trading
    # day) as "today" so a Saturday cron run still resolves correctly.
    today_ts = prices_wide.index.asof(pd.Timestamp(today))
    if pd.isna(today_ts):
        print("[live] no trading day on/before today — aborting.")
        return

    rebal_dates = set(signals.rebalance_dates(
        prices_wide.index, prices_wide.index.min(), today_ts,
    ))
    if today_ts not in rebal_dates and not args.force:
        print(f"[live] {today_ts.date()} is not the month's first trading day — no rebalance.")
        return
    if today_ts not in rebal_dates and args.force:
        print(f"[live] forcing rebalance on {today_ts.date()} (not the month's first trading day)")

    # 4. Compute target portfolio.
    eligible = [t for t in live_universe if t in prices_wide.columns]
    scores = signals.compute_momentum(prices_wide[eligible], today_ts)
    picks = signals.rank_and_select(scores, TOP_N)
    print(f"[live] picks for {today_ts.date()}: {picks}")

    # Persist the ranked board.
    ranked = scores.dropna().sort_values(ascending=False)
    db.insert_signals([
        (today_ts.date(), tkr, float(score), rank)
        for rank, (tkr, score) in enumerate(ranked.items(), start=1)
    ])

    # 5. Send orders.
    account = trading_client.get_account()
    account_value = float(account.equity)
    result = execution.rebalance(trading_client, picks, account_value)
    print(f"[live] closed {result['closed']}, submitted {len(result['submitted'])} new orders @ ~${result['target_dollar']:.2f}")

    # Record live trades. We log buys at the notional we requested; the
    # actual fill price comes back later via Alpaca's order-update stream
    # (out of scope for this learning project).
    for order in result["submitted"]:
        db.insert_trade(
            ticker=order["ticker"],
            date=today_ts.date(),
            action="buy",
            price=float(prices_wide.loc[today_ts, order["ticker"]]),
            shares=order["notional"] / float(prices_wide.loc[today_ts, order["ticker"]]),
            signal_value=float(scores[order["ticker"]]),
            source="live",
        )
    for ticker in result["closed"]:
        if ticker in prices_wide.columns:
            db.insert_trade(
                ticker=ticker,
                date=today_ts.date(),
                action="sell",
                price=float(prices_wide.loc[today_ts, ticker]),
                shares=0,  # unknown — close_position liquidates whatever was there
                signal_value=None,
                source="live",
            )

    # 6. Snapshot.
    positions = execution.current_positions(trading_client)
    db.upsert_snapshot(
        today_ts.date(), "live",
        float(account.equity), float(account.cash), positions,
    )
    print(f"[live] equity=${float(account.equity):,.2f} cash=${float(account.cash):,.2f}")


if __name__ == "__main__":
    main()
