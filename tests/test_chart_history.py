import unittest
from pathlib import Path

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

    def test_dashboard_does_not_turn_missing_pattern_levels_into_zero(self):
        dashboard = (Path(__file__).parents[1] / "docs" / "index.html").read_text()

        self.assertIn('x[0]!==null&&x[0]!==undefined&&x[0]!==""', dashboard)

    def test_dashboard_offers_persistent_history_ranges(self):
        dashboard = (Path(__file__).parents[1] / "docs" / "index.html").read_text()

        self.assertIn('const RANGE_BARS={"3m":63,"6m":126,"1y":252,"2y":504}', dashboard)
        self.assertIn('localStorage.getItem("paChartRange")||"2y"', dashboard)
        self.assertIn('data-global-range="3m"', dashboard)
        self.assertIn('data-global-range="2y"', dashboard)
        self.assertIn('data-chart-range=', dashboard)

    def test_dashboard_uses_wide_chart_viewports(self):
        dashboard = (Path(__file__).parents[1] / "docs" / "index.html").read_text()

        self.assertNotIn("max-height:360px", dashboard)
        self.assertGreaterEqual(dashboard.count("W=1600"), 3)

    def test_dashboard_places_inspection_chart_after_clicked_row(self):
        dashboard = (Path(__file__).parents[1] / "docs" / "index.html").read_text()

        row_append = dashboard.index('tb.appendChild(tr);')
        detail_append = dashboard.index('tb.appendChild(detail);', row_append)
        self.assertLess(row_append, detail_append)

    def test_dashboard_scrolls_only_the_ticker_table(self):
        dashboard = (Path(__file__).parents[1] / "docs" / "index.html").read_text()

        self.assertIn('id="tableShell" class="table-shell"', dashboard)
        self.assertIn('.table-shell{flex:1;min-height:0;overflow:auto', dashboard)
        self.assertIn('height:100dvh;overflow:hidden;display:flex;flex-direction:column', dashboard)
        self.assertIn('header,.tabs,.banner,.board,.bar{flex:0 0 auto}', dashboard)
        self.assertIn('th{position:sticky;top:0;z-index:5', dashboard)


if __name__ == "__main__":
    unittest.main()
