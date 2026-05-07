import unittest

import pandas as pd

from src import signals


class SignalsTest(unittest.TestCase):
    def test_compute_momentum_uses_lookback_window_and_skips_recent_month(self):
        prices = pd.DataFrame(
            {
                "AAA": [100.0, 999.0, 130.0, 200.0],
                "BBB": [50.0, 999.0, 45.0, 55.0],
            },
            index=pd.to_datetime([
                "2022-12-30",
                "2023-06-30",
                "2023-12-29",
                "2024-01-31",
            ]),
        )

        scores = signals.compute_momentum(prices, "2024-01-31")

        self.assertAlmostEqual(scores["AAA"], 0.30)
        self.assertAlmostEqual(scores["BBB"], -0.10)

    def test_compute_momentum_returns_empty_series_without_enough_history(self):
        prices = pd.DataFrame(
            {"AAA": [100.0, 110.0]},
            index=pd.to_datetime(["2024-01-02", "2024-02-01"]),
        )

        scores = signals.compute_momentum(prices, "2024-02-01")

        self.assertTrue(scores.empty)

    def test_rank_and_select_drops_nan_and_returns_top_scores(self):
        scores = pd.Series({"AAA": 0.10, "BBB": None, "CCC": 0.30, "DDD": 0.20})

        selected = signals.rank_and_select(scores, top_n=2)

        self.assertEqual(selected, ["CCC", "DDD"])

    def test_month_start_rebalance_dates_uses_first_trading_day(self):
        index = pd.to_datetime([
            "2024-01-02",
            "2024-01-03",
            "2024-02-01",
            "2024-02-02",
            "2024-03-01",
        ])

        dates = signals.month_start_rebalance_dates(index, "2024-01-01", "2024-02-28")

        self.assertEqual(dates, [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-02-01")])


if __name__ == "__main__":
    unittest.main()
