"""Central configuration. All tunable knobs live here."""
from dataclasses import dataclass


@dataclass
class Config:
    # --- data ---
    daily_period: str = "2y"          # history pulled per symbol
    weekly_anchor: str = "W-FRI"
    download_chunk: int = 100         # tickers per yfinance batch
    min_daily_bars: int = 120
    min_weekly_bars: int = 40

    # --- liquidity filter ---
    min_price: float = 10.0
    min_avg_dollar_vol: float = 20_000_000.0
    dollar_vol_window: int = 20

    # --- shared indicators ---
    atr_window: int = 14
    ema_fast_daily: int = 20

    # --- Signal 1: reversal at weekly level ---
    s1_pivot_left: int = 2
    s1_pivot_right: int = 2
    s1_pivot_lookback_weeks: int = 52
    s1_cluster_atr: float = 0.75      # zone-merge tolerance (x weekly ATR)
    s1_near_atr: float = 1.0          # "near" band (x daily ATR)

    # --- Signal 2: trend pullback breakout ---
    s2_wema_fast: int = 10
    s2_wema_slow: int = 30
    s2_require_structure: bool = False  # also require weekly HH/HL (else adds to score)
    s2_pullback_lookback: int = 10      # days to look back for the counter-trend dip
    s2_pullback_min_pct: float = 0.03   # retrace depth used to normalise pullback quality
    s2_breakout_n: int = 7              # Donchian breakout window (days)
    s2_swing_window: int = 20
    s2_vol_window: int = 20
    s2_vol_mult: float = 1.2            # volume-expansion bonus threshold

    # --- Signal 3: range / chop (neutral) ---
    s3_adx_max: float = 20.0           # ADX below this = not trending
    s3_range_window: int = 20          # window defining the range
    s3_pos_low: float = 0.30           # price must sit in the mid-band of the range
    s3_pos_high: float = 0.70
    s3_min_width_pct: float = 0.04     # range wide enough to be tradeable (>=4%)
    s3_max_width_pct: float = 0.25     # but not a blow-off (<=25%)
    s3_ema_flat_pct: float = 0.015     # |emaFast - emaSlow| / price < this = flat

    # --- direction ---
    allow_long: bool = True
    allow_short: bool = True
    allow_neutral: bool = True          # S3 range/chop signals

    # --- regime: direction read (price-only, all environments) ---
    ema_slow_daily: int = 50
    adx_window: int = 14
    adx_trend_min: float = 20.0        # below this -> Neutral (no directional conviction)

    # --- regime: vol-state read (cheap / fair / rich) ---
    # True IVR needs IV history (TWS path). On the free path the bucket is
    # seeded from realized-vol rank instead; VRP nudge + backwardation still apply.
    ivr_cheap: float = 30.0            # IVR < cheap -> cheap   (TWS path)
    ivr_rich: float = 60.0            # IVR > rich  -> rich    (TWS path)
    rvr_cheap: float = 30.0            # RV-rank < cheap -> cheap (free-path seed)
    rvr_rich: float = 70.0            # RV-rank > rich  -> rich
    vrp_nudge_cheaper: bool = True     # VRP <= 0 nudges one bucket cheaper
    backwardation_force_cheap: bool = True   # inverted term structure forces cheap
    rv_window: int = 20               # realized-vol window (days)
    rv_rank_lookback: int = 252       # realized-vol percentile lookback

    # --- regime: vol provider ---
    iv_enrich_hits: bool = True        # 1A: pull yfinance ATM IV for signal hits
    iv_front_dte: int = 30            # target DTE for the front expiry
    iv_back_dte: int = 75             # target DTE for the back expiry
    vol_source: str = "auto"          # "auto" (realized + IV-on-hits) | "tws" (later)

    # --- TWS / IBKR (accurate vol via ib_async) ---
    tws_host: str = "127.0.0.1"
    tws_port: int = 7496              # live TWS 7496 | paper 7497 | gateway 4001/4002
    tws_client_id: int = 0           # 0 -> random dynamic id (avoids collisions)
    tws_timeout: float = 8.0
    tws_max_enrich: int = 25         # cap TWS-enriched hits (IBKR hist-data pacing ~60/10min)
    tws_market_data_type: int = 2    # 1 live | 2 frozen | 3 delayed | 4 delayed-frozen
    tws_greek_wait: float = 2.0      # seconds to let model greeks populate per contract
    tws_snapshot_wait: float = 1.5   # seconds to let a real-time price snapshot populate

    # Which direction drives the strategy structure:
    #   "signal" -> express the signal's own side (long->bullish row, short->bearish)
    #   "regime" -> express the trend regime (legacy; can contradict the signal)
    structure_from: str = "signal"

    # --- report ---
    spark_bars: int = 40


CFG = Config()


# --- markets -------------------------------------------------------------
# US is the options path (vol/structure/TWS). ASX + India are directional
# (long-only screen, no options): the dollar-volume floor is relaxed because
# index membership already guarantees liquidity, and turnover is in local ccy.
MARKETS = {
    "us":  {"mode": "options",     "suffix": "",    "ccy": "USD", "label": "US",
            "tv": "",    "min_price": 10.0, "min_dollar_vol": 20_000_000.0},
    "asx": {"mode": "directional", "suffix": ".AX", "ccy": "AUD", "label": "ASX",
            "tv": "ASX", "min_price": 0.20, "min_dollar_vol": 0.0},
    "in":  {"mode": "directional", "suffix": ".NS", "ccy": "INR", "label": "India",
            "tv": "NSE", "min_price": 5.0,  "min_dollar_vol": 0.0},
}


def market(name="us"):
    return MARKETS[name]
