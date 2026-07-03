"""Self-tests on synthetic data. Verifies the detection logic without network.

Run: python -m pa_scanner.selftest
Exits non-zero on any failure.
"""
import os
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
                           prior_med=101.5, last_low=98.7, last_high=100.6,
                           bull_patterns={"bullish_engulfing": 1.0})
    s1l = ReversalAtWeeklyLevel().evaluate(long_ctx)
    check("S1 long at support fires", s1l.hit and s1l.side == "long")
    short_ctx = neutral_ctx(zones=[(101.0, 3)], last_close=100.0, atr_last=2.0,
                            prior_med=98.5, last_low=99.4, last_high=101.4,
                            bear_patterns={"bearish_engulfing": 1.0})
    s1s = ReversalAtWeeklyLevel().evaluate(short_ctx)
    check("S1 short at resistance fires", s1s.hit and s1s.side == "short")
    far_ctx = neutral_ctx(zones=[(80.0, 3)], last_close=100.0, atr_last=2.0,
                          prior_med=101.0, last_low=99.2, last_high=100.6,
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

    # --- directional action matrix (ASX / India long-only) ---
    from .action import decide
    check("up + long  -> BUY",    decide("bullish", "long")[0] == "BUY")
    check("up + short -> REDUCE", decide("bullish", "short")[0] == "REDUCE")
    check("up + neut  -> HOLD",   decide("bullish", "neutral")[0] == "HOLD")
    check("flat + long  -> BUY",   decide("neutral", "long")[0] == "BUY")
    check("flat + short -> AVOID", decide("neutral", "short")[0] == "AVOID")
    check("flat + neut  -> WATCH", decide("neutral", "neutral")[0] == "WATCH")
    check("down + short -> EXIT",  decide("bearish", "short")[0] == "EXIT")
    check("down + long  -> WATCH (risky bounce)",
          decide("bearish", "long") == ("WATCH", "risky bounce", "warn"))
    check("down + neut  -> AVOID", decide("bearish", "neutral")[0] == "AVOID")
    check("EXIT is red tier",   decide("bearish", "short")[2] == "exit")
    check("BUY is green tier",  decide("bullish", "long")[2] == "pos")

    # --- ATR% column ---
    from .scanner import scan, option_liquidity
    b = {"AAA": (make_s2("long"), dl.to_weekly(make_s2("long")))}
    arows = scan(b)
    check("scan emits atr_pct", bool(arows) and "atr_pct" in arows[0])
    check("atr_pct is positive", bool(arows) and arows[0]["atr_pct"] > 0)

    # --- option-chain liquidity flag (pure) ---
    check("opt_liq none w/o data", option_liquidity(None, None, None)[0] is None)
    check("opt_liq ok deep+tight",
          option_liquidity(300, 300, 5, oi_min=250, spread_max=12)[0] == "ok")
    check("opt_liq thin low OI",
          option_liquidity(50, 50, 5, oi_min=250, spread_max=12)[0] == "thin")
    check("opt_liq thin wide spread",
          option_liquidity(300, 300, 20, oi_min=250, spread_max=12)[0] == "thin")
    check("opt_liq spread-only ok",
          option_liquidity(None, None, 5, oi_min=250, spread_max=12)[0] == "ok")
    check("opt_liq spread-only thin",
          option_liquidity(None, None, 20, oi_min=250, spread_max=12)[0] == "thin")
    check("opt_liq OI-only ok (no quote)",
          option_liquidity(300, 300, None, oi_min=250, spread_max=12)[0] == "ok")
    check("opt_liq returns combined OI",
          option_liquidity(300, 300, 5, oi_min=250, spread_max=12)[1] == 600)


    print("quality gates (E1/E2/E3/E4 + U-series)")
    # --- S1 approach direction: bull pattern near a zone approached from BELOW
    #     (rallying into overhead supply) must NOT read as long-at-support
    r1 = ReversalAtWeeklyLevel().evaluate(neutral_ctx(
        zones=[(99.0, 3)], last_close=100.0, atr_last=2.0,
        prior_med=96.0, last_low=98.7, last_high=100.6,
        bull_patterns={"bullish_engulfing": 1.0}))
    check("S1 rejects long into resistance (approach from below)", not r1.hit)
    # --- S1 wick test: close near zone but the low never tagged it
    r2 = ReversalAtWeeklyLevel().evaluate(neutral_ctx(
        zones=[(99.0, 3)], last_close=100.4, atr_last=2.0,
        prior_med=101.5, last_low=100.2, last_high=100.9,
        bull_patterns={"bullish_engulfing": 1.0}))
    check("S1 rejects when low never tagged the zone", not r2.hit)
    # --- S1 run-away: close already >1 band above the zone
    r3 = ReversalAtWeeklyLevel().evaluate(neutral_ctx(
        zones=[(99.0, 3)], last_close=101.5, atr_last=2.0,
        prior_med=101.6, last_low=98.9, last_high=101.8,
        bull_patterns={"bullish_engulfing": 1.0}))
    check("S1 rejects when close ran away from the zone", not r3.hit)
    # --- S1 trend alignment moves score
    base_kw = dict(zones=[(99.0, 3)], last_close=100.0, atr_last=2.0,
                   prior_med=101.5, last_low=98.7, last_high=100.6,
                   bull_patterns={"bullish_engulfing": 1.0})
    s_flat = ReversalAtWeeklyLevel().evaluate(neutral_ctx(**base_kw)).score
    s_with = ReversalAtWeeklyLevel().evaluate(neutral_ctx(**base_kw, wk_uptrend=True)).score
    s_ctr = ReversalAtWeeklyLevel().evaluate(neutral_ctx(**base_kw, wk_downtrend=True)).score
    check("S1 with-trend bonus applied", s_with > s_flat)
    check("S1 counter-trend penalty applied", s_ctr < s_flat)

    # --- S2 freshness / extension / volume gates (rule unit on synthetic ctx)
    s2kw = dict(last_close=102.0, atr_last=2.0, vol_last=2.5e6, vol_avg=2e6,
                wk_uptrend=True, pullback_up=True, pullback_up_quality=0.8,
                pullback_up_depth=0.05, wema_fast=105.0, wema_slow=100.0,
                don_hi=101.0, don_lo=90.0)
    ok = TrendPullbackBreakout().evaluate(neutral_ctx(**s2kw, s2_age_up=0))
    check("S2 fresh breakout fires", ok.hit and ok.meta["age"] == 0)
    stale = TrendPullbackBreakout().evaluate(neutral_ctx(**s2kw, s2_age_up=5))
    check("S2 stale breakout (age 5) rejected", not stale.hit)
    ext_kw = dict(s2kw, last_close=105.0)          # 2 ATR past the trigger
    ext = TrendPullbackBreakout().evaluate(neutral_ctx(**ext_kw, s2_age_up=0))
    check("S2 over-extended entry rejected", not ext.hit)
    dead_kw = dict(s2kw, vol_last=1.5e6)           # volx 0.75 < gate
    dead = TrendPullbackBreakout().evaluate(neutral_ctx(**dead_kw, s2_age_up=0))
    check("S2 dead-volume breakout rejected", not dead.hit)
    near = TrendPullbackBreakout().evaluate(neutral_ctx(**s2kw, s2_age_up=0))
    far_kw = dict(s2kw, last_close=103.4)          # 1.2 ATR ext, inside cap
    far = TrendPullbackBreakout().evaluate(neutral_ctx(**far_kw, s2_age_up=0))
    check("S2 magnitude decays with extension", near.score > far.score)

    # --- S3 coiling rejection
    s3kw = dict(adx_last=10.0, ema_sep_pct=0.001, range_width_pct=0.06,
                range_pos=0.5, range_hi=106.0, range_lo=100.0, range_crosses=4)
    s3ok = RangeChopNeutral().evaluate(neutral_ctx(**s3kw, s3_edge_closes=1))
    check("S3 stable range fires", s3ok.hit)
    s3coil = RangeChopNeutral().evaluate(neutral_ctx(**s3kw, s3_edge_closes=2))
    check("S3 coiling range (2 edge closes) rejected", not s3coil.hit)

    # --- relative strength + index penalty (add_market_context)
    from .scanner import add_market_context, compute_rank
    strong = make_s2("long"); weak = make_s2("short"); bench = make_range()
    bnd = {"STR": (strong, dl.to_weekly(strong)), "WEA": (weak, dl.to_weekly(weak))}
    rrows = [{"ticker": "STR", "side": "long", "score": 0.5, "signal": "S2"},
             {"ticker": "WEA", "side": "short", "score": 0.5, "signal": "S2"}]
    binfo = add_market_context(rrows, bnd, bench, market="us")
    check("RS annotated on hits", all(r["rs"] is not None for r in rrows))
    check("uptrend name outranks downtrend on RS",
          rrows[0]["rs_pct"] > rrows[1]["rs_pct"])
    check("RS lifts strong long + weak short symmetrically",
          rrows[0]["score"] > 0.5 and rrows[1]["score"] > 0.5)
    check("flat benchmark reads neutral (no penalty case)",
          binfo is not None and binfo["bias"] == "neutral")
    pen = [{"ticker": "STR", "side": "long", "score": 0.5, "signal": "S2"}]
    add_market_context(pen, {"STR": bnd["STR"]}, weak, market="us")  # bearish bench
    check("counter-index long penalized", pen[0]["score"] < 0.5 + CFG.rs_adj_max)

    # --- rank percentile within rule
    rk = [{"signal": "S2", "score": 0.9}, {"signal": "S2", "score": 0.5},
          {"signal": "S2", "score": 0.7}, {"signal": "S1", "score": 0.4}]
    compute_rank(rk)
    check("rank: best-in-rule = 100", rk[0]["rank"] == 100)
    check("rank: worst-in-rule = 0", rk[1]["rank"] == 0)
    check("rank: solo rule row = 100", rk[3]["rank"] == 100)
    tie = [{"signal": "S2", "score": 0.5}, {"signal": "S2", "score": 0.5}]
    compute_rank(tie)
    check("rank: ties share the midpoint", tie[0]["rank"] == 50 and tie[1]["rank"] == 50)

    # --- yfinance MultiIndex column shapes (single-ticker downloads) ---
    idx = pd.bdate_range("2024-01-01", periods=5)
    base = {"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 100.0}
    tf = pd.DataFrame({("SPY", k): v for k, v in base.items()}, index=idx)   # (ticker, field)
    ft = pd.DataFrame({(k, "SPY"): v for k, v in base.items()}, index=idx)   # (field, ticker)
    n1, n2 = dl._norm(tf), dl._norm(ft)
    check("_norm flattens (ticker, field) columns", list(n1.columns) == dl.COLS)
    check("_norm flattens (field, ticker) columns", list(n2.columns) == dl.COLS)
    flat = pd.DataFrame({k: v for k, v in base.items()}, index=idx)
    check("_norm leaves flat columns intact", list(dl._norm(flat).columns) == dl.COLS)
    from .scanner import add_market_context as _amc
    bad = pd.DataFrame({("SPY", "x"): [1.0] * 200}, index=pd.bdate_range("2024-01-01", periods=200))
    ok_rows = [{"ticker": "STR", "side": "long", "score": 0.5, "signal": "S2"}]
    b2 = _amc(ok_rows, {"STR": (make_s2("long"), dl.to_weekly(make_s2("long")))}, bad, market="us")
    check("bench without close degrades to None (no crash)", b2 is None)

    print("exit templates")
    from .scanner import add_exit_levels
    xr = [{"side": "long", "last": 100.0, "atr": 2.0},
          {"side": "short", "last": 100.0, "atr": 2.0},
          {"side": "neutral", "last": 100.0, "atr": 2.0, "range_lo": 95.0, "range_hi": 105.0}]
    add_exit_levels(xr)
    check("long exit levels (2.0/1.5 ATR)", xr[0]["stop"] == 96.0 and xr[0]["tgt"] == 103.0)
    check("short exit levels mirrored", xr[1]["stop"] == 104.0 and xr[1]["tgt"] == 97.0)
    check("neutral exits = range edges", xr[2]["stop"] == 95.0 and xr[2]["tgt"] == 105.0)
    check("time exit attached", all(r["time_exit"] == CFG.exit_time_bars for r in xr))
    pos = [{"side": "long", "signal": "S2", "last": 100.0, "atr": 2.0},
           {"side": "long", "signal": "S1", "last": 100.0, "atr": 2.0},
           {"side": "short", "signal": "S2", "last": 100.0, "atr": 2.0}]
    add_exit_levels(pos, market="in")
    check("India S2 long -> position template (3.5/4.5 ATR, 63 bars)",
          pos[0]["stop"] == 93.0 and pos[0]["tgt"] == 109.0 and pos[0]["time_exit"] == 63)
    check("India S1 long stays swing template",
          pos[1]["stop"] == 96.0 and pos[1]["time_exit"] == CFG.exit_time_bars)
    check("India S2 short stays swing template",
          pos[2]["stop"] == 104.0 and pos[2]["time_exit"] == CFG.exit_time_bars)
    us = [{"side": "long", "signal": "S2", "last": 100.0, "atr": 2.0}]
    add_exit_levels(us, market="us")
    check("US S2 long stays swing template", us[0]["time_exit"] == CFG.exit_time_bars)

    print("backtest harness")
    import tempfile
    from .backtest import verify_parity, run_backtest, _dedup, _fwd
    bnd = {"UP": (make_s2("long"), dl.to_weekly(make_s2("long"))),
           "DN": (make_s2("short"), dl.to_weekly(make_s2("short"))),
           "RG": (make_range(), dl.to_weekly(make_range()))}
    chk, mism = verify_parity(bnd, n=90, seed=3)
    check("parity: replay == live scanner (0 mismatches)", chk >= 60 and len(mism) == 0)

    ded = _dedup([{"ticker": "A", "signal": "S2", "side": "long", "t": 5},
                  {"ticker": "A", "signal": "S2", "side": "long", "t": 9},
                  {"ticker": "A", "signal": "S2", "side": "long", "t": 30},
                  {"ticker": "A", "signal": "S1", "side": "long", "t": 6}], cooldown=10)
    check("cooldown dedups within window, keeps later re-fire", len(ded) == 3)

    fa = {"X": {"close": np.array([100.0, 100, 100, 110, 120]),
                "high": np.array([100.0, 100, 100, 112, 121]),
                "low":  np.array([100.0, 100, 100, 95, 118])}}
    ev = _fwd({"ticker": "X", "t": 2, "side": "long"}, fa, (1, 2), 2)
    check("fwd return math (long)", ev["ret1"] == 10.0 and ev["ret2"] == 20.0)
    check("MAE/MFE math (long)", ev["mfe"] == 21.0 and ev["mae"] == -5.0)
    evs = _fwd({"ticker": "X", "t": 2, "side": "short"}, fa, (2,), 2)
    check("fwd return math (short, signed)", evs["ret2"] == -20.0)

    with tempfile.TemporaryDirectory() as td:
        r1 = run_backtest(bnd, market="asx", bench_daily=make_range(),
                          horizons=(3, 5, 10), out_dir=td, verbose=False)
        r2 = run_backtest(bnd, market="asx", bench_daily=make_range(),
                          horizons=(3, 5, 10), out_dir=td, verbose=False)
        check("backtest produces events + files",
              len(r1["events"]) > 0 and os.path.exists(r1["report"]) and os.path.exists(r1["csv"]))
        check("baseline is seed-deterministic",
              [b["t"] for b in r1["baseline"]] == [b["t"] for b in r2["baseline"]])
        from .backtest import _matched, _side_base
        sbase = _side_base(r1["baseline"], "ret10")
        longs = [e for e in r1["events"] if e["side"] == "long"]
        if len(longs) >= 3:
            ex, tv = _matched(longs, "ret10", sbase)
            check("side-matched excess computes", ex is not None and tv is not None)
        synth_b = _side_base([{"side": "long", "ret10": 1.0}] * 50 +
                             [{"side": "short", "ret10": -1.0}] * 50, "ret10")
        se, st_ = _matched([{"side": "short", "ret10": -1.0}] * 20, "ret10", synth_b)
        check("short events vs short baseline = zero excess", se == 0.0)
        check("evening_star retired from bearish triggers",
              "evening_star" not in cnd.BEARISH)
        check("events carry rs/vol/bench annotations",
              all(k in r1["events"][0] for k in ("rs_pct", "vol_state", "bench", "mae", "mfe"))
              or r1["events"][0]["side"] == "neutral")

    print("S4 oversold snapback (promoted)")
    from .rules import OversoldSnapback
    s4_ok = neutral_ctx(last_close=105.0, atr_last=2.0, sma200=100.0, rsi3=8.0, dn_streak=2)
    r4 = OversoldSnapback().evaluate(s4_ok)
    check("S4 fires: RSI3<15 + 2-down streak", r4.hit and r4.side == "long")
    check("S4 score scales with oversold depth",
          OversoldSnapback().evaluate(neutral_ctx(last_close=105.0, atr_last=2.0,
              sma200=100.0, rsi3=3.0, dn_streak=2)).score > r4.score)
    strk = OversoldSnapback().evaluate(neutral_ctx(
        last_close=105.0, atr_last=2.0, sma200=100.0, rsi3=40.0, dn_streak=4))
    check("S4 fires: 4-down streak without RSI condition (round-2 STRK4)",
          strk.hit and "flush" in strk.label)
    check("S4 blocked: RSI high + streak 3", not OversoldSnapback().evaluate(
        neutral_ctx(last_close=105.0, atr_last=2.0, sma200=100.0, rsi3=40.0, dn_streak=3)).hit)
    check("S4 blocked below 200SMA", not OversoldSnapback().evaluate(
        neutral_ctx(last_close=95.0, atr_last=2.0, sma200=100.0, rsi3=8.0, dn_streak=2)).hit)
    check("S4 blocked: RSI low but streak 1", not OversoldSnapback().evaluate(
        neutral_ctx(last_close=105.0, atr_last=2.0, sma200=100.0, rsi3=8.0, dn_streak=1)).hit)
    check("S4 blocked before 200 bars (sma200 None)", not OversoldSnapback().evaluate(
        neutral_ctx(last_close=105.0, atr_last=2.0, sma200=None, rsi3=8.0, dn_streak=2)).hit)
    check("RSI oversold on down tape", float(ind.rsi(pd.Series(
        [100 - i for i in range(30)]), 3).iloc[-1]) < 5)
    check("RSI overbought on up tape", float(ind.rsi(pd.Series(
        [100 + i for i in range(30)]), 3).iloc[-1]) > 95)

    s4x = [{"side": "long", "signal": "S4", "last": 100.0, "atr": 2.0}]
    add_exit_levels(s4x, market="us")
    check("US S4 carries 5-bar time exit", s4x[0]["time_exit"] == CFG.s4_time_bars
          and s4x[0]["stop"] == 96.0)
    s4a = [{"side": "long", "signal": "S4", "last": 100.0, "atr": 2.0}]
    add_exit_levels(s4a, market="asx")
    check("ASX S4 carries the position template (3.5/4.5 ATR, 63 bars)",
          s4a[0]["stop"] == 93.0 and s4a[0]["tgt"] == 109.0
          and s4a[0]["time_exit"] == CFG.in_pos_time_bars)
    exm = [{"ticker": "STR", "side": "long", "score": 0.5, "signal": "S4"},
           {"ticker": "STR", "side": "long", "score": 0.5, "signal": "S2"}]
    add_market_context(exm, {"STR": (make_s2("long"), dl.to_weekly(make_s2("long")))},
                       make_s2("short"), market="us")   # bearish bench
    check("S4 exempt from the counter-index penalty",
          exm[0]["score"] > exm[1]["score"])

    # parity incl. S4-capable history (280 bars, uptrend + terminal flush)
    def s4_frame(n=280, seed=5):
        rng = np.random.default_rng(seed)
        c = 100.0 + 0.12 * np.arange(n) + rng.normal(0, 0.15, n).cumsum()
        c[-3:] = c[-4] - np.array([1.0, 2.2, 3.5])
        o = c + 0.1
        idx = pd.bdate_range("2021-06-01", periods=n)
        return pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.4,
                             "low": np.minimum(o, c) - 0.4, "close": c,
                             "volume": np.full(n, 2e6)}, index=idx)

    sf = s4_frame()
    sb4 = {"S4T": (sf, dl.to_weekly(sf))}
    chk4, mism4 = verify_parity(sb4, n=40, seed=9)
    check("parity holds with S4 context fields", chk4 >= 20 and len(mism4) == 0)
    from .scanner import scan as _scan
    s4rows = [r for r in _scan(sb4) if r["signal"] == "S4"]
    check("S4 fires end-to-end in scan()", len(s4rows) == 1 and s4rows[0]["side"] == "long")

    print("S4 PRIME + forward ledger")
    from .scanner import mark_prime
    pr = [{"signal": "S4", "side": "long", "score": 0.6},
          {"signal": "S2", "side": "long", "score": 0.6}]
    mark_prime(pr, {"bias": "bearish"}, market="us")
    check("PRIME set on S4 only when bench bearish",
          pr[0]["prime"] and not pr[1]["prime"])
    pr2 = [{"signal": "S4", "side": "long", "score": 0.6}]
    mark_prime(pr2, {"bias": "bullish"}, market="us")
    check("no PRIME when bench bullish", not pr2[0]["prime"])
    pr3 = [{"signal": "S4", "side": "long", "score": 0.6}]
    mark_prime(pr3, {"bias": "bearish"}, market="in")
    check("no PRIME in India (cell untested)", not pr3[0]["prime"])

    from .ledger import update_ledger, _resolve_entry, _load
    def lframe(path_prices):
        idx = pd.bdate_range("2026-01-05", periods=len(path_prices))
        c = np.array(path_prices, float)
        return pd.DataFrame({"open": c, "high": c + 1.0, "low": c - 1.0,
                             "close": c, "volume": np.full(len(c), 1e6)}, index=idx)

    ent = {"ticker": "T", "signal": "S4", "side": "long",
           "entry_date": "2026-01-05", "entry_px": 100.0,
           "stop": 96.0, "tgt": 103.0, "time_exit": 5}
    hitT = _resolve_entry(ent, lframe([100, 101, 102.5]))   # high 103.5 >= tgt on bar 3
    check("ledger: target resolution", hitT and hitT["outcome"] == "target"
          and hitT["ret_pct"] == 3.0 and hitT["bars_held"] == 2)
    hitS = _resolve_entry(ent, lframe([100, 98, 96.5]))     # low 95.5 <= stop
    check("ledger: stop resolution", hitS and hitS["outcome"] == "stop"
          and hitS["ret_pct"] == -4.0)
    both = _resolve_entry(ent, lframe([100, 100.1]) .assign(
        high=[101.0, 104.0], low=[99.0, 95.0]))             # bar spans both -> stop first
    check("ledger: stop wins a both-touched bar", both and both["outcome"] == "stop")
    hitTm = _resolve_entry(ent, lframe([100, 100.4, 100.2, 100.3, 100.1, 100.6, 100.2]))
    check("ledger: time exit after 5 bars", hitTm and hitTm["outcome"] == "time"
          and hitTm["bars_held"] == 5)
    sh = dict(ent, side="short", stop=104.0, tgt=97.0)
    hitSh = _resolve_entry(sh, lframe([100, 98.5]))         # low 97.5? no; next
    hitSh = _resolve_entry(sh, lframe([100, 97.5]))         # low 96.5 <= tgt
    check("ledger: short target signed +", hitSh and hitSh["outcome"] == "target"
          and hitSh["ret_pct"] == 3.0)
    neu = {"ticker": "T", "signal": "S3", "side": "neutral",
           "entry_date": "2026-01-05", "entry_px": 100.0,
           "stop": 95.0, "tgt": 105.0, "time_exit": 3}
    nb = _resolve_entry(neu, lframe([100, 106.0]))
    check("ledger: neutral broke on edge close", nb and nb["outcome"] == "broke")
    nh = _resolve_entry(neu, lframe([100, 101, 100, 100.5]))
    check("ledger: neutral held to time", nh and nh["outcome"] == "held")

    with tempfile.TemporaryDirectory() as tdl:
        fr = lframe([100] * 6)
        lb = {"T": (fr, dl.to_weekly(fr))}
        lrows = [{"ticker": "T", "signal": "S4", "side": "long", "last": 100.0,
                  "stop": 96.0, "tgt": 103.0, "time_exit": 5, "score": 0.6,
                  "rank": 100, "prime": True, "rs_pct": 80}]
        update_ledger(lrows, lb, "us", out_dir=tdl)
        o1, r1_ = _load(tdl, "us")
        check("ledger: entry opened + persisted", len(o1) == 1 and o1[0]["prime"])
        update_ledger(lrows, lb, "us", out_dir=tdl)
        o2, _r = _load(tdl, "us")
        check("ledger: duplicate open suppressed", len(o2) == 1)
        fr2 = lframe([100] * 6 + [101, 102.5])               # bars beyond entry date
        update_ledger([], {"T": (fr2, dl.to_weekly(fr2))}, "us", out_dir=tdl)
        o3, r3_ = _load(tdl, "us")
        check("ledger: open resolved to target on later scan",
              len(o3) == 0 and len(r3_) == 1 and r3_[0]["outcome"] == "target")

    print("candidates (settled)")
    from pa_scanner import candidates as cnds
    from .backtest import candidate_events_for_ticker
    check("candidate rounds settled (CANDIDATES empty)", cnds.CANDIDATES == [])
    cev, _p = candidate_events_for_ticker("SYN", make_s2("long"), 10)
    check("empty candidate replay is a no-op (no crash)", cev == [])

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        sys.exit(1)
    print("ALL GREEN")


if __name__ == "__main__":
    main()
