"""Strategy board - ranks the four live rules by conviction for the day.

Every tier is keyed to a backtest finding, not a heuristic. The only
market-wide conditioner used is the benchmark regime (the validated
stand-down axis; PRIME retired by the date-matched audit); the rest is each rule's validation status in the
given market. The same assessment annotates each row and gates entry actions,
sizing and enrichment order; it still does not alter the rule's raw score.

Tiers (high -> low): PRIME, PREFERRED, EXPERIMENTAL, CONTEXT, CAUTION, AVOID.
"""
from collections import Counter

TIERS = {
    "PRIME":     (0, "#f0c000", "top attention/ordering - NOT a sizing signal"),
    "PREFERRED": (1, "#3fb950", "favoured"),
    "EXPERIMENTAL": (2, "#58a6ff", "forward-track; matched edge not established"),
    "CONTEXT":   (3, "#8b949e", "ideas only, no measured entry edge"),
    "CAUTION":   (4, "#d29922", "usable with a caveat"),
    "AVOID":     (5, "#f85149", "negative in this regime"),
}

NAMES = {"S1": "Reversal at level", "S2": "Pullback breakout",
         "S3": "Range / chop", "S4": "Oversold snapback"}


def assess_rule(code, market, bearish):
    """Return (tier, reason, alt) for one rule given market + bench regime."""
    if code == "S4":
        # PRIME retired: the date-matched, block-bootstrapped audit found no
        # selection edge in bearish regimes (US excess -0.36%, CI [-3.6,+3.1]).
        # Gate on CFG.s4_prime so a market whose own audit clears zero can
        # re-enable the tier.
        from .config import CFG as _C
        if _C.s4_prime and market in ("us", "asx") and bearish:
            return ("PRIME", "s4_prime re-enabled by config (run --prime-audit to justify)", None)
        if market == "us":
            return ("EXPERIMENTAL", "matched OCO near-miss: +0.015R, CI [-0.005,+0.036]; "
                    "positive holdout but not promoted", None)
        if market == "asx":
            return ("AVOID", "matched OCO failed: -0.046R; final holdout -0.166R", "stand aside")
        return ("CONTEXT", "matched OCO did not promote: CI crosses zero and final holdout is negative", None)

    if code == "S3":
        if market == "us":
            return ("PREFERRED", "quiet-name SELECTION screen (option expectancy untested); prefer high realized-vol rows", None)
        return ("CONTEXT", "range = no directional edge here; stand aside on these names", None)

    if code == "S1":
        if market == "in":
            return ("CONTEXT", "bearish S1 is an exit/risk flag; this rule-wide card is not an entry signal", None)
        if bearish:
            return ("AVOID", "trend entries stand down (-0.6% to -2.5% excess, t=-4.0)", "S4 snapbacks")
        return ("CONTEXT", "no measured directional alpha; candidate ideas only", None)

    if code == "S2":
        if market == "in":
            return ("EXPERIMENTAL", "suggestive 6-13wk long result, but below the registered promotion bar", None)
        if bearish:
            return ("AVOID", "trend entries stand down (-0.6% to -2.5% excess, t=-4.0)", "S4 snapbacks")
        if market == "asx":
            return ("CONTEXT", "null at all horizons; candidate screen only", None)
        return ("CAUTION", "no US alpha; if traded, do not hold past ~21d", "S3 premium / S4 snapbacks")

    return ("CONTEXT", "", None)


def assess_row(row, market, bearish):
    """Evidence tier for one concrete row, including side-specific findings.

    The board is deliberately rule-wide; rows can be more precise. In India,
    only bearish S1 events have measured exit value, while the bullish side is
    context. Likewise the suggestive India S2 result applies to longs only.
    """
    code, side = row.get("signal"), row.get("side")
    if market == "in" and code == "S1":
        if side == "short":
            return ("PREFERRED", "bearish S1 exit/risk flag replicated; not a short entry", None)
        return ("CONTEXT", "India S1 bullish entry has no measured edge", None)
    if market == "in" and code == "S2" and side != "long":
        return ("CONTEXT", "India S2 evidence applies to longs only", None)
    return assess_rule(code, market, bearish)


def annotate_evidence(rows, market, bench_bias):
    """Attach the evidence decision consumed by rows, sizing and exports."""
    bearish = bench_bias == "bearish"
    for row in rows:
        tier, reason, _alt = assess_row(row, market, bearish)
        row["evidence_tier"] = tier
        row["evidence_reason"] = reason
        row["evidence_rank"] = TIERS[tier][0]
    return rows


def build_board(market, bench_bias, rows, snap_state=None):
    """Ordered strategy board for the day. Returns {header, entries}."""
    bearish = bench_bias == "bearish"
    hits = Counter(r.get("signal") for r in rows)
    entries = []
    for code in ("S1", "S2", "S3", "S4"):
        tier, reason, alt = assess_rule(code, market, bearish)
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
