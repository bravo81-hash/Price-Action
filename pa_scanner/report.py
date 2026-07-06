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
 #twrap{overflow-x:auto}
 table{border-collapse:collapse;table-layout:fixed}
 th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--bd);
   white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 th{position:sticky;top:0;background:var(--panel);cursor:pointer;
   color:var(--mut);font-weight:600;user-select:none;z-index:5}
 th:hover{color:var(--fg)}
 th .thlabel{overflow:hidden;text-overflow:ellipsis;display:block;pointer-events:none}
 th.dragging{opacity:.4}
 th.dragover{box-shadow:inset 2px 0 0 var(--accent)}
 .colresizer{position:absolute;right:0;top:0;bottom:0;width:6px;cursor:col-resize}
 .colresizer:hover,.colresizer:active{background:var(--accent)}
 #colsPanel{display:none;position:absolute;top:100%;right:20px;background:var(--panel);
   border:1px solid var(--bd);border-radius:8px;padding:8px 10px;max-height:360px;
   overflow-y:auto;z-index:50;min-width:190px;box-shadow:0 8px 24px rgba(0,0,0,.4)}
 #colsPanel.open{display:block}
 #colsPanel .colsRow{display:flex;align-items:center;gap:6px;padding:4px 2px;
   color:var(--fg);cursor:pointer;white-space:nowrap}
 #colsPanel .colsReset{width:100%;margin-bottom:6px}
 td.num{text-align:right;font-variant-numeric:tabular-nums}
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
  <button id="colsBtn">&#9881; Columns</button>
  <button id="csv">Export CSV</button>
  <div id="colsPanel"></div>
</div>
<div id="twrap"><table id="t"><thead><tr id="head"></tr></thead><tbody id="b"></tbody></table></div>
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
function sigTag(r){ return `<span class="tag ${r.prime?"prime":String(r.signal).toLowerCase()}">${r.signal}${r.prime?"\u2605":""}</span>`; }
function chartCell(r){ return `<a href="https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSym(r.ticker))}" target="_blank">TV</a>`; }

