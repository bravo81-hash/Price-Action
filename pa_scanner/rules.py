"""Rule plugins.

To add a pattern later: write a class with `code`, `name`, and
`evaluate(ctx) -> Signal`, decorate it with `@register`. That's the whole
extension surface. Shared indicators are precomputed in scanner.prepare_context
and handed to every rule via the SymbolContext, so rules stay thin.
"""
from dataclasses import dataclass, field
from typing import Optional

RULES = []


def register(cls):
    RULES.append(cls())
    return cls


@dataclass
class Signal:
    hit: bool
    side: Optional[str]          # "long" | "short" | None
    score: float                 # 0..1
    label: str
    meta: dict = field(default_factory=dict)


def _clip01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


@register
class ReversalAtWeeklyLevel:
    """Reversal candle testing a weekly S/R zone.

    A zone only counts as SUPPORT if price approached it from above (median of
    the prior N closes sits above the zone) and the bar's LOW actually reached
    into it; mirror for RESISTANCE. Without the approach check, a rally poking
    above overhead supply reads as "long @ support" - exactly backwards.
    Reversals aligned with the weekly trend score up; knife-catches against it
    score down.
    """
    code = "S1"
    name = "Reversal at weekly level"

    def evaluate(self, ctx) -> Signal:
        from .config import CFG
        price, atr = ctx.last_close, ctx.atr_last
        if atr <= 0 or not ctx.zones:
            return Signal(False, None, 0.0, "")
        band = CFG.s1_near_atr * atr
        wick = CFG.s1_wick_frac * band
        hold = CFG.s1_close_frac * band
        zp, zc = min(ctx.zones, key=lambda z: abs(price - z[0]))
        zstr = _clip01(zc / 4.0)

        # ---- support test (long): approached from above, low tagged the zone,
        #      close held at/above it and hasn't already run away upward
        if (CFG.allow_long and ctx.bull_patterns
                and ctx.prior_med > zp
                and ctx.last_low <= zp + wick
                and zp - hold <= price <= zp + band):
            pname = max(ctx.bull_patterns, key=ctx.bull_patterns.get)
            touch = _clip01(1 - abs(ctx.last_low - zp) / wick) if wick > 0 else 0.0
            score = 0.5 * ctx.bull_patterns[pname] + 0.3 * touch + 0.2 * zstr
            if ctx.wk_uptrend:
                score += CFG.s1_with_trend_bonus
            elif ctx.wk_downtrend:
                score -= CFG.s1_counter_trend_penalty
            return Signal(True, "long", _clip01(score),
                          f"{pname} @ wk support {zp:.2f}",
                          {"level": round(zp, 2),
                           "dist_atr": round(abs(price - zp) / atr, 2),
                           "pattern": pname, "zone_hits": zc})

        # ---- resistance test (short): approached from below, high tagged the
        #      zone, close held at/below it and hasn't already broken down
        if (CFG.allow_short and ctx.bear_patterns
                and ctx.prior_med < zp
                and ctx.last_high >= zp - wick
                and zp - band <= price <= zp + hold):
            pname = max(ctx.bear_patterns, key=ctx.bear_patterns.get)
            touch = _clip01(1 - abs(ctx.last_high - zp) / wick) if wick > 0 else 0.0
            score = 0.5 * ctx.bear_patterns[pname] + 0.3 * touch + 0.2 * zstr
            if ctx.wk_downtrend:
                score += CFG.s1_with_trend_bonus
            elif ctx.wk_uptrend:
                score -= CFG.s1_counter_trend_penalty
            return Signal(True, "short", _clip01(score),
                          f"{pname} @ wk resistance {zp:.2f}",
                          {"level": round(zp, 2),
                           "dist_atr": round(abs(price - zp) / atr, 2),
                           "pattern": pname, "zone_hits": zc})

        return Signal(False, None, 0.0, "")


