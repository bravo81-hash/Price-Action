"""Regime classification.

direction (price-only) x vol-state (cheap/fair/rich) -> regime cell -> structure.

Direction is computed from price/ADX everywhere identically. Vol-state is driven
by a VolInputs bundle produced by a vol provider (realized-vol baseline, yfinance
ATM-IV enrichment, or TWS later). The strategy matrix mirrors the entry playbook:

                CHEAP                FAIR                 RICH
  BEAR   Long Put (D)         Call Credit Spread(C) Call Credit Spread(C)
  NEUT   Calendar (D)         Iron Condor (C)       Iron Condor (C)
  BULL   Call Debit Spread(D) Put Credit Spread (C) Put Credit Spread (C)
"""
import math
from dataclasses import dataclass
from typing import Optional

from .config import CFG
from . import indicators as ind

DIRS = ("bearish", "neutral", "bullish")
VOLS = ("cheap", "fair", "rich")

STRATEGY_MATRIX = {
    ("bearish", "cheap"): ("Long Put", "D"),
    ("bearish", "fair"):  ("Call Credit Spread", "C"),
    ("bearish", "rich"):  ("Call Credit Spread", "C"),
    ("neutral", "cheap"): ("Calendar", "D"),
    ("neutral", "fair"):  ("Iron Condor", "C"),
    ("neutral", "rich"):  ("Iron Condor", "C"),
    ("bullish", "cheap"): ("Call Debit Spread", "D"),
    ("bullish", "fair"):  ("Put Credit Spread", "C"),
    ("bullish", "rich"):  ("Put Credit Spread", "C"),
}


@dataclass
class VolInputs:
    rv: Optional[float] = None            # annualised realized vol (decimal, e.g. 0.22)
    rv_rank: Optional[float] = None       # 0..100 percentile of rv over lookback
    iv: Optional[float] = None            # current ATM IV (decimal)
    ivr: Optional[float] = None           # IV rank 0..100 (TWS path only)
    vrp: Optional[float] = None           # iv - rv (decimal)
    term_slope: Optional[float] = None    # front_iv - back_iv (decimal; >0 = backwardation)
    backwardation: Optional[bool] = None
    source: str = "na"                    # provider tag: "rv" | "yf" | "tws"
    # option-chain liquidity (TWS path; harvested from the front-expiry ATM call/put)
    oi_call: Optional[float] = None
    oi_put: Optional[float] = None
    opt_spread_pct: Optional[float] = None  # ATM bid/ask spread as % of mid


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def direction_read(daily):
    """Trend / ADX / bias -> 'bearish' | 'neutral' | 'bullish' (+ meta)."""
    c = daily["close"]
    ema_f = ind.ema(c, CFG.ema_fast_daily)
    ema_s = ind.ema(c, CFG.ema_slow_daily)
    adx_s, plus_di, minus_di = ind.adx(daily)

    last_c = float(c.iloc[-1])
    ef, es = float(ema_f.iloc[-1]), float(ema_s.iloc[-1])
    k = 5 if len(ema_f) >= 5 else 2
    slope_up = ema_f.iloc[-1] > ema_f.iloc[-k]
    adx_v = 0.0 if _nan(adx_s.iloc[-1]) else float(adx_s.iloc[-1])
    pdi = 0.0 if _nan(plus_di.iloc[-1]) else float(plus_di.iloc[-1])
    mdi = 0.0 if _nan(minus_di.iloc[-1]) else float(minus_di.iloc[-1])

    if ef > es and last_c >= ef and slope_up and pdi >= mdi:
        bias = "bullish"
    elif ef < es and last_c <= ef and (not slope_up) and mdi >= pdi:
        bias = "bearish"
    else:
        bias = "neutral"
    if adx_v < CFG.adx_trend_min:        # no directional conviction
        bias = "neutral"

    return bias, {"adx": adx_v, "plus_di": pdi, "minus_di": mdi,
                  "ema_fast": ef, "ema_slow": es}


def vol_read(v: VolInputs):
    """cheap / fair / rich from the image's 3-step logic:
    1) bucket from IVR (or RV-rank seed on the free path),
    2) VRP <= 0 nudges one bucket cheaper,
    3) backwardation forces cheap."""
    if not _nan(v.ivr):
        bucket = "cheap" if v.ivr < CFG.ivr_cheap else ("rich" if v.ivr > CFG.ivr_rich else "fair")
        seed = "ivr"
    elif not _nan(v.rv_rank):
        bucket = "cheap" if v.rv_rank < CFG.rvr_cheap else ("rich" if v.rv_rank > CFG.rvr_rich else "fair")
        seed = "rvr"
    else:
        bucket, seed = "fair", "na"

    if CFG.vrp_nudge_cheaper and not _nan(v.vrp) and v.vrp <= 0:
        bucket = {"rich": "fair", "fair": "cheap", "cheap": "cheap"}[bucket]
    if CFG.backwardation_force_cheap and v.backwardation:
        bucket = "cheap"

    meta = {"seed": seed, "provider": v.source, "ivr": v.ivr, "rv_rank": v.rv_rank,
            "iv": v.iv, "rv": v.rv, "vrp": v.vrp, "term_slope": v.term_slope,
            "backwardation": v.backwardation}
    return bucket, meta


def strategy(direction: str, vol_state: str):
    """Return (cell_label, structure_name, debit_or_credit)."""
    name, dc = STRATEGY_MATRIX[(direction, vol_state)]
    short = {"bearish": "Bear", "neutral": "Neut", "bullish": "Bull"}[direction]
    return f"{short}x{vol_state.title()}", name, dc


def signal_direction(side: str) -> str:
    """A fired signal is directional: long -> bullish row, short -> bearish row.
    A neutral (range/chop) signal maps to the neutral row."""
    if side == "long":
        return "bullish"
    if side == "short":
        return "bearish"
    return "neutral"


def alignment(regime_dir: str, side: str) -> str:
    """How a directional signal sits versus the trend regime: 'with' | 'counter'.
    Neutral (range) signals have no tape direction -> 'neutral'."""
    if side not in ("long", "short"):
        return "neutral"
    if regime_dir == "neutral":
        return "neutral"
    return "with" if signal_direction(side) == regime_dir else "counter"
