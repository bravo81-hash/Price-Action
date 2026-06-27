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

**S3 — Range / chop (neutral).** A *non*-directional setup: the ticker is not
trending (ADX < `s3_adx_max`), its fast/slow EMAs are flat, and price sits in the
middle band of a well-formed range (width within `s3_min/max_width_pct`, position
`s3_pos_low..s3_pos_high`). Side = **neutral**; it routes to the neutral matrix
row → **Calendar** (cheap vol) or **Iron Condor** (fair/rich vol). S3 is mutually
exclusive with S1/S2 by construction (mid-range ≠ at a level ≠ breakout). Disable
with `--no-neutral`.

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

## Run on any computer (GitHub Pages + Actions)

The work the system does splits in two: **compute** (pull data, run signals —
needs Python + internet) and **viewing** (browser only). The viewing layer is a
static dashboard at `docs/index.html` that reads `docs/data/latest.json`, so a
locked-down machine with no installs just opens a URL.

**Live dashboard:** https://bravo81-hash.github.io/Price-Action/

### One-time setup
1. Repo must be **public** for free GitHub Pages (this repo only — your private
   strategy repos are unaffected).
2. **Settings → Pages → Build and deployment → Source: Deploy from a branch →
   Branch `main`, folder `/docs` → Save.** Wait ~1 min; the URL above goes live.

### Auto-updates (no computer needed)
The `scan` GitHub Action (`.github/workflows/scan.yml`) runs the scan in the
cloud on weekdays at **22:30 UTC** (after the US close), writes a JSON snapshot,
and commits it. It uses the built-in Actions token — no PAT required.
Trigger it by hand anytime: **Actions tab → scan → Run workflow**.

### Run it from your personal PC
Same command writes the same snapshot:
```bash
python -m pa_scanner.cli --web docs --no-html      # JSON only
python -m pa_scanner.cli --web docs                 # JSON + local HTML
git add docs/data && git commit -m "scan" && git push
```
The dashboard picks up the new snapshot on reload. Past snapshots are kept (last
60 days) and selectable from the dropdown.

### Fully offline / private alternative
`pa_report.html` (from a plain `python -m pa_scanner.cli`) is a single
self-contained file with the data baked in. Drop it in OneDrive/Drive and open it
in any browser — no hosting, stays private.

## Regime context per ticker (direction × vol-state → structure)

Every signal row is annotated with a trade-construction read, so pre-market /
post-market prep on any machine shows not just *what* fired but *how to express
it*:

- **Regime** — direction from trend/ADX/bias: **Bull / Bear / Neut** (Neutral
  when ADX < `adx_trend_min`, i.e. no directional conviction). Price-only, so it
  is identical in every environment.
- **Vol** — **cheap / fair / rich**, via the playbook's 3-step logic:
  1. bucket from **IVR** (or realized-vol rank as the free-path seed),
  2. **VRP ≤ 0** nudges one bucket cheaper,
  3. **backwardation** forces cheap.
  The small tag shows the seed used: `ivr` (true IV rank, TWS path) or `rvr`
  (realized-vol rank, free path). Hover the cell for IV / RV / VRP / term.
- **Structure** — the regime cell mapped through the 3×3 matrix, with the
  debit/credit tag:

  |        | cheap | fair | rich |
  |--------|-------|------|------|
  | **Bear** | Long Put (D) | Call Credit Spread (C) | Call Credit Spread (C) |
  | **Neut** | Calendar (D) | Iron Condor (C) | Iron Condor (C) |
  | **Bull** | Call Debit Spread (D) | Put Credit Spread (C) | Put Credit Spread (C) |

  Structure expresses the **signal's own side** (long -> bullish row, short ->
  bearish row), so it is always coherent with the trade. The **Regime** column is
  the separate trend backdrop and carries a **with / counter** flag when the
  signal runs with or against that trend (a counter-trend fade carries different
  risk). Set `structure_from = "regime"` in `config.py` for the legacy
  regime-led behaviour.

### Two accuracy tiers (same matrix, different vol source)
- **Free path (cloud / work-computer prep):** no IV history, so IVR isn't
  available. For each *signal hit* the scanner pulls **current ATM IV** from
  yfinance option chains → real **VRP** (IV vs realized vol) + per-ticker **term
  slope**; vol-state is seeded from realized-vol rank. Clearly tagged `rvr`.
  `--no-iv` skips the option fetch entirely (realized-vol only, fastest).
- **Personal PC + TWS (`--tws`):** connects to a running TWS / IB Gateway via
  `ib_async` (`config.py`: `tws_host`/`tws_port`/`tws_client_id`; default live
  port 7496, dynamic clientId so it never collides with your other API apps) and
  pulls, for each hit: **true IVR** (1-yr underlying `OPTION_IMPLIED_VOLATILITY`
  history — impossible on the free path), **real ATM IV + term structure** from
  live option greeks, and **VRP**. Tagged `ivr`. IBKR throttles historical data
  (~60 / 10 min), so only the top `tws_max_enrich` (default 25) hits get the full
  TWS read; the rest fall back to realized vol. If TWS isn't running / the API is
  off, `--tws` degrades gracefully to the yfinance approximation.

  Requires: `pip install ib_async`, and TWS/IBG with **API enabled** (Configure →
  API → Settings → *Enable ActiveX and Socket Clients*, port 7496, 127.0.0.1
  trusted). Live market-data subscriptions affect which greeks populate.

All thresholds (IVR/RV-rank buckets, ADX trend floor, VRP/backwardation rules,
target DTEs for the IV pull, TWS connection) live in `config.py`.

> Note: live data fetching (yfinance option chains, TWS) can't run in the build
> sandbox, so the regime **logic, matrix, and rendering are verified by
> self-tests** (54 checks) and the **TWS-down fallback path is verified**; the
> live IBKR fetch itself is structure-verified — it runs on your machine.
