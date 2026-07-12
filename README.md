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

**Evidence gate:** the technical matrix cannot create entry authority. Only
PRIME/PREFERRED rows retain BUY/HOLD. EXPERIMENTAL, CONTEXT and CAUTION entries
become WATCH; AVOID remains AVOID. Technical REDUCE/EXIT warnings stay visible
with their evidence tier. Qty is emitted only for an evidence-authorized BUY.

This is a **screen**, not position-aware: it flags any constituent firing an
exit/avoid setup; cross-reference your own holdings (ASX via TWS, India via your
NSE broker). Universes are curated ~100-name index lists (ASX 50 + mid-caps;
NIFTY 50 + Next 50); the dollar-volume filter is relaxed since index membership
guarantees liquidity. yfinance handles `.AX` / `.NS` natively.

**Dashboard:** the US / ASX / India tabs at the top switch markets; each has its
own JSON snapshot (`latest.json`, `latest_asx.json`, `latest_in.json`) and the
cloud Action refreshes all three daily. Local buttons:
`run_scan_all.bat` (US + ASX daily, via TWS — the recommended default),
`run_scan_live_us.bat` and `run_scan_live_asx.bat` (last-hour real-time,
local-only — split because each market's last hour falls at a different clock
time: US ~3–4pm ET / ~5–6am AEST, ASX ~3–4pm AEST / ~1–2am ET), and the
single-market `run_scan.bat` / `run_scan_asx.bat` / `run_scan_india.bat`
(and `.command` equivalents). ASX runs on IBKR/TWS so it shares the US live
last-hour path (S2 triggered/pending, S4 reclaimed/below-MA, S1 at-level);
India is EOD-only (separate broker).

## Findings (5y CURRENT-COHORT event study, side-matched baselines)

> Caveat: this is a current-cohort study (survivor-biased), baselines are
> side-matched but not date/sector/beta matched, and the same 5y window was
> used for discovery and confirmation. Findings below are strong *hypotheses*
> pending out-of-sample confirmation (the forward ledger accrues that). Do not
> read "validated" as "out-of-sample proven".

Honest positioning after 59k backtested events across all three markets:

- **US/ASX directional entries (S1/S2) carry no measured aggregate alpha**
  (|t| < 1.6 everywhere after drift correction). Treat them as *context and
  candidate generation*, not edge. Score/rank organize the list; they do not
  predict returns (deciles are flat over 5y).
- **India EXIT flags are validated** — bearish S1 triggers predict
  underperformance (+0.54% excess over 10d, t=3.0). The long-only tab's
  get-out logic is the strongest result in the study.
- **US bench-bearish stand-down is real risk information**: all signals fired
  while SPY reads bearish lose −0.70% excess @5d (t=−6.05), negative at every horizon on the clean S1/S2-only slice (to −1.59% @42d, t=−4.36). The dashboard and
  report show a STAND-DOWN banner in that state (`bench_standdown`).
- **S3 quiet-name selection works in all three markets** (~8–10% lower 10-day
  absolute move than baseline) — the condor-selection function is the app's
  measured edge for premium selling.
- **Exit templates** (from the 5y MAE/MFE distributions: median MAE ≈ −3.4%):
  every hit carries Stop (2.0×ATR), Tgt (1.5×ATR; range edges for S3), and a
  10-bar time exit (`exit_stop_atr`, `exit_target_atr`, `exit_time_bars`).
- Isolated significant cells (single patterns in single markets) are treated
  as multiple-comparison artifacts unless they replicate.

**Horizon study (10/21/42/63d, cooldown 42):**

- **US: do not extend directional holds past ~21d.** Signal excess turns
  significantly negative at 42-63d (S2 t=-4.6 to -5.4; longs alone -1.4%,
  t=-2.9). Part is vol/beta composition (signals cluster in high-ATR names),
  but the conclusion stands. The bench-bearish stand-down strengthens with
  horizon (-2.45% @63d, t=-4.5). S3 quiet-name selection persists to 63d
  (11.3% vs 12.7% baseline abs move). Quietness-persistence SCREEN, not a validated option edge - the harness shows the underlying stays quiet, not that a condor/calendar is profitable. 30-60 DTE is a sensible pairing; option expectancy is untested.
