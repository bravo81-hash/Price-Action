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

    # --- direction ---
    allow_long: bool = True
    allow_short: bool = True

    # --- report ---
    spark_bars: int = 40


CFG = Config()
