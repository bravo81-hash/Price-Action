"""CLI entrypoint.

Examples:
  python -m pa_scanner.cli                       # full scan -> pa_report.html
  python -m pa_scanner.cli --web docs            # write JSON for the Pages dashboard
  python -m pa_scanner.cli --web docs --no-html
  python -m pa_scanner.cli --no-iv               # skip yfinance IV enrichment (faster)
  python -m pa_scanner.cli --tickers AAPL MSFT NVDA SPY
"""
import argparse
import sys

from .config import CFG, MARKETS
from . import universe as uni
from . import data as dl
from .scanner import scan, add_regime, add_market_context, compute_rank, add_exit_levels, mark_prime, add_live_directional
from .action import add_action
from .earnings import annotate_earnings
from .ledger import update_ledger
from .snapshot import build_snapshot
from .strategy_board import build_board, annotate_evidence
from .report import write_report
from .webexport import write_web
from .pattern_integration import annotate_pattern_matches


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


def _live_failure_reason(health):
    """Human-readable reason for a failed --live health gate."""
    if not (health or {}).get("connected"):
        return "TWS not connected"
    return (f"only {(health or {}).get('fresh', 0)}/"
            f"{(health or {}).get('total', 0)} rows got fresh quotes")


def main():
    ap = argparse.ArgumentParser(description="Weekly-level / trend-pullback price-action scanner")
    ap.add_argument("--market", choices=list(MARKETS), default="us",
                    help="us = options playbook (default); asx / in = long-only directional screen")
    ap.add_argument("--out", default=None, help="self-contained HTML output path")
    ap.add_argument("--web", metavar="DIR", default=None,
                    help="write JSON snapshot for the static dashboard into DIR (e.g. docs)")
    ap.add_argument("--no-html", action="store_true", help="skip the standalone HTML report")
    ap.add_argument("--no-iv", action="store_true",
                    help="skip yfinance ATM-IV enrichment; vol-state from realized vol only")
    ap.add_argument("--min-score", type=float, default=None,
                    help=f"post-adjustment score floor (default {CFG.min_score}; 0 disables)")
    ap.add_argument("--no-earnings", action="store_true",
                    help="US: skip days-to-earnings enrichment")
    ap.add_argument("--no-ledger", action="store_true",
                    help="skip forward-ledger update")
    ap.add_argument("--tws", action="store_true",
                    help="prefer the TWS vol provider (stub for now; falls back to approx)")
    ap.add_argument("--live", action="store_true",
                    help="last-hour mode: real-time TWS prices + live trigger status (implies --tws, live data)")
    ap.add_argument("--long-only", action="store_true")
    ap.add_argument("--short-only", action="store_true")
    ap.add_argument("--no-neutral", action="store_true", help="disable S3 range/chop signals")
    ap.add_argument("--limit", type=int, default=None, help="cap universe size (debug)")
    ap.add_argument("--tickers", nargs="*", help="scan only these tickers")
    a = ap.parse_args()

    mkt = MARKETS[a.market]
    directional = mkt["mode"] == "directional"

    if a.long_only:
        CFG.allow_short = False
    if a.short_only:
        CFG.allow_long = False
    if a.no_neutral:
        CFG.allow_neutral = False
    live_directional = a.live and a.market == "asx"   # ASX trades via IBKR/TWS
    if a.tws and not directional:
        CFG.vol_source = "tws"
    if a.live and not directional:      # real-time last-hour mode (US/options)
        CFG.vol_source = "tws"
        CFG.tws_market_data_type = 1    # live ticks for prices + greeks
    if live_directional:                # ASX directional live
        CFG.tws_market_data_type = 1
    live = a.live and not directional
    if a.live and a.market == "in":
        print("[live] India trades via a separate broker (no TWS); --live ignored")

    syms = a.tickers or uni.universe_for(a.market)
    if a.limit:
        syms = syms[:a.limit]
    print(f"[scan] {mkt['label']} universe = {len(syms)} symbols; downloading daily history...")

    daily = dl.download_daily(syms)
    print(f"[scan] fetched {len(daily)}; liquidity filter + weekly resample...")

    bundle = {}
    for t, d in daily.items():
        if not dl.passes_liquidity(d, mkt["min_price"], mkt["min_dollar_vol"]):
            continue
        bundle[t] = (d, dl.to_weekly(d))
    print(f"[scan] {len(bundle)} liquid symbols; running rules...")

    rows = scan(bundle)

    # market context: relative strength vs the benchmark + index-regime read
    bench_sym = mkt["bench"]
    aux_syms = [bench_sym] + (["QQQ", "IWM", "^VIX", "HYG"] if a.market == "us" else [])
    bd = dl.download_daily(aux_syms)
    bench_daily = bd.get(bench_sym)
    binfo = add_market_context(rows, bundle, bench_daily, market=a.market)
    snap = build_snapshot(bench_daily, qqq=bd.get("QQQ"), iwm=bd.get("IWM"),
                          vix=bd.get("^VIX"), hyg=bd.get("HYG"))
    if binfo is not None:
        binfo["snap"] = {"state": snap["state"], "guidance": snap["guidance"]}
    print(f"[snapshot] {snap['state']} - {snap['guidance']} "
          f"({'; '.join(snap['reasons'])})")

    floor = CFG.min_score if a.min_score is None else a.min_score
    if floor > 0:
        n0 = len(rows)
        rows = [r for r in rows if r["score"] >= floor]
        print(f"[scan] score floor {floor}: {n0} -> {len(rows)} signals")
    # PRIME before enrichment: TWS budget (top-N in row order) must reach the
    # highest-evidence rows first, not just highest raw score.
    mark_prime(rows, binfo, market=a.market)
    bench_bias = (binfo or {}).get("bias")
    annotate_evidence(rows, a.market, bench_bias)
    rows.sort(key=lambda r: (r.get("evidence_rank", 99), -r["score"]))
    live_health = None
    if directional:
        print(f"[scan] {len(rows)} signals; assigning long-only actions...")
        add_action(rows, bundle)
        if live_directional:
            print(f"[scan] {len(rows)} signals; real-time TWS refresh...")
            _, live_health = add_live_directional(rows, market=a.market)
    else:
        print(f"[scan] {len(rows)} signals; classifying regime"
              + (" + IV enrichment" if (CFG.iv_enrich_hits and not a.no_iv) else "") + "...")
        vix_bw = fetch_vix_backwardation()
        if live:
            rows, live_health = add_regime(
                rows, bundle, iv_enrich=(CFG.iv_enrich_hits and not a.no_iv),
                vix_backwardation=vix_bw, live=True, market=a.market,
                return_health=True)
        else:
            add_regime(rows, bundle, iv_enrich=(CFG.iv_enrich_hits and not a.no_iv),
                       vix_backwardation=vix_bw, live=False, market=a.market)
        if CFG.earnings_enrich and not a.no_earnings:
            annotate_earnings(rows)

    # Fail before writing reports or publishing snapshots. A command explicitly
    # named --live must never leave behind a fresh-looking fallback artifact.
    live_requested = a.live and a.market in ("us", "asx")
    if live_requested and rows and not (live_health or {}).get("ok"):
        reason = _live_failure_reason(live_health)
        print(f"[live] FAIL: real-time data incomplete ({reason}). "
              f"Is TWS running, logged in, and entitled for {a.market.upper()}?")
        sys.exit(2)

    compute_rank(rows)
    add_exit_levels(rows, market=a.market)
    pattern_meta = annotate_pattern_matches(rows, bundle, bench_daily=bench_daily)
    print(f"[patterns] {pattern_meta['matched_tickers']}/"
          f"{pattern_meta['tickers_scanned']} tickers have actionable FVS patterns")

    board = build_board(a.market, bench_bias, rows,
                        snap_state=snap["state"])
    if binfo is not None:
        binfo["board"] = board
    print("[board] " + " > ".join(f"{e['code']}:{e['tier']}" for e in board["entries"]))

    if a.web:
        path = write_web(rows, a.web, scanned=len(bundle), universe=len(syms),
                         market=a.market, bench=binfo, pattern=pattern_meta)
        print(f"[scan] -> {path} (+ dated snapshot)")
        if not a.no_ledger:
            update_ledger(rows, bundle, a.market, out_dir=a.web)

    if not a.no_html:
        out = a.out or ("pa_report.html" if a.market == "us" else f"pa_report_{a.market}.html")
        write_report(rows, out, scanned=len(bundle), universe=len(syms),
                     market=a.market, bench=binfo)
        print(f"[scan] HTML report -> {out}")

if __name__ == "__main__":
    main()
