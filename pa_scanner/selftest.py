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
from .scanner import prepare_context, SymbolContext
from .rules import ReversalAtWeeklyLevel, TrendPullbackBreakout
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

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        sys.exit(1)
    print("ALL GREEN")


if __name__ == "__main__":
    main()
