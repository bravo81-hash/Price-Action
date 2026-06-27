"""Vol-state data providers.

RealizedVolProvider  always-on baseline (no option data): realized vol + rank,
                     plus an optional global VIX backwardation flag.
YFinanceIVProvider   1A enrichment: current ATM IV from yfinance option chains
                     -> real VRP + per-ticker term slope. IVR unavailable (no IV
                     history on the free path). Network + sometimes flaky.
TWSVolProvider       2B stub: accurate IVR/VRP/term via IBKR. Implement later.
"""
import datetime as dt
import math

import numpy as np

from .config import CFG
from . import indicators as ind
from .regime import VolInputs


def _rv_and_rank(daily):
    rv_series = ind.realized_vol(daily)
    last = rv_series.iloc[-1]
    rv = None if (last is None or math.isnan(last)) else float(last)
    rank = ind.pct_rank(rv_series, CFG.rv_rank_lookback)
    rank = None if math.isnan(rank) else rank
    return rv, rank


class RealizedVolProvider:
    def __init__(self, vix_backwardation=None):
        self.vix_bw = vix_backwardation

    def inputs_for(self, ticker, daily) -> VolInputs:
        rv, rank = _rv_and_rank(daily)
        return VolInputs(rv=rv, rv_rank=rank, backwardation=self.vix_bw, source="rv")


class YFinanceIVProvider:
    def __init__(self, vix_backwardation=None):
        self.vix_bw = vix_backwardation

    @staticmethod
    def _atm_iv(chain, spot):
        ivs = []
        for side in (getattr(chain, "calls", None), getattr(chain, "puts", None)):
            if side is None or len(side) == 0:
                continue
            side = side.dropna(subset=["impliedVolatility"])
            if len(side) == 0:
                continue
            i = (side["strike"] - spot).abs().idxmin()
            iv = float(side.loc[i, "impliedVolatility"])
            if iv > 0:
                ivs.append(iv)
        return float(np.mean(ivs)) if ivs else None

    def inputs_for(self, ticker, daily) -> VolInputs:
        import yfinance as yf
        rv, rank = _rv_and_rank(daily)
        spot = float(daily["close"].iloc[-1])
        fallback = VolInputs(rv=rv, rv_rank=rank, backwardation=self.vix_bw, source="rv")

        tk = yf.Ticker(ticker)
        exps = list(tk.options or [])
        if not exps:
            return fallback
        today = dt.date.today()
        valid = [(e, (dt.date.fromisoformat(e) - today).days) for e in exps]
        valid = [(e, d) for e, d in valid if d >= 1]
        if not valid:
            return fallback

        front = min(valid, key=lambda x: abs(x[1] - CFG.iv_front_dte))[0]
        back = min(valid, key=lambda x: abs(x[1] - CFG.iv_back_dte))[0]
        iv_f = self._atm_iv(tk.option_chain(front), spot)
        if iv_f is None:
            return fallback
        iv_b = self._atm_iv(tk.option_chain(back), spot) if back != front else None
        term = (iv_f - iv_b) if iv_b is not None else None
        bw = (iv_f > iv_b) if iv_b is not None else self.vix_bw
        vrp = (iv_f - rv) if rv is not None else None
        return VolInputs(rv=rv, rv_rank=rank, iv=iv_f, ivr=None, vrp=vrp,
                         term_slope=term, backwardation=bw, source="yf")


class TWSVolProvider:
    """STUB (2B). Accurate vol via IBKR/TWS — implement with ib_async.

    Implementation outline:
      ib = IB(); ib.connect('127.0.0.1', 7496, clientId=N)
      # IVR (needs IV history — this is what the free path cannot do):
      bars = ib.reqHistoricalData(underlying, '', '1 Y', '1 day',
                 'OPTION_IMPLIED_VOLATILITY', useRTH=True)
      ivr = percentile(latest, [b.close for b in bars])           # 0..100
      # Current ATM IV + term slope:
      params = ib.reqSecDefOptParams(sym, '', secType, conId)
      # pick front/back expiries near CFG.iv_front_dte / iv_back_dte, qualify the
      # ATM strike per expiry, reqMktData(genericTick='106') -> modelGreeks.impliedVol
      term_slope = iv_front - iv_back ; backwardation = iv_front > iv_back
      # RV: indicators.realized_vol(daily), or 'HISTORICAL_VOLATILITY' bars.
      return VolInputs(rv, rv_rank, iv=iv_front, ivr=ivr, vrp=iv_front-rv,
                       term_slope=term_slope, backwardation=backwardation, source='tws')
    """

    def inputs_for(self, ticker, daily) -> VolInputs:
        raise NotImplementedError("TWS vol provider not implemented yet (2B stub)")


def make_vol_provider(iv_enrich=True, vix_backwardation=None):
    """Return (primary_or_None, baseline). Caller tries primary, falls back to baseline."""
    if CFG.vol_source == "tws":
        print("[regime] TWS provider is a stub; using yfinance/realized approximation")
    if iv_enrich:
        return YFinanceIVProvider(vix_backwardation), RealizedVolProvider(vix_backwardation)
    return None, RealizedVolProvider(vix_backwardation)
