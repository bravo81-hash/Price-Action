"""Market-state snapshot - last-hour context line (ported from STFS-EQ).

Classifies the day into one of five states from benchmark + companion feeds
and maps each to size guidance for the last-hour workflow. DISPLAY-ONLY: it
never gates or scores signals. Only RISK_OFF overlaps a backtest-validated
finding (the bench-bearish stand-down); the other states are heuristics and
are labelled as context.

US uses SPY + QQQ/IWM/^VIX/HYG when available; ASX/India degrade to a
benchmark-only read (companion feeds None -> those checks are skipped).
S4 remains exempt from RISK_OFF per the validated MR-in-bear-regime finding.
"""
from __future__ import annotations


STATES = {
    # Descriptive context only. These are heuristic reads, NOT validated
    # sizing multipliers - the old full/half/quarter language implied a
    # position-sizing edge the backtest never established. size_mod is kept
    # for internal ordering but is not a risk instruction.
    "RISK_OFF":             ("risk-off tape - trend entries stand down (S4 exempt)", 0.0),
    "RISK_ON_EXTENDED":     ("uptrend but short-term extended - pullbacks cleaner", 0.5),
    "RISK_ON_CONTINUATION": ("constructive continuation tape", 1.0),
    "PULLBACK_BUYABLE":     ("pullback without risk-off confirmation", 0.5),
    "CHOP_NO_EDGE":         ("no strong directional market edge", 0.25),
    "UNKNOWN":              ("insufficient data", 0.0),
}


def _pct(df, periods=1):
    try:
        c = df["close"].dropna()
        if len(c) <= periods or c.iloc[-periods - 1] == 0:
            return None
        return float((c.iloc[-1] / c.iloc[-periods - 1] - 1.0) * 100.0)
    except Exception:
        return None


def _clv(df):
    """Close location value on the latest bar: 0 = low, 1 = high."""
    try:
        row = df.dropna().iloc[-1]
        rng = float(row["high"] - row["low"])
        return float((row["close"] - row["low"]) / rng) if rng > 0 else None
    except Exception:
        return None


def build_snapshot(bench, qqq=None, iwm=None, vix=None, hyg=None):
    """Return {"state", "guidance", "size_mod", "reasons"} from daily frames."""
    def out(state, reasons):
        g, m = STATES[state]
        return {"state": state, "guidance": g, "size_mod": m, "reasons": reasons}

    if bench is None or len(bench) < 60 or "close" not in bench.columns:
        return out("UNKNOWN", ["insufficient benchmark data"])

    b1 = _pct(bench, 1)
    b5 = _pct(bench, 5)
    b20 = _pct(bench, 20)
    q1 = _pct(qqq, 1) if qqq is not None else None
    i1 = _pct(iwm, 1) if iwm is not None else None
    v1 = _pct(vix, 1) if vix is not None else None
    h5 = _pct(hyg, 5) if hyg is not None else None
    clv = _clv(bench)

    reasons = []
    if ((b1 is not None and b1 < -1.0 and clv is not None and clv < 0.35)
            or (v1 is not None and v1 > 8.0)
            or (h5 is not None and h5 < -1.0)):
        if b1 is not None and b1 < -1.0:
            reasons.append("bench down materially")
        if clv is not None and clv < 0.35:
            reasons.append("weak close")
        if v1 is not None and v1 > 8.0:
            reasons.append("VIX spiking")
        if h5 is not None and h5 < -1.0:
            reasons.append("credit (HYG) weak")
        return out("RISK_OFF", reasons)

    strong_close = clv is not None and clv >= 0.70
    weak_close = clv is not None and clv <= 0.35
    qqq_leading = q1 is not None and b1 is not None and q1 >= b1
    iwm_ok = i1 is not None and i1 > -0.25
    vix_calm = v1 is None or v1 < 5.0
    credit_ok = h5 is None or h5 > -0.5

    if b20 is not None and b20 > 3.0 and b5 is not None and b5 > 3.5:
        return out("RISK_ON_EXTENDED", ["trend strong but short-term extended"])

    cont = (b1 is not None and b1 > 0.3 and strong_close and vix_calm and credit_ok
            and (qqq is None or qqq_leading) and (iwm is None or iwm_ok))
    if cont:
        return out("RISK_ON_CONTINUATION",
                   ["bench positive", "strong close", "vol/credit acceptable"])

    if (b5 is not None and b5 < -2.0 and b20 is not None and b20 > -5.0
            and not weak_close and vix_calm):
        return out("PULLBACK_BUYABLE", ["pullback without risk-off confirmation"])

    return out("CHOP_NO_EDGE", ["no strong directional market edge"])
