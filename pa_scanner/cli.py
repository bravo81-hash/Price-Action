"""CLI entrypoint.

Examples:
  python -m pa_scanner.cli                       # full scan -> pa_report.html
  python -m pa_scanner.cli --long-only
  python -m pa_scanner.cli --out today.html --limit 150
  python -m pa_scanner.cli --tickers AAPL MSFT NVDA SPY
"""
import argparse

from .config import CFG
from . import universe as uni
from . import data as dl
from .scanner import scan
from .report import write_report


def main():
    ap = argparse.ArgumentParser(description="Weekly-level / trend-pullback price-action scanner")
    ap.add_argument("--out", default="pa_report.html")
    ap.add_argument("--long-only", action="store_true")
    ap.add_argument("--short-only", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="cap universe size (debug)")
    ap.add_argument("--tickers", nargs="*", help="scan only these tickers")
    a = ap.parse_args()

    if a.long_only:
        CFG.allow_short = False
    if a.short_only:
        CFG.allow_long = False

    syms = a.tickers or uni.build_universe()
    if a.limit:
        syms = syms[:a.limit]
    print(f"[scan] universe = {len(syms)} symbols; downloading daily history...")

    daily = dl.download_daily(syms)
    print(f"[scan] fetched {len(daily)}; liquidity filter + weekly resample...")

    bundle = {}
    for t, d in daily.items():
        if not dl.passes_liquidity(d):
            continue
        bundle[t] = (d, dl.to_weekly(d))
    print(f"[scan] {len(bundle)} liquid symbols; running rules...")

    rows = scan(bundle)
    write_report(rows, a.out, scanned=len(bundle), universe=len(syms))
    print(f"[scan] {len(rows)} signals -> {a.out}")


if __name__ == "__main__":
    main()
