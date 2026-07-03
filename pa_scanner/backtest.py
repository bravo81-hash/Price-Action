"""Event-study backtest: replay the scanner over history, measure forward edge.

Fidelity model
--------------
Every daily indicator in prepare_context is causal (ewm / rolling), so its
full-series value at bar t equals what a prefix computation would produce.
The replay therefore precomputes full-series arrays once per ticker, rebuilds
the exact SymbolContext at each bar, and feeds it to the REAL rule objects
(pa_scanner.rules.RULES) - zero reimplementation of signal logic. Weekly
zones/trend per completed week are built by calling the real pivots/cluster/
ema functions on the same windows live uses. `verify_parity()` proves the
equivalence by running the live prepare_context on prefix slices at sampled
bars and diffing rule outputs; the selftest requires 100% agreement.

What it measures
----------------
For each first-fire event (per ticker+rule+side, cooldown-deduplicated):
  - signed forward returns at the requested horizons (long +, short -)
  - MAE / MFE within the max horizon (stop/target placement data)
  - S3 (neutral): range hold-rate and absolute move vs baseline
against a seeded random baseline drawn from the same universe/date-range,
sliced by rule, score decile, RS bucket, weekly-trend alignment, benchmark
regime, S2 age and S1 pattern.

Historical vol-state uses the free-path proxy (realized-vol rank), tagged
"rv-proxy" - true IVR history isn't replayable without stored option data.

Usage
-----
  python -m pa_scanner.backtest --market us            # full US event study
  python -m pa_scanner.backtest --market asx --verify 150
  python -m pa_scanner.backtest --tickers AAPL MSFT --horizons 5 10
"""
import argparse
import datetime as dt
import os
import random

import numpy as np
import pandas as pd

from .config import CFG, MARKETS
from . import indicators as ind
from . import candles as cnd
from . import data as dl
from . import universe as uni
from . import regime as rg
from .rules import RULES
from .scanner import SymbolContext, prepare_context

MAX_AGE_SCAN = 15          # mirrors prepare_context's age cap
WEAK_BULL = ("hammer", "tweezer_bottom")
WEAK_BEAR = ("shooting_star", "tweezer_top")


# --------------------------------------------------------------------------
# per-ticker precomputation
# --------------------------------------------------------------------------
def _week_label(ts):
    """Daily timestamp -> its W-FRI resample label (the week's Friday)."""
    return ts + pd.Timedelta(days=4 - ts.weekday())


def _weekly_tables(weekly):
    """Per completed-week-view tables, built with the live code's own functions.

    view w = weekly.iloc[:w+1]  (all weeks up to and including label w)
    Returns dict of arrays/lists indexed by w.
    """
    n = len(weekly)
    wc = weekly["close"]
    wema_f = ind.ema(wc, CFG.s2_wema_fast).to_numpy()
    wema_s = ind.ema(wc, CFG.s2_wema_slow).to_numpy()

    up = np.zeros(n, bool)
    dn = np.zeros(n, bool)
    zones = [[] for _ in range(n)]
    for w in range(1, n):
        u = (wema_f[w] > wema_s[w]) and (wema_f[w] > wema_f[w - 1])
        d_ = (wema_f[w] < wema_s[w]) and (wema_f[w] < wema_f[w - 1])
        if CFG.s2_require_structure:
            view = weekly.iloc[:w + 1]
            ph_s, pl_s = ind.pivots(view, CFG.s1_pivot_left, CFG.s1_pivot_right)
            ris = len(ph_s) >= 2 and ph_s[-1][1] > ph_s[-2][1]
            fal = len(ph_s) >= 2 and ph_s[-1][1] < ph_s[-2][1]
            ris_l = len(pl_s) >= 2 and pl_s[-1][1] > pl_s[-2][1]
            fal_l = len(pl_s) >= 2 and pl_s[-1][1] < pl_s[-2][1]
            u = u and ris and ris_l
            d_ = d_ and fal and fal_l
        up[w], dn[w] = u, d_

        wk_lb = weekly.iloc[max(0, w + 1 - CFG.s1_pivot_lookback_weeks):w + 1]
        if len(wk_lb) > CFG.atr_window:
            watr = float(ind.atr(wk_lb).iloc[-1])
            if watr > 0:
                ph, pl = ind.pivots(wk_lb, CFG.s1_pivot_left, CFG.s1_pivot_right)
                levels = [p for _, p in ph] + [p for _, p in pl]
                zones[w] = ind.cluster(levels, CFG.s1_cluster_atr * watr)
    return {"wema_f": wema_f, "wema_s": wema_s, "up": up, "dn": dn,
            "zones": zones, "labels": weekly.index}