/* ---------- column model (reorder / hide / resize) ---------- */
const TICKER_COL = {id:"ticker",key:"ticker",label:"Ticker",w:90};
const COLUMNS = {
  options:[
    {id:"signal",key:"signal",label:"Sig",w:70,render:sigTag},
    {id:"side",key:"side",label:"Side",w:64,rowCls:r=>r.side,render:r=>r.side},
    {id:"rank",key:"rank",label:"Rank",cls:"num",w:56,render:r=>r.rank??""},
    {id:"score",key:"score",label:"Score",cls:"num score",w:70,render:r=>Number(r.score).toFixed(3)},
    {id:"last",key:"last",label:"Last",cls:"num",w:70,render:r=>r.last??""},
    {id:"live",key:"live",label:"Live",cls:"num",w:140,render:r=>liveCell(r)},
    {id:"level",key:"level",label:"Level",cls:"num",w:74,render:r=>r.level??""},
    {id:"dist",key:"dist",label:"Dist/Brk(ATR)",cls:"num",w:110,render:r=>r.dist??""},
    {id:"age",key:"age",label:"Age",cls:"num",w:50,render:r=>r.age??""},
    {id:"stop",key:"stop",label:"Stop",cls:"num",w:70,render:r=>r.stop??""},
    {id:"tgt",key:"tgt",label:"Tgt",cls:"num",w:70,render:r=>r.tgt??""},
    {id:"qty",key:"qty",label:"Qty",cls:"num",w:60,render:r=>r.qty??""},
    {id:"detail",key:"detail",label:"Detail",w:200,render:r=>r.detail??""},
    {id:"volx",key:"volx",label:"Vol\u00d7",cls:"num",w:60,render:r=>r.volx??""},
    {id:"atr",key:"atr",label:"ATR",cls:"num",w:60,render:r=>r.atr??""},
    {id:"atr_pct",key:"atr_pct",label:"ATR%",cls:"num",w:64,render:r=>r.atr_pct??""},
    {id:"rs",key:"rs_pct",label:"RS",cls:"num",w:56,render:r=>rsCell(r)},
    {id:"ern",key:"ern",label:"Ern(d)",cls:"num",w:60,render:r=>ernCell(r)},
    {id:"regime",key:"regime",label:"Regime",w:110,render:r=>regCell(r)},
    {id:"vol",key:"vol_state",label:"Vol",w:140,title:volTitle,render:r=>volCell(r)},
    {id:"structure",key:"structure",label:"Structure",w:120,render:r=>structCell(r)},
    {id:"opt_liq",key:"opt_liq",label:"Opt Liq",w:130,render:r=>optLiqCell(r)},
    {id:"spark",key:"",label:"Trend",w:110,render:r=>r.spark_svg},
    {id:"chart",key:"",label:"Chart",w:56,render:chartCell},
  ],
  directional:[
    {id:"action",key:"action",label:"Action",w:110,render:r=>actionCell(r)},
    {id:"trend",key:"trend",label:"Weekly Trend",w:110,render:r=>trendCell(r)},
    {id:"signal",key:"signal",label:"Sig",w:70,render:sigTag},
    {id:"trigger",key:"trigger",label:"Trigger",w:90,rowCls:r=>r.trigger,render:r=>r.trigger||""},
    {id:"rank",key:"rank",label:"Rank",cls:"num",w:56,render:r=>r.rank??""},
    {id:"score",key:"score",label:"Score",cls:"num score",w:70,render:r=>Number(r.score).toFixed(3)},
    {id:"last",key:"last",label:"Last",cls:"num",w:70,render:r=>r.last??""},
    {id:"live",key:"live",label:"Live",cls:"num",w:140,render:r=>liveCell(r)},
    {id:"atr_pct",key:"atr_pct",label:"ATR%",cls:"num",w:64,render:r=>r.atr_pct??""},
    {id:"rs",key:"rs_pct",label:"RS",cls:"num",w:56,render:r=>rsCell(r)},
    {id:"level",key:"level",label:"Level",cls:"num",w:74,render:r=>r.level??""},
    {id:"dist",key:"dist",label:"Dist/Brk(ATR)",cls:"num",w:110,render:r=>r.dist??""},
    {id:"age",key:"age",label:"Age",cls:"num",w:50,render:r=>r.age??""},
    {id:"stop",key:"stop",label:"Stop",cls:"num",w:70,render:r=>r.stop??""},
    {id:"tgt",key:"tgt",label:"Tgt",cls:"num",w:70,render:r=>r.tgt??""},
    {id:"qty",key:"qty",label:"Qty",cls:"num",w:60,render:r=>r.qty??""},
    {id:"detail",key:"detail",label:"Detail",w:200,render:r=>r.detail??""},
    {id:"spark",key:"",label:"Trend",w:110,render:r=>r.spark_svg},
    {id:"chart",key:"",label:"Chart",w:56,render:chartCell},
  ]
};
function lsGet(k){ try{return localStorage.getItem(k);}catch(e){return null;} }
function lsSet(k,v){ try{localStorage.setItem(k,v);}catch(e){} }
function lsDel(k){ try{localStorage.removeItem(k);}catch(e){} }
function colStateKey(mode){ return "pa_cols_"+mode; }
function loadColState(mode){
  const ids = COLUMNS[mode].map(c=>c.id);
  let st=null;
  try{ st = JSON.parse(lsGet(colStateKey(mode))); }catch(e){}
  if(!st || !Array.isArray(st.order)) st={order:ids.slice(), hidden:[], widths:{}};
  st.order = st.order.filter(id=>ids.includes(id));
  ids.forEach(id=>{ if(!st.order.includes(id)) st.order.push(id); });
  st.hidden = (st.hidden||[]).filter(id=>ids.includes(id));
  st.widths = st.widths||{};
  return st;
}
const colStateCache = {};
function getColState(mode){
  if(!colStateCache[mode]) colStateCache[mode] = loadColState(mode);
  return colStateCache[mode];
}
function saveColState(mode){ lsSet(colStateKey(mode), JSON.stringify(colStateCache[mode])); }
function colWidth(mode, id){
  const st=getColState(mode);
  if(st.widths[id]) return st.widths[id];
  const col = id==="ticker" ? TICKER_COL : COLUMNS[mode].find(c=>c.id===id);
  return col ? col.w : 80;
}
let resizeState=null;
function startResize(e, id){
  e.preventDefault(); e.stopPropagation();
  const col = document.querySelector(`#t colgroup col[data-col-id="${id}"]`);
  if(!col) return;
  resizeState = { id, startX:e.clientX, startW: col.offsetWidth || colWidth(MODE,id), col };
  document.addEventListener("mousemove", onResizeMove);
  document.addEventListener("mouseup", onResizeUp);
}
function onResizeMove(e){
  if(!resizeState) return;
  const w = Math.max(32, resizeState.startW + (e.clientX - resizeState.startX));
  resizeState.col.style.width = w+"px";
  const table=$("#t");
  const total=[...table.querySelectorAll("colgroup col")].reduce((s,c)=>s+c.offsetWidth,0);
  table.style.width = total+"px";
}
function onResizeUp(){
  if(!resizeState) return;
  const w = parseInt(resizeState.col.style.width,10);
  getColState(MODE).widths[resizeState.id] = w;
  saveColState(MODE);
  resizeState=null;
  document.removeEventListener("mousemove", onResizeMove);
  document.removeEventListener("mouseup", onResizeUp);
}
function buildChrome(){
  const st = getColState(MODE);
  const cols = COLUMNS[MODE];
  const visible = st.order.filter(id=>!st.hidden.includes(id));
  const table = $("#t");
  const oldCg = table.querySelector("colgroup");
  if(oldCg) oldCg.remove();
  const cg = document.createElement("colgroup");
  const tCol = document.createElement("col");
  tCol.dataset.colId="ticker"; tCol.style.width=colWidth(MODE,"ticker")+"px";
  cg.appendChild(tCol);
  visible.forEach(id=>{
    const c=document.createElement("col");
    c.dataset.colId=id; c.style.width=colWidth(MODE,id)+"px";
    cg.appendChild(c);
  });
  table.insertBefore(cg, table.firstChild);
  const total=[...cg.querySelectorAll("col")].reduce((s,c)=>s+parseInt(c.style.width,10),0);
  table.style.width = total+"px";

  function makeTh(id,label,key,cls){
    const th=document.createElement("th");
    th.dataset.id=id;
    if(key) th.dataset.k=key; if(cls) th.className=cls;
    const span=document.createElement("span");
    span.className="thlabel"; span.textContent=label;
    th.appendChild(span);
    const rez=document.createElement("div");
    rez.className="colresizer"; rez.draggable=false;
    rez.onmousedown=e=>startResize(e,id);
    rez.ondragstart=e=>e.preventDefault();
    th.appendChild(rez);
    return th;
  }
  const hr=$("#head"); hr.innerHTML="";
  hr.appendChild(makeTh("ticker","Ticker","ticker",null));
  visible.forEach(id=>{
    const c = cols.find(x=>x.id===id);
    if(!c) return;
    const th = makeTh(id, c.label, c.key, c.cls ? c.cls.split(" ")[0] : null);
    th.draggable = true;
    th.ondragstart = e=>{ e.dataTransfer.setData("text/plain", id); th.classList.add("dragging"); };
    th.ondragend = ()=>{ th.classList.remove("dragging"); hr.querySelectorAll("th").forEach(x=>x.classList.remove("dragover")); };
    th.ondragover = e=>{ e.preventDefault(); th.classList.add("dragover"); };
    th.ondragleave = ()=> th.classList.remove("dragover");
    th.ondrop = e=>{
      e.preventDefault(); th.classList.remove("dragover");
      const srcId = e.dataTransfer.getData("text/plain");
      if(!srcId || srcId===id) return;
      const order = st.order;
      const from = order.indexOf(srcId);
      if(from<0) return;
      order.splice(from,1);
      const to = order.indexOf(id);
      if(to<0){ order.splice(from,0,srcId); return; }
      const rect = th.getBoundingClientRect();
      const after = (e.clientX - rect.left) > rect.width/2;
      order.splice(after? to+1 : to, 0, srcId);
      saveColState(MODE);
      buildChrome(); render();
    };
    hr.appendChild(th);
  });
  hr.querySelectorAll("th[data-k]").forEach(th=>{
    th.onclick=e=>{
      if(e.target.classList.contains("colresizer")) return;
      const k=th.dataset.k;
      if(sortK===k) sortDir*=-1;
      else {sortK=k; sortDir=(k==="ticker"||k==="detail"||k==="side"||k==="action"||k==="trend"||k==="trigger")?1:-1;}
      render();
    };
  });
  buildColsPanel();
}
function buildColsPanel(){
  const panel = $("#colsPanel");
  const st = getColState(MODE);
  const cols = COLUMNS[MODE];
  panel.innerHTML = "";
  const resetBtn=document.createElement("button");
  resetBtn.textContent="Reset columns"; resetBtn.className="colsReset";
  resetBtn.onclick=()=>{ lsDel(colStateKey(MODE)); colStateCache[MODE]=null; buildChrome(); render(); };
  panel.appendChild(resetBtn);
  st.order.forEach(id=>{
    const c = cols.find(x=>x.id===id);
    if(!c) return;
    const row=document.createElement("label");
    row.className="colsRow";
    const cb=document.createElement("input");
    cb.type="checkbox"; cb.checked = !st.hidden.includes(id);
    cb.onchange=()=>{
      if(cb.checked) st.hidden = st.hidden.filter(x=>x!==id);
      else if(!st.hidden.includes(id)) st.hidden.push(id);
      saveColState(MODE);
      buildChrome(); render();
    };
    row.appendChild(cb);
    row.appendChild(document.createTextNode(" "+c.label));
    panel.appendChild(row);
  });
}
function rowHTML(r){
  const st = getColState(MODE);
  const cols = COLUMNS[MODE];
  const visible = st.order.filter(id=>!st.hidden.includes(id));
  let out = `<td><b>${dispSym(r.ticker)}</b></td>`;
  visible.forEach(id=>{
    const c = cols.find(x=>x.id===id);
    if(!c) return;
    const cls=[c.cls, c.rowCls?c.rowCls(r):""].filter(Boolean).join(" ");
    const t = c.title ? ` title="${c.title(r)}"` : "";
    out += `<td${cls?` class="${cls}"`:""}${t}>${c.render(r)}</td>`;
  });
  return out;
}

