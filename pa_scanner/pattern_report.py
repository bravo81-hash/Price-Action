"""Self-contained decision report for the chart-pattern pipeline."""
from __future__ import annotations

import datetime as dt
import json


def _html(rows, meta):
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pattern Scanner</title><style>
:root{--bg:#0d1117;--panel:#161b22;--bd:#30363d;--fg:#e6edf3;--mut:#8b949e;--blue:#58a6ff;--green:#3fb950;--red:#f85149;--amber:#d29922}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
header{padding:16px 20px;border-bottom:1px solid var(--bd);display:flex;gap:10px 20px;flex-wrap:wrap;align-items:baseline}h1{font-size:16px;margin:0}.meta{color:var(--mut)}
.architecture{padding:10px 20px;border-bottom:1px solid var(--bd);color:#c9d1d9}.architecture b{color:var(--blue)}
.bar{padding:10px 20px;display:flex;gap:7px;flex-wrap:wrap;border-bottom:1px solid var(--bd)}button,input{font:inherit;background:var(--panel);color:var(--fg);border:1px solid var(--bd);border-radius:6px;padding:6px 10px}button{cursor:pointer}button.on{background:var(--blue);color:#07111f}input{min-width:180px}
table{width:100%;border-collapse:collapse}th,td{padding:8px 10px;border-bottom:1px solid var(--bd);white-space:nowrap;text-align:left}th{position:sticky;top:0;background:var(--panel);color:var(--mut);cursor:pointer}td.num,th.num{text-align:right}tr:hover td{background:#1c2230}
.tag{padding:2px 7px;border-radius:4px;background:#1f6feb33;color:#79c0ff}.long{color:var(--green)}.short{color:var(--red)}.ok{color:var(--green)}.warn{color:var(--amber)}.bad{color:var(--red)}a{color:var(--blue);text-decoration:none}.small{font-size:10px;color:var(--mut)}
</style></head><body><header><h1>CHART-PATTERN SHORTLIST</h1><span class="meta">__DATE__</span><span class="meta">__COUNTS__</span></header>
<div class="architecture"><b>Bulk OHLCV geometry</b> → momentum + relative strength + volume + market/sector context → <b>3–10 actionable candidates</b> → visual review → TWS live validation. A pattern row is a candidate, not an automatic trade.</div>
<div class="bar"><input id="q" placeholder="filter ticker or pattern"><button data-f="all" class="on">All</button><button data-f="NEAR_TRIGGER">Near trigger</button><button data-f="TRIGGERED_INTRADAY">Triggered intraday</button><button data-f="CLOSE_CONFIRMED">Close confirmed</button><button data-f="RETESTING">Retesting</button><button data-f="long">Long</button><button data-f="short">Short</button><button id="csv">Export CSV</button></div>
<table><thead><tr id="head"></tr></thead><tbody id="body"></tbody></table>
<script>const ROWS=__ROWS__;let filt='all',q='',sortK='score',dir=-1;
const cols=[['ticker','Ticker'],['pattern','Pattern'],['status','Status'],['side','Side'],['score','Score'],['geometry_score','Geometry'],['context_score','Context'],['rs_pct','RS'],['momentum_score','Momentum'],['volx','Vol×'],['sector','Sector'],['market_bias','Market'],['last','Last'],['trigger','Trigger'],['distance_atr','Dist ATR'],['invalidation','Invalidation'],['target','Target'],['ern','Earn(d)'],['review','Review'],['detail','Geometry detail'],['mini','90d shape'],['chart','Chart']];
const $=s=>document.querySelector(s);function clsStatus(s){return ['CLOSE_CONFIRMED','RETESTING','TRIGGERED_INTRADAY'].includes(s)?'ok':s==='FAILED'?'bad':'warn'}
function spark(r){const a=r.spark||[];if(a.length<2)return'';const all=[...a,r.trigger],lo=Math.min(...all),hi=Math.max(...all),rng=(hi-lo)||1,w=130,h=34,p=2,step=(w-2*p)/(a.length-1);const pts=a.map((v,i)=>`${(p+i*step).toFixed(1)},${(p+(h-2*p)*(1-(v-lo)/rng)).toFixed(1)}`).join(' '),ty=(p+(h-2*p)*(1-(r.trigger-lo)/rng)).toFixed(1),color=r.side==='long'?'#3fb950':'#f85149';return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><line x1="0" x2="${w}" y1="${ty}" y2="${ty}" stroke="#d29922" stroke-dasharray="3 2"/><polyline fill="none" stroke="${color}" stroke-width="1.3" points="${pts}"/></svg>`}
function cell(r,k){if(k==='ticker')return `<b>${r.ticker}</b>`;if(k==='pattern')return `<span class="tag">${r.pattern}</span>`;if(k==='status'){const s=r.live_status||r.status;return `<b class="${clsStatus(s)}">${s.replaceAll('_',' ')}</b>${r.live!=null?`<div class="small">live ${r.live}</div>`:''}`};if(k==='side')return `<span class="${r.side}">${r.side}</span>`;if(k==='score'||k==='geometry_score'||k==='context_score'||k==='momentum_score')return Number(r[k]||0).toFixed(3);if(k==='mini')return spark(r);if(k==='chart')return `<a target="_blank" href="https://www.tradingview.com/chart/?symbol=${encodeURIComponent(r.ticker)}">TradingView</a>`;return r[k]??''}
function passes(r){const hay=(r.ticker+' '+r.pattern).toLowerCase();if(q&&!hay.includes(q))return false;if(filt==='all')return true;if(filt==='long'||filt==='short')return r.side===filt;return (r.live_status||r.status)===filt}
function drawHead(){const h=$('#head');h.innerHTML='';for(const [k,l] of cols){const th=document.createElement('th');th.textContent=l;th.dataset.k=k;if(['score','geometry_score','context_score','rs_pct','momentum_score','volx','last','trigger','distance_atr','invalidation','target','ern'].includes(k))th.className='num';th.onclick=()=>{if(sortK===k)dir*=-1;else{sortK=k;dir=-1}render()};h.appendChild(th)}}
function view(){return ROWS.filter(passes).sort((a,b)=>{const x=a[sortK],y=b[sortK];if(typeof x==='number'&&typeof y==='number')return (x-y)*dir;return String(x??'').localeCompare(String(y??''))*dir})}
function render(){const b=$('#body');b.innerHTML='';for(const r of view()){const tr=document.createElement('tr');tr.innerHTML=cols.map(([k])=>`<td class="${['score','geometry_score','context_score','rs_pct','momentum_score','volx','last','trigger','distance_atr','invalidation','target','ern'].includes(k)?'num':''}">${cell(r,k)}</td>`).join('');b.appendChild(tr)}}
document.querySelectorAll('button[data-f]').forEach(x=>x.onclick=()=>{filt=x.dataset.f;document.querySelectorAll('button[data-f]').forEach(y=>y.classList.remove('on'));x.classList.add('on');render()});$('#q').oninput=e=>{q=e.target.value.trim().toLowerCase();render()};$('#csv').onclick=()=>{const keys=cols.filter(x=>x[0]!=='chart').map(x=>x[0]);const lines=[keys.join(','),...view().map(r=>keys.map(k=>'"'+String(r[k]??'').replaceAll('"','""')+'"').join(','))];const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([lines.join('\n')],{type:'text/csv'}));a.download='pattern_scan.csv';a.click()};drawHead();render();</script></body></html>""".replace("__ROWS__", json.dumps(rows)).replace("__DATE__", meta["date"]).replace("__COUNTS__", meta["counts"])


def write_pattern_report(rows, path, result):
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    counts = (f"{result.symbols_scanned} liquid symbols · {result.geometry_count} geometry · "
              f"{result.context_count} context-ranked · {len(rows)} final")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_html(rows, {"date": now, "counts": counts}))
    return path
