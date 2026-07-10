"""Self-contained HTML report. No external assets; opens in any browser.

Two layouts, chosen by market mode:
  options     (US)        - full options/vol column set
  directional (ASX/India) - Action / Trend / Trigger long-only set
Columns are quality-weighted by default (decision -> execution -> context) and
user-adjustable: drag headers to reorder, drag header edges to resize, hide or
show via the Cols panel, Reset restores defaults. Preferences persist per
layout in localStorage.
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
        elif r["signal"] == "S4":
            d["detail"] = r.get("label", "")
            d["dist"] = r.get("dist_atr", "")
            d["volx"] = ""
        else:  # S3 range / chop
            d["detail"] = r.get("label", "")
            d["dist"] = ""
            d["volx"] = ""
        d["spark_svg"] = _sparkline(r.get("spark", []), r.get("side"))
        d.pop("spark", None)
        out.append(d)
    return out


_FILTERS_OPTIONS = """
  <button data-f="all" class="on">All</button>
  <button data-f="S1">S1 reversal</button>
  <button data-f="S2">S2 breakout</button>
  <button data-f="S3">S3 chop</button>
  <button data-f="S4">S4 snapback</button>
  <button data-f="prime">S4&#9733; Prime</button>
  <button data-f="long">Long</button>
  <button data-f="short">Short</button>
  <button data-f="neutral">Neutral</button>
  <button data-f="rs">RS&gt;50</button>
  <button data-f="ern">Ern safe</button>"""

_FILTERS_DIRECTIONAL = """
  <button data-f="all" class="on">All</button>
  <button data-f="buy">Buy</button>
  <button data-f="hold">Hold</button>
  <button data-f="exit">Exit / Trim</button>
  <button data-f="avoid">Avoid / Watch</button>
  <button data-f="S1">S1</button>
  <button data-f="S2">S2</button>
  <button data-f="S3">S3</button>
  <button data-f="S4">S4</button>
  <button data-f="prime">S4&#9733;</button>
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
   border-bottom:1px solid var(--bd);position:relative}
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
 th .rz{position:absolute;right:0;top:0;width:7px;height:100%;cursor:col-resize}
 th{position:sticky;position:sticky}
 th{overflow:hidden}
 th{position:sticky}
 td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
 tr:hover td{background:#1c2230}
 .tag{padding:1px 7px;border-radius:4px;font-size:11px;font-weight:600}
 .s1{background:#1f6feb33;color:#79c0ff} .s2{background:#a371f733;color:#d2a8ff}
 .s3{background:#8b949e33;color:#c9d1d9} .s4{background:#2ea04333;color:#7ee787}
 .prime{background:#f0c00033;color:#f0c000;font-weight:700}
 .long{color:var(--grn)} .short{color:var(--red)}
 .bullish{color:var(--grn)} .bearish{color:var(--red)} .neutral{color:var(--mut)}
 .src{color:var(--mut);font-size:10px;text-transform:uppercase}
 .dc-D{color:#79c0ff} .dc-C{color:#d2a8ff}
 .score{font-weight:600}
 a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
 .empty{padding:40px 20px;color:var(--mut)}
 .colpanel{display:none;position:absolute;top:100%;right:20px;z-index:30;
   background:var(--panel);border:1px solid var(--bd);border-radius:8px;
   padding:10px 14px;max-height:60vh;overflow:auto;box-shadow:0 8px 24px #0008}
 .colpanel label{display:block;margin:4px 0;color:#c9d1d9;cursor:pointer}
  .colpanel .rst{margin-top:8px;width:100%}
 .board{padding:12px 20px;border-bottom:1px solid var(--bd);display:flex;
   flex-wrap:wrap;gap:8px;align-items:stretch}
 .board .bhdr{width:100%;color:var(--mut);font-size:11px;text-transform:uppercase;
   letter-spacing:.5px;margin-bottom:2px}
 .bcard{background:var(--panel);border:1px solid var(--bd);border-left-width:3px;
   border-radius:6px;padding:7px 11px;min-width:190px;flex:1 1 190px}
 .bcard .top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
 .bcard .nm{font-weight:600}
 .bcard .tier{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px}
 .bcard .rz2{color:var(--mut);font-size:11px;margin-top:3px;white-space:normal;line-height:1.35}
 .bcard .alt{color:var(--accent);font-size:11px;margin-top:2px}
 .bcard .hh{color:var(--mut);font-size:11px}
</style></head><body>
<header>
  <h1>__TITLE__</h1>
  <span class="meta">__DATE__</span>
  <span class="meta">universe __UNIVERSE__ &middot; liquid __SCANNED__ &middot; signals __NHITS__</span>
  <span class="meta">__BENCH__</span>
</header>
<div class="board" id="board"></div>
<div class="bar">
  <input id="q" placeholder="filter ticker...">__FILTERS__
  <span class="spacer"></span>
  <button id="colsBtn">Cols &#9662;</button>
  <button id="csv">Export CSV</button>
  <div class="colpanel" id="colPanel"></div>
</div>
<table id="t"><thead><tr id="hr"></tr></thead><tbody id="b"></tbody></table>
<div id="empty" class="empty" style="display:none">No signals matched.</div>
<script>
const ROWS = __ROWS__;
const MODE = "__MODE__";        // "options" | "directional"
const TVP  = "__TV__";          // TradingView exchange prefix, "" for US
const ERNWARN = __ERNWARN__;
const BOARD = __BOARD__;
let view = ROWS.slice(), sortK = "rank", sortDir = -1, filt = "all", q = "";
const $ = s => document.querySelector(s);
function dispSym(t){ return MODE==="options" ? t : t.replace(/\\.(AX|NS)$/,''); }
function tvSym(t){ return TVP ? (TVP+":"+dispSym(t)) : t; }

/* ---------- cells ---------- */
const REG={bullish:'Bull',bearish:'Bear',neutral:'Neut'};
function sigCell(r){return `<span class="tag ${r.prime?"prime":String(r.signal).toLowerCase()}">${r.signal}${r.prime?"\\u2605":""}</span>`;}
function sideCell(r){return `<span class="${r.side}">${r.side}</span>`;}
function regCell(r){
  if(!r.regime) return "";
  const A={with:['\\u2197 with','#3fb950'],counter:['\u26a0 counter','#d29922']}, a=A[r.align];
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
  return f.join(" \u00b7 ") || "no IV data";
}
function volCell(r){ if(!r.vol_state) return ""; return `<span title="${volTitle(r)}">${r.vol_state} <span class="src">${r.vol_src||''}</span></span>`; }
function liveCell(r){
  if(r.live==null) return "";
  const S={'triggered':'#3fb950','pending':'#d29922','at level':'#58a6ff','in range':'#8b949e','broke out':'#d29922','away':'#8b949e','reclaimed':'#3fb950','below MA':'#d29922'};
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
  if(r.ern==null){
    return r.ern_status==="unknown" ? `<span class="src" style="color:#d29922" title="earnings date unknown - not confirmed safe">?</span>` : "";
  }
  if(r.ern_status==="inside") return `<b style="color:#f85149" title="earnings inside the intended tenor">${r.ern}</b>`;
  if(r.ern_status==="unknown") return `<span style="color:#d29922">${r.ern}?</span>`;
  return `<span title="clears the tenor">${r.ern}</span>`;
}
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
function tvCell(r){return `<a href="https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSym(r.ticker))}" target="_blank">TV</a>`;}
const scoreCell=r=>`<span class="score">${Number(r.score).toFixed(3)}</span>`;
const tickCell=r=>`<b>${dispSym(r.ticker)}</b>`;
const sparkCell=r=>r.spark_svg||"";

/* ---------- column model (quality-weighted defaults) ---------- */
const COLS = {
 options:[
  {k:"ticker",l:"Ticker",cell:tickCell},
  {k:"signal",l:"Sig",cell:sigCell},
  {k:"side",l:"Side",cell:sideCell},
  {k:"rank",l:"Rank",cls:"num"},
  {k:"rs_pct",l:"RS",cls:"num",cell:rsCell},
  {k:"vol_state",l:"Vol",cell:volCell},
  {k:"ern",l:"Ern(d)",cls:"num",cell:ernCell},
  {k:"age",l:"Age",cls:"num"},
  {k:"score",l:"Score",cls:"num",cell:scoreCell},
  {k:"live",l:"Live",cls:"num",cell:liveCell},
  {k:"last",l:"Last",cls:"num"},
  {k:"stop",l:"Stop",cls:"num"},
  {k:"tgt",l:"Tgt",cls:"num"},
  {k:"qty",l:"Qty",cls:"num"},
  {k:"level",l:"Level",cls:"num"},
  {k:"dist",l:"Dist/Brk(ATR)",cls:"num"},
  {k:"structure",l:"Structure",cell:structCell},
  {k:"regime",l:"Regime",cell:regCell},
  {k:"opt_liq",l:"Opt Liq",cell:optLiqCell},
  {k:"volx",l:"Vol\\u00d7",cls:"num"},
  {k:"atr",l:"ATR",cls:"num"},
  {k:"atr_pct",l:"ATR%",cls:"num"},
  {k:"detail",l:"Detail"},
  {k:"spark",l:"Chart",cell:sparkCell,nosort:true},
  {k:"tv",l:"TV",cell:tvCell,nosort:true}],
 directional:[
  {k:"ticker",l:"Ticker",cell:tickCell},
  {k:"action",l:"Action",cell:actionCell},
  {k:"signal",l:"Sig",cell:sigCell},
  {k:"rank",l:"Rank",cls:"num"},
  {k:"rs_pct",l:"RS",cls:"num",cell:rsCell},
  {k:"trend",l:"Weekly Trend",cell:trendCell},
  {k:"trigger",l:"Trigger",cell:r=>`<span class="${r.trigger}">${r.trigger||''}</span>`},
  {k:"score",l:"Score",cls:"num",cell:scoreCell},
  {k:"live",l:"Live",cls:"num",cell:liveCell},
  {k:"last",l:"Last",cls:"num"},
  {k:"stop",l:"Stop",cls:"num"},
  {k:"tgt",l:"Tgt",cls:"num"},
  {k:"qty",l:"Qty",cls:"num"},
  {k:"age",l:"Age",cls:"num"},
  {k:"atr_pct",l:"ATR%",cls:"num"},
  {k:"level",l:"Level",cls:"num"},
  {k:"dist",l:"Dist/Brk(ATR)",cls:"num"},
  {k:"detail",l:"Detail"},
  {k:"spark",l:"Chart",cell:sparkCell,nosort:true},
  {k:"tv",l:"TV",cell:tvCell,nosort:true}]
};

/* ---------- prefs: order / hidden / widths, persisted per layout ---------- */
function prefKey(){return "paCols."+MODE;}
let prefs={order:null,hidden:[],widths:{}};
function loadPrefs(){
  try{const p=JSON.parse(localStorage.getItem(prefKey()));if(p)prefs={order:p.order||null,hidden:p.hidden||[],widths:p.widths||{}};}catch(e){}
}
function savePrefs(){try{localStorage.setItem(prefKey(),JSON.stringify(prefs));}catch(e){}}
function resetPrefs(){try{localStorage.removeItem(prefKey());}catch(e){} prefs={order:null,hidden:[],widths:{}};}
function allCols(){return COLS[MODE];}
function orderedCols(){
  const defs=allCols(), byK={}; defs.forEach(c=>byK[c.k]=c);
  let ord=(prefs.order||defs.map(c=>c.k)).filter(k=>byK[k]);
  defs.forEach(c=>{if(!ord.includes(c.k))ord.push(c.k);});
  return ord.map(k=>byK[k]);
}
function visibleCols(){return orderedCols().filter(c=>!prefs.hidden.includes(c.k));}

/* ---------- header build: sort + drag-reorder + resize ---------- */
let dragK=null;
function buildHead(){
  const hr=$("#hr"); hr.innerHTML="";
  for(const c of visibleCols()){
    const th=document.createElement("th");
    th.dataset.k=c.k; th.textContent=c.l;
    if(c.cls) th.className=c.cls;
    if(prefs.widths[c.k]) th.style.width=prefs.widths[c.k]+"px";
    th.style.position="sticky";
    if(!c.nosort) th.onclick=()=>{ if(sortK===c.k) sortDir*=-1;
      else {sortK=c.k; sortDir=["ticker","detail","side","action","trend","trigger"].includes(c.k)?1:-1;} render(); };
    th.draggable=true;
    th.ondragstart=e=>{dragK=c.k; e.dataTransfer.setData("text/plain",c.k);};
    th.ondragover=e=>e.preventDefault();
    th.ondrop=e=>{e.preventDefault(); if(!dragK||dragK===c.k)return;
      const ord=orderedCols().map(x=>x.k);
      ord.splice(ord.indexOf(c.k),0,ord.splice(ord.indexOf(dragK),1)[0]);
      prefs.order=ord; savePrefs(); rebuild(); dragK=null;};
    const rz=document.createElement("span"); rz.className="rz";
    rz.onpointerdown=e=>{e.stopPropagation(); e.preventDefault();
      const sx=e.clientX, w0=th.offsetWidth;
      const mv=ev=>{const w=Math.max(50,w0+ev.clientX-sx); th.style.width=w+"px"; prefs.widths[c.k]=w;};
      const up=()=>{document.removeEventListener("pointermove",mv);document.removeEventListener("pointerup",up);savePrefs();};
      document.addEventListener("pointermove",mv);document.addEventListener("pointerup",up);};
    rz.onclick=e=>e.stopPropagation();
    th.appendChild(rz);
    hr.appendChild(th);
  }
}
function buildColPanel(){
  const p=$("#colPanel"); p.innerHTML="";
  for(const c of orderedCols()){
    const lab=document.createElement("label");
    const cb=document.createElement("input"); cb.type="checkbox";
    cb.checked=!prefs.hidden.includes(c.k);
    cb.onchange=()=>{ if(cb.checked) prefs.hidden=prefs.hidden.filter(k=>k!==c.k);
      else prefs.hidden.push(c.k); savePrefs(); rebuild(); };
    lab.appendChild(cb); lab.appendChild(document.createTextNode(" "+c.l));
    p.appendChild(lab);
  }
  const rst=document.createElement("button"); rst.className="rst";
  rst.textContent="Reset columns";
  rst.onclick=()=>{resetPrefs(); rebuild();};
  p.appendChild(rst);
}
function rebuild(){buildHead(); buildColPanel(); render();}

/* ---------- filtering / sorting / rows ---------- */
function passes(r){
  if(q && !dispSym(r.ticker).toLowerCase().includes(q) && !r.ticker.toLowerCase().includes(q)) return false;
  if(filt==="all") return true;
  if(["S1","S2","S3","S4"].includes(filt)) return r.signal===filt;
  if(filt==="prime") return !!r.prime;
  if(filt==="rs") return r.rs_pct!=null && r.rs_pct>50;
  if(filt==="ern") return r.ern_status==="safe" || r.ern_status==="n/a";
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
    return String(x??"").localeCompare(String(y??""))*sortDir;
  });
  const cols=visibleCols();
  const tb=$("#b"); tb.innerHTML="";
  for(const r of view){
    const tr=document.createElement("tr");
    tr.innerHTML=cols.map(c=>`<td class="${c.cls||""}">${c.cell?c.cell(r):(r[c.k]??"")}</td>`).join("");
    tb.appendChild(tr);
  }
  $("#empty").style.display = view.length? "none":"block";
}
document.querySelectorAll(".bar button[data-f]").forEach(btn=>btn.onclick=()=>{
  filt=btn.dataset.f;
  document.querySelectorAll(".bar button[data-f]").forEach(b=>b.classList.remove("on"));
  btn.classList.add("on"); render();
});
$("#q").oninput=e=>{q=e.target.value.trim().toLowerCase(); render();};
$("#colsBtn").onclick=()=>{const p=$("#colPanel"); p.style.display=(p.style.display==="block")?"none":"block";};
$("#csv").onclick=()=>{
  const cols = MODE==="directional"
    ? ["ticker","action","action_note","trend","trend_adx","signal","trigger","side","rank","score","prime","last","live","live_status","live_dist","atr","atr_pct","rs","rs_pct","level","dist","age","stop","tgt","time_exit","qty","detail","label"]
    : ["ticker","signal","side","rank","score","prime","last","live","live_status","live_dist","level","dist","age","stop","tgt","time_exit","qty","detail","volx","atr","atr_pct","rs","rs_pct","ern",
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
function renderBoard(){
  const el=$("#board"); if(!el) return;
  if(!BOARD || !BOARD.entries || !BOARD.entries.length){ el.style.display="none"; return; }
  let h=`<div class="bhdr">Today's strategy order \u2014 ${BOARD.header}</div>`;
  for(const e of BOARD.entries){
    h+=`<div class="bcard" style="border-left-color:${e.color}" title="click to filter to ${e.code}" data-code="${e.code}">`+
       `<div class="top"><span class="nm">${e.order}. ${e.code} <span class="hh">${e.name}</span></span>`+
       `<span class="tier" style="color:${e.color}">${e.tier}</span></div>`+
       `<div class="rz2">${e.reason}</div>`+
       (e.alt?`<div class="alt">\u2192 ${e.alt}</div>`:"")+
       `<div class="hh">${e.hits} hit${e.hits===1?"":"s"} today</div></div>`;
  }
  el.innerHTML=h;
  el.querySelectorAll(".bcard").forEach(c=>c.onclick=()=>{
    const code=c.dataset.code;
    const btn=[...document.querySelectorAll(".bar button[data-f]")].find(b=>b.dataset.f===code);
    if(btn) btn.click();
  });
}
renderBoard();
loadPrefs(); rebuild();
</script></body></html>"""


def write_report(rows, path, scanned=0, universe=0, market="us", bench=None):
    mkt = MARKETS[market]
    directional = mkt["mode"] == "directional"
    enriched = _enrich(rows)
    now = dt.datetime.now()
    title = f"PRICE-ACTION SCAN \u2014 {mkt['label']}"
    filters = _FILTERS_DIRECTIONAL if directional else _FILTERS_OPTIONS
    html_out = (_TEMPLATE
                .replace("__ROWS__", json.dumps(enriched))
                .replace("__FILTERS__", filters)
                .replace("__MODE__", mkt["mode"])
                .replace("__ERNWARN__", str(CFG.earnings_warn_days))
                .replace("__BOARD__", json.dumps((bench or {}).get("board")) if bench else "null")
                .replace("__BENCH__",
                         ((f"{bench['symbol']}: {bench['bias'].upper()} (ADX {bench['adx']})"
                           + (f"  \u00b7 {bench['snap']['state']} \u2014 {bench['snap']['guidance']} [context]"
                              if bench.get("snap") else "")
                           + ("  \u26a0 STAND-DOWN: bench bearish; trend entries (S1/S2) -0.63% excess (t=-4.0). S4 exempt from this warning (stand-down evidence is S1/S2-specific); note the bearish-regime S4 'supercharge' was retired by the date-matched audit"
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
