"""Command-line entrypoint for the two-pass chart-pattern scanner."""
from __future__ import annotations

import argparse
import json
import sys

from . import data as dl
from . import universe as uni
from .config import CFG, MARKETS
from .earnings import annotate_earnings
from .pattern_report import write_pattern_report
from .pattern_scanner import SECTOR_ETFS, add_live_patterns, scan_patterns


def main():
    ap = argparse.ArgumentParser(description="Daily chart-pattern shortlist with context scoring")
    ap.add_argument("--market", choices=("us",), default="us",
                    help="patterns are currently calibrated for liquid US daily charts")
    ap.add_argument("--tickers", nargs="*", help="ad-hoc ticker list")
    ap.add_argument("--limit", type=int, default=None, help="cap universe for testing")
    ap.add_argument("--out", default="pattern_report.html")
    ap.add_argument("--json", default=None, help="optional machine-readable output")
    ap.add_argument("--geometry-limit", type=int, default=100)
    ap.add_argument("--context-limit", type=int, default=20)
    ap.add_argument("--final-limit", type=int, default=10)
    ap.add_argument("--include-forming", action="store_true",
                    help="include strong forming patterns in the final report")
    ap.add_argument("--live", action="store_true",
                    help="validate only the final shortlist with live TWS prices")
    ap.add_argument("--no-earnings", action="store_true")
    a = ap.parse_args()

    symbols = a.tickers or uni.universe_for("us")
    if a.limit:
        symbols = symbols[:a.limit]
    print(f"[pattern] universe {len(symbols)}; bulk daily OHLCV download...")
    daily = dl.download_daily(symbols)
    mkt = MARKETS["us"]
    liquid = {t: d for t, d in daily.items()
              if dl.passes_liquidity(d, mkt["min_price"], mkt["min_dollar_vol"])}
    print(f"[pattern] {len(liquid)} liquid symbols; geometry pass...")

    context_symbols = ["SPY", *SECTOR_ETFS]
    context = dl.download_daily(context_symbols)
    result = scan_patterns(
        liquid, bench_daily=context.get("SPY"),
        sector_daily={t: context[t] for t in SECTOR_ETFS if t in context},
        geometry_limit=a.geometry_limit, context_limit=a.context_limit,
        final_limit=a.final_limit, include_forming=a.include_forming,
    )
    rows = result.rows
    print(f"[pattern] {result.geometry_count} geometry -> {result.context_count} context -> {len(rows)} final")

    if not a.no_earnings and rows:
        annotate_earnings(rows)
        before = len(rows)
        rows[:] = [r for r in rows if r.get("ern_status") != "inside"]
        if before != len(rows):
            print(f"[pattern] earnings inside 20-day hold excluded: {before - len(rows)}")

    if a.live and rows:
        CFG.tws_market_data_type = 1
        rows, health = add_live_patterns(rows)
        if not health["ok"]:
            print(f"[pattern/live] FAIL: only {health['fresh']}/{health['total']} fresh quotes")
            sys.exit(2)

    write_pattern_report(rows, a.out, result)
    print(f"[pattern] report -> {a.out}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"pipeline": result.__dict__ | {"rows": None}, "rows": rows}, fh,
                      separators=(",", ":"))
        print(f"[pattern] JSON -> {a.json}")


if __name__ == "__main__":
    main()
