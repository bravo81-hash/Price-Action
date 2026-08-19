"""Data-freshness guard.

Detect when a scan ran before the most recent completed market session has
posted to the data provider, so a (typically pre-market) run does not silently
publish a dashboard whose newest candle is a session stale.

The check is calendar-light: it knows each market's timezone + regular open and
walks weekends. It does NOT model exchange holidays, so the morning after a
holiday it can report a false "stale" -- pass --allow-stale to publish anyway.
"""
import datetime as dt

try:                                    # stdlib; needs tzdata on bare Windows
    from zoneinfo import ZoneInfo
    def _tz(name):
        return ZoneInfo(name)
except Exception:                       # pragma: no cover - pytz ships with yfinance
    import pytz
    def _tz(name):
        return pytz.timezone(name)


# market -> (IANA tz, regular session open, local time).
# yfinance returns a *forming* bar dated D once session D has opened, so the
# newest bar we can expect is the most recent weekday whose open is in the past
# in the market's own timezone.
MARKET_SESSIONS = {
    "us":  ("America/New_York", dt.time(9, 30)),
    "asx": ("Australia/Sydney", dt.time(10, 0)),
    "in":  ("Asia/Kolkata",     dt.time(9, 15)),
}


def expected_last_session(market, now=None):
    """Date of the most recent weekday whose session has opened, in market tz."""
    tzname, open_t = MARKET_SESSIONS.get(market, MARKET_SESSIONS["us"])
    now = now or dt.datetime.now(dt.timezone.utc)
    local = now.astimezone(_tz(tzname))
    d = local.date()
    if local.time() < open_t:            # today's session has not started yet
        d -= dt.timedelta(days=1)
    while d.weekday() >= 5:               # 5=Sat, 6=Sun -> walk back to Friday
        d -= dt.timedelta(days=1)
    return d


def _sessions_between(after, upto):
    """Weekdays in (after, upto] -- sessions missed, exchange holidays aside."""
    n, d = 0, after + dt.timedelta(days=1)
    while d <= upto:
        if d.weekday() < 5:
            n += 1
        d += dt.timedelta(days=1)
    return n


def _frame_last_date(df):
    if df is None or len(df) == 0:
        return None
    d = df.index[-1]
    try:
        return d.date()
    except AttributeError:
        return dt.date.fromisoformat(str(d)[:10])


def bar_dates(frames):
    """Sorted last-bar dates across an iterable of daily frames (empties skip)."""
    out = [d for d in (_frame_last_date(f) for f in frames) if d is not None]
    out.sort()
    return out


def representative_bar_date(frames):
    """Median last-bar date across frames (lower-middle on ties); None if empty.

    The dashboard's charts are only as current as the *bulk* of the universe.
    A median ignores the handful of symbols whose feed runs a session ahead or
    behind the market, so a few early-posting names can't mask a stale run (nor
    a few laggards trip a false alarm) the way max/min would.
    """
    ds = bar_dates(frames)
    if not ds:
        return None
    return ds[(len(ds) - 1) // 2]


def latest_bar_date(frames):
    """Newest last-bar date across frames. Accepts an iterable or a dict."""
    if isinstance(frames, dict):
        frames = frames.values()
    ds = bar_dates(frames)
    return ds[-1] if ds else None


def check_freshness(bar_date, market, now=None, freshest=None):
    """Compare the representative fetched bar against the expected last session.

    bar_date: datetime.date representing the bulk of the fetched universe
              (see representative_bar_date), or None if nothing was fetched.
    freshest: optional newest date any symbol reached, for context only.
    Returns {stale, latest, expected, missing_sessions, freshest, message}.
    """
    expected = expected_last_session(market, now)
    if bar_date is None:
        return {"stale": False, "latest": None, "expected": expected,
                "missing_sessions": 0, "freshest": freshest,
                "message": "no data fetched; freshness check skipped"}
    stale = bar_date < expected
    missing = _sessions_between(bar_date, expected) if stale else 0
    if stale:
        tail = ""
        if freshest is not None and freshest > bar_date:
            tail = f"; freshest single symbol {freshest.isoformat()}"
        msg = (f"most candles end {bar_date.isoformat()}, behind the last "
               f"expected {market.upper()} session {expected.isoformat()} "
               f"({missing} completed session{'s' if missing != 1 else ''} "
               f"missing{tail})")
    else:
        msg = (f"candles current through {bar_date.isoformat()} "
               f"(expected {expected.isoformat()})")
    return {"stale": stale, "latest": bar_date, "expected": expected,
            "missing_sessions": missing, "freshest": freshest, "message": msg}
