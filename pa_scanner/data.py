"""yfinance data layer.

NOTE: live use requires network access to Yahoo Finance
(query1/query2.finance.yahoo.com). The detection logic is verified on synthetic
data in selftest.py; run an actual scan on a machine with internet access.
"""
import time

import pandas as pd
import yfinance as yf

from .config import CFG

COLS = ["open", "high", "low", "close", "volume"]


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse yfinance MultiIndex columns to the OHLCV field level.

    Single-ticker downloads with group_by='ticker' (and some yfinance versions
    generally) return 2-level columns like (TICKER, Close) or (Close, TICKER).
    Pick whichever level actually holds the field names and drop the other.
    """
    if not isinstance(df.columns, pd.MultiIndex):
        return df
    fields = {"open", "high", "low", "close", "volume", "adj close"}
    for lvl in range(df.columns.nlevels):
        vals = {str(v).lower() for v in df.columns.get_level_values(lvl)}
        if vals & fields:
            out = df.copy()
            out.columns = df.columns.get_level_values(lvl)
            return out
    return df


def _norm(df: pd.DataFrame) -> pd.DataFrame:
    df = _flatten(df)
    df = df.rename(columns=lambda c: str(c).lower())
    df = df.loc[:, ~df.columns.duplicated()]
    keep = [c for c in COLS if c in df.columns]
    return df[keep].dropna()


def download_daily(tickers, period=None, chunk=None, retries=2) -> dict:
    """Return {ticker: daily OHLCV DataFrame}. Bad/empty symbols are skipped."""
    period = period or CFG.daily_period
    chunk = chunk or CFG.download_chunk
    out = {}
    for i in range(0, len(tickers), chunk):
        batch = tickers[i:i + chunk]
        data = None
        for attempt in range(retries + 1):
            try:
                data = yf.download(
                    batch, period=period, interval="1d", group_by="ticker",
                    auto_adjust=True, threads=True, progress=False,
                )
                break
            except Exception:
                if attempt == retries:
                    data = None
                else:
                    time.sleep(1.5 * (attempt + 1))
        if data is None or len(data) == 0:
            continue
        for t in batch:
            try:
                sub = data[t] if len(batch) > 1 else data
                sub = _norm(sub)
                if len(sub) >= CFG.min_daily_bars:
                    out[t] = sub
            except Exception:
                continue
    return out


def to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    a = CFG.weekly_anchor
    o = daily["open"].resample(a).first()
    h = daily["high"].resample(a).max()
    l = daily["low"].resample(a).min()
    c = daily["close"].resample(a).last()
    v = daily["volume"].resample(a).sum()
    return pd.concat([o, h, l, c, v], axis=1, keys=COLS).dropna()


def passes_liquidity(daily: pd.DataFrame, min_price=None, min_dollar_vol=None) -> bool:
    mp = CFG.min_price if min_price is None else min_price
    mdv = CFG.min_avg_dollar_vol if min_dollar_vol is None else min_dollar_vol
    if len(daily) < CFG.dollar_vol_window:
        return False
    last = float(daily["close"].iloc[-1])
    adv = float((daily["close"] * daily["volume"]).tail(CFG.dollar_vol_window).mean())
    return last >= mp and adv >= mdv
