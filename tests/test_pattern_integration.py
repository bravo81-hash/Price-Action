import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from pa_scanner.fvs_patterns.scanner import PipelineResult, scan_patterns
from pa_scanner.pattern_integration import annotate_pattern_matches


def bars(close):
    close = np.asarray(close, dtype=float)
    wiggle = np.maximum(close * 0.006, 0.35)
    return pd.DataFrame({
        "open": np.r_[close[0], close[:-1]],
        "high": close + wiggle,
        "low": close - wiggle,
        "close": close,
        "volume": np.full(len(close), 5_000_000.0),
    }, index=pd.bdate_range("2025-01-02", periods=len(close)))


class PatternIntegrationTests(unittest.TestCase):
    def test_promotes_matches_and_prefers_side_alignment(self):
        frame = bars(np.linspace(80, 100, 140))
        rows = [
            {"ticker": "AAA", "side": "long", "evidence_rank": 2,
             "rank": 10, "score": .6},
            {"ticker": "BBB", "side": "long", "evidence_rank": 1,
             "rank": 20, "score": .8},
        ]
        matches = [
            {"ticker": "AAA", "code": "P6", "pattern": "Head and shoulders",
             "side": "short", "status": "NEAR_TRIGGER", "score": .95},
            {"ticker": "AAA", "code": "P1", "pattern": "Flat base",
             "side": "long", "status": "CLOSE_CONFIRMED", "score": .70,
             "chart": {"close": [98, 100], "open": [97, 99],
                       "high": [99, 101], "low": [96, 98],
                       "dates": ["2026-07-20", "2026-07-21"]}},
        ]
        fake = PipelineResult(matches, 2, 2, 2, 2)
        with patch("pa_scanner.pattern_integration.scan_patterns", return_value=fake):
            meta = annotate_pattern_matches(
                rows, {"AAA": (frame, frame), "BBB": (frame, frame)}, frame)

        self.assertEqual(rows[0]["ticker"], "AAA")
        self.assertEqual(rows[0]["pattern_code"], "P1")
        self.assertEqual(rows[0]["pattern_alignment"], "aligned")
        self.assertEqual(rows[0]["pattern_priority"], 0)
        self.assertFalse(rows[1]["pattern_match"])
        self.assertEqual(meta["matched_tickers"], 1)

    def test_current_fvs_geometry_engine_detects_a_base(self):
        prior = np.linspace(70, 100, 80)
        base = np.array([
            96, 98, 99.6, 97, 98.8, 99.7, 97.5, 99.2, 99.8, 98.2,
            99.1, 99.7, 98.8, 99.4, 99.8, 99.0, 99.5, 99.9, 99.2, 99.6,
            99.8, 99.4, 99.7, 99.9, 99.6, 99.8, 99.7, 99.85, 99.8, 99.9,
            100.7,
        ])
        frame = bars(np.r_[prior, base])
        result = scan_patterns(
            {"BASE": frame}, bench_daily=frame, min_geometry=.2,
            min_context=0, geometry_limit=100, context_limit=20,
            final_limit=10,
        )
        self.assertGreaterEqual(result.geometry_count, 1)
        self.assertTrue(any(row["code"] in {"P1", "P5"} for row in result.rows))


if __name__ == "__main__":
    unittest.main()
