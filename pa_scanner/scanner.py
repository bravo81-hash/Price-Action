"""Scanner orchestration: prepare per-symbol context, then run all rules."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import CFG
from . import indicators as ind
from . import candles as cnd
from .rules import RULES
from . import regime as rg
from .volproviders import make_vol_provider


@dataclass
class SymbolContext:
    ticker: str
    last_close: float
    atr_last: float
    vol_last: float
    vol_avg: float
    zones: list                  # [(price, count)] weekly S/R
    bull_patterns: dict
    bear_patterns: dict
    wk_uptrend: bool
    wk_downtrend: bool
    wema_fast: float
    wema_slow: float
    pullback_up: bool
    pullback_dn: bool
    pullback_up_quality: float
    pullback_dn_quality: float
    pullback_up_depth: float
    pullback_dn_depth: float
    don_hi: float
    don_lo: float
    spark: list
    # --- S3 range / chop ---
    adx_last: float = 0.0
    range_hi: float = 0.0
    range_lo: float = 0.0
    range_pos: float = 0.5
    range_width_pct: float = 0.0
    ema_sep_pct: float = 0.0
    range_crosses: int = 0


def _clip01(x):
    return float(max(0.0, min(1.0, x)))


def _rising(pivs):
    return len(pivs) >= 2 and pivs[-1][1] > pivs[-2][1]


def _falling(pivs):
    return len(pivs) >= 2 and pivs[-1][1] < pivs[-2][1]


def prepare_context(ticker, daily, weekly):
    if len(daily) < CFG.min_daily_bars or len(weekly) < CFG.min_weekly_bars:
        return None

    d = daily.copy()
    d["atr"] = ind.atr(d)
    d["ema20"] = ind.ema(d["close"], CFG.ema_fast_daily)
    don_hi, don_lo = ind.donchian(d, CFG.s2_breakout_n)
    last = d.iloc[-1]
    atr_last = float(d["atr"].iloc[-1])

    # weekly trend on completed weekly bars (drop the developing week)
    wk = weekly.iloc[:-1] if len(weekly) > CFG.min_weekly_bars else weekly
    wema_f = ind.ema(wk["close"], CFG.s2_wema_fast)
    wema_s = ind.ema(wk["close"], CFG.s2_wema_slow)
    wf, ws = float(wema_f.iloc[-1]), float(wema_s.iloc[-1])
    slope_up = wema_f.iloc[-1] > wema_f.iloc[-2]
    slope_dn = wema_f.iloc[-1] < wema_f.iloc[-2]
    up = (wf > ws) and slope_up
    dn = (wf < ws) and slope_dn

    if CFG.s2_require_structure:
        ph_s, pl_s = ind.pivots(wk, CFG.s1_pivot_left, CFG.s1_pivot_right)
        up = up and _rising(ph_s) and _rising(pl_s)
        dn = dn and _falling(ph_s) and _falling(pl_s)

    # weekly S/R zones from confirmed pivots over the lookback window
    wk_lb = wk.tail(CFG.s1_pivot_lookback_weeks)
    ph, pl = ind.pivots(wk_lb, CFG.s1_pivot_left, CFG.s1_pivot_right)
    watr = float(ind.atr(wk_lb).iloc[-1]) if len(wk_lb) > CFG.atr_window else 0.0
    levels = [p for _, p in ph] + [p for _, p in pl]
    zones = ind.cluster(levels, CFG.s1_cluster_atr * watr) if watr > 0 else []

    # daily candlestick patterns on the latest bar
    bull = cnd.last_patterns(d, cnd.BULLISH)
    bear = cnd.last_patterns(d, cnd.BEARISH)

    # pullback (up): recent dip to/below ema20, now recovered above it
    look = CFG.s2_pullback_lookback
    recent = d.tail(look + 1)
    dipped_up = bool((recent["low"].iloc[:-1] <= recent["ema20"].iloc[:-1]).any())
    pullback_up = dipped_up and (last["close"] > last["ema20"])
    swing_hi = float(d["high"].tail(CFG.s2_swing_window).max())
    pull_lo = float(recent["low"].min())
    depth_up = (swing_hi - pull_lo) / swing_hi if swing_hi > 0 else 0.0
    pbq_up = _clip01(depth_up / CFG.s2_pullback_min_pct)

    # pullback (down): recent pop to/above ema20, now rolled back under it
    popped_dn = bool((recent["high"].iloc[:-1] >= recent["ema20"].iloc[:-1]).any())
    pullback_dn = popped_dn and (last["close"] < last["ema20"])
    swing_lo = float(d["low"].tail(CFG.s2_swing_window).min())
    pull_hi = float(recent["high"].max())
    depth_dn = (pull_hi - swing_lo) / swing_lo if swing_lo > 0 else 0.0
    pbq_dn = _clip01(depth_dn / CFG.s2_pullback_min_pct)

    dh = float(don_hi.iloc[-1]) if not np.isnan(don_hi.iloc[-1]) else float(last["close"])
    dlo = float(don_lo.iloc[-1]) if not np.isnan(don_lo.iloc[-1]) else float(last["close"])

    # S3 range / chop metrics
    price = float(last["close"])
    adx_s, _, _ = ind.adx(d)
    adx_last = 0.0 if np.isnan(adx_s.iloc[-1]) else float(adx_s.iloc[-1])
    ema_slow = ind.ema(d["close"], CFG.ema_slow_daily)
    ef_last, es_last = float(d["ema20"].iloc[-1]), float(ema_slow.iloc[-1])
    ema_sep_pct = abs(ef_last - es_last) / price if price > 0 else 0.0
    rng = d.tail(CFG.s3_range_window)
    r_hi, r_lo = float(rng["high"].max()), float(rng["low"].min())
    range_pos = (price - r_lo) / (r_hi - r_lo) if r_hi > r_lo else 0.5
    range_width_pct = (r_hi - r_lo) / price if price > 0 else 0.0
    mid = (r_hi + r_lo) / 2.0
    above = rng["close"] > mid
    range_crosses = int((above != above.shift(1)).iloc[1:].sum())

    return SymbolContext(
        ticker=ticker, last_close=price, atr_last=atr_last,
        vol_last=float(last["volume"]),
        vol_avg=float(d["volume"].tail(CFG.s2_vol_window).mean()),
        zones=zones, bull_patterns=bull, bear_patterns=bear,
        wk_uptrend=up, wk_downtrend=dn, wema_fast=wf, wema_slow=ws,
        pullback_up=pullback_up, pullback_dn=pullback_dn,
        pullback_up_quality=pbq_up, pullback_dn_quality=pbq_dn,
        pullback_up_depth=depth_up, pullback_dn_depth=depth_dn,
        don_hi=dh, don_lo=dlo,
        spark=[round(x, 4) for x in d["close"].tail(CFG.spark_bars).tolist()],
        adx_last=adx_last, range_hi=r_hi, range_lo=r_lo, range_pos=range_pos,
        range_width_pct=range_width_pct, ema_sep_pct=ema_sep_pct, range_crosses=range_crosses,
    )


def scan(bundle: dict) -> list:
    """bundle: {ticker: (daily_df, weekly_df)} -> ranked list of hit rows."""
    rows = []
    for t, (daily, weekly) in bundle.items():
        try:
            ctx = prepare_context(t, daily, weekly)
            if ctx is None:
                continue
            for rule in RULES:
                sig = rule.evaluate(ctx)
                if sig.hit:
                    rows.append({
                        "ticker": t, "signal": rule.code, "signal_name": rule.name,
                        "side": sig.side, "score": round(sig.score, 3),
                        "last": round(ctx.last_close, 2), "label": sig.label,
                        "atr": round(ctx.atr_last, 2), "spark": ctx.spark,
                        **sig.meta,
                    })
        except Exception:
            continue
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


def live_status(row, live_price, atr):
    """Given a real-time price, where does the setup stand right now?
    Returns (status_word, metric). Metric is ATR-distance to the trigger for
    S1/S2, or position-in-range for S3."""
    sig, side, lvl = row.get("signal"), row.get("side"), row.get("level")
    if sig == "S2" and lvl:
        past = live_price > lvl if side == "long" else live_price < lvl
        d = abs(live_price - lvl) / atr if atr else None
        return ("triggered" if past else "pending"), (round(d, 2) if d is not None else None)
    if sig == "S1" and lvl:
        d = abs(live_price - lvl) / atr if atr else None
        return ("at level" if (d is not None and d <= 1) else "away"), (round(d, 2) if d is not None else None)
    if sig == "S3":
        lo, hi = row.get("range_lo"), row.get("range_hi")
        if lo and hi and hi > lo:
            pos = (live_price - lo) / (hi - lo)
            return ("in range" if 0 <= pos <= 1 else "broke out"), round(pos, 2)
    return ("", None)


def add_regime(rows, bundle, iv_enrich=None, vix_backwardation=None, live=False):
    """Annotate each hit row with direction read, vol-state, and suggested structure.

    Direction is price-only (computed for every hit). Vol-state uses the primary
    provider (yfinance ATM IV) when iv_enrich is on, falling back per-ticker to the
    realized-vol baseline on any error. Results are cached per ticker so a symbol
    that fires both S1 and S2 is classified once.
    """
    if iv_enrich is None:
        iv_enrich = CFG.iv_enrich_hits
    primary, baseline = make_vol_provider(iv_enrich, vix_backwardation)
    cap = getattr(primary, "enrich_cap", None)   # TWS: limit enriched hits (pacing)
    is_live = live and hasattr(primary, "snapshot")   # real-time prices available?
    dir_cache, vol_cache, live_cache, enriched = {}, {}, {}, set()

    try:
        for r in rows:
            t = r["ticker"]
            daily = bundle[t][0]
            if t not in dir_cache:
                dir_cache[t] = rg.direction_read(daily)
            direction, dmeta = dir_cache[t]

            if t not in vol_cache:
                vinp = None
                budget_ok = cap is None or t in enriched or len(enriched) < cap
                if primary is not None and budget_ok:
                    try:
                        vinp = primary.inputs_for(t, daily)
                        if vinp is not None and vinp.source != "rv":
                            enriched.add(t)        # counts only true enrichments
                    except Exception:
                        vinp = None
                if vinp is None:
                    vinp = baseline.inputs_for(t, daily)
                vol_cache[t] = (rg.vol_read(vinp), vinp)
            (vstate, vmeta), vinp = vol_cache[t]

            matrix_dir = rg.signal_direction(r["side"]) if CFG.structure_from == "signal" else direction
            cell, structure, dc = rg.strategy(matrix_dir, vstate)
            pts = lambda x: None if x is None else round(x * 100, 1)
            r["regime"] = direction                    # trend backdrop (context)
            r["regime_adx"] = round(dmeta["adx"], 1)
            r["align"] = rg.alignment(direction, r["side"])   # with | counter | neutral
            r["vol_state"] = vstate
            r["vol_src"] = vmeta["seed"]               # ivr | rvr | na (fidelity)
            r["cell"] = cell
            r["structure"] = f"{structure} ({dc})"     # expresses the signal's side
            r["ivr"] = None if vmeta["ivr"] is None else round(vmeta["ivr"], 1)
            r["iv"] = pts(vinp.iv)
            r["rv"] = pts(vinp.rv)
            r["vrp"] = pts(vmeta["vrp"])               # vol points (iv - rv)
            r["term"] = pts(vmeta["term_slope"])       # vol points (front - back)

            if is_live:                                 # real-time refresh (last hour)
                if t not in live_cache:
                    live_cache[t] = primary.snapshot(t)
                snap = live_cache[t]
                if snap and snap.get("last"):
                    lp = snap["last"]
                    r["live"] = round(lp, 2)
                    status, metric = live_status(r, lp, r.get("atr") or 0.0)
                    r["live_status"] = status
                    r["live_dist"] = metric
    finally:
        if hasattr(primary, "close"):
            primary.close()
    if is_live:
        n_live = sum(1 for r in rows if r.get("live") is not None)
        print(f"[live] real-time prices on {n_live}/{len(rows)} signals")
    print(f"[regime] vol-enriched {len(enriched)}/{len(dir_cache)} hit-tickers")
    return rows
