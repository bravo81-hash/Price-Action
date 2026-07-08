"""Strategy board - ranks the four live rules by conviction for the day.

Every tier is keyed to a backtest finding, not a heuristic. The only
market-wide conditioner used is the benchmark regime (the validated
stand-down / PRIME axis); the rest is each rule's validation status in the
given market. This is a display layer - it does not change per-ticker scoring.

Tiers (high -> low): PRIME, PREFERRED, CONTEXT, CAUTION, AVOID.
"""
from collections import Counter

TIERS = {
    "PRIME":     (0, "#f0c000", "must-consider"),
    "PREFERRED": (1, "#3fb950", "favoured"),
    "CONTEXT":   (2, "#8b949e", "ideas only, no measured entry edge"),
    "CAUTION":   (3, "#d29922", "usable with a caveat"),
    "AVOID":     (4, "#f85149", "negative in this regime"),
}

NAMES = {"S1": "Reversal at level", "S2": "Pullback breakout",
         "S3": "Range / chop", "S4": "Oversold snapback"}


def _assess(code, market, bearish):
    """Return (tier, reason, alt) for one rule given market + bench regime."""
    if code == "S4":
        if market in ("us", "asx") and bearish:
            m = "US +5.6%" if market == "us" else "ASX +4.1%"
            t = "t=9.4" if market == "us" else "t=7.0"
            return ("PRIME", f"bench bearish supercharges mean reversion ({m} excess @63d, {t})", None)
        if market == "in":
            return ("PREFERRED", "validated snapback; PRIME n/a in India (cell untested)", None)
        base = "5d t=3.4; ASX position, excess grows with horizon" if market == "asx" else "5d t=3.4, both triggers"
        return ("PREFERRED", f"validated snapback edge ({base})", None)

    if code == "S3":
        if market == "us":
            return ("PREFERRED", "quiet-name selection for premium selling; prefer rich-vol rows", None)
        return ("CONTEXT", "range = no directional edge here; stand aside on these names", None)

    if code == "S1":
        if market == "in":
            return ("PREFERRED", "EXIT flags validated (t=3.0); entries are context", None)
        if bearish:
            return ("AVOID", "trend entries stand down (-0.6% to -2.5% excess, t=-4.0)", "S4 snapbacks (PRIME today)")
        return ("CONTEXT", "no measured directional alpha; candidate ideas only", None)

    if code == "S2":
        if market == "in":
            return ("PREFERRED", "validated 6-13wk position trade (+0.95-1.14% @42-63d)", None)
        if bearish:
            return ("AVOID", "trend entries stand down (-0.6% to -2.5% excess, t=-4.0)", "S4 snapbacks (PRIME today)")
        if market == "asx":
            return ("CONTEXT", "null at all horizons; candidate screen only", None)
        return ("CAUTION", "no US alpha; if traded, do not hold past ~21d", "S3 premium / S4 snapbacks")

    return ("CONTEXT", "", None)


def build_board(market, bench_bias, rows, snap_state=None):
    """Ordered strategy board for the day. Returns {header, entries}."""
    bearish = bench_bias == "bearish"
    hits = Counter(r.get("signal") for r in rows)
    entries = []
    for code in ("S1", "S2", "S3", "S4"):
        tier, reason, alt = _assess(code, market, bearish)
        rank, color, _gloss = TIERS[tier]
        entries.append({"code": code, "name": NAMES[code], "tier": tier,
                        "tier_rank": rank, "color": color, "reason": reason,
                        "alt": alt, "hits": hits.get(code, 0)})
    # sort by tier, then by today's hit count (more actionable first)
    entries.sort(key=lambda e: (e["tier_rank"], -e["hits"]))
    for i, e in enumerate(entries, 1):
        e["order"] = i
    bench_txt = (bench_bias or "?").upper()
    header = f"bench {bench_txt}" + (f" \u00b7 {snap_state}" if snap_state else "")
    return {"header": header, "entries": entries}
