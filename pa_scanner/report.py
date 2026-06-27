"""Self-contained HTML report. No external assets; opens in any browser."""
import datetime as dt
import html
import json


def _sparkline(closes, side, w=110, h=28, pad=2):
    if not closes or len(closes) < 2:
        return ""
    lo, hi = min(closes), max(closes)
    rng = (hi - lo) or 1.0
    n = len(closes)
    step = (w - 2 * pad) / (n - 1)
    pts = []
    for i, c in enumerate(closes):
        x = pad + i * step
        y = pad + (h - 2 * pad) * (1 - (c - lo) / rng)
        pts.append(f"{x:.1f},{y:.1f}")
    color = "#3fb950" if side == "long" else "#f85149"
    return (f"<svg width='{w}' height='{h}' viewBox='0 0 {w} {h}'>"
            f"<polyline fill='none' stroke='{color}' stroke-width='1.4' "
            f"points='{' '.join(pts)}'/></svg>")


def _enrich(rows):
    out = []
    for r in rows:
        d = dict(r)
        if r["signal"] == "S1":
            d["detail"] = r.get("pattern", "")
            d["dist"] = r.get("dist_atr", "")
            d["volx"] = ""
        else:
            d["detail"] = f"pullback {r.get('pullback_pct', '')}%"
            d["dist"] = r.get("breakout_atr", "")
            d["volx"] = r.get("volx", "")
        d["spark_svg"] = _sparkline(r.get("spark", []), r.get("side"))
        d.pop("spark", None)
        out.append(d)
    return out


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Price-Action Scan __DATE__</title>
<style>
 :root{--bg:#0d1117;--panel:#161b22;--bd:#30363d;--fg:#e6edf3;--mut:#8b949e;
   --grn:#3fb950;--red:#f85149;--accent:#58a6ff}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--fg);
   font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
 header{padding:16px 20px;border-bottom:1px solid var(--bd);display:flex;
   flex-wrap:wrap;align-items:baseline;gap:8px 18px}
 h1{font-size:15px;margin:0;font-weight:600;letter-spacing:.3px}
 .meta{color:var(--mut);font-size:12px}
 .bar{padding:12px 20px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;
   border-bottom:1px solid var(--bd)}
 .bar input{background:var(--panel);border:1px solid var(--bd);color:var(--fg);
   padding:6px 10px;border-radius:6px;font:inherit;min-width:200px}
 button{background:var(--panel);border:1px solid var(--bd);color:var(--fg);
   padding:6px 12px;border-radius:6px;cursor:pointer;font:inherit}
 button:hover{border-color:var(--accent)}
 button.on{background:var(--accent);color:#0d1117;border-color:var(--accent)}
 .spacer{flex:1}
 table{width:100%;border-collapse:collapse}
 th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--bd);
   white-space:nowrap}
 th{position:sticky;top:0;background:var(--panel);cursor:pointer;
   color:var(--mut);font-weight:600;user-select:none}
 th:hover{color:var(--fg)}
 td.num{text-align:right;font-variant-numeric:tabular-nums}
 tr:hover td{background:#1c2230}
 .tag{padding:1px 7px;border-radius:4px;font-size:11px;font-weight:600}
 .s1{background:#1f6feb33;color:#79c0ff} .s2{background:#a371f733;color:#d2a8ff}
 .long{color:var(--grn)} .short{color:var(--red)}
 .score{font-weight:600}
 a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
 .empty{padding:40px 20px;color:var(--mut)}
</style></head><body>
<header>
  <h1>PRICE-ACTION SCAN</h1>
  <span class="meta">__DATE__</span>
  <span class="meta">universe __UNIVERSE__ &middot; liquid __SCANNED__ &middot; signals __NHITS__</span>
</header>
<div class="bar">
  <input id="q" placeholder="filter ticker...">
  <button data-f="all" class="on">All</button>
  <button data-f="S1">S1 reversal</button>
  <button data-f="S2">S2 breakout</button>
  <button data-f="long">Long</button>
  <button data-f="short">Short</button>
  <span class="spacer"></span>
  <button id="csv">Export CSV</button>
</div>
<table id="t"><thead><tr>
  <th data-k="ticker">Ticker</th>
  <th data-k="signal">Sig</th>
  <th data-k="side">Side</th>
  <th data-k="score" class="num">Score</th>
  <th data-k="last" class="num">Last</th>
  <th data-k="level" class="num">Level</th>
  <th data-k="dist" class="num">Dist/Brk(ATR)</th>
  <th data-k="detail">Detail</th>
  <th data-k="volx" class="num">Vol&times;</th>
  <th data-k="atr" class="num">ATR</th>
  <th>Trend</th>
  <th>Chart</th>
</tr></thead><tbody id="b"></tbody></table>
<div id="empty" class="empty" style="display:none">No signals matched.</div>
<script>
const ROWS = __ROWS__;
let view = ROWS.slice(), sortK = "score", sortDir = -1, filt = "all", q = "";
const $ = s => document.querySelector(s);
function passes(r){
  if(q && !r.ticker.toLowerCase().includes(q)) return false;
  if(filt==="all") return true;
  if(filt==="S1"||filt==="S2") return r.signal===filt;
  return r.side===filt;
}
function render(){
  view = ROWS.filter(passes).sort((a,b)=>{
    let x=a[sortK], y=b[sortK];
    if(typeof x==="number"&&typeof y==="number") return (x-y)*sortDir;
    return String(x).localeCompare(String(y))*sortDir;
  });
  const tb=$("#b"); tb.innerHTML="";
  for(const r of view){
    const tr=document.createElement("tr");
    tr.innerHTML=
      `<td><b>${r.ticker}</b></td>`+
      `<td><span class="tag ${r.signal.toLowerCase()}">${r.signal}</span></td>`+
      `<td class="${r.side}">${r.side}</td>`+
      `<td class="num score">${r.score.toFixed(3)}</td>`+
      `<td class="num">${r.last}</td>`+
      `<td class="num">${r.level??""}</td>`+
      `<td class="num">${r.dist??""}</td>`+
      `<td>${r.detail??""}</td>`+
      `<td class="num">${r.volx??""}</td>`+
      `<td class="num">${r.atr}</td>`+
      `<td>${r.spark_svg}</td>`+
      `<td><a href="https://www.tradingview.com/chart/?symbol=${encodeURIComponent(r.ticker)}" target="_blank">TV</a></td>`;
    tb.appendChild(tr);
  }
  $("#empty").style.display = view.length? "none":"block";
}
document.querySelectorAll("th[data-k]").forEach(th=>th.onclick=()=>{
  const k=th.dataset.k;
  if(sortK===k) sortDir*=-1; else {sortK=k; sortDir=(k==="ticker"||k==="detail"||k==="side")?1:-1;}
  render();
});
document.querySelectorAll(".bar button[data-f]").forEach(btn=>btn.onclick=()=>{
  filt=btn.dataset.f;
  document.querySelectorAll(".bar button[data-f]").forEach(b=>b.classList.remove("on"));
  btn.classList.add("on"); render();
});
$("#q").oninput=e=>{q=e.target.value.trim().toLowerCase(); render();};
$("#csv").onclick=()=>{
  const cols=["ticker","signal","side","score","last","level","dist","detail","volx","atr","label"];
  const head=cols.join(",");
  const lines=view.map(r=>cols.map(c=>{
    let v=r[c]; if(v==null) v=""; v=String(v).replace(/"/g,'""');
    return /[",\\n]/.test(v)? '"'+v+'"': v;
  }).join(","));
  const blob=new Blob([head+"\\n"+lines.join("\\n")],{type:"text/csv"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download="pa_scan_"+"__DATESTAMP__"+".csv"; a.click();
};
render();
</script></body></html>"""


def write_report(rows, path, scanned=0, universe=0):
    enriched = _enrich(rows)
    now = dt.datetime.now()
    html_out = (_TEMPLATE
                .replace("__ROWS__", json.dumps(enriched))
                .replace("__DATE__", now.strftime("%Y-%m-%d %H:%M"))
                .replace("__DATESTAMP__", now.strftime("%Y%m%d_%H%M"))
                .replace("__UNIVERSE__", str(universe))
                .replace("__SCANNED__", str(scanned))
                .replace("__NHITS__", str(len(rows))))
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_out)
    return path
