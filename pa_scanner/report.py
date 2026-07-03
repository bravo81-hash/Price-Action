"""Self-contained HTML report. No external assets; opens in any browser.

Two layouts, chosen by market mode:
  options     (US)        — Side / Vol / Structure / Live columns (unchanged)
  directional (ASX/India) — Action / Trend / Trigger columns, long-only
"""
import datetime as dt
import json

from .config import CFG, MARKETS


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
        elif r["signal"] == "S2":
            d["detail"] = f"pullback {r.get('pullback_pct', '')}%"
            d["dist"] = r.get("breakout_atr", "")
            d["volx"] = r.get("volx", "")
        else:  # S3 range / chop
            d["detail"] = r.get("label", "")
            d["dist"] = ""
            d["volx"] = ""
        d["spark_svg"] = _sparkline(r.get("spark", []), r.get("side"))
        d.pop("spark", None)
        out.append(d)
    return out


_HEAD_OPTIONS = """
  <th data-k="ticker">Ticker</th>
  <th data-k="signal">Sig</th>
  <th data-k="side">Side</th>
  <th data-k="rank" class="num">Rank</th>
  <th data-k="score" class="num">Score</th>
  <th data-k="last" class="num">Last</th>
  <th data-k="live" class="num">Live</th>
  <th data-k="level" class="num">Level</th>
  <th data-k="dist" class="num">Dist/Brk(ATR)</th>
  <th data-k="age" class="num">Age</th>
  <th data-k="stop" class="num">Stop</th>
  <th data-k="tgt" class="num">Tgt</th>
  <th data-k="detail">Detail</th>
  <th data-k="volx" class="num">Vol&times;</th>
  <th data-k="atr" class="num">ATR</th>
  <th data-k="atr_pct" class="num">ATR%</th>
  <th data-k="rs_pct" class="num">RS</th>
  <th data-k="ern" class="num">Ern(d)</th>
  <th data-k="regime">Regime</th>
  <th data-k="vol_state">Vol</th>
  <th data-k="structure">Structure</th>
  <th data-k="opt_liq">Opt Liq</th>
  <th>Trend</th>
  <th>Chart</th>"""

_HEAD_DIRECTIONAL = """
  <th data-k="ticker">Ticker</th>
  <th data-k="action">Action</th>
  <th data-k="trend">Weekly Trend</th>
  <th data-k="signal">Sig</th>
  <th data-k="trigger">Trigger</th>
  <th data-k="rank" class="num">Rank</th>
  <th data-k="score" class="num">Score</th>
  <th data-k="last" class="num">Last</th>
  <th data-k="atr_pct" class="num">ATR%</th>
  <th data-k="rs_pct" class="num">RS</th>
  <th data-k="level" class="num">Level</th>
  <th data-k="dist" class="num">Dist/Brk(ATR)</th>
  <th data-k="age" class="num">Age</th>
  <th data-k="stop" class="num">Stop</th>
  <th data-k="tgt" class="num">Tgt</th>
  <th data-k="detail">Detail</th>
  <th>Chart</th>"""

_FILTERS_OPTIONS = """
  <button data-f="all" class="on">All</button>
  <button data-f="S1">S1 reversal</button>
  <button data-f="S2">S2 breakout</button>
  <button data-f="S3">S3 chop</button>
  <button data-f="long">Long</button>
  <button data-f="short">Short</button>
  <button data-f="neutral">Neutral</button>
  <button data-f="rs">RS&gt;50</button>
  <button data-f="ern">Ern OK</button>"""

