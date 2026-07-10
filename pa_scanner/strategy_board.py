"""Strategy board - ranks the four live rules by conviction for the day.

Every tier is keyed to a backtest finding, not a heuristic. The only
market-wide conditioner used is the benchmark regime (the validated
stand-down axis; PRIME retired by the date-matched audit); the rest is each rule's validation status in the
given market. This is a display layer - it does not change per-ticker scoring.

Tiers (high -> low): PRIME, PREFERRED, CONTEXT, CAUTION, AVOID.
"""
from collections import Counter

TIERS = {
    "PRIME":     (0, "#f0c000", "top attention/ordering - NOT a sizing signal"),
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
        # PRIME retired: the date-matched, block-bootstrapped audit found no
        # selection edge in bearish regimes (US excess -0.36%, CI [-3.6,+3.1]).
        # Gate on CFG.s4_prime so a market whose own audit clears zero can
        # re-enable the tier.
        from .config import CFG as _C
        if _C.s4_prime and market in ("us", "asx") and bearish:
            return ("PRIME", "s4_prime re-enabled by config (run --prime-audit to justify)", None)
        return ("PREFERRED", "only rule with positive realized OCO expectancy "
                "(US +0.05R/trade pre-cost); bearish-regime 'supercharge' retired by audit", None)

    if code == "S3":
        if market == "us":
            return ("PREFERRED", "quiet-name SELECTION screen (option expectancy untested); prefer high realized-vol rows", None)
        return ("CONTEXT", "range = no directional edge here; stand aside on these names", None)

    if code == "S1":
        if market == "in":
            return ("PREFERRED", "EXIT flags validated (t=3.0); entries are context", None)
        if bearish:
            return ("AVOID", "trend entries stand down (-0.6% to -2.5% excess, t=-4.0)", "S4 snapbacks")
        return ("CONTEXT", "no measured directional alpha; candidate ideas only", None)

    if code == "S2":
        if market == "in":
            return ("PREFERRED", "validated 6-13wk position trade (+0.95-1.14% @42-63d)", None)
        if bearish:
            return ("AVOID", "trend entries stand down (-0.6% to -2.5% excess, t=-4.0)", "S4 snapbacks")
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
