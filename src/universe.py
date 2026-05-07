"""
Point-in-time S&P 500 membership reconstructed from Wikipedia.

Why bother: the previous version used current membership, which is severely
survivorship-biased — today's index over-represents stocks that joined
*because* they 10x'd. A momentum backtest over such a list isn't testing
momentum, it's testing "stocks that got added to the index after a huge run."

Approach: scrape today's constituents AND the "Selected Changes" log on the
same Wikipedia page. To get membership on any past date, walk the change
log backward from today's set:
  - if X was REMOVED after target_date → add X back (it was a member then)
  - if X was ADDED after target_date  → remove X (it wasn't a member yet)

Caveats that remain:
  - Wikipedia's changes table starts a few decades back; deep history may
    be incomplete, but for our 2018+ window it's reliable.
  - Tickers that fully delisted (bankruptcy, going private without a successor)
    won't have price data in Alpaca, so they'll silently drop out of the
    eligible set. This is "delisting bias" — small in our window since most
    removals 2018-2024 were mergers (acquirer continues) or cap demotions.
  - Ticker renames (FB → META, SQ → XYZ) appear as add+remove pairs in the
    log; whichever ticker Alpaca maps to internally is what we get.
"""

import csv
import re
from io import StringIO
from pathlib import Path
from typing import List, Set

import pandas as pd
import requests

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_PATH = DATA_DIR / "sp500.csv"
CHANGES_PATH = DATA_DIR / "sp500_changes.csv"
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

_HEADERS = {"User-Agent": "TradingBotLearningProject/0.1 (educational use)"}


def _fetch_wiki_tables():
    resp = requests.get(WIKI_URL, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return pd.read_html(StringIO(resp.text))


def _clean_ticker(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.strip().upper()
    # Strip footnote markers like [1], [12]
    s = re.sub(r"\[\d+\]", "", s).strip()
    if s.lower() in ("nan", "none", ""):
        return ""
    # Wikipedia occasionally uses non-breaking spaces inside multi-class tickers
    return s.replace("\xa0", "").replace(" ", "")


# --- current constituents -----------------------------------------------

def _scrape_constituents(tables) -> List[str]:
    df = tables[0]
    return sorted({_clean_ticker(t) for t in df["Symbol"]} - {""})


# --- change log ---------------------------------------------------------

def _scrape_changes(tables) -> pd.DataFrame:
    raw = tables[1].copy()
    # The header is multi-level; flatten to simple names.
    raw.columns = [
        "date", "added_ticker", "added_security",
        "removed_ticker", "removed_security", "reason",
    ]
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    raw["added_ticker"] = raw["added_ticker"].apply(_clean_ticker)
    raw["removed_ticker"] = raw["removed_ticker"].apply(_clean_ticker)
    raw = raw.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return raw[["date", "added_ticker", "removed_ticker"]]


# --- public API ---------------------------------------------------------

def refresh_cache() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tables = _fetch_wiki_tables()

    constituents = _scrape_constituents(tables)
    with CACHE_PATH.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker"])
        for t in constituents:
            w.writerow([t])

    changes = _scrape_changes(tables)
    changes.to_csv(CHANGES_PATH, index=False)


def get_sp500(refresh: bool = False) -> List[str]:
    """Today's S&P 500 constituents."""
    if refresh or not CACHE_PATH.exists():
        refresh_cache()
    with CACHE_PATH.open() as f:
        return [row[0] for row in csv.reader(f)][1:]


def get_sp500_changes(refresh: bool = False) -> pd.DataFrame:
    if refresh or not CHANGES_PATH.exists():
        refresh_cache()
    return pd.read_csv(CHANGES_PATH, parse_dates=["date"])


def get_sp500_at(target_date) -> Set[str]:
    """Reconstruct membership at `target_date` by walking the change log
    backward from today's set."""
    target = pd.Timestamp(target_date)
    members = set(get_sp500())
    changes = get_sp500_changes()
    future = changes[changes["date"] > target]
    for _, row in future.iterrows():
        added = row["added_ticker"]
        removed = row["removed_ticker"]
        if isinstance(added, str) and added:
            members.discard(added)
        if isinstance(removed, str) and removed:
            members.add(removed)
    return members


def get_all_historical_tickers(start, end) -> Set[str]:
    """Every ticker that was in the S&P 500 at any point in [start, end].
    Used to figure out which prices we need to seed."""
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    members = set(get_sp500_at(start_ts))
    changes = get_sp500_changes()
    in_window = changes[(changes["date"] >= start_ts) & (changes["date"] <= end_ts)]
    for _, row in in_window.iterrows():
        added = row["added_ticker"]
        removed = row["removed_ticker"]
        if isinstance(added, str) and added:
            members.add(added)
        if isinstance(removed, str) and removed:
            members.add(removed)
    return members


if __name__ == "__main__":
    import sys
    if "--refresh" in sys.argv:
        refresh_cache()

    today = get_sp500()
    print(f"today: {len(today)} tickers")

    for d in ["2019-01-01", "2020-01-01", "2022-01-01", "2024-01-01"]:
        snap = get_sp500_at(d)
        print(f"as of {d}: {len(snap)} tickers")

    full = get_all_historical_tickers("2018-12-01", "2024-12-31")
    print(f"union 2018-2024: {len(full)} tickers")

    # How many were eligible in 2024 but not in 2019? (Recent additions —
    # the bias-amplifying tail.)
    snap_2019 = get_sp500_at("2019-01-01")
    snap_2024 = get_sp500_at("2024-01-01")
    print(f"added since 2019: {len(snap_2024 - snap_2019)} tickers")
    print(f"removed since 2019: {len(snap_2019 - snap_2024)} tickers")
