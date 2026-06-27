"""Build the scan universe: S&P 500 + NASDAQ 100 + liquid ETFs.

Primary source for the index constituents is Wikipedia (current membership).
If that fetch fails (offline / page-layout change) a bundled curated large-cap
subset is used instead so the scanner always runs. Requires network for the
Wikipedia fetch; the ETF + fallback lists are local.
"""
import io

import pandas as pd

# Wikipedia 403s the default urllib user-agent; use a browser UA.
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def _read_tables(url):
    """Fetch HTML tables with a real user-agent (Wikipedia blocks the default)."""
    try:
        import requests  # bundled with yfinance
        r = requests.get(url, headers=_HEADERS, timeout=20)
        r.raise_for_status()
        return pd.read_html(io.StringIO(r.text))
    except ImportError:
        # pandas can pass headers via storage_options on newer versions
        return pd.read_html(url, storage_options=_HEADERS)

LIQUID_ETFS = [
    "SPY", "QQQ", "IWM", "DIA", "XLF", "XLK", "XLE", "XLV", "XLI", "XLY",
    "XLP", "XLU", "XLB", "XLRE", "XLC", "SMH", "SOXX", "ARKK", "GLD", "SLV",
    "TLT", "HYG", "LQD", "EEM", "EFA", "FXI", "GDX", "GDXJ", "KRE", "XBI",
    "XOP", "XHB", "ITB", "IBB", "VNQ", "USO", "UNG", "DBA", "XME", "TAN",
    "JETS", "KWEB", "VWO", "VEA", "EWZ", "EWW", "INDA", "BITO", "ARKG",
]

# Curated liquid large-caps used only if the Wikipedia fetch fails.
FALLBACK_STOCKS = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "NVDA", "TSLA", "AVGO",
    "AMD", "NFLX", "ADBE", "CRM", "ORCL", "CSCO", "INTC", "QCOM", "TXN",
    "MU", "AMAT", "INTU", "NOW", "PANW", "SNOW", "PLTR", "UBER", "ABNB",
    "SHOP", "SQ", "PYPL", "COIN", "MRVL", "ASML", "ARM", "SMCI", "DELL",
    "JPM", "BAC", "WFC", "GS", "MS", "C", "SCHW", "BLK", "AXP", "V", "MA",
    "BRK-B", "UNH", "JNJ", "LLY", "PFE", "MRK", "ABBV", "TMO", "ABT", "DHR",
    "BMY", "AMGN", "GILD", "CVS", "MDT", "ISRG", "VRTX", "REGN", "HUM",
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "OXY", "HAL", "DVN",
    "WMT", "COST", "HD", "LOW", "TGT", "NKE", "MCD", "SBUX", "PG", "KO",
    "PEP", "PM", "MDLZ", "CL", "DIS", "CMCSA", "T", "VZ", "TMUS", "CAT",
    "DE", "BA", "GE", "HON", "UPS", "FDX", "LMT", "RTX", "MMM", "EMR",
    "F", "GM", "RIVN", "LCID", "NEE", "DUK", "SO", "LIN", "FCX", "NUE",
    "DOW", "ENPH", "FSLR", "MARA", "RIOT", "DKNG", "ROKU", "ZM", "DDOG",
    "NET", "CRWD", "ZS", "MDB", "OKTA", "TTD", "SPOT", "PINS", "SNAP",
]

_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_NDX_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"


def _wiki_symbols(url, candidate_cols):
    tables = _read_tables(url)
    for t in tables:
        for col in candidate_cols:
            if col in t.columns:
                syms = [str(s).replace(".", "-").strip().upper() for s in t[col].tolist()]
                syms = [s for s in syms if s and s.isascii() and 1 <= len(s) <= 6]
                if len(syms) > 50:
                    return syms
    raise ValueError(f"no symbol column in {url}")


def build_universe(verbose=True):
    syms = set(LIQUID_ETFS)
    try:
        syms |= set(_wiki_symbols(_SP500_URL, ["Symbol", "Ticker"]))
        if verbose:
            print("[universe] S&P 500 constituents loaded")
    except Exception as e:
        if verbose:
            print(f"[universe] S&P 500 fetch failed ({e}); using fallback large-cap subset")
        syms |= set(FALLBACK_STOCKS)
    try:
        syms |= set(_wiki_symbols(_NDX_URL, ["Ticker", "Symbol"]))
        if verbose:
            print("[universe] NASDAQ-100 constituents loaded")
    except Exception as e:
        if verbose:
            print(f"[universe] NASDAQ-100 fetch failed ({e}); continuing")
    return sorted(syms)
