"""Candidate directional setups - EXPERIMENTAL, backtest-only.

BOTH ROUNDS SETTLED.

Round 1: OSMR promoted -> live rule S4 (US 5d t=3.44, ASX t=2.13).
NH52 / HVOL / GAPD failed, deleted. All candidate shorts harmful (US t=-3.9).

Round 2 (OSMR family, all long-only above the 200SMA): STRK4 (4+ down closes)
cleared the bar (US 5d t=3.17, ASX t=2.73 + ASX 21/42/63d persistence) and was
FOLDED INTO S4 as a second trigger. OSMR2 settled the parameter test - RSI(2)
lost to RSI(3) in the US, so S4 keeps RSI(3) < 15. LO7 / BBMR / IBSMR failed
the bar and were deleted. Replicated regime findings applied to the app:
bench-bearish regimes supercharge MR (US +5.57% @63d t=9.37, ASX +4.09%
t=6.96) -> stand-down banner and index penalty exempt S4; ASX MR excess grows
with horizon -> ASX S4 rows use the position exit template.

CANDIDATES is empty until a new hypothesis round opens. PBEMA remains parked
below awaiting an out-of-sample re-test on data unseen by round 1.
"""
import numpy as np

from .config import CFG
from . import indicators as ind

WARMUP = 260

CANDIDATES = []


def prep_arrays(d):
    """Minimal shared arrays (kept for the harness API and PBEMA re-test)."""
    P = {}
    P["close"] = d["close"].to_numpy(float)
    P["open"] = d["open"].to_numpy(float)
    P["high"] = d["high"].to_numpy(float)
    P["low"] = d["low"].to_numpy(float)
    P["vol"] = d["volume"].to_numpy(float)
    P["atr"] = ind.atr(d).to_numpy()
    return P


# ---------------------------------------------------------------------------
# PARKED (round-1 near-miss; awaiting out-of-sample re-test):
class PBEMA:
    code, name = "PBEMA", "momentum-leader 20-EMA pullback"

    def prep_extra(self, d):
        import pandas as pd
        P = {}
        P["ema20"] = ind.ema(d["close"], CFG.ema_fast_daily).to_numpy()
        P["sma50"] = pd.Series(d["close"]).rolling(50).mean().to_numpy()
        c = d["close"].to_numpy(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            P["ret126"] = np.where(np.arange(len(c)) >= 126,
                                   c / np.roll(c, 126) - 1, np.nan)
        return P

    def check_with(self, P, X, t):
        if np.isnan(X["ret126"][t]) or np.isnan(X["sma50"][t]):
            return None
        if (X["ret126"][t] > 0.25 and P["close"][t] > X["sma50"][t]
                and P["low"][t] <= X["ema20"][t] and P["close"][t] > X["ema20"][t]):
            return ("long", 0.6, {"ret126": round(X["ret126"][t] * 100, 1)})
        return None