function passes(r){
  if(q && !dispSym(r.ticker).toLowerCase().includes(q) && !r.ticker.toLowerCase().includes(q)) return false;
  if(filt==="all") return true;
  if(filt==="S1"||filt==="S2"||filt==="S3"||filt==="S4") return r.signal===filt;
  if(filt==="prime") return !!r.prime;
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
document.querySelectorAll(".bar button[data-f]").forEach(btn=>btn.onclick=()=>{
  filt=btn.dataset.f;
  document.querySelectorAll(".bar button[data-f]").forEach(b=>b.classList.remove("on"));
  btn.classList.add("on"); render();
});
$("#q").oninput=e=>{q=e.target.value.trim().toLowerCase(); render();};
$("#colsBtn").onclick=e=>{ e.stopPropagation(); $("#colsPanel").classList.toggle("open"); };
document.addEventListener("click", e=>{
  const p=$("#colsPanel");
  if(p.classList.contains("open") && !p.contains(e.target) && e.target.id!=="colsBtn") p.classList.remove("open");
});
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
buildChrome();
render();
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
                .replace("__BENCH__",
                         ((f"{bench['symbol']}: {bench['bias'].upper()} (ADX {bench['adx']})"
                           + (f"  \u00b7 {bench['snap']['state']} \u2014 {bench['snap']['guidance']} [context]"
                              if bench.get("snap") else "")
                           + ("  \u26a0 STAND-DOWN: bench bearish; trend entries (S1/S2) -0.63% excess (t=-4.0). S4 snapbacks EXEMPT: MR outperforms in bearish regimes (+5.6% US / +4.1% ASX @63d)"
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
