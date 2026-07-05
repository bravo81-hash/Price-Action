"""Forward ledger - logs every fired signal and tracks it to resolution.

Purpose: true out-of-sample evidence. Every scan appends its hits as OPEN
entries (entry = signal-bar close, stop/target/time from the exit template)
and re-checks prior opens against subsequent daily bars until one of:

  target - favorable level touched first        (long: high >= tgt)
  stop   - protective level touched first       (long: low <= stop)
  time   - time_exit bars elapsed, exit at close

Fill assumptions are conservative: entered at the signal close (no slippage
modeled), and when a single bar spans both levels the STOP is assumed filled
first. Neutral (S3) entries resolve as 'broke' (a range edge closed through)
or 'held' (survived time_exit inside the range).

State lives at <out_dir>/data/ledger_<mkt>.json (published with the dashboard
data and versioned by the normal docs commit). Resolved history is capped at
CFG.ledger_keep_resolved per market.

Stats: python -m pa_scanner.ledger --market us [--dir docs]
"""
import argparse
import datetime as dt
import json
import os

import numpy as np

from .config import CFG, MARKETS


def _path(out_dir, market):
    return os.path.join(out_dir, "data", f"ledger_{market}.json")


def _load(out_dir, market):
    p = _path(out_dir, market)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            return d.get("open", []), d.get("resolved", [])
        except Exception:
            pass
    return [], []


def _save(out_dir, market, open_e, resolved):
    os.makedirs(os.path.join(out_dir, "data"), exist_ok=True)
    resolved = resolved[-CFG.ledger_keep_resolved:]
    with open(_path(out_dir, market), "w", encoding="utf-8") as f:
        json.dump({"updated": dt.datetime.now(dt.timezone.utc)
                   .strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "open": open_e, "resolved": resolved},
                  f, separators=(",", ":"))


def _signed_ret(side, entry, exit_px):
    r = exit_px / entry - 1.0
    return round(100 * (-r if side == "short" else r), 2)


def _resolve_entry(e, daily):
    """Walk bars strictly after entry_date; return resolved dict or None."""
    idx = daily.index
    pos = idx.searchsorted(np.datetime64(e["entry_date"]), side="right")
    highs = daily["high"].to_numpy()
    lows = daily["low"].to_numpy()
    closes = daily["close"].to_numpy()
    side, entry = e["side"], e["entry_px"]
    stop, tgt, tmax = e.get("stop"), e.get("tgt"), e.get("time_exit") or CFG.exit_time_bars
    bars = 0
    for i in range(pos, len(idx)):
        bars += 1
        outcome, px = None, None
        if side == "long":
            if stop is not None and lows[i] <= stop:
                outcome, px = "stop", stop
            elif tgt is not None and highs[i] >= tgt:
                outcome, px = "target", tgt
        elif side == "short":
            if stop is not None and highs[i] >= stop:
                outcome, px = "stop", stop
            elif tgt is not None and lows[i] <= tgt:
                outcome, px = "target", tgt
        else:  # neutral: stop=range_lo, tgt=range_hi; a close through = broke
            if (stop is not None and closes[i] < stop) or \
                    (tgt is not None and closes[i] > tgt):
                outcome, px = "broke", closes[i]
        if outcome is None and bars >= tmax:
            outcome = "held" if side == "neutral" else "time"
            px = closes[i]
        if outcome:
            out = dict(e)
            out.update({"outcome": outcome, "exit_px": round(float(px), 4),
                        "exit_date": str(idx[i].date()), "bars_held": bars,
                        "ret_pct": _signed_ret(side, entry, float(px))})
            return out
    return None


