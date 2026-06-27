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
    """Accurate vol via IBKR/TWS (ib_async). Connects once, reused across hits.

    Gives true IVR (1-yr underlying implied-vol history — impossible on the free
    path), real ATM IV + term structure from live option greeks, and VRP. Because
    IBKR throttles historical-data requests (~60 / 10 min), only the top
    `tws_max_enrich` hits are enriched here; the rest fall back to realized vol.
    """

    enrich_cap = None  # set per-instance from CFG.tws_max_enrich

    def __init__(self, host="127.0.0.1", port=7496, client_id=0,
                 timeout=8.0, vix_backwardation=None):
        import logging
        import random
        from ib_async import IB
        logging.getLogger("ib_async").setLevel(logging.CRITICAL)  # quiet routine API errors
        self.vix_bw = vix_backwardation
        self.enrich_cap = CFG.tws_max_enrich
        self._greek_wait = CFG.tws_greek_wait
        self.client_id = client_id or random.randint(10_000, 9_999_999)  # dynamic
        self.ib = IB()
        self.ib.connect(host, port, clientId=self.client_id, timeout=timeout)
        # so model greeks populate after the close / without live ticks
        self.ib.reqMarketDataType(CFG.tws_market_data_type)

    def close(self):
        try:
            self.ib.disconnect()
        except Exception:
            pass

    def _atm_iv(self, symbol, expiry, spot):
        """Mean model IV of the ATM call & put that actually exist for this expiry.
        Strikes are enumerated per-expiry via reqContractDetails (the union list
        from reqSecDefOptParams contains strikes that don't trade every expiry)."""
        from ib_async import Option
        ivs = []
        for right in ("C", "P"):
            try:
                cds = self.ib.reqContractDetails(Option(symbol, expiry, 0, right, "SMART"))
            except Exception:
                cds = []
            if not cds:
                continue
            con = min(cds, key=lambda cd: abs(cd.contract.strike - spot)).contract
            try:
                tk = self.ib.reqMktData(con, "", False, False)
                self.ib.sleep(self._greek_wait)
                mg = tk.modelGreeks
                if mg and mg.impliedVol and mg.impliedVol > 0:
                    ivs.append(float(mg.impliedVol))
                self.ib.cancelMktData(con)
            except Exception:
                continue
        return sum(ivs) / len(ivs) if ivs else None

    def _chain_atm(self, stk, spot):
        import datetime as dt
        try:
            params = self.ib.reqSecDefOptParams(stk.symbol, "", stk.secType, stk.conId)
        except Exception:
            return None, None
        p = next((x for x in params if x.exchange == "SMART"), params[0] if params else None)
        if p is None or not p.expirations:
            return None, None
        today = dt.date.today()

        def dte(e):
            return (dt.date(int(e[:4]), int(e[4:6]), int(e[6:8])) - today).days

        valid = [(e, dte(e)) for e in sorted(p.expirations) if dte(e) >= 1]
        if not valid:
            return None, None
        front = min(valid, key=lambda z: abs(z[1] - CFG.iv_front_dte))[0]
        back = min(valid, key=lambda z: abs(z[1] - CFG.iv_back_dte))[0]
        iv_f = self._atm_iv(stk.symbol, front, spot)
        iv_b = self._atm_iv(stk.symbol, back, spot) if back != front else None
        return iv_f, iv_b

    def inputs_for(self, ticker, daily) -> VolInputs:
        from ib_async import Stock
        rv, rank = _rv_and_rank(daily)
        fallback = VolInputs(rv=rv, rv_rank=rank, backwardation=self.vix_bw, source="rv")
        try:
            q = self.ib.qualifyContracts(Stock(ticker, "SMART", "USD"))
            if not q:
                return fallback
            stk = q[0]
            spot = float(daily["close"].iloc[-1])

            # true IVR from 1-yr underlying option-implied-vol history
            ivr = None
            bars = self.ib.reqHistoricalData(
                stk, "", "1 Y", "1 day", "OPTION_IMPLIED_VOLATILITY",
                useRTH=True, formatDate=1)
            ivs = [b.close for b in bars if b.close and b.close > 0]
            if len(ivs) > 20:
                lo, hi = min(ivs), max(ivs)
                ivr = 100.0 * (ivs[-1] - lo) / (hi - lo) if hi > lo else None
            iv_hist = ivs[-1] if ivs else None

            iv_f, iv_b = self._chain_atm(stk, spot)
            iv = iv_f if iv_f is not None else iv_hist
            term = (iv_f - iv_b) if (iv_f is not None and iv_b is not None) else None
            bw = (iv_f > iv_b) if (iv_f is not None and iv_b is not None) else self.vix_bw
            vrp = (iv - rv) if (iv is not None and rv is not None) else None
            return VolInputs(rv=rv, rv_rank=rank, iv=iv, ivr=ivr, vrp=vrp,
                             term_slope=term, backwardation=bw, source="tws")
        except Exception:
            return fallback


def make_vol_provider(iv_enrich=True, vix_backwardation=None):
    """Return (primary_or_None, baseline). Caller tries primary, falls back to baseline.
    With vol_source='tws' the primary is a live IBKR connection; if the connect
    fails (TWS not running, API off) it degrades to the yfinance approximation."""
    if CFG.vol_source == "tws":
        try:
            tws = TWSVolProvider(host=CFG.tws_host, port=CFG.tws_port,
                                 client_id=CFG.tws_client_id, timeout=CFG.tws_timeout,
                                 vix_backwardation=vix_backwardation)
            print(f"[regime] TWS connected at {CFG.tws_host}:{CFG.tws_port} "
                  f"(clientId {tws.client_id}); enriching top {tws.enrich_cap} hits")
            return tws, RealizedVolProvider(vix_backwardation)
        except Exception as e:
            print(f"[regime] TWS connect failed ({e}); using yfinance/realized approximation")
    if iv_enrich:
        return YFinanceIVProvider(vix_backwardation), RealizedVolProvider(vix_backwardation)
    return None, RealizedVolProvider(vix_backwardation)
