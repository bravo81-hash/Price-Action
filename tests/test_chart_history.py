import unittest

import numpy as np
import pandas as pd

from pa_scanner.config import CFG
from pa_scanner.scanner import prepare_context
from pa_scanner.webexport import _row


def daily_bars(count=620):
    close = np.linspace(80.0, 120.0, count)
    return pd.DataFrame({
        "open": close - 0.25,
        "high": close + 0.75,
        "low": close - 0.75,
        "close": close,
        "volume": np.full(count, 5_000_000.0),
    }, index=pd.bdate_range("2024-01-02", periods=count))


def weekly_bars(daily):
    return daily.resample("W-FRI").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum",
    }).dropna()


class ChartHistoryTests(unittest.TestCase):
    def test_context_carries_two_trading_years_of_ohlc(self):
        daily = daily_bars()
        ctx = prepare_context("TEST", daily, weekly_bars(daily))

        self.assertEqual(len(ctx.chart["close"]), CFG.chart_bars)
        self.assertEqual(CFG.chart_bars, 504)
        self.assertEqual(set(ctx.chart), {"dates", "open", "high", "low", "close"})
        self.assertTrue(all(len(values) == CFG.chart_bars
                            for values in ctx.chart.values()))
        self.assertEqual(ctx.chart["dates"][0],
                         daily.index[-CFG.chart_bars].date().isoformat())

    def test_web_export_preserves_full_chart_payload(self):
        chart = {key: [value, value + 1] for key, value in {
            "open": 10, "high": 11, "low": 9, "close": 10,
        }.items()}
        chart["dates"] = ["2026-07-20", "2026-07-21"]

        exported = _row({"ticker": "TEST", "signal": "S2", "side": "long",
                         "chart": chart})

        self.assertEqual(exported["chart"], chart)


if __name__ == "__main__":
    unittest.main()
