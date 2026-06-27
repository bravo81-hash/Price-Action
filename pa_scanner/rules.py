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
    code = "S1"
    name = "Reversal at weekly level"

    def evaluate(self, ctx) -> Signal:
        from .config import CFG
        price, atr = ctx.last_close, ctx.atr_last
        if atr <= 0 or not ctx.zones:
            return Signal(False, None, 0.0, "")
        band = CFG.s1_near_atr * atr
        zp, zc = min(ctx.zones, key=lambda z: abs(price - z[0]))
        dist = abs(price - zp)
        if dist > band:
            return Signal(False, None, 0.0, "")
        prox = _clip01(1 - dist / band)
        zstr = _clip01(zc / 4.0)
        if zp <= price and ctx.bull_patterns and CFG.allow_long:
            pname = max(ctx.bull_patterns, key=ctx.bull_patterns.get)
            score = _clip01(0.5 * ctx.bull_patterns[pname] + 0.3 * prox + 0.2 * zstr)
            return Signal(True, "long", score, f"{pname} @ wk support {zp:.2f}",
                          {"level": round(zp, 2), "dist_atr": round(dist / atr, 2),
                           "pattern": pname, "zone_hits": zc})
        if zp > price and ctx.bear_patterns and CFG.allow_short:
            pname = max(ctx.bear_patterns, key=ctx.bear_patterns.get)
            score = _clip01(0.5 * ctx.bear_patterns[pname] + 0.3 * prox + 0.2 * zstr)
            return Signal(True, "short", score, f"{pname} @ wk resistance {zp:.2f}",
                          {"level": round(zp, 2), "dist_atr": round(dist / atr, 2),
                           "pattern": pname, "zone_hits": zc})
        return Signal(False, None, 0.0, "")


@register
class TrendPullbackBreakout:
    code = "S2"
    name = "Trend pullback breakout"

    def evaluate(self, ctx) -> Signal:
        from .config import CFG
        price, atr = ctx.last_close, ctx.atr_last
        if atr <= 0:
            return Signal(False, None, 0.0, "")
        volx = ctx.vol_last / ctx.vol_avg if ctx.vol_avg > 0 else 0.0
        vbonus = 0.1 if volx >= CFG.s2_vol_mult else 0.0

        if ctx.wk_uptrend and ctx.pullback_up and price > ctx.don_hi and CFG.allow_long:
            tstr = _clip01((ctx.wema_fast - ctx.wema_slow) / ctx.wema_slow * 20) if ctx.wema_slow else 0.5
            mag = _clip01((price - ctx.don_hi) / atr)
            score = _clip01(0.4 * tstr + 0.3 * ctx.pullback_up_quality + 0.3 * mag + vbonus)
            return Signal(True, "long", score, "pullback breakout (wk uptrend)",
                          {"level": round(ctx.don_hi, 2),
                           "breakout_atr": round((price - ctx.don_hi) / atr, 2),
                           "volx": round(volx, 2), "pullback_pct": round(ctx.pullback_up_depth * 100, 1)})

        if ctx.wk_downtrend and ctx.pullback_dn and price < ctx.don_lo and CFG.allow_short:
            tstr = _clip01((ctx.wema_slow - ctx.wema_fast) / ctx.wema_slow * 20) if ctx.wema_slow else 0.5
            mag = _clip01((ctx.don_lo - price) / atr)
            score = _clip01(0.4 * tstr + 0.3 * ctx.pullback_dn_quality + 0.3 * mag + vbonus)
            return Signal(True, "short", score, "breakdown (wk downtrend)",
                          {"level": round(ctx.don_lo, 2),
                           "breakout_atr": round((ctx.don_lo - price) / atr, 2),
                           "volx": round(volx, 2), "pullback_pct": round(ctx.pullback_dn_depth * 100, 1)})

        return Signal(False, None, 0.0, "")


@register
class RangeChopNeutral:
    code = "S3"
    name = "Range / chop (neutral)"

    def evaluate(self, ctx) -> Signal:
        from .config import CFG
        if not CFG.allow_neutral:
            return Signal(False, None, 0.0, "")
        # not trending, flat EMAs, price contained in the mid-band of a real range
        if ctx.adx_last >= CFG.s3_adx_max:
            return Signal(False, None, 0.0, "")
        if ctx.ema_sep_pct > CFG.s3_ema_flat_pct:
            return Signal(False, None, 0.0, "")
        if not (CFG.s3_min_width_pct <= ctx.range_width_pct <= CFG.s3_max_width_pct):
            return Signal(False, None, 0.0, "")
        if not (CFG.s3_pos_low <= ctx.range_pos <= CFG.s3_pos_high):
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
