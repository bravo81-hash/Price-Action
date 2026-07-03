"""Candidate directional setups - EXPERIMENTAL, backtest-only.

None of these run in the live scanner. Measured by pa_scanner.backtest
--candidates against 5y side-matched baselines; promotion bar (pre-registered):
|t| >= 2.5 at two adjacent horizons with consistent sign, or >= 2.0 replicated
across US and ASX.

ROUND 1 (settled): OSMR promoted -> live rule S4 (US 5d t=3.44, ASX t=2.13).
NH52 / HVOL / GAPD failed and were deleted. PBEMA near-missed (US 63d t=2.33,
ASX 1.65) and is parked below, excluded from CANDIDATES, awaiting an
out-of-sample re-test on fresh data.

ROUND 2 (this file): five long-only mean-reversion variants of the OSMR
family, all gated on close > 200SMA. Because they overlap heavily (same flush
days), at most ONE gets promoted - the strongest - unless event dates show
genuine distinctness. OSMR2 doubles as the S4 parameter test: S4 switches to
RSI(2) < 10 only if OSMR2 beats RSI(3) at 5d in BOTH markets.

  OSMR2 - RSI(2) < 10 + two down closes        (S4 parameter variant)
  LO7   - lowest close of 7 days, down day      (Connors Double-7s entry)
  BBMR  - close < 20SMA - 2 sigma               (Bollinger snapback)
  STRK4 - 4+ consecutive down closes            (deep streak reversion)
  IBSMR - internal bar strength < 0.15, down day (close pinned to day low)
"""
import numpy as np

from .config import CFG
from . import indicators as ind

WARMUP = 260          # 200SMA + buffer


def _roll_min_incl(x: np.ndarray, n: int) -> np.ndarray:
    import pandas as pd
    return pd.Series(x).rolling(n).min().to_numpy()


def _sma(x: np.ndarray, n: int) -> np.ndarray:
    import pandas as pd
    return pd.Series(x).rolling(n).mean().to_numpy()


def _std(x: np.ndarray, n: int) -> np.ndarray:
    import pandas as pd
    return pd.Series(x).rolling(n).std(ddof=0).to_numpy()


def prep_arrays(d):
    """All arrays every candidate needs, computed once per ticker (causal)."""
    import pandas as pd
    P = {}
    P["close"] = d["close"].to_numpy(float)
    P["open"] = d["open"].to_numpy(float)
    P["high"] = d["high"].to_numpy(float)
    P["low"] = d["low"].to_numpy(float)
    P["vol"] = d["volume"].to_numpy(float)
    P["atr"] = ind.atr(d).to_numpy()
    P["sma200"] = _sma(P["close"], 200)
    P["sma20"] = _sma(P["close"], 20)
    P["std20"] = _std(P["close"], 20)
    P["rsi2"] = ind.rsi(d["close"], 2).to_numpy()
    P["lo7"] = _roll_min_incl(P["close"], 7)
    c = pd.Series(P["close"])
    dn = (c < c.shift(1))
    # consecutive down-close streak length ending at t
    streak = np.zeros(len(c), int)
    dnv = dn.to_numpy()
    for i in range(1, len(c)):
        streak[i] = streak[i - 1] + 1 if dnv[i] else 0
    P["dn_streak"] = streak
    rng = P["high"] - P["low"]
    with np.errstate(divide="ignore", invalid="ignore"):
        P["ibs"] = np.where(rng > 0, (P["close"] - P["low"]) / rng, 0.5)
    return P


def _uptrend(P, t):
    return not np.isnan(P["sma200"][t]) and P["close"][t] > P["sma200"][t]


class OSMR2:
    code, name = "OSMR2", "RSI(2)<10 snapback (S4 parameter variant)"

    def check(self, P, t):
        if not _uptrend(P, t) or t < 2:
            return None
        if P["rsi2"][t] < 10 and P["dn_streak"][t] >= 2:
            return ("long", 0.6, {"rsi2": round(P["rsi2"][t], 1)})
        return None


class LO7:
    code, name = "LO7", "7-day-low close (Connors Double-7s)"

    def check(self, P, t):
        if not _uptrend(P, t) or t < 1 or np.isnan(P["lo7"][t]):
            return None
        if P["close"][t] <= P["lo7"][t] and P["close"][t] < P["close"][t - 1]:
            return ("long", 0.6, {})
        return None


class BBMR:
    code, name = "BBMR", "Bollinger lower-band snapback"

    def check(self, P, t):
        if not _uptrend(P, t) or np.isnan(P["sma20"][t]) or np.isnan(P["std20"][t]):
            return None
        if P["std20"][t] > 0 and P["close"][t] < P["sma20"][t] - 2.0 * P["std20"][t]:
            z = (P["close"][t] - P["sma20"][t]) / P["std20"][t]
            return ("long", 0.6, {"bb_z": round(z, 2)})
        return None


class STRK4:
    code, name = "STRK4", "4+ consecutive down closes"

    def check(self, P, t):
        if not _uptrend(P, t):
            return None
        if P["dn_streak"][t] >= 4:
            return ("long", 0.6, {"streak": int(P["dn_streak"][t])})
        return None


class IBSMR:
    code, name = "IBSMR", "internal-bar-strength < 0.15"

    def check(self, P, t):
        if not _uptrend(P, t) or t < 1:
            return None
        if P["ibs"][t] < 0.15 and P["close"][t] < P["close"][t - 1]:
            return ("long", 0.6, {"ibs": round(P["ibs"][t], 2)})
        return None


CANDIDATES = [OSMR2(), LO7(), BBMR(), STRK4(), IBSMR()]


# ---------------------------------------------------------------------------
# PARKED (round-1 near-miss; excluded from CANDIDATES pending an
# out-of-sample re-test on data unseen by the round-1 study):
class PBEMA:
    code, name = "PBEMA", "momentum-leader 20-EMA pullback"

    def prep_extra(self, d):
        P = {}
        P["ema20"] = ind.ema(d["close"], CFG.ema_fast_daily).to_numpy()
        P["sma50"] = _sma(d["close"].to_numpy(float), 50)
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
