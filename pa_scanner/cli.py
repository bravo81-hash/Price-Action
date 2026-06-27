"""CLI entrypoint.

Examples:
  python -m pa_scanner.cli                       # full scan -> pa_report.html
  python -m pa_scanner.cli --web docs            # write JSON for the Pages dashboard
  python -m pa_scanner.cli --web docs --no-html
  python -m pa_scanner.cli --no-iv               # skip yfinance IV enrichment (faster)
  python -m pa_scanner.cli --tickers AAPL MSFT NVDA SPY
"""
import argparse

from .config import CFG
from . import universe as uni
from . import data as dl
from .scanner import scan, add_regime
from .report import write_report
from .webexport import write_web


def fetch_vix_backwardation():
    """Global term-structure flag: VIX > VIX3M -> backwardation (stress)."""
    try:
        import yfinance as yf
        df = yf.download(["^VIX", "^VIX3M"], period="5d", interval="1d",
                         progress=False, auto_adjust=True)
        close = df["Close"]
        vix = float(close["^VIX"].dropna().iloc[-1])
        vix3 = float(close["^VIX3M"].dropna().iloc[-1])
        return vix > vix3
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="Weekly-level / trend-pullback price-action scanner")
    ap.add_argument("--out", default=None, help="self-contained HTML output path")
    ap.add_argument("--web", metavar="DIR", default=None,
                    help="write JSON snapshot for the static dashboard into DIR (e.g. docs)")
    ap.add_argument("--no-html", action="store_true", help="skip the standalone HTML report")
    ap.add_argument("--no-iv", action="store_true",
                    help="skip yfinance ATM-IV enrichment; vol-state from realized vol only")
    ap.add_argument("--tws", action="store_true",
                    help="prefer the TWS vol provider (stub for now; falls back to approx)")
    ap.add_argument("--long-only", action="store_true")
    ap.add_argument("--short-only", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="cap universe size (debug)")
    ap.add_argument("--tickers", nargs="*", help="scan only these tickers")
    a = ap.parse_args()

    if a.long_only:
        CFG.allow_short = False
    if a.short_only:
        CFG.allow_long = False
    if a.tws:
        CFG.vol_source = "tws"

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
    print(f"[scan] {len(rows)} signals; classifying regime"
          + (" + IV enrichment" if (CFG.iv_enrich_hits and not a.no_iv) else "") + "...")
    vix_bw = fetch_vix_backwardation()
    add_regime(rows, bundle, iv_enrich=(CFG.iv_enrich_hits and not a.no_iv),
               vix_backwardation=vix_bw)

    if a.web:
        path = write_web(rows, a.web, scanned=len(bundle), universe=len(syms))
        print(f"[scan] -> {path} (+ dated snapshot)")

    if not a.no_html:
        out = a.out or "pa_report.html"
        write_report(rows, out, scanned=len(bundle), universe=len(syms))
        print(f"[scan] HTML report -> {out}")


if __name__ == "__main__":
    main()
