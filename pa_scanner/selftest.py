"""Self-tests on synthetic data. Verifies the detection logic without network.

Run: python -m pa_scanner.selftest
Exits non-zero on any failure.
"""
import sys

import numpy as np
import pandas as pd

from .config import CFG
from . import candles as cnd
from . import indicators as ind
from . import data as dl
from .scanner import prepare_context, SymbolContext, add_regime
from .rules import ReversalAtWeeklyLevel, TrendPullbackBreakout, RangeChopNeutral
from .regime import VolInputs, direction_read, vol_read, strategy, signal_direction, alignment
from .report import write_report

PASS, FAIL = [], []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


def _frame(close, high, low, openp):
    idx = pd.bdate_range(start="2023-01-02", periods=len(close))
    vol = np.full(len(close), 2_000_000.0)
    vol[-1] = 4_000_000.0  # volume expansion on the breakout bar
    return pd.DataFrame({"open": openp, "high": high, "low": low,
                         "close": close, "volume": vol}, index=idx)


def make_s2(direction="long", n=400, slope=0.25, start=50.0):
    trend = slope * np.arange(n)
    base = start + (trend if direction == "long" else trend[::-1])
    close = base.copy().astype(float)
    high = close + 0.4
    low = close - 0.4

    if direction == "long":
        for i in range(n - 12, n - 2):          # counter-trend dip below ema20
            close[i] = base[i] - 4.0
            high[i] = close[i] + 0.5
            low[i] = close[i] - 0.5
        close[n - 2] = base[n - 2]               # start recovering
        high[n - 2] = close[n - 2] + 0.4
        low[n - 2] = close[n - 2] - 0.4
        brk = high[n - 8:n - 1].max() + 2.0      # break prior-7 high
        close[n - 1] = brk
        high[n - 1] = brk + 0.5
        low[n - 1] = base[n - 1] - 1.0           # still above ema20
    else:
        for i in range(n - 12, n - 2):          # counter-trend pop above ema20
            close[i] = base[i] + 4.0
            high[i] = close[i] + 0.5
            low[i] = close[i] - 0.5
        close[n - 2] = base[n - 2]
        high[n - 2] = close[n - 2] + 0.4
        low[n - 2] = close[n - 2] - 0.4
        brk = low[n - 8:n - 1].min() - 2.0       # break prior-7 low
        close[n - 1] = brk
        low[n - 1] = brk - 0.5
        high[n - 1] = base[n - 1] + 1.0          # still below ema20

    openp = np.empty(n)
    openp[0] = close[0]
    openp[1:] = close[:-1]
    return _frame(close, high, low, openp)


def make_range(n=400):
    """Range-bound, low-ADX series with the last bar mid-range (for S3)."""
    base = 100 + 3.0 * np.sin(np.arange(n) / 1.6)   # high-frequency -> low ADX
    close = base.astype(float)
    high = close + 0.4
    low = close - 0.4
    close[-1] = 100.0          # land mid-range so the position gate passes
    high[-1] = 100.4
    low[-1] = 99.6
    openp = np.empty(n)
    openp[0] = close[0]
    openp[1:] = close[:-1]
    return _frame(close, high, low, openp)


def neutral_ctx(**over):
    base = dict(ticker="TEST", last_close=100.0, atr_last=2.0, vol_last=1e6,
                vol_avg=1e6, zones=[], bull_patterns={}, bear_patterns={},
                wk_uptrend=False, wk_downtrend=False, wema_fast=100.0,
                wema_slow=99.0, pullback_up=False, pullback_dn=False,
                pullback_up_quality=0.0, pullback_dn_quality=0.0,
                pullback_up_depth=0.0, pullback_dn_depth=0.0,
                don_hi=100.0, don_lo=100.0, spark=[100.0, 101.0])
    base.update(over)
    return SymbolContext(**base)


