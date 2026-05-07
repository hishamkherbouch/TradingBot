"""
Three matplotlib charts off the populated DB:

  1. Equity curve (strategy backtest) vs. SPY buy-and-hold, normalized to 1.0.
  2. Monthly returns heatmap (year x month grid).
  3. Per-stock contribution bar chart (FIFO-paired round-trip PnL).

Saved to charts/*.png. If running interactively, also displayed.
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from src import db, metrics
from src.data import BENCHMARK


CHARTS_DIR = Path(__file__).parent / "charts"
CHARTS_DIR.mkdir(exist_ok=True)


def _load() -> dict:
    snaps = db.get_snapshots("backtest")
    trades = db.get_trades("backtest")
    if snaps.empty:
        raise SystemExit("No backtest snapshots in DB. Run backtest.py first.")

    snaps = snaps.set_index("date").sort_index()
    equity = pd.to_numeric(snaps["total_value"]).astype(float)

    spy = db.get_prices_wide(equity.index.min(), equity.index.max())
    spy_close = spy[BENCHMARK].reindex(equity.index).ffill() if BENCHMARK in spy.columns else None

    return {"equity": equity, "spy": spy_close, "trades": trades}


# --- Chart 1: equity curve vs SPY -----------------------------------------

def chart_equity_vs_spy(data: dict) -> Path:
    equity = data["equity"]
    spy = data["spy"]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(equity.index, equity / equity.iloc[0], label="Strategy (12-1 momentum)", linewidth=1.6)
    if spy is not None and not spy.empty:
        ax.plot(spy.index, spy / spy.iloc[0], label=f"{BENCHMARK} buy-and-hold", linewidth=1.2, alpha=0.8)
    ax.set_title("Equity curve (normalized to 1.0)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Growth of $1")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = CHARTS_DIR / "01_equity_vs_spy.png"
    fig.savefig(out, dpi=120)
    return out


# --- Chart 2: monthly returns heatmap -------------------------------------

def chart_monthly_heatmap(data: dict) -> Path:
    equity = data["equity"]
    monthly = equity.resample("ME").last() if hasattr(equity.index, "freqstr") else equity.resample("M").last()
    monthly_ret = monthly.pct_change().dropna()

    df = monthly_ret.to_frame("ret").reset_index()
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    grid = df.pivot(index="year", columns="month", values="ret")
    grid = grid.reindex(columns=range(1, 13))

    fig, ax = plt.subplots(figsize=(10, max(3, 0.6 * len(grid))))
    vmax = np.nanmax(np.abs(grid.values)) if grid.size else 0.1
    im = ax.imshow(grid.values, aspect="auto", cmap="RdYlGn", vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(12))
    ax.set_xticklabels(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"])
    ax.set_yticks(range(len(grid.index)))
    ax.set_yticklabels(grid.index)
    ax.set_title("Monthly returns")
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            v = grid.values[i, j]
            if pd.notna(v):
                ax.text(j, i, f"{v*100:.1f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, label="Monthly return")
    fig.tight_layout()
    out = CHARTS_DIR / "02_monthly_heatmap.png"
    fig.savefig(out, dpi=120)
    return out


# --- Chart 3: per-stock contribution --------------------------------------

def chart_per_stock(data: dict) -> Path:
    rounds = metrics.pair_trades(data["trades"])
    if rounds.empty:
        # Empty plot rather than crashing — useful during early dev runs.
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No round-trip trades yet.", ha="center", va="center")
        ax.set_axis_off()
        out = CHARTS_DIR / "03_per_stock_contribution.png"
        fig.savefig(out, dpi=120)
        return out

    by_ticker = rounds.groupby("ticker")["pnl"].sum().sort_values()
    fig, ax = plt.subplots(figsize=(8, max(3, 0.35 * len(by_ticker))))
    colors = ["#2ca02c" if v >= 0 else "#d62728" for v in by_ticker.values]
    ax.barh(by_ticker.index, by_ticker.values, color=colors)
    ax.axvline(0, color="black", linewidth=0.6)
    ax.set_title("Per-stock contribution (FIFO-paired round-trip PnL)")
    ax.set_xlabel("PnL ($)")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    out = CHARTS_DIR / "03_per_stock_contribution.png"
    fig.savefig(out, dpi=120)
    return out


def main():
    data = _load()
    p1 = chart_equity_vs_spy(data)
    p2 = chart_monthly_heatmap(data)
    p3 = chart_per_stock(data)
    print(f"Saved:\n  {p1}\n  {p2}\n  {p3}")
    if os.environ.get("DASHBOARD_SHOW", "0") == "1":
        plt.show()


if __name__ == "__main__":
    main()
