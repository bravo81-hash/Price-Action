"""Export scan results as JSON for the static GitHub Pages dashboard.

Writes:
  <out_dir>/data/latest.json      most recent scan (default the dashboard loads)
  <out_dir>/data/<YYYY-MM-DD>.json dated snapshot (history)
  <out_dir>/data/index.json       list of available snapshot dates
  <out_dir>/.nojekyll             so Pages serves files verbatim
"""
import datetime as dt
import glob
import json
import os


def _row(r: dict) -> dict:
    d = {k: r.get(k) for k in
         ("ticker", "signal", "signal_name", "side", "score", "last", "atr", "label", "level")}
    if r.get("signal") == "S1":
        d["detail"] = r.get("pattern", "")
        d["dist"] = r.get("dist_atr", "")
        d["volx"] = ""
    else:
        d["detail"] = f"pullback {r.get('pullback_pct', '')}%"
        d["dist"] = r.get("breakout_atr", "")
        d["volx"] = r.get("volx", "")
    d["spark"] = r.get("spark", [])
    return d


def write_web(rows, out_dir="docs", scanned=0, universe=0, keep=60, note=None):
    data_dir = os.path.join(out_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)

    payload = {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe": universe,
        "scanned": scanned,
        "count": len(rows),
        "rows": [_row(r) for r in rows],
    }
    if note:
        payload["note"] = note

    date = now.strftime("%Y-%m-%d")
    blob = json.dumps(payload, separators=(",", ":"))
    with open(os.path.join(data_dir, f"{date}.json"), "w", encoding="utf-8") as f:
        f.write(blob)
    with open(os.path.join(data_dir, "latest.json"), "w", encoding="utf-8") as f:
        f.write(blob)

    # prune old snapshots, then rebuild the index (newest first)
    dated = sorted(glob.glob(os.path.join(data_dir, "20*.json")))
    for old in dated[:-keep]:
        os.remove(old)
    dated = sorted(glob.glob(os.path.join(data_dir, "20*.json")), reverse=True)
    snapshots = [os.path.basename(f)[:-5] for f in dated]
    with open(os.path.join(data_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"snapshots": snapshots}, f)

    open(os.path.join(out_dir, ".nojekyll"), "a").close()
    return os.path.join(data_dir, "latest.json")