def _daily_arrays(d):
    """Full-series causal arrays matching prepare_context field-for-field."""
    A = {}
    c, h, lo, v = d["close"], d["high"], d["low"], d["volume"]
    A["close"], A["high"], A["low"], A["vol"] = (x.to_numpy(float) for x in (c, h, lo, v))
    A["atr"] = ind.atr(d).to_numpy()
    ema20 = ind.ema(c, CFG.ema_fast_daily)
    ema50 = ind.ema(c, CFG.ema_slow_daily)
    A["ema20"], A["ema50"] = ema20.to_numpy(), ema50.to_numpy()
    don_hi, don_lo = ind.donchian(d, CFG.s2_breakout_n)
    A["don_hi"], A["don_lo"] = don_hi.to_numpy(), don_lo.to_numpy()
    adx_s, pdi, mdi = ind.adx(d)
    A["adx"] = np.nan_to_num(adx_s.to_numpy())
    A["pdi"], A["mdi"] = np.nan_to_num(pdi.to_numpy()), np.nan_to_num(mdi.to_numpy())
    A["vol_avg"] = v.rolling(CFG.s2_vol_window).mean().shift(1).to_numpy()
    A["prior_med"] = c.rolling(CFG.s1_approach_bars).median().shift(1).to_numpy()

    # donchian cross ages
    ok_hi = don_hi.notna() & don_hi.shift(1).notna()
    ok_lo = don_lo.notna() & don_lo.shift(1).notna()
    up_x = ((c > don_hi) & (c.shift(1) <= don_hi.shift(1)) & ok_hi).to_numpy()
    dn_x = ((c < don_lo) & (c.shift(1) >= don_lo.shift(1)) & ok_lo).to_numpy()
    idx = np.arange(len(d))
    last_up = np.maximum.accumulate(np.where(up_x, idx, -1))
    last_dn = np.maximum.accumulate(np.where(dn_x, idx, -1))
    A["age_up"] = np.where(last_up >= 0, idx - last_up, -1)
    A["age_dn"] = np.where(last_dn >= 0, idx - last_dn, -1)

    # pullbacks
    low_le = (lo <= ema20)
    hi_ge = (h >= ema20)
    lk = CFG.s2_pullback_lookback
    A["dipped_up"] = low_le.rolling(lk).max().shift(1).fillna(0).to_numpy() > 0
    A["popped_dn"] = hi_ge.rolling(lk).max().shift(1).fillna(0).to_numpy() > 0
    A["swing_hi"] = h.rolling(CFG.s2_swing_window).max().to_numpy()
    A["swing_lo"] = lo.rolling(CFG.s2_swing_window).min().to_numpy()
    A["pull_lo"] = lo.rolling(lk + 1).min().to_numpy()
    A["pull_hi"] = h.rolling(lk + 1).max().to_numpy()

    # S3 range
    A["r_hi"] = h.rolling(CFG.s3_range_window).max().to_numpy()
    A["r_lo"] = lo.rolling(CFG.s3_range_window).min().to_numpy()

    # candle masks (full-frame vectorized, same detectors as live)
    A["bull"] = {k: (fn(d).to_numpy(bool), st) for k, (fn, st) in cnd.BULLISH.items()}
    A["bear"] = {k: (fn(d).to_numpy(bool), st) for k, (fn, st) in cnd.BEARISH.items()}

    # week-view index per bar: number of completed weeks strictly before t's week
    labels_d = pd.DatetimeIndex([_week_label(ts) for ts in d.index])
    A["labels_d"] = labels_d
    return A