- **India: S2-long is an experimental 6-13 week candidate** (+0.95-1.14%
  excess at 42-63d, t~1.8-2.3), below the promotion bar. Its 3.5xATR / 4.5xATR /
  63-bar policy remains research context; rows are WATCH with no Qty pending
  matched validation. India S1 bearish exit flags strengthen at 63d - treat as
  underweight-for-months, not a short-term trim.
- **ASX: null at every horizon** - remains a candidate screen on the 10-bar
  swing template.

## Signal quality (v2)

The signal core was hardened after review; the visible list should be shorter
and materially better:

- **S1 direction fixed** — a zone only counts as *support* if price approached
  it from above and the bar's **low** actually tagged it (mirror for
  resistance). Previously a rally poking above overhead supply could read as
  "long @ support". Reversals aligned with the weekly trend score up;
  knife-catches against it score down.
- **S2 freshness + no chasing** — only breakouts whose Donchian cross happened
  within the last `s2_max_age` (2) bars list, an **Age** column shows how old
  the trigger is, entries further than 1.5 ATR past the trigger are rejected,
  and the magnitude term now peaks near the trigger instead of rewarding
  extension. The breakout bar must at least match prior-20 average volume
  (self-dilution in the volume baseline also fixed).
- **S3 stability** — ranges whose recent closes press a boundary are coiling,
  not chopping, and are rejected; on the US tab, high realized-vol chop ranks above
  cheap-vol chop.
- **Relative strength (RS)** — 63-day return vs the market benchmark
  (SPY / ^AXJO / ^NSEI), shown as a universe percentile. Strong RS lifts longs;
  weak RS lifts shorts/exits. `RS>50` filter chip on every tab.
- **Index regime** — the benchmark's own trend read is shown in the header and
  counter-index signals take a score penalty.
- **Earnings (US)** — days-to-next-earnings on each hit (amber ≤10d, `Ern OK`
  filter chip); yfinance best-effort, blank when unavailable.
- **Rank + floor** — `rank` = score percentile within the signal's own rule
  (cross-rule sortable; the default sort). A post-adjustment score floor
  (`min_score` 0.45, CLI `--min-score`, 0 disables) cuts the weak tail.
- Sub-half-ATR bars can't print hammer/star/tweezer patterns; tweezers are
  down-weighted; **evening_star retired** (negative expectancy in all three
  markets in the event study).

## PRIME audit (date-matched + block bootstrap)

`python -m pa_scanner.backtest --market us --prime-audit --horizons 63` scopes
the two criticisms that most inflate the S4-in-bench-bearish (PRIME) claim.
(1) **Date-matched baseline**: each S4-long hit on a bearish-bench date is
compared to the mean forward return of ALL longs available on that SAME date,
so 'stocks bounce on down days' is subtracted and only S4's selection excess
remains. (2) **Block bootstrap by date**: whole dates are resampled with
replacement (each selloff = one block carrying all its hits), so the 95% CI
reflects the number of independent DAYS, not clustered hits. Writes
report_<mkt>_prime.md with date-matched mean excess, bootstrap CI, p(excess<=0),
and the independent-day count. If the CI straddles 0, PRIME is
ordering/attention only - never a sizing signal.

## OCO exit-policy simulation + matched audit

Every directional event is now also replayed as the **actual bracket the app
prints** - stop k_s x ATR, target k_t x ATR, time exit (per-market template:
US S4 2.0/1.5/5, ASX S4 & India S2-long 3.5/4.5/63, else 2.0/1.5/10) - with
entry at the next session's open, gap-through fills at the open, market-specific
round-trip costs, and the stop assumed first on a both-touched bar. Trades without
their complete time horizon are right-censored rather than force-exited early.
The report's **OCO exit-policy (realized)** table gives per-rule n, win%,
**exp_R** (mean R-multiple; positive = the template nets money on this
cohort), exp_%, the target/stop/time outcome split, and average bars held.
This describes the exit POLICY, which the MAE/MFE distributions never did -
MAE/MFE showed where price wandered, not whether a 0.75-R:R bracket profits
after the stop-first convention. Raw expectancy is not selection alpha. Run
`python -m pa_scanner.backtest --market us --oco-audit` to apply the identical
policy to same-date non-S4 controls matched on SMA200 side, ATR%, distance from
SMA200 and relative strength. The audit collapses hits to weeks, uses a moving-
block bootstrap, and reports a final 20% chronological-tail diagnostic. That
tail is not untouched rule-development OOS because S4 was originally researched
on the full cohort. S4 is promoted only if matched excess clears zero and the
tail remains positive, followed by genuine forward evidence.

