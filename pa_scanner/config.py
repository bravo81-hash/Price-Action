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
    s1_approach_bars: int = 10        # prior closes defining the approach direction
    s1_wick_frac: float = 0.5         # wick must reach within this x band of the zone
    s1_close_frac: float = 0.5        # close must hold within this x band past the zone
    s1_min_bar_range_atr: float = 0.5  # single-bar patterns need a real bar (x ATR)
    s1_with_trend_bonus: float = 0.10  # reversal aligned with the weekly trend
    s1_counter_trend_penalty: float = 0.15  # knife-catch against the weekly trend

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
    s2_vol_gate: float = 1.0            # breakout bar must at least match prior-20 avg volume
    s2_max_age: int = 1                 # breakout must be <= this many bars old (0 = today); backtest: age2 negative in US+ASX
    s2_max_ext_atr: float = 1.5         # reject entries further than this past the trigger
    s2_ext_sweet_atr: float = 0.5       # full magnitude score up to this extension

    # --- Signal 3: range / chop (neutral) ---
    s3_adx_max: float = 20.0           # ADX below this = not trending
    s3_range_window: int = 20          # window defining the range
    s3_pos_low: float = 0.30           # price must sit in the mid-band of the range
    s3_pos_high: float = 0.70
    s3_min_width_pct: float = 0.04     # range wide enough to be tradeable (>=4%)
    s3_max_width_pct: float = 0.25     # but not a blow-off (<=25%)
    s3_ema_flat_pct: float = 0.015     # |emaFast - emaSlow| / price < this = flat
    s3_edge_frac: float = 0.10         # boundary band as a fraction of range width
    s3_max_edge_closes: int = 1        # >this many of last 3 closes at a boundary = coiling, reject
    s3_vol_adj: float = 0.07           # US: S3 score +adj when vol rich, -adj when cheap

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
    live_min_fresh_frac: float = 0.6  # --live fails loud unless >= this frac of rows got fresh quotes

    # --- option-chain liquidity check (US/TWS path, on hits) ---
    # Harvested from the same ATM call+put the vol provider already prices on the
    # front expiry, so it adds no extra contract requests. A hit is flagged "thin"
    # if ATM open interest is below the floor or the ATM bid/ask is too wide.
    opt_oi_min: float = 250.0        # min combined ATM (call+put) open interest
    opt_spread_max_pct: float = 12.0  # max ATM bid/ask spread as % of mid

    # Which direction drives the strategy structure:
    #   "signal" -> express the signal's own side (long->bullish row, short->bearish)
    #   "regime" -> express the trend regime (legacy; can contradict the signal)
    structure_from: str = "signal"

    # --- quality / ranking ---
    bt_period: str = "5y"              # backtest history window (scan uses daily_period)
    rs_window: int = 63                # relative-strength lookback (days) vs the market benchmark
    rs_adj_max: float = 0.10           # max score adjustment from RS percentile
    index_penalty: float = 0.10        # counter-index-regime score penalty
    min_score: float = 0.45            # post-adjustment score floor (CLI --min-score)
    earnings_enrich: bool = True       # US: annotate days-to-earnings on hits (yfinance)
    earnings_warn_days: int = 10       # directional: <= this many days = warn
    s3_earnings_tenor: int = 60        # S3 premium: earnings must clear the whole 30-60 DTE window

    # --- S4: oversold snapback (EXPERIMENTAL; promotion-era edge did not replicate) ---
    s4_rsi_max: float = 15.0           # RSI(3) must be below this
    s4_streak_min: int = 4             # alt trigger (round-2 STRK4: US t=3.17, ASX t=2.73)
    s4_time_bars: int = 5              # US edge decays past ~10d; ASX S4 uses the position template

    # --- exit templates (from the 5y MAE/MFE study: med MAE ~ -3.4%) ---
    exit_stop_atr: float = 2.0         # protective stop distance (x ATR)
    exit_target_atr: float = 1.5       # first target distance (x ATR)
    exit_time_bars: int = 10           # time stop (bars) matching the study horizon
    # India S2-long experimental 42-63d research policy (below promotion bar)
    in_pos_stop_atr: float = 3.5       # from 63d med MAE ~ -7.9%
    in_pos_tgt_atr: float = 4.5        # from 63d med MFE ~ +9.6%
    in_pos_time_bars: int = 63
    risk_dollars: float = 0.0          # >0 -> Qty column = floor(risk / stop distance)
    s4_prime: bool = False             # RETIRED by the date-matched audit (US, 795 hits
                                       # / 94 independent days: excess -0.36%, CI [-3.6,+3.1],
                                       # p<=0 = 0.60): S4 in bearish regimes adds nothing beyond
                                       # being long that day. Re-enable only if a market's
                                       # --prime-audit CI clears zero.
    ledger_keep_resolved: int = 1000   # resolved forward-ledger entries kept per market
    bench_standdown: bool = True       # warn when the benchmark regime reads bearish
                                       # (5y US study: all signals -0.63% excess, t=-4.0)

    # --- report ---
    spark_bars: int = 40


CFG = Config()


# --- markets -------------------------------------------------------------
# US is the options path (vol/structure/TWS). ASX + India are directional
# (long-only screen, no options): the dollar-volume floor is relaxed because
# index membership already guarantees liquidity, and turnover is in local ccy.
MARKETS = {
    "us":  {"mode": "options",     "suffix": "",    "ccy": "USD", "label": "US",
            "tv": "",    "min_price": 10.0, "min_dollar_vol": 20_000_000.0,
            "bench": "SPY",   "ib_exchange": "SMART"},
    "asx": {"mode": "directional", "suffix": ".AX", "ccy": "AUD", "label": "ASX",
            "tv": "ASX", "min_price": 0.20, "min_dollar_vol": 0.0,
            "bench": "^AXJO", "ib_exchange": "ASX"},
    "in":  {"mode": "directional", "suffix": ".NS", "ccy": "INR", "label": "India",
            "tv": "NSE", "min_price": 5.0,  "min_dollar_vol": 0.0,
            "bench": "^NSEI", "ib_exchange": "NSE"},
}


def market(name="us"):
    return MARKETS[name]


def contract_spec(yf_ticker, market_key="us"):
    """Map a yfinance ticker to IBKR (symbol, exchange, currency).

    yfinance suffixes (.AX/.NS) are not IBKR symbols; IBKR wants the bare
    local symbol plus a market-specific exchange and currency. US routes
    through SMART/USD; ASX -> ASX/AUD; NSE -> NSE/INR. Returns a dict so the
    caller can build Stock(**spec) without hard-coding SMART/USD.
    """
    mkt = MARKETS.get(market_key, MARKETS["us"])
    suffix = mkt["suffix"]
    sym = yf_ticker[:-len(suffix)] if suffix and yf_ticker.endswith(suffix) else yf_ticker
    return {"symbol": sym, "exchange": mkt["ib_exchange"], "currency": mkt["ccy"]}
