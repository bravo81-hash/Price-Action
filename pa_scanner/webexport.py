"""Export scan results as JSON for the static GitHub Pages dashboard.

Per market (us | asx | in) writes, with suffix "" for US and "_<mkt>" otherwise:
  <out_dir>/data/latest<suffix>.json   most recent scan for that market
  <out_dir>/data/<YYYY-MM-DD><suffix>.json   dated snapshot (history)
  <out_dir>/data/index<suffix>.json    list of available snapshot dates
  <out_dir>/.nojekyll                  so Pages serves files verbatim
US filenames are unsuffixed for backwards compatibility.
"""
import datetime as dt
import glob
import json
import os
import tempfile

from .config import MARKETS


def _row(r: dict) -> dict:
    d = {k: r.get(k) for k in
          ("ticker", "signal", "signal_name", "side", "score", "rank", "prime", "last", "atr", "atr_pct",
           "rs", "rs_pct", "age", "ern", "ern_status", "stop", "tgt", "time_exit", "label", "level",
           "range_lo", "range_hi",
           "qty", "evidence_tier", "evidence_reason", "evidence_rank",
          # options (US) fields
          "regime", "regime_adx", "align", "vol_state", "vol_src", "cell", "structure",
          "ivr", "iv", "rv", "vrp", "term", "live", "live_status", "live_dist",
          "opt_liq", "opt_oi", "opt_spread",
          # directional (ASX / India) fields
          "trend", "trend_adx", "trigger", "action", "action_note", "action_tier")}
    if r.get("signal") == "S1":
        d["detail"] = r.get("pattern", "")
        d["dist"] = r.get("dist_atr", "")
        d["volx"] = ""
    elif r.get("signal") == "S2":
        d["detail"] = f"pullback {r.get('pullback_pct', '')}%"
        d["dist"] = r.get("breakout_atr", "")
        d["volx"] = r.get("volx", "")
    elif r.get("signal") == "S4":
        d["detail"] = r.get("label", "")
        d["dist"] = r.get("dist_atr", "")
        d["volx"] = ""
    else:  # S3 range / chop
        d["detail"] = r.get("label", "")
        d["dist"] = ""
        d["volx"] = ""
    d["spark"] = r.get("spark", [])
    return d


FVS_FEED_SCHEMA_VERSION = 1
FVS_FEED_FIELDS = (
    "ticker", "signal", "signal_name", "side", "score", "rank", "last", "atr",
    "rs_pct", "age", "ern", "ern_status", "level", "range_lo", "range_hi",
    "evidence_tier", "evidence_reason", "evidence_rank", "regime", "align",
)


def build_fvs_feed(rows, *, generated, bench=None) -> dict:
    """Build the compact, context-only contract consumed by Forward-Vol-Scanner."""
    compact_rows = []
    for source in rows:
        row = {key: source.get(key) for key in FVS_FEED_FIELDS}
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        row["ticker"] = ticker
        compact_rows.append(row)
    snap = (bench or {}).get("snap") or {}
    board = (bench or {}).get("board") or {}
    compact_bench = {
        "symbol": (bench or {}).get("symbol"),
        "bias": (bench or {}).get("bias"),
        "adx": (bench or {}).get("adx"),
        "state": snap.get("state"),
        "guidance": snap.get("guidance"),
        "evidence_asof": board.get("asof"),
    }
    return {
        "schema_version": FVS_FEED_SCHEMA_VERSION,
        "source": "bravo81-hash/Price-Action",
        "market": "us",
        "authority": "context_only",
        "generated": generated,
        "count": len(compact_rows),
        "bench": compact_bench,
        "rows": compact_rows,
    }


def _write_json_atomic(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".fvs-feed-", suffix=".json",
                               dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def write_fvs_feed(rows, out_dir="docs", *, generated, bench=None) -> str:
    path = os.path.join(out_dir, "data", "fvs_feed.json")
    _write_json_atomic(path, build_fvs_feed(rows, generated=generated, bench=bench))
    return path


def write_web(rows, out_dir="docs", scanned=0, universe=0, keep=60, note=None, market="us", bench=None):
    mkt = MARKETS[market]
    suffix = "" if market == "us" else f"_{market}"
    data_dir = os.path.join(out_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)

    payload = {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "market": market,
        "mode": mkt["mode"],
        "label": mkt["label"],
        "ccy": mkt["ccy"],
        "tv": mkt["tv"],
        "universe": universe,
        "scanned": scanned,
        "count": len(rows),
        "rows": [_row(r) for r in rows],
    }
    if note:
        payload["note"] = note
    if bench:
        payload["bench"] = bench

    if market == "us":
        write_fvs_feed(payload["rows"], out_dir, generated=payload["generated"], bench=bench)

    date = now.strftime("%Y-%m-%d")
    blob = json.dumps(payload, separators=(",", ":"))
    with open(os.path.join(data_dir, f"{date}{suffix}.json"), "w", encoding="utf-8") as f:
        f.write(blob)
    with open(os.path.join(data_dir, f"latest{suffix}.json"), "w", encoding="utf-8") as f:
        f.write(blob)

    # dated snapshots for THIS market only (US = unsuffixed, others = _<mkt>)
    if market == "us":
        dated = [f for f in glob.glob(os.path.join(data_dir, "20*.json"))
                 if "_" not in os.path.basename(f)]
    else:
        dated = glob.glob(os.path.join(data_dir, f"20*{suffix}.json"))
    for old in sorted(dated)[:-keep]:
        os.remove(old)
    # Build the index from files that still exist after retention; the old code
    # listed just-deleted snapshots until the following scan.
    keep_dates = sorted((f for f in dated if os.path.exists(f)), reverse=True)
    n = len(suffix) + 5  # strip "<suffix>.json"
    snapshots = [os.path.basename(f)[:-n] for f in keep_dates]
    with open(os.path.join(data_dir, f"index{suffix}.json"), "w", encoding="utf-8") as f:
        json.dump({"snapshots": snapshots}, f)

    open(os.path.join(out_dir, ".nojekyll"), "a").close()
    return os.path.join(data_dir, f"latest{suffix}.json")