Full five-year current-cohort results (2026-07-12):

- **US:** 11,636 hits / 58,180 controls / 218 weeks; +0.0154R matched excess,
  95% moving-block CI [-0.0046,+0.0362], final-20% holdout +0.0347R — near-miss,
  remains **EXPERIMENTAL**.
- **ASX:** 827 hits / 4,135 controls / 179 weeks; -0.0461R, CI
  [-0.1238,+0.0357], holdout -0.1655R — **AVOID**, no support for trading the
  long-duration S4 template.
- **India:** 2,415 hits / 12,075 controls / 209 weeks; +0.0191R, CI
  [-0.0112,+0.0488], holdout -0.0114R — not promoted; **CONTEXT** only.

## Backtest (event study)

`python -m pa_scanner.backtest --market us|asx|in` replays the scanner over
5 years of history (`--period` to change; the daily scan itself stays on 2y) and measures forward edge per rule. `run_backtest.bat` runs
all three markets. Outputs (local-only, gitignored): `backtest/report_<mkt>.md`
and raw `events_<mkt>.csv`.

- **Fidelity:** the replay rebuilds the exact live SymbolContext per bar and
  feeds the real rule objects; `--verify N` cross-checks N random bars against
  the live `prepare_context` (the selftest requires 100% parity).