@register
class TrendPullbackBreakout:
    """Weekly-trend pullback resolving through the prior-7 Donchian band.

    Only FRESH breakouts list (cross within s2_max_age bars) and chasing is
    rejected: past s2_max_ext_atr beyond the trigger there is no hit, and the
    magnitude term peaks near the trigger instead of rewarding extension.
    The breakout bar must at least match prior-20 average volume.
    """
    code = "S2"
    name = "Trend pullback breakout"

    def evaluate(self, ctx) -> Signal:
        from .config import CFG
        price, atr = ctx.last_close, ctx.atr_last
        if atr <= 0:
            return Signal(False, None, 0.0, "")
        volx = ctx.vol_last / ctx.vol_avg if ctx.vol_avg > 0 else 0.0
        if volx < CFG.s2_vol_gate:              # dead-volume breakouts are fades
            return Signal(False, None, 0.0, "")
        vbonus = 0.1 if volx >= CFG.s2_vol_mult else 0.0

        def mag(ext):
            if ext <= CFG.s2_ext_sweet_atr:
                return 1.0
            span = CFG.s2_max_ext_atr - CFG.s2_ext_sweet_atr
            return _clip01((CFG.s2_max_ext_atr - ext) / span) if span > 0 else 0.0

        if (ctx.wk_uptrend and ctx.pullback_up and price > ctx.don_hi
                and CFG.allow_long
                and ctx.s2_age_up is not None and ctx.s2_age_up <= CFG.s2_max_age):
            ext = (price - ctx.don_hi) / atr
            if ext > CFG.s2_max_ext_atr:
                return Signal(False, None, 0.0, "")
            tstr = _clip01((ctx.wema_fast - ctx.wema_slow) / ctx.wema_slow * 20) if ctx.wema_slow else 0.5
            score = _clip01(0.4 * tstr + 0.3 * ctx.pullback_up_quality + 0.3 * mag(ext) + vbonus)
            return Signal(True, "long", score, "pullback breakout (wk uptrend)",
                          {"level": round(ctx.don_hi, 2),
                           "breakout_atr": round(ext, 2), "age": ctx.s2_age_up,
                           "volx": round(volx, 2),
                           "pullback_pct": round(ctx.pullback_up_depth * 100, 1)})

        if (ctx.wk_downtrend and ctx.pullback_dn and price < ctx.don_lo
                and CFG.allow_short
                and ctx.s2_age_dn is not None and ctx.s2_age_dn <= CFG.s2_max_age):
            ext = (ctx.don_lo - price) / atr
            if ext > CFG.s2_max_ext_atr:
                return Signal(False, None, 0.0, "")
            tstr = _clip01((ctx.wema_slow - ctx.wema_fast) / ctx.wema_slow * 20) if ctx.wema_slow else 0.5
            score = _clip01(0.4 * tstr + 0.3 * ctx.pullback_dn_quality + 0.3 * mag(ext) + vbonus)
            return Signal(True, "short", score, "breakdown (wk downtrend)",
                          {"level": round(ctx.don_lo, 2),
                           "breakout_atr": round(ext, 2), "age": ctx.s2_age_dn,
                           "volx": round(volx, 2),
                           "pullback_pct": round(ctx.pullback_dn_depth * 100, 1)})

        return Signal(False, None, 0.0, "")


@register
class RangeChopNeutral:
    """Established, stable range with price mid-band and no trend conviction.

    A range whose recent closes press a boundary is coiling for a breakout,
    not chopping - rejected via s3_max_edge_closes.
    """
    code = "S3"
    name = "Range / chop (neutral)"

    def evaluate(self, ctx) -> Signal:
        from .config import CFG
        if not CFG.allow_neutral:
            return Signal(False, None, 0.0, "")
        if ctx.adx_last >= CFG.s3_adx_max:
            return Signal(False, None, 0.0, "")
        if ctx.ema_sep_pct > CFG.s3_ema_flat_pct:
            return Signal(False, None, 0.0, "")
        if not (CFG.s3_min_width_pct <= ctx.range_width_pct <= CFG.s3_max_width_pct):
            return Signal(False, None, 0.0, "")
        if not (CFG.s3_pos_low <= ctx.range_pos <= CFG.s3_pos_high):
            return Signal(False, None, 0.0, "")
        if ctx.s3_edge_closes > CFG.s3_max_edge_closes:   # coiling, not chopping
            return Signal(False, None, 0.0, "")

        chop = _clip01(1 - ctx.adx_last / CFG.s3_adx_max)
        center = _clip01(1 - abs(ctx.range_pos - 0.5) * 2)
        osc = _clip01(ctx.range_crosses / 6.0)
        score = _clip01(0.5 * chop + 0.3 * center + 0.2 * osc)
        return Signal(True, "neutral", score,
                      f"range {ctx.range_lo:.2f}-{ctx.range_hi:.2f} (mid)",
                      {"range_lo": round(ctx.range_lo, 2), "range_hi": round(ctx.range_hi, 2),
                       "range_pos": round(ctx.range_pos, 2), "adx": round(ctx.adx_last, 1),
                       "width_pct": round(ctx.range_width_pct * 100, 1),
                       "crosses": ctx.range_crosses})


@register
class OversoldSnapback:
    """Promoted candidate OSMR (5y study: US 5d excess +0.38%, t=3.44;
    replicated ASX t=2.13; persists in ASX to 63d). Long-only mean reversion:
    an uptrend name (above its 200SMA) hit by a sharp multi-day flush
    (RSI(3) < 15, two consecutive down closes) tends to snap back within
    ~5 bars. No short mirror - candidate shorts were harmful everywhere.
    """
    code = "S4"
    name = "Oversold snapback"

    def evaluate(self, ctx) -> Signal:
        from .config import CFG
        if not CFG.allow_long:
            return Signal(False, None, 0.0, "")
        if ctx.sma200 is None or ctx.rsi3 is None or ctx.atr_last <= 0:
            return Signal(False, None, 0.0, "")
        if ctx.last_close <= ctx.sma200:
            return Signal(False, None, 0.0, "")
        if ctx.rsi3 >= CFG.s4_rsi_max or not ctx.down2:
            return Signal(False, None, 0.0, "")
        score = _clip01(0.55 + (CFG.s4_rsi_max - ctx.rsi3) / 100.0)
        return Signal(True, "long", score,
                      f"RSI3 {ctx.rsi3:.0f} snapback above 200SMA",
                      {"level": round(ctx.sma200, 2),
                       "rsi3": round(ctx.rsi3, 1),
                       "dist_atr": round((ctx.last_close - ctx.sma200) / ctx.atr_last, 2)})