_FILTERS_DIRECTIONAL = """
  <button data-f="all" class="on">All</button>
  <button data-f="buy">Buy</button>
  <button data-f="hold">Hold</button>
  <button data-f="exit">Exit / Trim</button>
  <button data-f="avoid">Avoid / Watch</button>
  <button data-f="S1">S1</button>
  <button data-f="S2">S2</button>
  <button data-f="S3">S3</button>
  <button data-f="rs">RS&gt;50</button>"""


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ __DATE__</title>
<style>
 :root{--bg:#0d1117;--panel:#161b22;--bd:#30363d;--fg:#e6edf3;--mut:#8b949e;
   --grn:#3fb950;--red:#f85149;--amb:#d29922;--accent:#58a6ff}
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
 .s3{background:#8b949e33;color:#c9d1d9}
 .long{color:var(--grn)} .short{color:var(--red)}
 .bullish{color:var(--grn)} .bearish{color:var(--red)} .neutral{color:var(--mut)}
 .src{color:var(--mut);font-size:10px;text-transform:uppercase}
 .dc-D{color:#79c0ff} .dc-C{color:#d2a8ff}
 .score{font-weight:600}
 a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
 .empty{padding:40px 20px;color:var(--mut)}
</style></head><body>
<header>
  <h1>__TITLE__</h1>
  <span class="meta">__DATE__</span>
  <span class="meta">universe __UNIVERSE__ &middot; liquid __SCANNED__ &middot; signals __NHITS__</span>
  <span class="meta">__BENCH__</span>
</header>
<div class="bar">
  <input id="q" placeholder="filter ticker...">__FILTERS__
  <span class="spacer"></span>
  <button id="csv">Export CSV</button>
</div>
<table id="t"><thead><tr>__HEAD__</tr></thead><tbody id="b"></tbody></table>
<div id="empty" class="empty" style="display:none">No signals matched.</div>
<script>
const ROWS = __ROWS__;
const MODE = "__MODE__";        // "options" | "directional"
const TVP  = "__TV__";          // TradingView exchange prefix (ASX / NSE), "" for US
let view = ROWS.slice(), sortK = "rank", sortDir = -1, filt = "all", q = "";
const $ = s => document.querySelector(s);
function dispSym(t){ return MODE==="options" ? t : t.replace(/\\.(AX|NS)$/,''); }
function tvSym(t){ return TVP ? (TVP+":"+dispSym(t)) : t; }

/* ---------- options (US) cells ---------- */
const REG={bullish:'Bull',bearish:'Bear',neutral:'Neut'};
function regCell(r){
  if(!r.regime) return "";
  const A={with:['\\u2197 with','#3fb950'],counter:['\\u26a0 counter','#d29922']}, a=A[r.align];
  const tag=a? ` <span class="src" style="color:${a[1]}">${a[0]}</span>`:'';
  return `<span class="${r.regime}">${REG[r.regime]||r.regime}</span> <span class="src">ADX ${r.regime_adx??''}</span>${tag}`;
}
function volTitle(r){
  const f=[];
  if(r.ivr!=null) f.push("IVR "+r.ivr);
  if(r.iv!=null) f.push("IV "+r.iv);
  if(r.rv!=null) f.push("RV "+r.rv);
  if(r.vrp!=null) f.push("VRP "+(r.vrp>0?"+":"")+r.vrp);
  if(r.term!=null) f.push("term "+(r.term>0?"+":"")+r.term);
  return f.join(" \\u00b7 ") || "no IV data";
}
function volCell(r){ if(!r.vol_state) return ""; return `${r.vol_state} <span class="src">${r.vol_src||''}</span>`; }
function liveCell(r){
  if(r.live==null) return "";
  const S={'triggered':'#3fb950','pending':'#d29922','at level':'#58a6ff','in range':'#8b949e','broke out':'#d29922','away':'#8b949e'};
  const c=S[r.live_status]||'#c9d1d9';
  const st=r.live_status?` <span class="src" style="color:${c}">${r.live_status}</span>`:'';
  const lbl=(r.live_status==='in range'||r.live_status==='broke out')?'pos':'\\u0394';
  const d=(r.live_dist!=null)?` <span class="src">${lbl} ${r.live_dist}</span>`:'';
  return `${r.live}${st}${d}`;
}
function structCell(r){
  if(!r.structure) return "";
  const m=String(r.structure).match(/\\((\\w)\\)$/), dc=m?m[1]:'';
  return `<span class="dc-${dc}">${r.structure}</span>`;
}
function optLiqCell(r){
  if(!r.opt_liq) return "";
  const c = r.opt_liq==="ok" ? "#3fb950" : "#d29922";
  const oi = r.opt_oi!=null ? "OI "+r.opt_oi : "";
  const sp = r.opt_spread!=null ? (oi?" \u00b7 ":"")+"sprd "+r.opt_spread+"%" : "";
  return `<b style="color:${c}">${r.opt_liq.toUpperCase()}</b> <span class="src">${oi}${sp}</span>`;
}
function rsCell(r){
  if(r.rs_pct==null) return "";
  const c = r.rs_pct>=70 ? "#3fb950" : (r.rs_pct<=30 ? "#f85149" : "#c9d1d9");
  const t = (r.rs!=null)? ((r.rs>0?"+":"")+r.rs+"% vs bench") : "";
  return `<span style="color:${c}" title="${t}">${r.rs_pct}</span>`;
}
function ernCell(r){
  if(r.ern==null) return "";
  return r.ern<=__ERNWARN__ ? `<b style="color:#d29922">${r.ern}</b>` : `${r.ern}`;
}
/* ---------- directional (ASX/India) cells ---------- */
function actionCell(r){
  const T={pos:'#3fb950',warn:'#d29922',exit:'#f85149'};
  const c=T[r.action_tier]||'#c9d1d9';
  const note=r.action_note? ` <span class="src">${r.action_note}</span>`:'';
  return `<b style="color:${c}">${r.action||''}</b>${note}`;
}
function trendCell(r){
  const T={up:'#3fb950',flat:'#8b949e',down:'#f85149'};
  return `<span style="color:${T[r.trend]||'#c9d1d9'}">${(r.trend||'').toUpperCase()}</span> <span class="src">ADX ${r.trend_adx??''}</span>`;
}

function rowHTML(r){
  const head=`<td><b>${dispSym(r.ticker)}</b></td>`;
  const tv=`<td><a href="https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSym(r.ticker))}" target="_blank">TV</a></td>`;
  if(MODE==="directional"){
    return head+
      `<td>${actionCell(r)}</td>`+
      `<td>${trendCell(r)}</td>`+
      `<td><span class="tag ${r.signal.toLowerCase()}">${r.signal}</span></td>`+
      `<td class="${r.trigger}">${r.trigger||''}</td>`+
      `<td class="num">${r.rank??""}</td>`+
      `<td class="num score">${r.score.toFixed(3)}</td>`+
      `<td class="num">${r.last}</td>`+
      `<td class="num">${r.atr_pct??""}</td>`+
      `<td class="num">${rsCell(r)}</td>`+
      `<td class="num">${r.level??""}</td>`+
      `<td class="num">${r.dist??""}</td>`+
      `<td class="num">${r.age??""}</td>`+
      `<td class="num">${r.stop??""}</td>`+
      `<td class="num">${r.tgt??""}</td>`+
      `<td>${r.detail??""}</td>`+
      `<td>${r.spark_svg}</td>`+tv;
  }
  return head+
    `<td><span class="tag ${r.signal.toLowerCase()}">${r.signal}</span></td>`+
    `<td class="${r.side}">${r.side}</td>`+
    `<td class="num">${r.rank??""}</td>`+
    `<td class="num score">${r.score.toFixed(3)}</td>`+
    `<td class="num">${r.last}</td>`+
    `<td class="num">${liveCell(r)}</td>`+
    `<td class="num">${r.level??""}</td>`+
    `<td class="num">${r.dist??""}</td>`+
    `<td class="num">${r.age??""}</td>`+
    `<td class="num">${r.stop??""}</td>`+
    `<td class="num">${r.tgt??""}</td>`+
    `<td>${r.detail??""}</td>`+
    `<td class="num">${r.volx??""}</td>`+
    `<td class="num">${r.atr}</td>`+
    `<td class="num">${r.atr_pct??""}</td>`+
    `<td class="num">${rsCell(r)}</td>`+
    `<td class="num">${ernCell(r)}</td>`+
    `<td>${regCell(r)}</td>`+
    `<td title="${volTitle(r)}">${volCell(r)}</td>`+
    `<td>${structCell(r)}</td>`+
    `<td>${optLiqCell(r)}</td>`+
    `<td>${r.spark_svg}</td>`+tv;
}

function passes(r){
  if(q && !dispSym(r.ticker).toLowerCase().includes(q) && !r.ticker.toLowerCase().includes(q)) return false;
  if(filt==="all") return true;
  if(filt==="S1"||filt==="S2"||filt==="S3") return r.signal===filt;
  if(filt==="rs") return r.rs_pct!=null && r.rs_pct>50;
  if(filt==="ern") return r.ern==null || r.ern>__ERNWARN__;
  if(MODE==="directional"){
    if(filt==="buy")   return r.action==="BUY";
    if(filt==="hold")  return r.action==="HOLD";
    if(filt==="exit")  return r.action==="EXIT"||r.action==="REDUCE";
    if(filt==="avoid") return r.action==="AVOID"||r.action==="WATCH";
    return true;
  }
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
    tr.innerHTML=rowHTML(r);
    tb.appendChild(tr);
  }
  $("#empty").style.display = view.length? "none":"block";
}
document.querySelectorAll("th[data-k]").forEach(th=>th.onclick=()=>{
  const k=th.dataset.k;
  if(sortK===k) sortDir*=-1; else {sortK=k; sortDir=(k==="ticker"||k==="detail"||k==="side"||k==="action"||k==="trend"||k==="trigger")?1:-1;}
  render();
});
document.querySelectorAll(".bar button[data-f]").forEach(btn=>btn.onclick=()=>{
  filt=btn.dataset.f;
  document.querySelectorAll(".bar button[data-f]").forEach(b=>b.classList.remove("on"));
  btn.classList.add("on"); render();
});
$("#q").oninput=e=>{q=e.target.value.trim().toLowerCase(); render();};
$("#csv").onclick=()=>{
  const cols = MODE==="directional"
    ? ["ticker","action","action_note","trend","trend_adx","signal","trigger","side","rank","score","last","atr","atr_pct","rs","rs_pct","level","dist","age","stop","tgt","time_exit","detail","label"]
    : ["ticker","signal","side","rank","score","last","live","live_status","live_dist","level","dist","age","stop","tgt","time_exit","detail","volx","atr","atr_pct","rs","rs_pct","ern",
       "regime","regime_adx","align","vol_state","vol_src","cell","structure","ivr","iv","rv","vrp","term","opt_liq","opt_oi","opt_spread","label"];
  const head=cols.join(",");
  const lines=view.map(r=>cols.map(c=>{
    let v=r[c]; if(v==null) v=""; v=String(v).replace(/"/g,'""');
    return /[",\\n]/.test(v)? '"'+v+'"': v;
  }).join(","));
  const blob=new Blob([head+"\\n"+lines.join("\\n")],{type:"text/csv"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download="pa_scan___MKT___"+"__DATESTAMP__"+".csv"; a.click();
};
render();
</script></body></html>"""


def write_report(rows, path, scanned=0, universe=0, market="us", bench=None):
    mkt = MARKETS[market]
    directional = mkt["mode"] == "directional"
    enriched = _enrich(rows)
    now = dt.datetime.now()
    title = f"PRICE-ACTION SCAN \u2014 {mkt['label']}"
    head = _HEAD_DIRECTIONAL if directional else _HEAD_OPTIONS
    filters = _FILTERS_DIRECTIONAL if directional else _FILTERS_OPTIONS
    html_out = (_TEMPLATE
                .replace("__ROWS__", json.dumps(enriched))
                .replace("__HEAD__", head)
                .replace("__FILTERS__", filters)
                .replace("__MODE__", mkt["mode"])
                .replace("__ERNWARN__", str(CFG.earnings_warn_days))
                .replace("__BENCH__",
                         ((f"{bench['symbol']}: {bench['bias'].upper()} (ADX {bench['adx']})"
                           + ("  \u26a0 STAND-DOWN: bench bearish; 5y study = -0.63% excess on all signals (t=-4.0)"
                              if CFG.bench_standdown and bench["bias"] == "bearish" else ""))
                          if bench else ""))
                .replace("__TV__", mkt["tv"])
                .replace("__TITLE__", title)
                .replace("__MKT__", market)
                .replace("__DATE__", now.strftime("%Y-%m-%d %H:%M"))
                .replace("__DATESTAMP__", now.strftime("%Y%m%d_%H%M"))
                .replace("__UNIVERSE__", str(universe))
                .replace("__SCANNED__", str(scanned))
                .replace("__NHITS__", str(len(rows))))
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_out)
    return path
