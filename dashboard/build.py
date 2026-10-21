"""Render data/listings.json into docs/index.html (GitHub Pages).

Self-contained: listing data is embedded as JSON and filtered/sorted client-side.
Forked from the apartment finder's dashboard. Commercial changes: all-in price
(canon + IVA + admin) with the breakdown shown, COP/m² vs the Cra 47B benchmark,
a pinned benchmark card, rent/sale filter, near-miss toggle.
Triage (✓ save / ✕ hide) persists in localStorage under ssf.* keys.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(__file__))
DOCS = os.path.join(ROOT, "docs")


def build(listings: list, cfg: dict) -> str:
    os.makedirs(DOCS, exist_ok=True)
    bench = cfg["benchmark"]
    meta = {
        "bench_m2": round(bench["all_in_cop"] / bench["total_m2"]),
        "bench_label": bench["label"],
        "cap": cfg["hard"]["max_all_in_cop"],
        "min_m2": cfg["hard"]["min_area_m2"],
        "max_m2": cfg["hard"]["max_area_m2"],
        "iva": cfg["hard"].get("iva_rate", 0.19),
        "areas": {k: v["label"] for k, v in cfg["areas"].items()},
    }
    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    html = (_TEMPLATE
            .replace("__TITLE__", cfg["output"].get("dashboard_title", "Site Finder"))
            .replace("__GENERATED__", generated)
            .replace("__META__", json.dumps(meta, ensure_ascii=False))
            .replace("__DATA__", json.dumps(listings, ensure_ascii=False)))
    out = os.path.join(DOCS, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    return out


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Smash Site Finder</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script defer src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root{
    --bg:#f6f7f5; --card:#fff; --ink:#14181a; --muted:#5d6966; --line:#e3e7e4;
    --accent:#2f6b4f; --accent-ink:#fff; --new:#c2410c; --chip:#edf1ee;
    --yes:#2f6b4f; --no:#b91c1c; --good:#15803d; --bad:#b45309; --bench:#7c3aed;
    --shadow:0 1px 3px rgba(0,0,0,.08);
  }
  @media (prefers-color-scheme:dark){
    :root{--bg:#0e1211;--card:#171c1b;--ink:#e5ebe8;--muted:#9aa8a3;--line:#26302d;
          --accent:#5fbf8f;--accent-ink:#0a1510;--new:#fb923c;--chip:#222b28;
          --yes:#5fbf8f;--no:#f87171;--good:#4ade80;--bad:#fbbf24;--bench:#a78bfa;
          --shadow:0 1px 3px rgba(0,0,0,.4);}
  }
  *{box-sizing:border-box}
  body{margin:0;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
       background:var(--bg);color:var(--ink)}
  header{padding:20px 16px 8px;max-width:1180px;margin:0 auto}
  h1{margin:0 0 2px;font-size:20px;letter-spacing:-.01em}
  .sub{color:var(--muted);font-size:13px}
  .sub a{color:var(--muted);text-decoration:underline;cursor:pointer}
  .bar{position:sticky;top:0;z-index:5;background:var(--bg);
       max-width:1180px;margin:0 auto;padding:10px 16px;display:flex;gap:8px;flex-wrap:wrap;
       align-items:center;border-bottom:1px solid var(--line)}
  select,button{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);
       border-radius:8px;padding:7px 10px;cursor:pointer}
  button.on{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
  .dd{position:relative}
  .dd>summary{list-style:none;cursor:pointer;background:var(--card);border:1px solid var(--line);
       border-radius:8px;padding:7px 10px;user-select:none;white-space:nowrap}
  .dd>summary::-webkit-details-marker{display:none}
  .dd[open]>summary{border-color:var(--accent)}
  .ddbody{position:absolute;top:calc(100% + 4px);left:0;z-index:20;background:var(--card);
       border:1px solid var(--line);border-radius:8px;box-shadow:var(--shadow);padding:8px;min-width:190px}
  .ddbody label{display:flex;align-items:center;gap:8px;padding:5px 6px;border-radius:6px;cursor:pointer;font-size:14px}
  .ddbody label:hover{background:var(--chip)}
  .ddall{border-bottom:1px solid var(--line);margin-bottom:4px;padding-bottom:6px!important;font-weight:600}
  .ddbody input[type=checkbox]{width:16px;height:16px;accent-color:var(--accent)}
  .spacer{flex:1}
  .link{background:none;border:none;color:var(--muted);text-decoration:underline;padding:7px 4px}
  .grid{max-width:1180px;margin:0 auto;padding:16px;display:grid;gap:14px;
        grid-template-columns:repeat(auto-fill,minmax(320px,1fr))}
  @media (max-width:420px){.grid{grid-template-columns:1fr}}
  @media (max-width:640px){.bar{position:static}}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;
        box-shadow:var(--shadow);display:flex;flex-direction:column}
  .card.saved{box-shadow:0 0 0 2px var(--yes) inset;border-color:var(--yes)}
  .card.bench{box-shadow:0 0 0 2px var(--bench) inset;border-color:var(--bench)}
  .thumb{aspect-ratio:16/10;background:var(--chip) center/cover no-repeat;position:relative;touch-action:pan-y}
  .nav{position:absolute;top:50%;transform:translateY(-50%);width:32px;height:32px;padding:0;
       border:none;border-radius:50%;background:rgba(0,0,0,.45);color:#fff;font-size:18px;line-height:1;
       display:flex;align-items:center;justify-content:center;cursor:pointer;opacity:.6}
  .nav:hover{opacity:1}
  .nav.prev{left:8px} .nav.next{right:8px}
  .counter{position:absolute;bottom:8px;right:8px;background:rgba(0,0,0,.6);color:#fff;
           font-size:11px;padding:2px 8px;border-radius:10px;pointer-events:none}
  .badges{position:absolute;top:8px;left:8px;display:flex;gap:6px;flex-wrap:wrap;max-width:75%}
  .b{border-radius:20px;padding:3px 9px;font-size:11px;font-weight:700;letter-spacing:.03em;color:#fff}
  .score{background:var(--accent);color:var(--accent-ink);font-size:13px}
  .newb{background:var(--new)} .benchb{background:var(--bench)}
  .t-local{background:#0369a1} .t-bodega{background:#475569} .t-casa{background:#b45309}
  .t-edificio{background:#6d28d9} .saleb{background:#be123c} .nearb{background:#78716c}
  .src{position:absolute;top:8px;right:8px;background:rgba(0,0,0,.55);color:#fff;border-radius:6px;
       padding:2px 7px;font-size:11px}
  .body{padding:12px 13px 13px;display:flex;flex-direction:column;gap:7px;flex:1}
  .label{font-weight:700}
  .price{font-size:18px;font-weight:700}
  .price small{font-weight:500;color:var(--muted);font-size:12px}
  .brk{color:var(--muted);font-size:12px}
  .meta{color:var(--muted);font-size:13px}
  .where{font-weight:600;color:var(--ink)}
  .cmp{font-size:12.5px;font-weight:600}
  .cmp.good{color:var(--good)} .cmp.bad{color:var(--bad)}
  .chips{display:flex;flex-wrap:wrap;gap:5px}
  .chip{background:var(--chip);border-radius:20px;padding:3px 8px;font-size:11.5px}
  .note{color:var(--new);font-size:12px}
  .unote{font-size:12.5px;background:var(--chip);border-radius:8px;padding:6px 8px}
  .foot{margin-top:auto;display:flex;justify-content:space-between;align-items:center;gap:8px}
  .acts{display:flex;gap:6px}
  .act{width:34px;height:34px;padding:0;border-radius:9px;font-size:16px;line-height:1;
       display:flex;align-items:center;justify-content:center}
  .act.save{width:auto;padding:0 11px;font-size:13px;font-weight:600}
  .act.no:hover{background:var(--no);color:#fff;border-color:var(--no)}
  .act.save.on{background:var(--yes);color:#fff;border-color:var(--yes)}
  .contact{display:flex;gap:6px}
  a.view,a.wa{background:var(--accent);color:var(--accent-ink);text-decoration:none;font-weight:600;
         border-radius:8px;padding:7px 11px;font-size:13px;white-space:nowrap}
  a.wa{background:#16a34a;color:#fff}
  .empty{max-width:1180px;margin:40px auto;text-align:center;color:var(--muted)}
  #mapwrap{max-width:1180px;margin:0 auto;padding:16px;display:none}
  #map{height:70vh;min-height:420px;border-radius:12px;border:1px solid var(--line);z-index:1}
  .maphint{color:var(--muted);font-size:12px;margin:8px 2px 0;display:flex;gap:14px;flex-wrap:wrap}
  .lg{display:inline-flex;align-items:center;gap:5px}
  .dot{width:11px;height:11px;border-radius:50%;display:inline-block}
  .pop{width:190px;font:13px/1.4 -apple-system,sans-serif}
  .pop img{width:100%;height:104px;object-fit:cover;border-radius:6px;display:block;margin-bottom:6px}
  .pop .pp{font-weight:700;font-size:14px}
  .pop .pm{color:#5d6966;font-size:12px;margin:2px 0 6px}
  .pop a{color:#2f6b4f;font-weight:600;text-decoration:none}
  footer{max-width:1180px;margin:0 auto;padding:8px 16px 40px;color:var(--muted);font-size:12px}
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <div class="sub"><span id="stat-count"></span> · <b id="stat-new"></b>
    · <span id="stat-saved">0 saved</span> · <span id="stat-hidden"></span> · updated __GENERATED__</div>
  <div class="sub" id="rules"></div>
</header>
<div class="bar">
  <button id="savedBtn">★ Saved (<span id="savedN">0</span>)</button>
  <details class="dd"><summary id="areaSum">All areas</summary>
    <div class="ddbody"><label class="ddall"><input type="checkbox" id="areaAll" checked> All areas</label>
      <div id="areaBoxes"></div></div></details>
  <select id="deal"><option value="">Rent + sale</option><option value="arriendo">For rent</option><option value="venta">For sale</option></select>
  <select id="type"><option value="">All types</option></select>
  <select id="src"><option value="">All sources</option></select>
  <select id="minscore"><option value="0">Any score</option><option value="40">40+</option>
    <option value="50">50+</option><option value="60">60+</option><option value="70">70+</option></select>
  <select id="sort">
    <option value="score">Sort: Best fit</option>
    <option value="new">Sort: New first</option>
    <option value="m2cost">Sort: COP/m² ↑</option>
    <option value="price_asc">Sort: Price ↑</option>
    <option value="area_desc">Sort: Size ↓</option>
  </select>
  <button id="nearBtn">Near-misses</button>
  <button id="newonly">New only</button>
  <button id="mapBtn">🗺 Map</button>
  <span class="spacer"></span>
  <button class="link" id="exportViewX">⬇ View (Excel)</button>
  <button class="link" id="exportView">View (CSV)</button>
  <button class="link" id="exportSaved">Saved (CSV)</button>
  <button class="link" id="exportRej">Hidden</button>
</div>
<div class="grid" id="grid"></div>
<div id="mapwrap"><div id="map"></div><div class="maphint" id="legend"></div></div>
<div class="empty" id="empty" style="display:none"></div>
<footer>All-in rent = canon + 19% IVA (unless the listing says IVA incluido) + administración.
COP/m² compares against the benchmark's all-in cost spread over all its m² (rooftop included).
Sale listings show price and price per m². ⚠️ = a spec couldn't be verified from the listing, so ask.
✓ saves · ✕ hides for good (reset up top). Decisions are stored in this browser.</footer>
<script>
const DATA=__DATA__, META=__META__;
const $=id=>document.getElementById(id);
const grid=$('grid'), empty=$('empty');
let newOnly=false, savedView=false, mapView=false, showNear=false;
const LS_REJ='ssf.rejected', LS_SAVE='ssf.saved';
function lsGet(k,d){try{return JSON.parse(localStorage.getItem(k)||d)}catch(e){return JSON.parse(d)}}
function lsSet(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}
let rejected=new Set(lsGet(LS_REJ,'[]')), saved=lsGet(LS_SAVE,'{}');
const byUid={}; DATA.forEach(d=>byUid[d.uid]=d);
function persist(){lsSet(LS_REJ,[...rejected]); lsSet(LS_SAVE,saved);}

const fmt=n=>Math.round(n).toLocaleString('es-CO');
const usd=n=>Math.round(n).toLocaleString('en-US');
const mCOP=n=>n>=1e9?(n/1e9).toFixed(2).replace(/\.?0+$/,'')+'B':(n/1e6).toFixed(1).replace(/\.0$/,'')+'M';
const areaLabel=k=>META.areas[k]||(k||'other').replace(/_/g,' ');
const TYPE_LABEL={local:'Locales',bodega:'Bodegas',casa:'Houses',edificio:'Buildings'};
const AREA_COLOR={manila_provenza:'#db2777',poblado:'#2f6b4f',ciudad_del_rio:'#0369a1',envigado:'#b45309',other:'#555'};

$('rules').textContent=`Rules: ${fmt(META.min_m2)}–${fmt(META.max_m2)} m² · rent ≤ ${mCOP(META.cap)} COP/mo all-in (with IVA) · `
  +`benchmark ${META.bench_label} = ${fmt(META.bench_m2)} COP/m²`;

const ALL_AREAS=[...new Set(DATA.map(d=>d.area_key))].sort();
ALL_AREAS.forEach(a=>{const lb=document.createElement('label');
  lb.innerHTML=`<input type="checkbox" class="areaChk" value="${a}" checked> ${areaLabel(a)}`;$('areaBoxes').appendChild(lb);});
const checkedAreas=()=>new Set([...document.querySelectorAll('.areaChk:checked')].map(c=>c.value));
function updateAreaSummary(){const n=checkedAreas().size;
  $('areaAll').checked=n===ALL_AREAS.length; $('areaAll').indeterminate=n>0&&n<ALL_AREAS.length;
  $('areaSum').textContent=n===ALL_AREAS.length?'All areas':n===0?'No areas':n===1?areaLabel([...checkedAreas()][0]):n+' areas';}
[...new Set(DATA.map(d=>d.property_type))].sort().forEach(t=>{const o=document.createElement('option');
  o.value=t;o.textContent=TYPE_LABEL[t]||t;$('type').appendChild(o);});
[...new Set(DATA.map(d=>d.source))].sort().forEach(s=>{const o=document.createElement('option');
  o.value=s;o.textContent=s;$('src').appendChild(o);});

function updateStats(){
  const live=DATA.filter(d=>!d.benchmark&&!rejected.has(d.uid));
  $('stat-count').textContent=`${live.filter(d=>!d.near_miss).length} matches (+${live.filter(d=>d.near_miss).length} near-miss)`;
  $('stat-new').textContent=`${live.filter(d=>d.is_new).length} new today`;
  const nS=Object.keys(saved).length,nH=rejected.size;
  $('savedN').textContent=nS; $('stat-saved').textContent=nS+' saved';
  $('stat-hidden').innerHTML=nH?nH+' hidden (<a id="resetHid">reset</a>)':'0 hidden';
  const r=$('resetHid'); if(r) r.onclick=()=>{if(confirm('Un-hide all '+nH+' listings?')){rejected=new Set();persist();updateStats();refresh();}};
}
function currentRows(){
  let rows=savedView?Object.values(saved):DATA.filter(d=>!rejected.has(d.uid));
  const ms=+$('minscore').value||0, areas=checkedAreas();
  rows=rows.filter(d=>d.benchmark&&!savedView ? true :
       areas.has(d.area_key)&&(!$('type').value||d.property_type===$('type').value)
    &&(!$('deal').value||d.deal===$('deal').value)&&(!$('src').value||d.source===$('src').value)
    &&d.score>=ms&&(savedView||showNear||!d.near_miss)&&(savedView||!newOnly||d.is_new));
  const s=$('sort').value, big=9e15;
  const cost=d=>d.deal==='venta'?d.price_sale:d.price_all_in;
  rows.sort((a,b)=>(b.benchmark-a.benchmark)||(
     s==='price_asc'?(cost(a)||big)-(cost(b)||big)
    :s==='m2cost'?((a.deal==='venta')-(b.deal==='venta'))||((a.cop_per_m2||big)-(b.cop_per_m2||big))
    :s==='area_desc'?(b.area_m2||0)-(a.area_m2||0)
    :s==='new'?(b.is_new-a.is_new)||(b.score-a.score)
    :b.score-a.score));
  return rows;
}
function priceBlock(d){
  if(d.deal==='venta'){
    return `<div class="price">${d.price_sale?'$'+mCOP(d.price_sale)+' COP':'Price not listed'} <small>${d.usd_sale?'≈ US$'+(d.usd_sale/1e6).toFixed(1)+'M':''}</small></div>
      <div class="brk">For sale${d.cop_per_m2?' · '+fmt(d.cop_per_m2)+' COP/m²':''}</div>`;
  }
  if(!d.price_rent) return `<div class="price">Price not listed</div>`;
  const iva=d.iva_included===true?0:Math.round(d.price_rent*META.iva);
  const parts=[`canon ${mCOP(d.price_rent)}`, d.iva_included===true?'IVA incl.':`IVA ${mCOP(iva)}${d.iva_included===null?'?':''}`,
    d.admin_known?`admin ${mCOP(d.price_admin)}`:'admin ?'];
  let cmp='';
  if(d.cop_per_m2&&!d.benchmark){const pct=Math.round((d.cop_per_m2/META.bench_m2-1)*100);
    cmp=`<div class="cmp ${pct<=0?'good':'bad'}">${fmt(d.cop_per_m2)} COP/m² · ${pct<=0?pct:'+'+pct}% vs ${META.bench_label}</div>`;}
  else if(d.cop_per_m2) cmp=`<div class="cmp">${fmt(d.cop_per_m2)} COP/m² (the yardstick)</div>`;
  return `<div class="price">$${mCOP(d.price_all_in)} COP/mo <small>≈ US$${usd(d.usd_month)} all-in</small></div>
    <div class="brk">${parts.join(' + ')}</div>${cmp}`;
}
function waLink(d){
  if(!d.contact_whatsapp) return '';
  const msg=`Hola, vi este inmueble (${d.property_type}, ${d.area_m2?Math.round(d.area_m2)+' m²':''}) en ${d.neighborhood||'Medellín'} `
    +`publicado en ${d.source}. Estamos buscando espacio para un club de bienestar con restaurante y gimnasio. `
    +`¿Sigue disponible? ¿Qué uso de suelo tiene y el canon incluye IVA? ${d.url}`;
  return `https://wa.me/${d.contact_whatsapp}?text=${encodeURIComponent(msg)}`;
}
function render(){
  const rows=currentRows(); grid.innerHTML='';
  empty.style.display=(!mapView&&!rows.length)?'block':'none';
  empty.textContent=savedView?'No saved sites yet. Tap ♡ Save on ones you like.':'No listings match this view.';
  for(const d of rows){
    const el=document.createElement('div');
    el.className='card'+(d.benchmark?' bench':saved[d.uid]?' saved':'');
    const gal=(d.images&&d.images.length)?d.images:(d.image?[d.image]:[]);
    const nav=gal.length>1?`<button class="nav prev" data-nav="prev" aria-label="Previous photo">‹</button>
      <button class="nav next" data-nav="next" aria-label="Next photo">›</button><span class="counter">1/${gal.length}</span>`:'';
    const badges=[`<span class="b score">${d.score}</span>`,
      d.benchmark?'<span class="b benchb">BENCHMARK</span>':'', d.is_new?'<span class="b newb">NEW</span>':'',
      `<span class="b t-${d.property_type}">${(d.property_type||'').toUpperCase()}</span>`,
      d.deal==='venta'?'<span class="b saleb">FOR SALE</span>':'', d.near_miss?'<span class="b nearb">NEAR-MISS</span>':''].join('');
    const chips=(d.score_flags||[]).map(f=>`<span class="chip">${f}</span>`).join('');
    const notes=[...(d.benchmark?d.hard_fails.map(f=>'fails your filter: '+f):[]),...(d.notes||[])]
      .map(n=>`<div class="note">⚠️ ${n}</div>`).join('');
    const isSaved=!!saved[d.uid], wa=waLink(d);
    el.innerHTML=`<div class="thumb" data-uid="${d.uid}" data-idx="0" ${gal.length?`style="background-image:url('${gal[0]}')"`:''}>
        <div class="badges">${badges}</div><span class="src">${d.source}</span>${nav}</div>
      <div class="body">
        ${d.label?`<div class="label">${d.label}</div>`:''}
        ${priceBlock(d)}
        <div class="meta"><span class="where">${areaLabel(d.area_key)}</span>${d.neighborhood?' · '+d.neighborhood:''}${d.address?' · '+d.address:''}</div>
        <div class="meta">${d.area_m2?fmt(d.area_m2)+' m²':'m² ?'}${d.stratum?' · estrato '+d.stratum:''}${d.garages?' · '+d.garages+' parking':''}${d.floor?' · piso '+d.floor:''}${d.contact_name?' · '+d.contact_name:''}</div>
        <div class="chips">${chips}</div>${notes}
        ${d.user_note?`<div class="unote">${d.user_note}</div>`:''}
        <div class="foot">
          <div class="acts">${d.benchmark?'':`<button class="act no" data-act="reject" data-uid="${d.uid}" title="Hide for good">✕</button>
            <button class="act save ${isSaved?'on':''}" data-act="save" data-uid="${d.uid}">${isSaved?'✓ Saved':'♡ Save'}</button>`}</div>
          <div class="contact">${wa?`<a class="wa" href="${wa}" target="_blank" rel="noopener">WhatsApp</a>`:''}
            <a class="view" href="${d.url}" target="_blank" rel="noopener">View →</a></div>
        </div>
      </div>`;
    grid.appendChild(el);
  }
}
function flip(t,dir){const d=byUid[t.dataset.uid]||saved[t.dataset.uid]||{},imgs=d.images||[];if(imgs.length<2)return;
  let i=((+t.dataset.idx||0)+dir+imgs.length)%imgs.length;t.dataset.idx=i;t.style.backgroundImage=`url('${imgs[i]}')`;
  const c=t.querySelector('.counter');if(c)c.textContent=(i+1)+'/'+imgs.length;}
grid.addEventListener('click',e=>{
  const n=e.target.closest('.nav'); if(n){e.preventDefault();flip(n.closest('.thumb'),n.dataset.nav==='next'?1:-1);return;}
  const b=e.target.closest('.act'); if(!b) return; const uid=b.dataset.uid;
  if(b.dataset.act==='reject'){delete saved[uid];rejected.add(uid);}
  else if(saved[uid]) delete saved[uid]; else {saved[uid]=byUid[uid];rejected.delete(uid);}
  persist();updateStats();refresh();});
grid.addEventListener('touchstart',e=>{const t=e.target.closest('.thumb');if(t)t._sx=e.touches[0].clientX;},{passive:true});
grid.addEventListener('touchend',e=>{const t=e.target.closest('.thumb');if(t&&t._sx!=null){
  const dx=e.changedTouches[0].clientX-t._sx;if(Math.abs(dx)>30)flip(t,dx<0?1:-1);t._sx=null;}},{passive:true});

// ---- exports: a call sheet for whoever phones the brokers ----
const COLS=[['score','score'],['area',d=>areaLabel(d.area_key)],['neighborhood','neighborhood'],['address','address'],
  ['type','property_type'],['deal','deal'],['m2',d=>d.area_m2?Math.round(d.area_m2):''],
  ['all_in_cop_month','price_all_in'],['canon_cop','price_rent'],['iva',d=>d.iva_included===true?'included':d.iva_included===false?'on top':'not stated'],
  ['admin_cop',d=>d.admin_known?d.price_admin:'unknown'],['sale_cop','price_sale'],['cop_per_m2','cop_per_m2'],
  ['contact_name','contact_name'],['phone','contact_phone'],['whatsapp_link',waLink],['email','contact_email'],
  ['listing_url','url'],['status',''],['notes',''],['fit_signals',d=>(d.score_flags||[]).join('; ')],
  ['warnings',d=>(d.notes||[]).join('; ')],['source','source'],['stratum','stratum'],['parking','garages'],
  ['lat','lat'],['lng','lng'],['id','uid']];
const cell=v=>{if(v==null)return'';const s=String(v).replace(/"/g,'""');return /[",\n\r]/.test(s)?`"${s}"`:s;};
const toCSV=rows=>'﻿'+[COLS.map(c=>c[0]).join(','),...rows.map(d=>COLS.map(c=>cell(typeof c[1]==='function'?c[1](d):d[c[1]])).join(','))].join('\r\n');
function dl(name,text,mime){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:mime}));a.download=name;a.click();URL.revokeObjectURL(a.href);}
$('exportView').onclick=()=>{const r=currentRows();r.length?dl('smash-sites-view.csv',toCSV(r),'text/csv;charset=utf-8'):alert('Nothing to export.');};
$('exportSaved').onclick=()=>{const r=Object.values(saved);r.length?dl('smash-sites-saved.csv',toCSV(r),'text/csv;charset=utf-8'):alert('Save some sites first.');};
$('exportRej').onclick=()=>dl('rejected.json',JSON.stringify([...rejected],null,2),'application/json');
$('exportViewX').onclick=()=>{const rows=currentRows();if(!rows.length){alert('Nothing to export.');return;}
  const go=()=>{const head=COLS.map(c=>c[0]);
    const ws=XLSX.utils.aoa_to_sheet([head,...rows.map(d=>COLS.map(c=>{const v=typeof c[1]==='function'?c[1](d):d[c[1]];return v==null?'':v;}))]);
    rows.forEach((d,ri)=>[['whatsapp_link','WhatsApp'],['listing_url','Ver anuncio']].forEach(([col,lab])=>{
      const a=XLSX.utils.encode_cell({r:ri+1,c:head.indexOf(col)}),x=ws[a];if(x&&x.v){x.l={Target:String(x.v)};x.v=lab;}}));
    const wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,ws,'Sitios');XLSX.writeFile(wb,'smash-sites.xlsx');};
  if(window.XLSX) return go();
  const s=document.createElement('script');s.src='https://unpkg.com/xlsx@0.18.5/dist/xlsx.full.min.js';
  s.onload=go;s.onerror=()=>alert('Excel library failed to load. Use CSV.');document.head.appendChild(s);};

// ---- map ----
let map=null,layer=null;
$('legend').innerHTML='<span id="mapcount"></span>'+Object.entries(META.areas).map(([k,v])=>
  `<span class="lg"><span class="dot" style="background:${AREA_COLOR[k]||'#555'}"></span>${v}</span>`).join('')
  +`<span class="lg"><span class="dot" style="background:#7c3aed"></span>Benchmark</span>`;
function renderMap(){
  if(!map){ if(typeof L==='undefined') return; map=L.map('map').setView([6.205,-75.57],13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(map);
    layer=L.layerGroup().addTo(map);}
  layer.clearLayers(); const shown=currentRows(), pts=[];
  for(const d of shown){ if(typeof d.lat!=='number'||typeof d.lng!=='number') continue;
    const gal=(d.images||[])[0]||d.image;
    L.circleMarker([d.lat,d.lng],{radius:d.benchmark?10:7,weight:1.5,color:'#fff',
      fillColor:d.benchmark?'#7c3aed':(AREA_COLOR[d.area_key]||'#555'),fillOpacity:.9})
     .bindPopup(`<div class="pop">${gal?`<img src="${gal}" alt="">`:''}<div class="pp">${d.deal==='venta'?'$'+mCOP(d.price_sale)+' sale':'$'+mCOP(d.price_all_in)+'/mo all-in'}</div>
       <div class="pm">${d.property_type} · ${d.area_m2?fmt(d.area_m2)+' m²':''} · ${d.neighborhood||''} · score ${d.score}</div>
       <a href="${d.url}" target="_blank" rel="noopener">View →</a></div>`).addTo(layer);
    pts.push([d.lat,d.lng]);}
  $('mapcount').textContent=`${pts.length} of ${shown.length} mapped`;
  if(pts.length) map.fitBounds(pts,{padding:[30,30],maxZoom:15}); setTimeout(()=>map.invalidateSize(),0);
}
function refresh(){render(); if(mapView) renderMap();}
$('mapBtn').onclick=()=>{mapView=!mapView;$('mapBtn').classList.toggle('on',mapView);
  $('mapwrap').style.display=mapView?'block':'none';grid.style.display=mapView?'none':'';refresh();};
['type','deal','src','minscore','sort'].forEach(i=>$(i).addEventListener('change',refresh));
$('areaBoxes').addEventListener('change',()=>{updateAreaSummary();refresh();});
$('areaAll').addEventListener('change',()=>{document.querySelectorAll('.areaChk').forEach(c=>c.checked=$('areaAll').checked);updateAreaSummary();refresh();});
$('nearBtn').onclick=()=>{showNear=!showNear;$('nearBtn').classList.toggle('on',showNear);refresh();};
$('newonly').onclick=()=>{newOnly=!newOnly;$('newonly').classList.toggle('on',newOnly);refresh();};
$('savedBtn').onclick=()=>{savedView=!savedView;$('savedBtn').classList.toggle('on',savedView);refresh();};
updateAreaSummary(); updateStats(); render();
</script>
</body>
</html>"""
