"""Indicator primitives. Pure functions over OHLC DataFrames (lowercase cols)."""
import numpy as np
import pandas as pd

from .config import CFG


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def atr(df: pd.DataFrame, n: int | None = None) -> pd.Series:
    n = n or CFG.atr_window
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()


def donchian(df: pd.DataFrame, n: int):
    """Prior-N high/low (shifted so the current bar can break it)."""
    hi = df["high"].rolling(n).max().shift(1)
    lo = df["low"].rolling(n).min().shift(1)
    return hi, lo


def pivots(df: pd.DataFrame, left: int, right: int):
    """Confirmed fractal pivots. Returns (highs, lows) as lists of (ts, price).
    A bar is a pivot high if its high is the unique max over [i-left, i+right];
    the last `right` bars cannot yet be pivots (no look-ahead)."""
    highs, lows = [], []
    H, L = df["high"].to_numpy(), df["low"].to_numpy()
    idx = df.index
    n = len(df)
    for i in range(left, n - right):
        wH = H[i - left:i + right + 1]
        wL = L[i - left:i + right + 1]
        if H[i] == wH.max() and int(wH.argmax()) == left:
            highs.append((idx[i], float(H[i])))
        if L[i] == wL.min() and int(wL.argmin()) == left:
            lows.append((idx[i], float(L[i])))
    return highs, lows


def cluster(levels, tol: float):
    """Merge nearby price levels into zones. Returns [(price, count)] sorted by price."""
    if not levels:
        return []
    xs = sorted(float(x) for x in levels)
    zones, grp = [], [xs[0]]
    for x in xs[1:]:
        if abs(x - float(np.mean(grp))) <= tol:
            grp.append(x)
        else:
            zones.append((float(np.mean(grp)), len(grp)))
            grp = [x]
    zones.append((float(np.mean(grp)), len(grp)))
    return zones
