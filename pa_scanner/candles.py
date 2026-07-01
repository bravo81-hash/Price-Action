"""Daily candlestick reversal patterns.

Each detector returns a boolean Series aligned to the input frame.
BULLISH patterns are used at support; BEARISH at resistance. Strengths weight
the score (engulfing / star = strong; hammer / piercing / tweezer = moderate).
"""
import numpy as np
import pandas as pd


def _parts(df: pd.DataFrame):
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    body = (c - o).abs()
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    bull = c > o
    bear = o > c
    return o, h, l, c, body, upper, lower, bull, bear


def bullish_engulfing(df):
    o, h, l, c, body, up, lo, bull, bear = _parts(df)
    return bull & bear.shift(1) & (c >= o.shift(1)) & (o <= c.shift(1))


def bearish_engulfing(df):
    o, h, l, c, body, up, lo, bull, bear = _parts(df)
    return bear & bull.shift(1) & (o >= c.shift(1)) & (c <= o.shift(1))


def hammer(df):
    o, h, l, c, body, up, lo, bull, bear = _parts(df)
    return (lo >= 2 * body) & (up <= body) & (body > 0)


def shooting_star(df):
    o, h, l, c, body, up, lo, bull, bear = _parts(df)
    return (up >= 2 * body) & (lo <= body) & (body > 0)


def piercing(df):
    o, h, l, c, body, up, lo, bull, bear = _parts(df)
    mid = (o.shift(1) + c.shift(1)) / 2
    return bear.shift(1) & bull & (o < c.shift(1)) & (c > mid) & (c < o.shift(1))


def dark_cloud(df):
    o, h, l, c, body, up, lo, bull, bear = _parts(df)
    mid = (o.shift(1) + c.shift(1)) / 2
    return bull.shift(1) & bear & (o > c.shift(1)) & (c < mid) & (c > o.shift(1))


def morning_star(df):
    o, h, l, c, body, up, lo, bull, bear = _parts(df)
    star = body.shift(1) < body.shift(2) * 0.5
    return bear.shift(2) & star & bull & (c > (o.shift(2) + c.shift(2)) / 2)


def evening_star(df):
    o, h, l, c, body, up, lo, bull, bear = _parts(df)
    star = body.shift(1) < body.shift(2) * 0.5
    return bull.shift(2) & star & bear & (c < (o.shift(2) + c.shift(2)) / 2)


def tweezer_bottom(df, tol=0.001):
    o, h, l, c, body, up, lo, bull, bear = _parts(df)
    same = (l - l.shift(1)).abs() <= (l * tol)
    return bear.shift(1) & bull & same


def tweezer_top(df, tol=0.001):
    o, h, l, c, body, up, lo, bull, bear = _parts(df)
    same = (h - h.shift(1)).abs() <= (h * tol)
    return bull.shift(1) & bear & same


# name -> (detector, strength 0..1)
BULLISH = {
    "bullish_engulfing": (bullish_engulfing, 1.0),
    "morning_star": (morning_star, 1.0),
    "piercing": (piercing, 0.8),
    "hammer": (hammer, 0.7),
    "tweezer_bottom": (tweezer_bottom, 0.5),
}
BEARISH = {
    "bearish_engulfing": (bearish_engulfing, 1.0),
    "evening_star": (evening_star, 1.0),
    "dark_cloud": (dark_cloud, 0.8),
    "shooting_star": (shooting_star, 0.7),
    "tweezer_top": (tweezer_top, 0.5),
}


def last_patterns(df: pd.DataFrame, which: dict) -> dict:
    """Return {name: strength} for patterns true on the most recent bar."""
    out = {}
    for name, (fn, strength) in which.items():
        s = fn(df)
        if bool(s.iloc[-1]):
            out[name] = strength
    return out
