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

## Live last-hour workflow (real-time TWS)

The price-action signals are computed on the **daily bar**, which does not close
until 4 pm ET. The final hour is the best intraday time to run the scan (the bar
is ~93% formed, so it is a strong *preview* of the closing signal), but it is a
preview — a setup can still change in the last minutes. Confirm in TWS before
executing.

```bash
python -m pa_scanner.cli --tws --live     # or double-click run_scan_live.bat
```

`--live` implies `--tws` and switches IBKR to **live** market data. It:

1. Screens the full universe on yfinance daily bars (~15 min delayed — fine for
   5–10 day swing setups).
2. Pulls **real-time IV / IVR / vol** for the top hits from TWS (as `--tws` does).
3. Pulls a **real-time price snapshot** for each hit and adds a **Live** column:
   the current price plus a live trigger status —
   - **S2**: `triggered` (price already past the breakout level) or `pending`,
     with Δ = ATR-distance to the level.
   - **S1**: `at level` (within 1 ATR of the weekly S/R) or `away`.
   - **S3**: `in range` or `broke out`, with the position in the range (0–1).

`run_scan_live.bat` / `run_scan_live.command` are **local-only** (no commit, no
push) — you are at your trading PC in the last hour, reading the local
`pa_report.html`. Re-run as often as you like as the hour progresses; each run
re-pulls real-time prices and re-evaluates triggers.

**Suggested last-hour loop:**

1. ~3:00 pm ET, run the live button. Sort by **Score**.
2. For each candidate, read **Sig** (S1/S2/S3) + **Side** + **Structure** (how to
   express it given vol), then the **Live** status — is it triggered now, or
   pending and how far?
3. Check **Regime** (`with` trend vs `⚠ counter` = riskier) and **Vol**
   (cheap → favour debit structures; rich → favour credit / condors).
4. For the names you like, pull the chart in **TWS** (real-time), confirm the
   candle / breakout is holding into the close, size the structure, and execute.
5. Re-run near 3:45 pm to catch setups that trigger late.

**Limitations (by design):** the broad screen is ~15 min delayed, so a brand-new
breakout in the final ~15 min may not be a hit yet — catch those with TWS
watchlists / alerts. The structure is a starting point; size and strikes are
chosen in TWS. If `iv`/`term` are blank but `ivr` is present, it is market-data
entitlement — set `tws_market_data_type` in `config.py` (1 live, 3/4 delayed).

## Markets: US (options) + ASX / India (long-only)

The scanner runs three markets. The **US** tab is the full options playbook
(vol-state, structure matrix, TWS, last-hour live mode). **ASX** and **India**
are a different model — long-only directional stock, no options and no short
selling in the relevant accounts — so they drop all vol/options/TWS machinery
and instead tag each hit with a single **Action**:

```bash
python -m pa_scanner.cli --market us            # options (default)
python -m pa_scanner.cli --market asx --web docs # ASX directional screen
python -m pa_scanner.cli --market in  --web docs # India directional screen
```

The same S1/S2/S3 pattern engine is reused; a bearish trigger that would be a
*short* in the US becomes an **exit/avoid** flag here. Action = weekly trend ×
trigger direction:

| Weekly trend | Bullish trigger | No trigger (chop) | Bearish trigger |
|---|---|---|---|
| **Up**   | BUY (add)            | HOLD  | REDUCE (trim)   |
| **Flat** | BUY (small)         | WATCH | AVOID           |
| **Down** | WATCH (risky bounce) | AVOID | **EXIT (get out)** |

Green = BUY/HOLD · amber = REDUCE/AVOID/WATCH · red = **EXIT**. Conservative by
design: a bullish reversal inside a downtrend is WATCH, not BUY, because these
names can't be hedged. The **Exit / Trim** filter isolates the get-out names.

This is a **screen**, not position-aware: it flags any constituent firing an
exit/avoid setup; cross-reference your own holdings (ASX via TWS, India via your
NSE broker). Universes are curated ~100-name index lists (ASX 50 + mid-caps;
NIFTY 50 + Next 50); the dollar-volume filter is relaxed since index membership
guarantees liquidity. yfinance handles `.AX` / `.NS` natively.

**Dashboard:** the US / ASX / India tabs at the top switch markets; each has its
own JSON snapshot (`latest.json`, `latest_asx.json`, `latest_in.json`) and the
cloud Action refreshes all three daily. Local buttons:
`run_scan_asx.bat` / `run_scan_india.bat` (and `.command`).

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