- **Measures:** signed forward returns at 1/3/5/10d vs a seeded random,
  **side-matched** baseline (long events vs random longs, short vs random shorts,
  so market drift can't masquerade as short-side edge; excess% column), win rate and t-stat sliced by rule, score decile
  (monotonicity check), RS bucket, weekly-trend alignment, benchmark regime,
  S2 age, S1 pattern, and vol-state (realized-vol proxy - true IVR history is
  not replayable). S3 reports range hold-rate and absolute move vs baseline
  (condor proxy). S1/S2 MAE/MFE inform stop and target placement.
- **Reading it:** a rule earns its place if mean/median beat baseline with a
  t-stat you trust and score deciles are monotonic. Use `events_<mkt>.csv` for
  custom slices; thresholds in config.py should be retuned from these tables,
  then re-run.
- First-fire events only (10-bar cooldown per ticker+rule+side); entries are
  next-day-close-agnostic (event-study convention: signal-bar close to t+h close).

## S4 — Oversold snapback (experimental / forward-track)

Live in all markets as a **market-specific, long-only** screen above the 200SMA,
with two former promotion triggers: **RSI(3) < 15 with a 2+ down-close streak**
(promotion-era discovery stats: US 5d +0.38% t=3.44, ASX t=2.13 — DID NOT
replicate on the refreshed 2026 cohort: ~0 excess at every horizon in every
trigger cell, robust to cooldown 10/21. The old +0.05R pre-cost OCO result was
raw policy expectancy, not selection alpha. The matched audit leaves US S4
EXPERIMENTAL, ASX S4 AVOID and India S4 CONTEXT. RSI(3) beat the RSI(2) textbook
variant in the US parameter test) **or a 4+ consecutive-down-close flush**
(round 2 STRK4: US t=3.17, ASX t=2.73, ASX persistence 21–63d;
`s4_streak_min`). Exits: US 5-bar time exit (`s4_time_bars`) with 2.0/1.5 ATR;
ASX still carries the historical 3.5/4.5 ATR, 63-bar research template, but its
matched OCO audit is negative and the board now marks it **AVOID**. **S4 is exempt from the STAND-DOWN
banner** — the raw bearish-regime slices looked strong
(US +5.57% excess @63d t=9.37, ASX +4.09% t=6.96) but BOTH failed the
date-matched + block-bootstrap PRIME audit (US: -0.36%, CI [-3.60,+3.11],
p=0.60 on 94 independent days; ASX: -0.24%, CI [-2.10,+1.72], p=0.60 on 95
days) — the apparent edge was date effect x clustering. PRIME is retired;
S4 keeps its S1/S2-independent exemption from the stand-down WARNING only. Rich-vol
names snap hardest (replicated t=2.86/5.65) — prefer higher-ATR% S4 hits. No
short mirror — candidate shorts were harmful in every market (US t=−3.9).

## Strategy Tester (backtest any ticker on TradingView)

`pa_strategy_tester.pine` is a combined Pine **strategy** (not just an
indicator) with dropdowns to pick the rule (S1/S2/S3/S4) and market template
(US/ASX/India), then run TradingView's Strategy Tester on any ticker. Entry
logic is copied verbatim from `pa_confirm.pine` v2; exit templates (SL/PT/time
exit) match the app exactly, including the India S2-long and ASX S4 position
templates, and a "block during bench STAND-DOWN" toggle for S1/S2 (S4 stays
exempt). A **Risk override** group lets you punch in custom SL/PT/time values
instead.

**S3 caveat:** the app's actual validated S3 edge is quiet-name *selection*
for **options premium selling** (sell a condor/calendar at the range edges),
which isn't a stock long/short trade and can't be represented in the Strategy
Tester. The S3 option here is a **fade-the-range proxy** (long at the range
low, short at the range high) for illustration only — its backtest numbers
are not validation of the app's S3 finding; treat S3's real edge as the
quiet-range screen it already is in the scanner.

Fill convention: `process_orders_on_close=true` fills at the signal bar's own
close (matching the app's "enter at signal close" assumption), not the next
bar's open — a same-bar-fill assumption to be aware of when comparing results
to slower, next-bar-open backtests.

## Strategy board (daily cross-rule ranking)

`pa_scanner/strategy_board.py` ranks the four live rules by conviction for the
day and renders as cards above the table (report + dashboard, click a card to
filter). Every tier is keyed to a backtest finding, conditioned on the
benchmark regime: **PREFERRED** (promotion bar cleared), **EXPERIMENTAL**
(forward-track only), **CONTEXT** (no measured entry edge), **CAUTION**
(usable with a caveat, e.g. US S2 <=21d), **AVOID** (S1/S2 during a
bench-bearish stand-down - card names the alternative). Order reshuffles with
the regime; hit counts show the day's signal volume per rule.

## STFS-EQ imports

Three pieces imported from the earlier `stfs-eq` project (audit verdicts in
the commit): the **market-state line** (`pa_scanner/snapshot.py`, ported from
`market_snapshot.py`) shown next to the benchmark regime — five states with
size guidance, display-only, US uses SPY/QQQ/IWM/^VIX/HYG with graceful
degradation, ASX/India benchmark-only; the **Qty column** (battle-card sizing:
`risk_dollars ÷ stop distance`, off by default via `risk_dollars=0`); and the
**ledger drift analysis** (`analyze_journal` pattern): per-rule
win%/payoff/expectancy, monthly drift buckets, oldest-open aging. Parked, not
imported: the 8-factor scoring and 256-combo optimizer (data mining our
promotion bar exists to prevent — available as a pre-registered round 3),
trailing-stop management (must beat the fixed template in the harness first),
the regime engine/order server/IVP (overlap or scope conflicts).

## S4★ PRIME + forward ledger

**PRIME (RETIRED):** the date-matched, block-bootstrapped audit
(`--prime-audit`) killed the underlying cell — US: 795 hits across only 94
independent bearish dates, date-matched excess **−0.36%**, 95% CI
[−3.60%, +3.11%], p(≤0)=0.60. S4 in bearish regimes adds nothing beyond being
long that day; the raw +5.57% was date effect × clustering. `s4_prime` now
defaults **False** (plumbing kept; re-enable only for a market whose own
prime-audit CI clears zero). The S4 index-penalty exemption, which rested on
the same cell, is also removed. The old OCO simulation showed +0.053R/trade
pre-cost, but that result is not a promotion claim: it used no matched control,
signal-close fills and no costs. The matched audit subsequently set US S4 to
EXPERIMENTAL, ASX S4 to AVOID and India S4 to CONTEXT.

**Forward ledger:** each scan appends its hits to
`docs/data/ledger_<mkt>.json` (entry = signal close, exits from the row's
stop/tgt/time template) and resolves prior opens against new bars —
`target` / `stop` / `time` for directional, `broke` / `held` for S3.
Conservative fills: stop wins a both-touched bar. This accumulates true
out-of-sample evidence for every live rule and the PRIME cell. Stats:
`python -m pa_scanner.ledger --market us [--dir docs]`. Skip with
`--no-ledger`; resolved history capped at `ledger_keep_resolved`.

## Candidate setups (experimental, backtest-only)

`pa_scanner/candidates.py` holds five directional-setup candidates being
evaluated to replace the null US/ASX directional edge. None run in the live
scanner. Test with:

```bash
python -m pa_scanner.backtest --market us  --candidates --horizons 5 10 21 42 63 --cooldown 21
python -m pa_scanner.backtest --market asx --candidates --horizons 5 10 21 42 63 --cooldown 21
```

Outputs `backtest/report_<mkt>_cand.md`. Candidates: **NH52** (fresh 52-week
high + volume), **HVOL** (>=3x-volume day premium, both sides), **GAPD**
(>=1-ATR gap held into the close, PEAD proxy, both sides), **OSMR** (RSI(3)
oversold snapback above the 200SMA), **PBEMA** (6-month momentum leader, first
20-EMA touch). Promotion bar (pre-registered): |t| >= 2.5 at two adjacent
horizons with consistent sign, or >= 2.0 replicated across US and ASX. Round-1 originally promoted OSMR, but the 2026 replication found ~0 selection excess and the matched OCO audit did not promote any market;
PBEMA near-miss (US 63d t=2.33, ASX 1.65) parked for out-of-sample re-test;
NH52/HVOL/GAPD failed and were deleted; all candidate shorts harmful (US t=-3.9).

**Round 2 (settled)**: STRK4 was folded into S4 during discovery, but the refreshed trigger cells did not replicate;
OSMR2 settled the parameter test (RSI(2) lost to RSI(3) in the US);
LO7/BBMR/IBSMR failed and were deleted. CANDIDATES is now empty; PBEMA stays
parked for an out-of-sample re-test. The Pine companion (`pa_confirm.pine`,
v2) mirrors the final engine: S1 approach/wick gates, S2
freshness/volume/extension gates, S4 dual trigger, benchmark stand-down
shading (S4 exempt), evening_star retired.

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
| `s2_max_age` | `1` | breakout freshness window (backtest: age-2 entries were negative) |
| `s2_max_ext_atr` | `1.5` | reject entries further than this past the trigger |
| `s2_vol_gate` | `1.0` | breakout bar volume must match prior-20 average |
| `rs_window` | `63` | relative-strength lookback vs benchmark |
| `min_score` | `0.45` | post-adjustment score floor (`--min-score`) |
| `earnings_warn_days` | `10` | Ern column warn threshold (US) |
| `opt_oi_min` | `250` | min combined ATM (call+put) OI before a US hit is flagged thin |
| `opt_spread_max_pct` | `12.0` | max ATM bid/ask spread (% of mid) before thin |

**ATR%** (`atr ÷ last × 100`) is a sortable column on every tab — currency-neutral,
so it ranks risk across US/ASX/India and converts straight to a % stop width.

**Opt Liq** (US tab, TWS path only) flags each hit `OK`/`thin` from the ATM
open interest and bid/ask spread on the front expiry. It is harvested from the
same ATM call/put the vol provider already prices, so it costs no extra option
requests. Blank on the yfinance/realized path (no chain data). Spread reads most
reliably in-hours; after the close the OI component (prior settle) carries it.

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