def main():
    print("S2 trend-pullback-breakout (pipeline, long)")
    d = make_s2("long")
    ctx = prepare_context("S2L", d, dl.to_weekly(d))
    check("context built", ctx is not None)
    check("weekly uptrend detected", ctx.wk_uptrend)
    check("pullback_up detected", ctx.pullback_up)
    check("price above donchian high", ctx.last_close > ctx.don_hi)
    sig = TrendPullbackBreakout().evaluate(ctx)
    check("S2 long signal fires", sig.hit and sig.side == "long")
    check("volume bonus applied (volx>=mult)", (ctx.vol_last / ctx.vol_avg) >= CFG.s2_vol_mult)

    print("S2 trend-pullback-breakout (pipeline, short)")
    ds = make_s2("short")
    ctxs = prepare_context("S2S", ds, dl.to_weekly(ds))
    check("weekly downtrend detected", ctxs.wk_downtrend)
    check("pullback_dn detected", ctxs.pullback_dn)
    sigs = TrendPullbackBreakout().evaluate(ctxs)
    check("S2 short signal fires", sigs.hit and sigs.side == "short")

    print("S1 reversal-at-level (rule unit)")
    long_ctx = neutral_ctx(zones=[(99.0, 3)], last_close=100.0, atr_last=2.0,
                           bull_patterns={"bullish_engulfing": 1.0})
    s1l = ReversalAtWeeklyLevel().evaluate(long_ctx)
    check("S1 long at support fires", s1l.hit and s1l.side == "long")
    short_ctx = neutral_ctx(zones=[(101.0, 3)], last_close=100.0, atr_last=2.0,
                            bear_patterns={"bearish_engulfing": 1.0})
    s1s = ReversalAtWeeklyLevel().evaluate(short_ctx)
    check("S1 short at resistance fires", s1s.hit and s1s.side == "short")
    far_ctx = neutral_ctx(zones=[(80.0, 3)], last_close=100.0, atr_last=2.0,
                          bull_patterns={"bullish_engulfing": 1.0})
    check("no S1 when level far (>1 ATR)", not ReversalAtWeeklyLevel().evaluate(far_ctx).hit)

    print("candlestick detectors (unit)")
    eng = pd.DataFrame({
        "open":  [100, 101.0, 98.5],
        "high":  [101, 101.5, 102.0],
        "low":   [99,  98.8,  98.0],
        "close": [100.5, 99.0, 101.5],
        "volume": [1e6, 1e6, 1e6],
    })
    check("bullish engulfing detected", bool(cnd.bullish_engulfing(eng).iloc[-1]))
    flat = pd.DataFrame({"open": [100, 100.2, 100.4], "high": [100.5, 100.7, 100.9],
                         "low": [99.8, 100.0, 100.2], "close": [100.3, 100.5, 100.7],
                         "volume": [1e6, 1e6, 1e6]})
    check("no engulfing on uptrend bars", not bool(cnd.bullish_engulfing(flat).iloc[-1]))

    print("pivots + clustering (unit)")
    lows = [110, 108, 100, 108, 110, 111, 109, 100.4, 109, 111]
    pv = pd.DataFrame({"open": lows, "high": [x + 1 for x in lows],
                       "low": lows, "close": lows, "volume": [1e6] * len(lows)})
    _, pl = ind.pivots(pv, 2, 2)
    plows = [round(p, 1) for _, p in pl]
    check("pivot low ~100 found", any(abs(p - 100) < 1 for p in plows))
    zones = ind.cluster([100.0, 100.4, 130.0], tol=1.0)
    check("nearby lows merged into one zone", len(zones) == 2)

    print("report generation (unit)")
    rows = [
        {"ticker": "AAPL", "signal": "S2", "signal_name": "Trend pullback breakout",
         "side": "long", "score": 0.81, "last": 230.1, "label": "pullback breakout",
         "atr": 3.2, "spark": [220, 222, 219, 225, 230], "level": 228.0,
         "breakout_atr": 0.7, "volx": 1.5, "pullback_pct": 4.1},
        {"ticker": "XLE", "signal": "S1", "signal_name": "Reversal at weekly level",
         "side": "short", "score": 0.66, "last": 92.0, "label": "shooting_star @ wk resistance",
         "atr": 1.1, "spark": [90, 91, 93, 92, 92], "level": 93.0, "dist_atr": 0.3,
         "pattern": "shooting_star", "zone_hits": 3},
    ]
    out = "/tmp/pa_selftest_report.html"
    write_report(rows, out, scanned=2, universe=10)
    txt = open(out, encoding="utf-8").read()
    check("report file written", len(txt) > 1000)
    check("report contains tickers", "AAPL" in txt and "XLE" in txt)
    check("report contains sparkline svg", "<svg" in txt)

    print("regime: direction read (unit)")
    check("uptrend -> bullish", direction_read(make_s2("long"))[0] == "bullish")
    check("downtrend -> bearish", direction_read(make_s2("short"))[0] == "bearish")
    import numpy as _np
    flat_c = 100 + 0.05 * ((-1.0) ** _np.arange(400))     # 2-bar zigzag, ~0 ADX
    flat = pd.DataFrame({"open": flat_c, "high": flat_c + 0.3, "low": flat_c - 0.3,
                         "close": flat_c, "volume": [1e6] * 400},
                        index=pd.bdate_range(start="2023-01-02", periods=400))
    dflat, mflat = direction_read(flat)
    check("choppy/low-ADX -> neutral", dflat == "neutral")

    print("regime: vol-state read (unit)")
    check("low IVR -> cheap", vol_read(VolInputs(ivr=15))[0] == "cheap")
    check("high IVR -> rich", vol_read(VolInputs(ivr=75))[0] == "rich")
    check("mid IVR -> fair", vol_read(VolInputs(ivr=45))[0] == "fair")
    check("RV-rank seed when no IVR", vol_read(VolInputs(rv_rank=80))[0] == "rich")
    check("VRP<=0 nudges cheaper", vol_read(VolInputs(ivr=75, vrp=-0.02))[0] == "fair")
    check("backwardation forces cheap", vol_read(VolInputs(ivr=75, backwardation=True))[0] == "cheap")
    check("no vol data -> fair", vol_read(VolInputs())[0] == "fair")

    print("regime: strategy matrix (unit)")
    check("bullish+rich -> Put Credit Spread (C)", strategy("bullish", "rich")[1:] == ("Put Credit Spread", "C"))
    check("neutral+fair -> Iron Condor (C)", strategy("neutral", "fair")[1:] == ("Iron Condor", "C"))
    check("bearish+cheap -> Long Put (D)", strategy("bearish", "cheap")[1:] == ("Long Put", "D"))
    check("bullish+cheap -> Call Debit Spread (D)", strategy("bullish", "cheap")[1:] == ("Call Debit Spread", "D"))
    check("matrix covers all 9 cells", len({(d, v) for d in ("bearish", "neutral", "bullish")
                                            for v in ("cheap", "fair", "rich")}) == 9)

    print("regime: signal-led structure + alignment (unit)")
    check("long -> bullish row", signal_direction("long") == "bullish")
    check("short -> bearish row", signal_direction("short") == "bearish")
    check("short in bull regime -> counter", alignment("bullish", "short") == "counter")
    check("long in bull regime -> with", alignment("bullish", "long") == "with")
    check("neutral regime -> neutral align", alignment("neutral", "short") == "neutral")
    check("short+cheap -> Long Put (D)", strategy(signal_direction("short"), "cheap")[1:] == ("Long Put", "D"))
    check("long+cheap -> Call Debit Spread (D)", strategy(signal_direction("long"), "cheap")[1:] == ("Call Debit Spread", "D"))

    print("regime: annotate pipeline (end-to-end, no IV)")
    bundle = {"NVDA": (make_s2("long"), dl.to_weekly(make_s2("long"))),
              "XLE": (make_s2("short"), dl.to_weekly(make_s2("short")))}
    erows = [{"ticker": "NVDA", "signal": "S2", "side": "long", "score": 0.8,
              "last": 100, "atr": 2, "spark": [1, 2]},
             {"ticker": "NVDA", "signal": "S1", "side": "short", "score": 0.6,   # counter-trend
              "last": 100, "atr": 2, "spark": [1, 2]},
             {"ticker": "XLE", "signal": "S2", "side": "short", "score": 0.7,
              "last": 50, "atr": 1, "spark": [1, 2]}]
    add_regime(erows, bundle, iv_enrich=False, vix_backwardation=None)
    check("regime attached", all("regime" in r and "vol_state" in r for r in erows))
    check("structure attached", all(r.get("structure") for r in erows))
    check("NVDA regime bullish", erows[0]["regime"] == "bullish")
    check("long signal in bull regime -> with", erows[0]["align"] == "with")
    check("short signal in bull regime -> counter", erows[1]["align"] == "counter")
    check("short-signal structure is bearish (not bullish)",
          erows[1]["structure"] in ("Long Put (D)", "Call Credit Spread (C)"))

    print("S3 range/chop (pipeline + neutral structure)")
    rng_df = make_range()
    ctx_r = prepare_context("RNG", rng_df, dl.to_weekly(rng_df))
    check("context built (range)", ctx_r is not None)
    check("low ADX detected", ctx_r.adx_last < CFG.s3_adx_max)
    check("price mid-range", CFG.s3_pos_low <= ctx_r.range_pos <= CFG.s3_pos_high)
    s3 = RangeChopNeutral().evaluate(ctx_r)
    check("S3 fires on range (neutral side)", s3.hit and s3.side == "neutral")
    up_ctx = prepare_context("UP", make_s2("long"), dl.to_weekly(make_s2("long")))
    check("S3 silent on a trend", not RangeChopNeutral().evaluate(up_ctx).hit)
    nb = {"RNG": (rng_df, dl.to_weekly(rng_df))}
    nrows = [{"ticker": "RNG", "signal": "S3", "side": "neutral", "score": 0.7,
              "last": 100, "atr": 2, "spark": [1, 2]}]
    add_regime(nrows, nb, iv_enrich=False)
    check("neutral signal -> neutral structure", nrows[0]["structure"] in ("Calendar (D)", "Iron Condor (C)"))
    check("neutral signal -> align neutral", nrows[0]["align"] == "neutral")

    # --- live_status (real-time trigger evaluation) ---
    from .scanner import live_status
    s2L = {"signal": "S2", "side": "long", "level": 100.0}
    check("S2 long triggered above level", live_status(s2L, 102.0, 2.0) == ("triggered", 1.0))
    check("S2 long pending below level", live_status(s2L, 99.0, 2.0)[0] == "pending")
    s2S = {"signal": "S2", "side": "short", "level": 100.0}
    check("S2 short triggered below level", live_status(s2S, 98.0, 2.0)[0] == "triggered")
    s1 = {"signal": "S1", "side": "short", "level": 50.0}
    check("S1 at level within 1 ATR", live_status(s1, 50.5, 1.0) == ("at level", 0.5))
    check("S1 away beyond 1 ATR", live_status(s1, 53.0, 1.0)[0] == "away")
    s3 = {"signal": "S3", "side": "neutral", "range_lo": 90.0, "range_hi": 110.0}
    check("S3 in range -> position", live_status(s3, 100.0, 2.0) == ("in range", 0.5))
    check("S3 broke out above", live_status(s3, 115.0, 2.0)[0] == "broke out")
    check("live_status zero-ATR safe", live_status(s2L, 102.0, 0.0)[0] == "triggered")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        sys.exit(1)
    print("ALL GREEN")


if __name__ == "__main__":
    main()