def _patterns_at(A, t):
    atr_t = A["atr"][t]
    rng = A["high"][t] - A["low"][t]
    weak = atr_t > 0 and rng < CFG.s1_min_bar_range_atr * atr_t
    bull, bear = {}, {}
    for k, (mask, st) in A["bull"].items():
        if mask[t] and not (weak and k in WEAK_BULL):
            bull[k] = st
    for k, (mask, st) in A["bear"].items():
        if mask[t] and not (weak and k in WEAK_BEAR):
            bear[k] = st
    return bull, bear


def ctx_at(ticker, d, A, WT, t):
    """Rebuild the exact SymbolContext for bar index t (or None pre-warmup)."""
    if t + 1 < CFG.min_daily_bars:
        return None
    # weekly view: replicate `weekly.iloc[:-1] if len>min else weekly`
    pos = WT["labels"].searchsorted(A["labels_d"][t], side="right") - 1
    prefix_len = pos + 1
    if prefix_len < CFG.min_weekly_bars:
        return None
    w = prefix_len - 2 if prefix_len > CFG.min_weekly_bars else prefix_len - 1
    if w < 1:
        return None

    price = A["close"][t]
    atr_t = float(A["atr"][t])
    bull, bear = _patterns_at(A, t)

    swing_hi, pull_lo = A["swing_hi"][t], A["pull_lo"][t]
    depth_up = (swing_hi - pull_lo) / swing_hi if swing_hi > 0 else 0.0
    swing_lo, pull_hi = A["swing_lo"][t], A["pull_hi"][t]
    depth_dn = (pull_hi - swing_lo) / swing_lo if swing_lo > 0 else 0.0

    r_hi, r_lo = float(A["r_hi"][t]), float(A["r_lo"][t])
    mid = (r_hi + r_lo) / 2.0
    win = A["close"][max(0, t - CFG.s3_range_window + 1):t + 1]
    above = win > mid
    crosses = int((above[1:] != above[:-1]).sum())
    edge = CFG.s3_edge_frac * (r_hi - r_lo)
    l3 = A["close"][max(0, t - 2):t + 1]
    edge_closes = int(((l3 > r_hi - edge) | (l3 < r_lo + edge)).sum())

    au, ad = int(A["age_up"][t]), int(A["age_dn"][t])
    dh = float(A["don_hi"][t]) if not np.isnan(A["don_hi"][t]) else float(price)
    dlo = float(A["don_lo"][t]) if not np.isnan(A["don_lo"][t]) else float(price)

    return SymbolContext(
        ticker=ticker, last_close=float(price), atr_last=atr_t,
        vol_last=float(A["vol"][t]), vol_avg=float(A["vol_avg"][t]),
        zones=WT["zones"][w], bull_patterns=bull, bear_patterns=bear,
        wk_uptrend=bool(WT["up"][w]), wk_downtrend=bool(WT["dn"][w]),
        wema_fast=float(WT["wema_f"][w]), wema_slow=float(WT["wema_s"][w]),
        pullback_up=bool(A["dipped_up"][t]) and price > A["ema20"][t],
        pullback_dn=bool(A["popped_dn"][t]) and price < A["ema20"][t],
        pullback_up_quality=float(max(0, min(1, depth_up / CFG.s2_pullback_min_pct))),
        pullback_dn_quality=float(max(0, min(1, depth_dn / CFG.s2_pullback_min_pct))),
        pullback_up_depth=float(depth_up), pullback_dn_depth=float(depth_dn),
        don_hi=dh, don_lo=dlo, spark=[],
        adx_last=float(A["adx"][t]), range_hi=r_hi, range_lo=r_lo,
        range_pos=float((price - r_lo) / (r_hi - r_lo)) if r_hi > r_lo else 0.5,
        range_width_pct=float((r_hi - r_lo) / price) if price > 0 else 0.0,
        ema_sep_pct=float(abs(A["ema20"][t] - A["ema50"][t]) / price) if price > 0 else 0.0,
        range_crosses=crosses,
        last_low=float(A["low"][t]), last_high=float(A["high"][t]),
        prior_med=float(A["prior_med"][t]) if not np.isnan(A["prior_med"][t]) else float(price),
        s2_age_up=(au if 0 <= au <= MAX_AGE_SCAN else None),
        s2_age_dn=(ad if 0 <= ad <= MAX_AGE_SCAN else None),
        s3_edge_closes=edge_closes,
    )


