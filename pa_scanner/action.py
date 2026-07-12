"""Directional (long-only) action layer for ASX / India.

These markets are traded as outright long stock, no options and (in the
relevant accounts) no short selling. So a fired signal is not an entry on both
sides: a bullish trigger is a buy/add, a bearish trigger is an exit/avoid
warning on an existing long. The action is read off weekly-trend x trigger:

                 BULLISH trigger     no trigger (chop)   BEARISH trigger
  UPtrend        BUY (add)           HOLD                REDUCE (trim)
  FLAT           BUY (small)         WATCH               AVOID
  DOWNtrend      WATCH (risky bounce) AVOID              EXIT (get out)

The matrix is technical context, then the row's evidence tier gates entry
authority: only PRIME/PREFERRED may retain BUY/HOLD; weaker tiers become WATCH
or AVOID. REDUCE/EXIT warnings remain visible with their evidence label.
"""
from . import regime as rg

# (trend_bias, trigger_dir) -> (verb, qualifier, tier)
ACTION_MATRIX = {
    ("bullish", "bullish"): ("BUY",    "add",           "pos"),
    ("bullish", "neutral"): ("HOLD",   "",              "pos"),
    ("bullish", "bearish"): ("REDUCE", "trim",          "warn"),
    ("neutral", "bullish"): ("BUY",    "small",         "pos"),
    ("neutral", "neutral"): ("WATCH",  "",              "warn"),
    ("neutral", "bearish"): ("AVOID",  "",              "warn"),
    ("bearish", "bullish"): ("WATCH",  "risky bounce",  "warn"),
    ("bearish", "neutral"): ("AVOID",  "",              "warn"),
    ("bearish", "bearish"): ("EXIT",   "get out",       "exit"),
}

_TREND = {"bullish": "up", "neutral": "flat", "bearish": "down"}


def decide(trend_bias, side):
    """Pure mapping: (trend bias, signal side) -> (verb, qualifier, tier)."""
    trig = rg.signal_direction(side)               # long->bullish, short->bearish, else neutral
    return ACTION_MATRIX[(trend_bias, trig)]


def gate_entry(action, evidence):
    """Apply evidence authority to a technical action tuple."""
    verb, note, tier = action
    if verb in ("BUY", "HOLD"):
        if evidence == "AVOID":
            return "AVOID", "evidence gate", "warn"
        if evidence not in ("PRIME", "PREFERRED"):
            return "WATCH", evidence.lower() + " evidence", "warn"
    return verb, note, tier


def add_action(rows, bundle):
    """Annotate each hit with evidence-gated long-only action authority.

    Direction is the same price-only read used by the US regime, so the two
    markets stay consistent. No vol / options / TWS work happens here.
    """
    dir_cache = {}
    for r in rows:
        t = r["ticker"]
        if t not in dir_cache:
            dir_cache[t] = rg.direction_read(bundle[t][0])
        bias, dmeta = dir_cache[t]
        verb, note, tier = decide(bias, r["side"])
        evidence = r.get("evidence_tier", "CONTEXT")
        # Evidence governs entry authority. Technical REDUCE/EXIT warnings are
        # left intact, but a null/experimental rule can never become a BUY just
        # because the background trend is up. AVOID is an explicit no-entry.
        verb, note, tier = gate_entry((verb, note, tier), evidence)
        r["trend"] = _TREND[bias]
        r["trend_adx"] = round(dmeta["adx"], 1)
        r["trigger"] = rg.signal_direction(r["side"])
        r["action"] = verb
        r["action_note"] = note
        r["action_tier"] = tier
    print(f"[action] long-only actions on {len(rows)} signals "
          f"({len(dir_cache)} tickers)")
    return rows
