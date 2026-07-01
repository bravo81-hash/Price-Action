"""Days-to-earnings enrichment (US hits only; yfinance, best-effort).

yfinance calendar data is flaky - shapes vary by version and it rate-limits on
datacenter IPs - so every failure degrades to a blank, never an exception.
"""
import datetime as dt


def _to_date(x):
    if x is None:
        return None
    if isinstance(x, dt.datetime):
        return x.date()
    if isinstance(x, dt.date):
        return x
    try:                       # pandas Timestamp / numpy datetime64 / str
        import pandas as pd
        return pd.Timestamp(x).date()
    except Exception:
        return None


def days_to_earnings(ticker):
    """Calendar days until the next scheduled earnings report, or None."""
    try:
        import yfinance as yf
        cal = yf.Ticker(ticker).calendar
        dates = []
        if isinstance(cal, dict):                      # yfinance >= 0.2.28
            ed = cal.get("Earnings Date") or []
            dates = list(ed) if isinstance(ed, (list, tuple)) else [ed]
        elif cal is not None and hasattr(cal, "loc"):  # legacy DataFrame shape
            try:
                dates = list(cal.loc["Earnings Date"].dropna())
            except Exception:
                dates = []
        today = dt.date.today()
        fut = [(d - today).days for d in map(_to_date, dates)
               if d is not None and (d - today).days >= 0]
        return min(fut) if fut else None
    except Exception:
        return None


def annotate_earnings(rows, cap=150):
    """Set r['ern'] (days to next earnings) on up to `cap` unique tickers."""
    cache, done = {}, 0
    for r in rows:
        t = r["ticker"]
        if t not in cache:
            if done >= cap:
                r["ern"] = None
                continue
            cache[t] = days_to_earnings(t)
            done += 1
        r["ern"] = cache[t]
    n = sum(1 for r in rows if r.get("ern") is not None)
    print(f"[earnings] dates on {n}/{len(rows)} hits ({done} lookups)")
    return rows
