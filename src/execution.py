"""
Alpaca paper-trading execution helpers. Used only by live.py.

Kept separate from signals/metrics so the backtest never imports anything
that needs network access or live credentials.
"""

from typing import Dict, List

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest


def current_positions(trading_client: TradingClient) -> Dict[str, float]:
    """Return a {ticker: qty} map of open positions."""
    return {p.symbol: float(p.qty) for p in trading_client.get_all_positions()}


def rebalance(
    trading_client: TradingClient,
    target_tickers: List[str],
    account_value: float,
) -> dict:
    """Move the live paper account toward the equal-weight target portfolio.

    Strategy (matches backtest semantics):
      1. Close any open position whose symbol is not in `target_tickers`.
      2. For each target we don't yet hold, submit a notional buy for
         account_value / N.

    --- Why notional orders? ----------------------------------------------
    A notional order tells Alpaca "spend $X" and lets it figure out the
    fractional share count. That gives us exact equal-weight sizing without
    integer-share rounding, which would skew the portfolio when prices vary
    across picks (e.g. NVDA at $900 vs. KO at $60).
    -----------------------------------------------------------------------
    """
    positions = trading_client.get_all_positions()
    held = {p.symbol for p in positions}

    closed = []
    for p in positions:
        if p.symbol not in target_tickers:
            trading_client.close_position(p.symbol)
            closed.append(p.symbol)

    target_dollar = float(account_value) / max(len(target_tickers), 1)
    submitted = []
    for t in target_tickers:
        if t in held:
            continue  # already holding — let the existing position drift; we
                      # do not top-up to the new target dollar each month.
        order = MarketOrderRequest(
            symbol=t,
            notional=round(target_dollar, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        resp = trading_client.submit_order(order)
        submitted.append({"ticker": t, "notional": round(target_dollar, 2), "order_id": str(resp.id)})

    return {"closed": closed, "submitted": submitted, "target_dollar": target_dollar}
