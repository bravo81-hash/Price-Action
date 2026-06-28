"""Directional (long-only) action layer for ASX / India.

These markets are traded as outright long stock, no options and (in the
relevant accounts) no short selling. So a fired signal is not an entry on both
sides: a bullish trigger is a buy/add, a bearish trigger is an exit/avoid
warning on an existing long. The action is read off weekly-trend x trigger:

                 BULLISH trigger     no trigger (chop)   BEARISH trigger
  UPtrend        BUY (add)           HOLD                REDUCE (trim)
  FLAT           BUY (small)         WATCH               AVOID
  DOWNtrend      WATCH (risky bounce) AVOID              EXIT (get out)

Conservative by design: a bullish reversal inside a *downtrend* is WATCH, not
BUY, because these names can't be hedged. Colour tiers: pos (green) = add/hold,
warn (amber) = reduce/avoid/watch, exit (red) = get out.
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


def add_action(rows, bundle):
    """Annotate each hit with weekly trend + the long-only action verb.

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
        r["trend"] = _TREND[bias]
        r["trend_adx"] = round(dmeta["adx"], 1)
        r["trigger"] = rg.signal_direction(r["side"])
        r["action"] = verb
        r["action_note"] = note
        r["action_tier"] = tier
    print(f"[action] long-only actions on {len(rows)} signals "
          f"({len(dir_cache)} tickers)")
    return rows
