# pa_scanner

Price-action scanner for liquid US equities + ETFs. Two signals, ranked, output
to a self-contained HTML report. Ships with a matching TradingView Pine v6
indicator for on-chart confirmation and Pine Screener use.

## Signals

**S1 — Reversal at weekly level.** Price within 1×daily-ATR of a weekly
support/resistance zone (fractal swing pivots clustered with a 0.75×weekly-ATR
tolerance) *and* a direction-matched daily reversal candle. Bullish candle at
support → long; bearish candle at resistance → short.

**S2 — Trend pullback breakout.** Weekly trend intact (EMA10 vs EMA30 + slope),
a recent daily pullback to/through the daily EMA20, then a daily close beyond the
prior-7-day Donchian extreme in the trend direction. Volume ≥1.2×20d avg adds to
the score. Mirror logic for downtrends (short).

Liquidity gate: last price ≥ $10 and 20-day average dollar volume ≥ $20M.
Universe: S&P 500 + NASDAQ 100 (live from Wikipedia) + a curated liquid ETF list.

## Install

```bash
pip install yfinance pandas numpy lxml
```

Python 3.10+.

## Run

```bash
python -m pa_scanner.cli                      # full scan -> pa_report.html
python -m pa_scanner.cli --long-only
python -m pa_scanner.cli --short-only
python -m pa_scanner.cli --out today.html --limit 150   # cap universe (debug)
python -m pa_scanner.cli --tickers AAPL MSFT NVDA SPY   # ad-hoc list
```

Open the resulting HTML in any browser. The table sorts (click headers),
filters (All / S1 / S2 / Long / Short + ticker search), exports CSV, and links
each row to its TradingView chart. Sparklines show the last 40 daily closes.

## Configuration

All knobs live in `pa_scanner/config.py` (`CFG`). Key ones:

| Knob | Default | Meaning |
|---|---|---|
| `daily_period` | `2y` | history pulled per symbol |
| `min_avg_dollar_vol` | `20M` | liquidity floor |
| `s1_near_atr` | `1.0` | "near a level" band (×daily ATR) |
| `s1_cluster_atr` | `0.75` | pivot→zone merge tolerance (×weekly ATR) |
| `s2_breakout_n` | `7` | Donchian breakout window (days) |
| `s2_pullback_lookback` | `10` | days to find the counter-trend dip |
| `s2_require_structure` | `False` | also require weekly HH/HL (else scored) |
| `s2_vol_mult` | `1.2` | volume-expansion bonus threshold |

## Adding a pattern later

The engine is a rule registry. To add a signal:

1. Open `pa_scanner/rules.py`.
2. Write a class with `code`, `name`, and `evaluate(ctx) -> Signal`, decorated
   with `@register`. Read whatever you need off `ctx` (a `SymbolContext` with
   precomputed indicators — see `scanner.py`); if you need a new precomputed
   field, add it in `prepare_context`.
3. Return `Signal(hit, side, score, label, meta)`. Done — it shows up in the
   report automatically.

No other file changes required.

## Architecture

```
pa_scanner/
  config.py       all tunable knobs (CFG)
  universe.py     S&P500 + NDX (Wikipedia) + liquid ETFs, with offline fallback
  data.py         yfinance daily download, weekly resample, liquidity filter
  indicators.py   EMA, ATR, Donchian, fractal pivots, level clustering
  candles.py      10 candlestick detectors + bullish/bearish strength maps
  rules.py        Signal + @register registry + the two rules  <- extend here
  scanner.py      prepare_context() (shared indicators) + scan()
  report.py       self-contained HTML dashboard
  cli.py          entrypoint (python -m pa_scanner.cli)
  selftest.py     synthetic-data tests (python -m pa_scanner.selftest)
```

## Pine indicator (`pa_confirm.pine`)

TradingView Pine v6, overlay. Run on the **Daily** timeframe. Plots weekly S/R
lines, marks S1/S2 long/short on the chart, and exposes alert conditions.

**On-chart:** add to a daily chart, set alerts on the four conditions.

**Pine Screener (Premium):**
1. Add the indicator to your chart, then star it into **Favorites**.
2. Open the **Pine Screener** (Products → Screeners → Pine).
3. Choose your watchlist and set the interval to **1D**.
4. Filter on the data-window columns `S1_Long`, `S1_Short`, `S2_Long`,
   `S2_Short`, or `AnySignal` ( = 1 means a hit ). `WeeklyTrend` = 1/-1/0.
5. Evaluate after the daily close for confirmed signals.

The Pine weekly S/R uses the latest confirmed weekly pivot high/low (lighter than
the Python engine, which clusters multiple pivots into zones). Use the Python
report as the source of truth and Pine for fast visual confirmation / screening.

## Data source & verification

- Data is pulled live from Yahoo Finance via `yfinance` (needs internet).
- The **detection logic and report generation are verified** by
  `python -m pa_scanner.selftest` (19 synthetic-data checks: S2 long/short
  pipeline incl. trend/pullback/breakout/volume, S1 long/short rule units +
  far-level negative, candlestick detection, pivot+clustering, report output).
- The live yfinance fetch is verified by structure only (the build sandbox can't
  reach Yahoo); run an actual scan on a machine with internet.
- Patterns are evaluated on the **last completed daily bar** — run the scan after
  the US close (or intraday accepting the forming bar).
