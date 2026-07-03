"""Candidate directional setups - EXPERIMENTAL, backtest-only.

None of these run in the live scanner. They exist to be measured by
pa_scanner.backtest --candidates against 5y side-matched baselines; only
candidates clearing the promotion bar (|t| >= 2.5 at two adjacent horizons
with consistent sign, or >= 2.0 replicated across US and ASX) get promoted
into rules.py.

All are price/volume-only so they are fully replayable without external data:
  NH52  - fresh 52-week closing high + volume            (long)
  HVOL  - extreme-volume day premium                     (long + short mirror)
  GAPD  - >= 1 ATR gap held into the close (PEAD proxy)  (long + short mirror)
  OSMR  - RSI(3) oversold snapback inside an uptrend     (long)
  PBEMA - 6-month momentum leader, first 20-EMA bounce   (long)
"""
import numpy as np

from .config import CFG
from . import indicators as ind

WARMUP = 260          # NH52 / SMA200 need a year of history


def _rsi(closes: np.ndarray, n: int = 3) -> np.ndarray:
    delta = np.diff(closes, prepend=closes[0])
    up = np.where(delta > 0, delta, 0.0)
    dn = np.where(delta < 0, -delta, 0.0)
    # Wilder smoothing
    au = np.empty_like(up)
    ad = np.empty_like(dn)
    au[0], ad[0] = up[0], dn[0]
    a = 1.0 / n
    for i in range(1, len(up)):
        au[i] = a * up[i] + (1 - a) * au[i - 1]
        ad[i] = a * dn[i] + (1 - a) * ad[i - 1]
    rs = np.divide(au, ad, out=np.full_like(au, np.inf), where=ad > 0)
    return 100 - 100 / (1 + rs)


def _roll_max(x: np.ndarray, n: int) -> np.ndarray:
    """Rolling max of the PRIOR n bars (excludes current); NaN during warmup."""
    import pandas as pd
    return pd.Series(x).rolling(n).max().shift(1).to_numpy()


def _sma(x: np.ndarray, n: int) -> np.ndarray:
    import pandas as pd
    return pd.Series(x).rolling(n).mean().to_numpy()


def prep_arrays(d):
    """All arrays every candidate needs, computed once per ticker (causal)."""
    P = {}
    P["close"] = d["close"].to_numpy(float)
    P["open"] = d["open"].to_numpy(float)
    P["high"] = d["high"].to_numpy(float)
    P["low"] = d["low"].to_numpy(float)
    P["vol"] = d["volume"].to_numpy(float)
    P["atr"] = ind.atr(d).to_numpy()
    P["ema20"] = ind.ema(d["close"], CFG.ema_fast_daily).to_numpy()
    P["vol_avg"] = (d["volume"].rolling(CFG.s2_vol_window).mean()
                    .shift(1).to_numpy())
    P["hi252"] = _roll_max(P["close"], 252)
    P["sma200"] = _sma(P["close"], 200)
    P["sma50"] = _sma(P["close"], 50)
    P["rsi3"] = _rsi(P["close"], 3)
    c = P["close"]
    with np.errstate(divide="ignore", invalid="ignore"):
        P["ret126"] = np.where(np.arange(len(c)) >= 126,
                               c / np.roll(c, 126) - 1, np.nan)
    # fresh 252d-high cross indices (close crosses above prior-252 max)
    nh = (c > P["hi252"])
    nh_x = nh & ~np.roll(nh, 1)
    nh_x[0] = False
    idx = np.arange(len(c))
    last_nh = np.maximum.accumulate(np.where(nh_x, idx, -1))
    P["nh_age"] = np.where(last_nh >= 0, idx - last_nh, 10 ** 6)
    return P


def _volx(P, t):
    va = P["vol_avg"][t]
    return P["vol"][t] / va if va and va > 0 and not np.isnan(va) else 0.0


class NH52:
    code, name = "NH52", "52-week-high breakout"

    def check(self, P, t):
        if np.isnan(P["hi252"][t]):
            return None
        if (P["close"][t] > P["hi252"][t] and P["nh_age"][t] == 0
                and _volx(P, t) >= 1.2):
            ext = ((P["close"][t] / P["hi252"][t]) - 1) * 100
            return ("long", 0.6, {"volx": round(_volx(P, t), 2),
                                  "nh_ext_pct": round(ext, 2)})
        return None


class HVOL:
    code, name = "HVOL", "extreme-volume premium"

    def check(self, P, t):
        vx = _volx(P, t)
        if vx < 3.0:
            return None
        r = P["close"][t] / P["close"][t - 1] - 1 if t > 0 else 0.0
        if r > 0:
            return ("long", 0.6, {"volx": round(vx, 2), "day_ret": round(r * 100, 2)})
        if r < 0:
            return ("short", 0.6, {"volx": round(vx, 2), "day_ret": round(r * 100, 2)})
        return None


class GAPD:
    code, name = "GAPD", "gap-and-hold drift (PEAD proxy)"

    def check(self, P, t):
        if t == 0 or P["atr"][t] <= 0:
            return None
        gap = (P["open"][t] - P["close"][t - 1]) / P["atr"][t]
        if abs(gap) < 1.0 or _volx(P, t) < 2.0:
            return None
        if gap > 0 and P["close"][t] >= P["open"][t]:
            return ("long", 0.6, {"gap_atr": round(gap, 2),
                                  "volx": round(_volx(P, t), 2)})
        if gap < 0 and P["close"][t] <= P["open"][t]:
            return ("short", 0.6, {"gap_atr": round(gap, 2),
                                   "volx": round(_volx(P, t), 2)})
        return None


class OSMR:
    code, name = "OSMR", "oversold snapback in uptrend"

    def check(self, P, t):
        if t < 2 or np.isnan(P["sma200"][t]):
            return None
        if (P["close"][t] > P["sma200"][t] and P["rsi3"][t] < 15
                and P["close"][t] < P["close"][t - 1] < P["close"][t - 2]):
            return ("long", 0.6, {"rsi3": round(P["rsi3"][t], 1)})
        return None


class PBEMA:
    code, name = "PBEMA", "momentum-leader 20-EMA pullback"

    def check(self, P, t):
        if np.isnan(P["ret126"][t]) or np.isnan(P["sma50"][t]):
            return None
        if (P["ret126"][t] > 0.25 and P["close"][t] > P["sma50"][t]
                and P["low"][t] <= P["ema20"][t] and P["close"][t] > P["ema20"][t]):
            return ("long", 0.6, {"ret126": round(P["ret126"][t] * 100, 1)})
        return None


CANDIDATES = [NH52(), HVOL(), GAPD(), OSMR(), PBEMA()]