# --------------------------------------------------------------------------
# event generation + parity
# --------------------------------------------------------------------------
def events_for_ticker(ticker, d, weekly, max_h):
    A = _daily_arrays(d)
    WT = _weekly_tables(weekly)
    out = []
    for t in range(CFG.min_daily_bars - 1, len(d) - max_h):
        ctx = ctx_at(ticker, d, A, WT, t)
        if ctx is None:
            continue
        for rule in RULES:
            sig = rule.evaluate(ctx)
            if sig.hit:
                out.append({"ticker": ticker, "t": t, "date": d.index[t],
                            "signal": rule.code, "side": sig.side,
                            "score": round(sig.score, 3),
                            "trend": "up" if ctx.wk_uptrend else ("down" if ctx.wk_downtrend else "flat"),
                            **sig.meta})
    return out, A


def verify_parity(bundle, n=120, seed=11):
    """Replay ctx vs live prepare_context on prefix slices -> mismatch list."""
    rng = random.Random(seed)
    mism, checked = [], 0
    for tk, (d, _) in bundle.items():
        A = _daily_arrays(d)
        WT = _weekly_tables(dl.to_weekly(d))
        lo = CFG.min_daily_bars - 1
        hi = len(d) - 1
        if hi <= lo:
            continue
        for _ in range(max(1, n // max(1, len(bundle)))):
            t = rng.randint(lo, hi)
            pre = d.iloc[:t + 1]
            live = prepare_context(tk, pre, dl.to_weekly(pre))
            fast = ctx_at(tk, d, A, WT, t)
            if (live is None) != (fast is None):
                mism.append((tk, t, "presence", live is None, fast is None))
                checked += 1
                continue
            if live is None:
                checked += 1
                continue
            for rule in RULES:
                a, b = rule.evaluate(live), rule.evaluate(fast)
                if (a.hit, a.side) != (b.hit, b.side) or abs(a.score - b.score) > 1e-9:
                    mism.append((tk, t, rule.code,
                                 (a.hit, a.side, round(a.score, 4)),
                                 (b.hit, b.side, round(b.score, 4))))
            checked += 1
    return checked, mism


# --------------------------------------------------------------------------
# study
# --------------------------------------------------------------------------
def _dedup(events, cooldown):
    events.sort(key=lambda e: (e["ticker"], e["signal"], str(e["side"]), e["t"]))
    out, last = [], {}
    for e in events:
        k = (e["ticker"], e["signal"], e["side"])
        if k in last and e["t"] - last[k] <= cooldown:
            continue
        last[k] = e["t"]
        out.append(e)
    return out


def _fwd(e, arrs, horizons, max_h):
    A = arrs[e["ticker"]]
    t, c0 = e["t"], A["close"][e["t"]]
    sgn = 1.0 if e["side"] == "long" else (-1.0 if e["side"] == "short" else 0.0)
    for h in horizons:
        r = A["close"][t + h] / c0 - 1
        e[f"ret{h}"] = round((sgn * r if sgn else abs(r)) * 100, 3)
    hiw = A["high"][t + 1:t + 1 + max_h]
    low = A["low"][t + 1:t + 1 + max_h]
    if len(hiw):
        if e["side"] == "long":
            e["mfe"] = round((hiw.max() / c0 - 1) * 100, 2)
            e["mae"] = round((low.min() / c0 - 1) * 100, 2)
        elif e["side"] == "short":
            e["mfe"] = round((1 - low.min() / c0) * 100, 2)
            e["mae"] = round((1 - hiw.max() / c0) * 100, 2)
        else:
            cw = A["close"][t + 1:t + 1 + max_h]
            e["hold"] = int(((cw <= e.get("range_hi", np.inf)) &
                             (cw >= e.get("range_lo", -np.inf))).all())
    return e


def _rs_table(bundle, bench_daily):
    closes = pd.DataFrame({t: d["close"] for t, (d, _) in bundle.items()})
    r = closes / closes.shift(CFG.rs_window) - 1
    if bench_daily is not None and "close" in getattr(bench_daily, "columns", []):
        b = bench_daily["close"].reindex(closes.index).ffill()
        r = r.sub(b / b.shift(CFG.rs_window) - 1, axis=0)
    return r.rank(axis=1, pct=True) * 100


def _bench_bias(bench_daily):
    if bench_daily is None or "close" not in getattr(bench_daily, "columns", []):
        return None
    c = bench_daily["close"]
    ef = ind.ema(c, CFG.ema_fast_daily).to_numpy()
    es = ind.ema(c, CFG.ema_slow_daily).to_numpy()
    adx_s, pdi_s, mdi_s = ind.adx(bench_daily)
    adx = np.nan_to_num(adx_s.to_numpy())
    pdi = np.nan_to_num(pdi_s.to_numpy())
    mdi = np.nan_to_num(mdi_s.to_numpy())
    cl = c.to_numpy()
    out = np.full(len(c), "neutral", dtype=object)
    for t in range(5, len(c)):
        if ef[t] > es[t] and cl[t] >= ef[t] and ef[t] > ef[t - 5] and pdi[t] >= mdi[t]:
            out[t] = "bullish"
        elif ef[t] < es[t] and cl[t] <= ef[t] and ef[t] <= ef[t - 5] and mdi[t] >= pdi[t]:
            out[t] = "bearish"
        if adx[t] < CFG.adx_trend_min:
            out[t] = "neutral"
    return pd.Series(out, index=bench_daily.index)


def _vol_proxy(bundle, events):
    rv_cache = {}
    for e in events:
        tk = e["ticker"]
        if tk not in rv_cache:
            rv_cache[tk] = ind.realized_vol(bundle[tk][0])
        s = rv_cache[tk].iloc[:e["t"] + 1].dropna()
        if len(s) < 30:
            e["vol_state"] = None
            continue
        rank = ind.pct_rank(s, CFG.rv_rank_lookback)
        vs, _ = rg.vol_read(rg.VolInputs(rv=float(s.iloc[-1]), rv_rank=rank, source="rv"))
        e["vol_state"] = vs
    return events


def _stats(rets):
    a = np.array([r for r in rets if r is not None and not np.isnan(r)])
    if len(a) == 0:
        return {"n": 0}
    return {"n": len(a), "mean": round(a.mean(), 3), "med": round(np.median(a), 3),
            "win": round(100 * (a > 0).mean(), 1), "sd": round(a.std(ddof=1), 3) if len(a) > 1 else 0.0}


def _tstat(sig, base):
    a = np.array(sig, float)
    b = np.array(base, float)
    if len(a) < 3 or len(b) < 3:
        return None
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return round(float((a.mean() - b.mean()) / se), 2) if se > 0 else None


def _bucket(events, key):
    g = {}
    for e in events:
        g.setdefault(key(e), []).append(e)
    return g


def run_backtest(bundle, market="us", bench_daily=None, horizons=(1, 3, 5, 10),
                 cooldown=10, seed=7, out_dir="backtest", verbose=True):
    max_h = max(horizons)
    raw, arrs = [], {}
    for tk, (d, wk) in bundle.items():
        try:
            ev, A = events_for_ticker(tk, d, wk, max_h)
            raw.extend(ev)
            arrs[tk] = A
        except Exception as ex:
            if verbose:
                print(f"[bt] {tk}: skipped ({ex})")
    events = _dedup(raw, cooldown)
    if verbose:
        print(f"[bt] {len(raw)} fires -> {len(events)} events after cooldown {cooldown}")

    # annotations
    rs = _rs_table(bundle, bench_daily)
    bb = _bench_bias(bench_daily)
    for e in events:
        try:
            v = rs.at[e["date"], e["ticker"]]
            e["rs_pct"] = None if pd.isna(v) else int(round(v))
        except KeyError:
            e["rs_pct"] = None
        e["bench"] = (bb.asof(e["date"]) if bb is not None else None)
        _fwd(e, arrs, horizons, max_h)
    _vol_proxy(bundle, events)

    # baseline: random (ticker, t) from the same universe/date-range
    rng = random.Random(seed)
    tks = [t for t in bundle if t in arrs]
    base = []
    target = min(10 * max(len(events), 30), 5000)
    guard = 0
    while len(base) < target and guard < target * 20:
        guard += 1
        tk = rng.choice(tks)
        n = len(bundle[tk][0])
        if n <= CFG.min_daily_bars + max_h:
            continue
        t = rng.randint(CFG.min_daily_bars - 1, n - max_h - 1)
        b = {"ticker": tk, "t": t, "side": rng.choice(["long", "short"])}
        _fwd(b, arrs, horizons, max_h)
        base.append(b)

    hz = f"ret{max_h}"
    lines = [f"# Backtest — {MARKETS[market]['label']}  ({dt.date.today()})",
             f"events {len(events)} · baseline {len(base)} · horizons {list(horizons)} "
             f"· cooldown {cooldown} · vol-state = rv-proxy", ""]

    def table(title, groups, horizon=hz, directional_only=False):
        lines.append(f"## {title}")
        lines.append(f"| bucket | n | mean%({horizon}) | med% | win% | t vs base |")
        lines.append("|---|---|---|---|---|---|")
        bvals = [b[horizon] for b in base]
        for k in sorted(groups, key=lambda x: str(x)):
            evs = groups[k]
            if directional_only:
                evs = [e for e in evs if e["side"] in ("long", "short")]
            st = _stats([e.get(horizon) for e in evs])
            if st["n"] == 0:
                continue
            tv = _tstat([e.get(horizon) for e in evs if e.get(horizon) is not None], bvals)
            lines.append(f"| {k} | {st['n']} | {st['mean']} | {st['med']} | "
                         f"{st['win']} | {tv if tv is not None else ''} |")
        lines.append("")

    dir_ev = [e for e in events if e["side"] in ("long", "short")]
    neu_ev = [e for e in events if e["side"] == "neutral"]

    bst = _stats([b[hz] for b in base])
    lines.append(f"**Baseline (random, signed)**: n {bst.get('n')} mean {bst.get('mean')}% "
                 f"med {bst.get('med')}% win {bst.get('win')}%\n")
    table("By rule (directional)", _bucket(dir_ev, lambda e: e["signal"]))
    for h in horizons:
        table(f"By rule @ {h}d", _bucket(dir_ev, lambda e: e["signal"]), horizon=f"ret{h}")

    def dec(e):
        s = e["score"]
        return f"{int(s * 10) / 10:.1f}"
    table("By score decile (directional)", _bucket(dir_ev, dec))
    table("By RS bucket", _bucket(dir_ev, lambda e: ("rs<=30" if (e.get("rs_pct") or 50) <= 30
                                                     else ("rs>=70" if (e.get("rs_pct") or 50) >= 70 else "rs-mid"))))
    table("By weekly-trend alignment", _bucket(dir_ev, lambda e: f"{e['trend']}/{e['side']}"))
    if any(e.get("bench") for e in dir_ev):
        table("By benchmark regime", _bucket(dir_ev, lambda e: e.get("bench")))
    table("S2 by age", _bucket([e for e in dir_ev if e["signal"] == "S2"], lambda e: f"age{e.get('age')}"))
    table("S1 by pattern", _bucket([e for e in dir_ev if e["signal"] == "S1"], lambda e: e.get("pattern")))
    table("By vol-state (rv-proxy)", _bucket(dir_ev, lambda e: e.get("vol_state")))

    if neu_ev:
        hold = _stats([100.0 * e.get("hold", 0) for e in neu_ev])
        mv = _stats([e.get(hz) for e in neu_ev])          # abs move for neutral
        bmv = _stats([abs(b[hz]) for b in base])
        lines.append(f"## S3 (neutral) — condor proxy\n"
                     f"- events {hold.get('n')} · range hold-rate {hold.get('mean')}% "
                     f"(price stayed inside the range for {max_h}d)\n"
                     f"- abs {max_h}d move: S3 {mv.get('mean')}% vs baseline {bmv.get('mean')}% "
                     f"(lower = better for premium selling)\n")

    # MAE/MFE for stop placement
    for code in ("S1", "S2"):
        evs = [e for e in dir_ev if e["signal"] == code]
        if evs:
            mae = _stats([e.get("mae") for e in evs])
            mfe = _stats([e.get("mfe") for e in evs])
            lines.append(f"**{code} MAE/MFE ({max_h}d)**: MAE mean {mae.get('mean')}% "
                         f"med {mae.get('med')}% · MFE mean {mfe.get('mean')}% med {mfe.get('med')}%\n")

    os.makedirs(out_dir, exist_ok=True)
    md = os.path.join(out_dir, f"report_{market}.md")
    with open(md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    csvp = os.path.join(out_dir, f"events_{market}.csv")
    pd.DataFrame(events).to_csv(csvp, index=False)
    if verbose:
        print("\n".join(lines))
        print(f"[bt] report -> {md}\n[bt] events -> {csvp}")
    return {"events": events, "baseline": base, "report": md, "csv": csvp}


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Event-study backtest of the pa_scanner rules")
    ap.add_argument("--market", choices=list(MARKETS), default="us")
    ap.add_argument("--tickers", nargs="+", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--horizons", nargs="+", type=int, default=[1, 3, 5, 10])
    ap.add_argument("--cooldown", type=int, default=10)
    ap.add_argument("--verify", type=int, default=0,
                    help="run N parity checks (replay vs live scanner) before the study")
    ap.add_argument("--out", default="backtest")
    a = ap.parse_args()

    mkt = MARKETS[a.market]
    syms = a.tickers or uni.universe_for(a.market)
    if a.limit:
        syms = syms[:a.limit]
    print(f"[bt] {mkt['label']}: downloading {len(syms)} symbols...")
    daily = dl.download_daily(syms)
    bundle = {}
    for t, d in daily.items():
        if dl.passes_liquidity(d, mkt["min_price"], mkt["min_dollar_vol"]):
            bundle[t] = (d, dl.to_weekly(d))
    print(f"[bt] {len(bundle)} liquid symbols")
    bench = dl.download_daily([mkt["bench"]]).get(mkt["bench"])

    if a.verify:
        checked, mism = verify_parity(bundle, n=a.verify)
        print(f"[bt] parity: {checked} contexts checked, {len(mism)} mismatches")
        for m in mism[:10]:
            print("   ", m)
        if mism:
            print("[bt] WARNING: replay diverges from live scanner; results suspect")

    run_backtest(bundle, market=a.market, bench_daily=bench,
                 horizons=tuple(a.horizons), cooldown=a.cooldown, out_dir=a.out)


if __name__ == "__main__":
    main()