def update_ledger(rows, bundle, market, out_dir="docs"):
    """Resolve prior opens against fresh data, then append today's hits."""
    open_e, resolved = _load(out_dir, market)

    still_open, n_res = [], 0
    for e in open_e:
        d = bundle.get(e["ticker"], (None,))[0]
        if d is None or len(d) == 0:
            e["stale"] = e.get("stale", 0) + 1
            if e["stale"] <= 20:          # ticker fell out of the scan; retry
                still_open.append(e)
            continue
        r = _resolve_entry(e, d)
        if r is None:
            still_open.append(e)
        else:
            resolved.append(r)
            n_res += 1

    seen = {(e["ticker"], e["signal"], e["side"]) for e in still_open}
    today = {(x["ticker"], x["signal"], x["side"]) for x in resolved
             if x.get("entry_date") == str(dt.date.today())}
    n_new = 0
    for r in rows:
        d = bundle.get(r["ticker"], (None,))[0]
        if d is None or len(d) == 0:
            continue
        key = (r["ticker"], r["signal"], r["side"])
        if key in seen or key in today:
            continue
        open_entry = {
            "ticker": r["ticker"], "signal": r["signal"], "side": r["side"],
            "entry_date": str(d.index[-1].date()),
            "entry_px": float(r["last"]),
            "stop": r.get("stop"), "tgt": r.get("tgt"),
            "time_exit": r.get("time_exit"),
            "score": r.get("score"), "rank": r.get("rank"),
            "prime": bool(r.get("prime")), "rs_pct": r.get("rs_pct"),
        }
        still_open.append(open_entry)
        seen.add(key)
        n_new += 1

    _save(out_dir, market, still_open, resolved)
    print(f"[ledger] {market}: +{n_new} opened, {n_res} resolved, "
          f"{len(still_open)} open, {len(resolved)} resolved on file")
    return still_open, resolved


def _stats2(entries):
    """Richer directional stats: win%, avg win/loss, payoff, expectancy/trade."""
    dirs = [e for e in entries if e["side"] in ("long", "short")]
    if not dirs:
        return None
    rets = [e["ret_pct"] for e in dirs]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    aw = float(np.mean(wins)) if wins else 0.0
    al = float(np.mean(losses)) if losses else 0.0
    return {"n": len(dirs),
            "win%": round(100 * len(wins) / len(dirs), 1),
            "avgW": round(aw, 2), "avgL": round(al, 2),
            "payoff": round(abs(aw / al), 2) if al else None,
            "exp/trade": round(float(np.mean(rets)), 2)}


def _stats(entries):
    dirs = [e for e in entries if e["side"] in ("long", "short")]
    out = {"n": len(dirs)}
    if dirs:
        rets = [e["ret_pct"] for e in dirs]
        out["win_pct"] = round(100 * sum(1 for r in rets if r > 0) / len(rets), 1)
        out["avg_ret"] = round(float(np.mean(rets)), 2)
        out["by_outcome"] = {o: sum(1 for e in dirs if e["outcome"] == o)
                             for o in ("target", "stop", "time")}
    neu = [e for e in entries if e["side"] == "neutral"]
    if neu:
        out["s3_n"] = len(neu)
        out["s3_held_pct"] = round(
            100 * sum(1 for e in neu if e["outcome"] == "held") / len(neu), 1)
    return out


def print_report(market, out_dir="docs"):
    open_e, resolved = _load(out_dir, market)
    print(f"# Forward ledger - {MARKETS[market]['label']}")
    print(f"open {len(open_e)} | resolved {len(resolved)}")
    if resolved:
        print("\n== By rule (directional; win%, avg win/loss, payoff, expectancy/trade) ==")
        allst = _stats2(resolved)
        if allst:
            print(f"ALL       : {allst}")
        for sig in sorted({e['signal'] for e in resolved}):
            st = _stats2([e for e in resolved if e['signal'] == sig])
            if st:
                print(f"{sig:<10}: {st}")
        primes = [e for e in resolved if e.get("prime")]
        pst = _stats2(primes)
        if pst:
            print(f"S4 PRIME  : {pst}")
        neu = [e for e in resolved if e["side"] == "neutral"]
        if neu:
            held = sum(1 for e in neu if e["outcome"] == "held")
            print(f"S3 neutral: n {len(neu)}, held {round(100 * held / len(neu), 1)}%")

        print("\n== Monthly drift (exit month; directional only) ==")
        months = {}
        for e in resolved:
            if e["side"] in ("long", "short") and e.get("exit_date"):
                months.setdefault(e["exit_date"][:7], []).append(e)
        for m in sorted(months):
            print(f"{m}  : {_stats2(months[m])}")

    if open_e:
        print("\n== Oldest open positions ==")
        aged = sorted(open_e, key=lambda e: e.get("entry_date", ""))[:10]
        for e in aged:
            print(f"  {e['entry_date']}  {e['ticker']:<10} {e['signal']}/{e['side']}"
                  f"  entry {e['entry_px']}  stop {e.get('stop')}  tgt {e.get('tgt')}"
                  f"  t{e.get('time_exit')}" + ("  PRIME" if e.get("prime") else ""))


def main():
    ap = argparse.ArgumentParser(description="Forward-ledger stats")
    ap.add_argument("--market", choices=list(MARKETS), default="us")
    ap.add_argument("--dir", default="docs")
    a = ap.parse_args()
    print_report(a.market, a.dir)


if __name__ == "__main__":
    main()
