"""Scanner orchestration: prepare per-symbol context, then run all rules."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from typing import Optional

from .config import CFG, MARKETS
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
    chart: dict = field(default_factory=dict)
    # --- S3 range / chop ---
    adx_last: float = 0.0
    range_hi: float = 0.0
    range_lo: float = 0.0
    range_pos: float = 0.5
    range_width_pct: float = 0.0
    ema_sep_pct: float = 0.0
    range_crosses: int = 0
    # --- quality context ---
    last_low: float = 0.0
    last_high: float = 0.0
    prior_med: float = 0.0          # median of the prior N closes (approach direction)
    s2_age_up: Optional[int] = None   # bars since the last close-above-donchian cross
    s2_age_dn: Optional[int] = None
    s3_edge_closes: int = 0         # of the last 3 closes, how many sit at a range boundary
    # --- S4 oversold snapback context ---
    sma200: Optional[float] = None  # 200d simple MA (None until 200 bars)
    rsi3: Optional[float] = None    # Wilder RSI(3)
    dn_streak: int = 0              # consecutive down closes ending at today


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

    # daily candlestick patterns on the latest bar; single-bar patterns on a
    # sub-half-ATR bar are noise -> dropped (engulfing/star keep multi-bar structure)
    bull = cnd.last_patterns(d, cnd.BULLISH)
    bear = cnd.last_patterns(d, cnd.BEARISH)
    bar_range = float(last["high"] - last["low"])
    if atr_last > 0 and bar_range < CFG.s1_min_bar_range_atr * atr_last:
        for k in ("hammer", "tweezer_bottom"):
            bull.pop(k, None)
        for k in ("shooting_star", "tweezer_top"):
            bear.pop(k, None)

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

    # breakout freshness: bars since the close last crossed the donchian band
    c = d["close"]
    ok_hi = don_hi.notna() & don_hi.shift(1).notna()
    ok_lo = don_lo.notna() & don_lo.shift(1).notna()
    up_x = ((c > don_hi) & (c.shift(1) <= don_hi.shift(1)) & ok_hi).to_numpy()
    dn_x = ((c < don_lo) & (c.shift(1) >= don_lo.shift(1)) & ok_lo).to_numpy()
    iu = np.where(up_x)[0]
    idn = np.where(dn_x)[0]
    age_up = int(len(d) - 1 - iu[-1]) if len(iu) else None
    age_dn = int(len(d) - 1 - idn[-1]) if len(idn) else None
    if age_up is not None and age_up > 15:
        age_up = None
    if age_dn is not None and age_dn > 15:
        age_dn = None

    # approach direction for S1: where price lived over the prior N closes
    ab = CFG.s1_approach_bars
    prior = c.iloc[-(ab + 1):-1]
    prior_med = float(prior.median()) if len(prior) else float(last["close"])

    # S4 oversold-snapback context
    sma200_s = c.rolling(200).mean()
    sma200_v = float(sma200_s.iloc[-1]) if not np.isnan(sma200_s.iloc[-1]) else None
    rsi3_v = float(ind.rsi(c, 3).iloc[-1])
    streak_v, _i = 0, len(c) - 1
    while _i > 0 and c.iloc[_i] < c.iloc[_i - 1]:
        streak_v += 1
        _i -= 1

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
    edge_band = CFG.s3_edge_frac * (r_hi - r_lo)
    last3 = d["close"].iloc[-3:]
    s3_edge_closes = int(((last3 > r_hi - edge_band) | (last3 < r_lo + edge_band)).sum())

    chart_df = d[["open", "high", "low", "close"]].dropna().tail(CFG.chart_bars)
    chart = {
        "dates": [pd.Timestamp(x).date().isoformat() for x in chart_df.index],
        "open": [round(float(x), 4) for x in chart_df["open"]],
        "high": [round(float(x), 4) for x in chart_df["high"]],
        "low": [round(float(x), 4) for x in chart_df["low"]],
        "close": [round(float(x), 4) for x in chart_df["close"]],
    }

    return SymbolContext(
        ticker=ticker, last_close=price, atr_last=atr_last,
        vol_last=float(last["volume"]),
        vol_avg=float(d["volume"].iloc[-(CFG.s2_vol_window + 1):-1].mean()
                      if len(d) > CFG.s2_vol_window else d["volume"].mean()),
        zones=zones, bull_patterns=bull, bear_patterns=bear,
        wk_uptrend=up, wk_downtrend=dn, wema_fast=wf, wema_slow=ws,
        pullback_up=pullback_up, pullback_dn=pullback_dn,
        pullback_up_quality=pbq_up, pullback_dn_quality=pbq_dn,
        pullback_up_depth=depth_up, pullback_dn_depth=depth_dn,
        don_hi=dh, don_lo=dlo,
        spark=[round(x, 4) for x in d["close"].tail(CFG.spark_bars).tolist()],
        chart=chart,
        adx_last=adx_last, range_hi=r_hi, range_lo=r_lo, range_pos=range_pos,
        range_width_pct=range_width_pct, ema_sep_pct=ema_sep_pct, range_crosses=range_crosses,
        last_low=float(last["low"]), last_high=float(last["high"]),
        prior_med=prior_med, s2_age_up=age_up, s2_age_dn=age_dn,
        s3_edge_closes=s3_edge_closes,
        sma200=sma200_v, rsi3=rsi3_v, dn_streak=streak_v,
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
                        "atr": round(ctx.atr_last, 2),
                        "atr_pct": (round(ctx.atr_last / ctx.last_close * 100, 2)
                                    if ctx.last_close else None),
                        "spark": ctx.spark,
                        "chart": ctx.chart,
                        **sig.meta,
                    })
        except Exception:
            continue
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


def add_market_context(rows, bundle, bench_daily=None, market="us"):
    """Relative strength + index-regime awareness. Mutates row scores in place.

    RS = ticker's rs_window return minus the market benchmark's (plain return if
    the benchmark is unavailable), ranked as a percentile across ALL liquid
    scanned symbols. Longs get up to +/- rs_adj_max from their RS percentile;
    shorts the inverse (weak names make better exits/shorts). Signals fighting
    the benchmark's own direction_read take a flat index_penalty.
    Returns {symbol, bias, adx} for the benchmark, or None.
    """
    import bisect
    w = CFG.rs_window
    bench_ret, binfo = None, None
    try:                                   # benchmark is best-effort, never fatal
        if (bench_daily is not None and len(bench_daily) > w
                and "close" in bench_daily.columns):
            bc = bench_daily["close"]
            bench_ret = float(bc.iloc[-1] / bc.iloc[-1 - w] - 1)
            bias, bm = rg.direction_read(bench_daily)
            binfo = {"symbol": MARKETS[market]["bench"], "bias": bias,
                     "adx": round(bm["adx"], 1)}
    except Exception:
        bench_ret, binfo = None, None

    rs_map = {}
    for t, (d, _) in bundle.items():
        cl = d["close"]
        if len(cl) > w:
            ret = float(cl.iloc[-1] / cl.iloc[-1 - w] - 1)
            rs_map[t] = ret - bench_ret if bench_ret is not None else ret
    vals = sorted(rs_map.values())

    def pct(x):
        if len(vals) < 2:
            return 100 if vals else None
        return int(round(100 * bisect.bisect_left(vals, x) / (len(vals) - 1)))

    n_rs = 0
    for r in rows:
        x = rs_map.get(r["ticker"])
        if x is None:
            r["rs"], r["rs_pct"] = None, None
            continue
        p = pct(x)
        r["rs"], r["rs_pct"] = round(x * 100, 1), p
        n_rs += 1
        adj = 0.0
        if r["side"] == "long":
            adj += CFG.rs_adj_max * (p - 50) / 50
        elif r["side"] == "short":
            adj += CFG.rs_adj_max * (50 - p) / 50
        if binfo:   # counter-index penalty applies to ALL rules; the old S4
                    # exemption rested on the PRIME cell the date-matched audit
                    # killed (excess -0.36%, CI straddles 0)
            if r["side"] == "long" and binfo["bias"] == "bearish":
                adj -= CFG.index_penalty
            elif r["side"] == "short" and binfo["bias"] == "bullish":
                adj -= CFG.index_penalty
        if adj:
            r["score"] = round(_clip01_f(r["score"] + adj), 3)
    if binfo:
        print(f"[context] bench {binfo['symbol']}: {binfo['bias']} "
              f"(ADX {binfo['adx']}); RS on {n_rs}/{len(rows)} hits")
    else:
        print(f"[context] benchmark unavailable; RS is absolute return "
              f"({n_rs}/{len(rows)} hits)")
    return binfo


def _clip01_f(x):
    return float(max(0.0, min(1.0, x)))


def mark_prime(rows, binfo, market="us"):
    """S4 PRIME - RETIRED (CFG.s4_prime defaults False). The date-matched,
    block-bootstrapped audit killed the underlying cell: US excess -0.36%,
    95% CI [-3.60, +3.11], p(<=0)=0.60 across 94 independent bearish dates.
    The raw +5.57% was date effect x clustering. Plumbing kept so a market
    whose own --prime-audit CI clears zero can re-enable it."""
    if not (CFG.s4_prime and binfo and binfo.get("bias") == "bearish"
            and market in ("us", "asx")):
        for r in rows:
            r["prime"] = False
        return rows
    n = 0
    for r in rows:
        r["prime"] = (r.get("signal") == "S4")
        n += r["prime"]
    if n:
        print(f"[prime] bench bearish: {n} S4 PRIME rows")
    return rows


def compute_rank(rows):
    """rank = percentile of a hit's score within its own rule (0..100).
    Makes S1/S2/S3 hits comparable in one sorted list."""
    by_sig = {}
    for r in rows:
        by_sig.setdefault(r["signal"], []).append(r["score"])
    for k in by_sig:
        by_sig[k].sort()
    for r in rows:
        vals = by_sig[r["signal"]]
        if len(vals) < 2:
            r["rank"] = 100
            continue
        below = sum(1 for v in vals if v < r["score"])
        eq_others = sum(1 for v in vals if v == r["score"]) - 1
        r["rank"] = int(round(100 * (below + 0.5 * eq_others) / (len(vals) - 1)))
    return rows


def add_exit_levels(rows, market="us"):
    """Stop / target / time-exit per hit, from the 5y MAE/MFE study.

    Swing template (default): stop 2.0 x ATR, target 1.5 x ATR, 10 bars
    (10d med MAE ~ -3.4%). Neutral (S3): range edges as short-strike refs.
    India S2 longs retain the experimental POSITION research template from the
    horizon study: stop 3.5 x ATR, target 4.5 x ATR, 63 bars. Evidence gating
    prevents BUY/Qty authority until matched validation promotes the rule.
    US directional holds should NOT be extended: 42-63d excess is negative
    (S2 t=-4.6), so US keeps the 10-bar template.
    """
    for r in rows:
        atr, last = r.get("atr"), r.get("last")
        if not atr or not last:
            r["stop"], r["tgt"] = None, None
            continue
        position = ((market == "in" and r.get("signal") == "S2"
                     and r.get("side") == "long")
                    or (market == "asx" and r.get("signal") == "S4"))
        stop_k = CFG.in_pos_stop_atr if position else CFG.exit_stop_atr
        tgt_k = CFG.in_pos_tgt_atr if position else CFG.exit_target_atr
        # compute levels at RAW precision first (sub-dollar ASX names lose the
        # whole stop distance to 2dp rounding); round only for display.
        raw_stop = raw_tgt = None
        if r["side"] == "long":
            raw_stop, raw_tgt = last - stop_k * atr, last + tgt_k * atr
        elif r["side"] == "short":
            raw_stop, raw_tgt = last + stop_k * atr, last - tgt_k * atr
        else:  # neutral: condor short-strike references (already price levels)
            raw_stop, raw_tgt = r.get("range_lo"), r.get("range_hi")
        # display precision scales with price: cheap names need more decimals,
        # normal names stay clean. Qty already used the RAW distance above.
        dp = 4 if last < 1.0 else (3 if last < 10.0 else 2)
        r["stop"] = round(raw_stop, dp) if raw_stop is not None else None
        r["tgt"] = round(raw_tgt, dp) if raw_tgt is not None else None
        if position:
            r["time_exit"] = CFG.in_pos_time_bars
        elif r.get("signal") == "S4":
            r["time_exit"] = CFG.s4_time_bars
        else:
            r["time_exit"] = CFG.exit_time_bars
        # position size from the RAW stop distance. Disabled on US option rows:
        # underlying stop distance is NOT option max loss (ignores the 100x
        # multiplier and the Greeks), so a share count there is meaningless.
        r["qty"] = None
        is_option_row = (market == "us")
        entry_authorized = (r.get("action") == "BUY"
                            and r.get("evidence_tier") in ("PRIME", "PREFERRED"))
        if (CFG.risk_dollars > 0 and not is_option_row and entry_authorized
                and r["side"] in ("long", "short")
                and raw_stop is not None and abs(last - raw_stop) > 0):
            r["qty"] = int(CFG.risk_dollars // abs(last - raw_stop))
    return rows


def option_liquidity(oi_call, oi_put, spread_pct, oi_min=None, spread_max=None):
    """Classify ATM option-chain liquidity for a hit -> (flag, oi_total, spread_pct).

    flag is 'ok' | 'thin' | None (None = no chain data, e.g. non-TWS path).
    Thin = combined ATM open interest below the floor OR ATM spread too wide.
    Judged on whichever signals are present (OI-only or spread-only both work).
    """
    oi_min = CFG.opt_oi_min if oi_min is None else oi_min
    spread_max = CFG.opt_spread_max_pct if spread_max is None else spread_max
    oi = None
    if oi_call is not None or oi_put is not None:
        oi = (oi_call or 0) + (oi_put or 0)
    if oi is None and spread_pct is None:
        return None, None, None
    spread_ok = (spread_pct is None) or (spread_pct <= spread_max)
    if oi is None:
        flag = "ok" if spread_ok else "thin"
    else:
        flag = "ok" if (oi >= oi_min and spread_ok) else "thin"
    return flag, oi, spread_pct


def live_status(row, live_price, atr):
    """Given a real-time price, where does the setup stand right now?
    Returns (status_word, metric). Metric is ATR-distance to the trigger for
    S1/S2, or position-in-range for S3."""
    sig, side, lvl = row.get("signal"), row.get("side"), row.get("level")
    if sig == "S2" and lvl:
        past = live_price > lvl if side == "long" else live_price < lvl
        d = abs(live_price - lvl) / atr if atr else None
        return ("triggered" if past else "pending"), (round(d, 2) if d is not None else None)
    if sig == "S4" and lvl:      # lvl = 200SMA; snapback wants price back above it
        d = (live_price - lvl) / atr if atr else None
        return ("reclaimed" if live_price > lvl else "below MA"), (round(d, 2) if d is not None else None)
    if sig == "S1" and lvl:
        d = abs(live_price - lvl) / atr if atr else None
        return ("at level" if (d is not None and d <= 1) else "away"), (round(d, 2) if d is not None else None)
    if sig == "S3":
        lo, hi = row.get("range_lo"), row.get("range_hi")
        if lo and hi and hi > lo:
            pos = (live_price - lo) / (hi - lo)
            return ("in range" if 0 <= pos <= 1 else "broke out"), round(pos, 2)
    return ("", None)


def add_live_directional(rows, market="asx"):
    """Real-time last-hour refresh for directional markets (ASX): TWS price
    snapshots + live trigger status, no vol/options work.

    Returns (rows, health) where health = {"connected", "fresh", "total",
    "ok"}. 'ok' is True only when TWS connected AND fresh real-time quotes
    reached at least CFG.live_min_fresh_frac of the actionable rows - so the
    caller (a command explicitly named --live) can FAIL LOUD rather than
    silently serve delayed data. The connection uses the full TWS config and
    the correct per-market contract spec.
    """
    from .volproviders import TWSVolProvider
    health = {"connected": False, "fresh": 0, "total": len(rows), "ok": False}
    try:
        prov = TWSVolProvider(host=CFG.tws_host, port=CFG.tws_port,
                              client_id=CFG.tws_client_id, timeout=CFG.tws_timeout,
                              vix_backwardation=None, market=market)
    except Exception as e:
        print(f"[live] TWS connect FAILED ({e}); live columns unavailable")
        return rows, health
    health["connected"] = True
    n = 0
    try:
        cache = {}
        for r in rows:
            t = r["ticker"]
            if t not in cache:
                try:
                    cache[t] = prov.snapshot(t)
                except Exception:
                    cache[t] = None
            snap = cache[t]
            if snap and snap.get("last"):
                lp = snap["last"]
                r["live"] = round(lp, 2)
                status, metric = live_status(r, lp, r.get("atr") or 0.0)
                r["live_status"] = status
                r["live_dist"] = metric
                n += 1
    finally:
        if hasattr(prov, "close"):
            prov.close()
    health["fresh"] = n
    frac = (n / len(rows)) if rows else 0.0
    health["ok"] = health["connected"] and (not rows or frac >= CFG.live_min_fresh_frac)
    print(f"[live] real-time prices on {n}/{len(rows)} signals "
          f"({frac:.0%}; need {CFG.live_min_fresh_frac:.0%})")
    return rows, health


def add_regime(rows, bundle, iv_enrich=None, vix_backwardation=None, live=False,
               market="us", return_health=False):
    """Annotate each hit row with direction read, vol-state, and suggested structure.

    Direction is price-only (computed for every hit). Vol-state uses the primary
    provider (yfinance ATM IV) when iv_enrich is on, falling back per-ticker to the
    realized-vol baseline on any error. Results are cached per ticker so a symbol
    that fires both S1 and S2 is classified once.
    """
    if iv_enrich is None:
        iv_enrich = CFG.iv_enrich_hits
    primary, baseline = make_vol_provider(iv_enrich, vix_backwardation, market=market)
    cap = getattr(primary, "enrich_cap", None)   # TWS: limit enriched hits (pacing)
    is_live = live and hasattr(primary, "snapshot")   # real-time TWS prices available?
    live_health = {"connected": bool(is_live), "fresh": 0,
                   "total": len(rows), "ok": False}
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
            if r["signal"] == "S3":        # condor quality tracks vol richness
                if vstate == "rich":
                    r["score"] = round(_clip01_f(r["score"] + CFG.s3_vol_adj), 3)
                elif vstate == "cheap":
                    r["score"] = round(_clip01_f(r["score"] - CFG.s3_vol_adj), 3)
            r["vol_src"] = vmeta["seed"]               # ivr | rvr | na (fidelity)
            r["cell"] = cell
            r["structure"] = f"{structure} ({dc})"     # expresses the signal's side
            r["ivr"] = None if vmeta["ivr"] is None else round(vmeta["ivr"], 1)
            r["iv"] = pts(vinp.iv)
            r["rv"] = pts(vinp.rv)
            r["vrp"] = pts(vmeta["vrp"])               # vol points (iv - rv)
            r["term"] = pts(vmeta["term_slope"])       # vol points (front - back)

            oliq, ooi, ospread = option_liquidity(
                vinp.oi_call, vinp.oi_put, vinp.opt_spread_pct)
            r["opt_liq"] = oliq                        # ok | thin | None (non-TWS path)
            r["opt_oi"] = None if ooi is None else int(ooi)
            r["opt_spread"] = ospread                  # ATM bid/ask spread, % of mid

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
        frac = (n_live / len(rows)) if rows else 0.0
        live_health.update({"fresh": n_live,
                            "ok": frac >= CFG.live_min_fresh_frac})
        print(f"[live] real-time prices on {n_live}/{len(rows)} signals "
              f"({frac:.0%}; need {CFG.live_min_fresh_frac:.0%})")
    print(f"[regime] vol-enriched {len(enriched)}/{len(dir_cache)} hit-tickers")
    return (rows, live_health) if return_health else rows
