import unittest

import pandas as pd

from src import metrics


class MetricsTest(unittest.TestCase):
    def test_total_and_annualized_return_use_daily_equity_curve(self):
        equity = pd.Series(
            [100.0, 110.0, 121.0],
            index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
        )

        self.assertAlmostEqual(metrics.total_return(equity), 0.21)
        expected_annualized = (121.0 / 100.0) ** (252.0 / 3.0) - 1.0
        self.assertAlmostEqual(metrics.annualized_return(equity), expected_annualized)

    def test_max_drawdown_returns_worst_peak_to_trough_loss(self):
        equity = pd.Series(
            [100.0, 120.0, 90.0, 110.0],
            index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
        )

        self.assertAlmostEqual(metrics.max_drawdown(equity), -0.25)

    def test_sharpe_ratio_returns_zero_for_flat_equity_curve(self):
        equity = pd.Series(
            [100.0, 100.0, 100.0],
            index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
        )

        self.assertEqual(metrics.sharpe_ratio(equity), 0.0)

    def test_pair_trades_fifo_pairs_partial_round_trips(self):
        trades = pd.DataFrame([
            {
                "ticker": "AAA",
                "date": pd.Timestamp("2024-01-02"),
                "action": "buy",
                "price": 10.0,
                "shares": 10.0,
            },
            {
                "ticker": "AAA",
                "date": pd.Timestamp("2024-01-03"),
                "action": "sell",
                "price": 12.0,
                "shares": 4.0,
            },
            {
                "ticker": "AAA",
                "date": pd.Timestamp("2024-01-04"),
                "action": "sell",
                "price": 8.0,
                "shares": 6.0,
            },
        ])

        rounds = metrics.pair_trades(trades)

        self.assertEqual(len(rounds), 2)
        self.assertEqual(rounds["shares"].tolist(), [4.0, 6.0])
        self.assertEqual(rounds["pnl"].tolist(), [8.0, -12.0])

    def test_win_rate_counts_profitable_fifo_round_trips(self):
        trades = pd.DataFrame([
            {
                "ticker": "AAA",
                "date": pd.Timestamp("2024-01-02"),
                "action": "buy",
                "price": 10.0,
                "shares": 10.0,
            },
            {
                "ticker": "AAA",
                "date": pd.Timestamp("2024-01-03"),
                "action": "sell",
                "price": 12.0,
                "shares": 5.0,
            },
            {
                "ticker": "AAA",
                "date": pd.Timestamp("2024-01-04"),
                "action": "sell",
                "price": 8.0,
                "shares": 5.0,
            },
        ])

        self.assertEqual(metrics.win_rate(trades), 0.5)


if __name__ == "__main__":
    unittest.main()
