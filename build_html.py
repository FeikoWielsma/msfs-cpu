#!/usr/bin/env python3
"""
Generate a self-contained, static HTML view of the MSFS 2024 CPU data from
both sources (Tom's Hardware + PCGH).

Reads msfs24_data.csv (Tom's, grouped by `epoch`) and pcgh_msfs24.csv (PCGH,
grouped by `scene`), unifies them, and embeds everything into one HTML file:

  * Mode 1 "By source": pick a Site, then a View (combined newest-per-CPU, a
    single epoch/scene, or all raw rows), Average / 1% Low metric, and hover any
    bar to make it the 100% baseline with relative +/- on every other bar.
  * Mode 2 "Normalized": Tom's + both PCGH scenes on one axis, each series scaled
    so a chosen reference CPU = 100% (cross-source relative index).
  * Sources panel + full raw data table (both sites).

Usage:
    python build_html.py            # writes msfs24.html
"""

import argparse
import csv
import json
import os


def load(path, site, group_col):
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append({
                "cpu": r["cpu"],
                "vendor": r["vendor"],
                "x3d": r["is_x3d"] == "1",
                "avg": float(r["avg_fps"]),
                "low": float(r["low_1pct"]) if r.get("low_1pct") else None,
                "p02": float(r["p02_low"]) if r.get("p02_low") else None,
                "source": r["source"],
                "date": r["review_date"],
                "site": site,
                "group": r[group_col],
                "url": r.get("url", ""),
            })
    return out


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MSFS 2024 CPU Performance — Tom's Hardware + PCGH</title>
<style>
  :root {
    --amd-avg:#d6433b; --amd-low:#8f211b;
    --intel-avg:#2f8fd6; --intel-low:#1b5687;
    --bg:#f6f7f9; --card:#fff; --ink:#1d2127; --muted:#6b7280; --line:#e3e6ea;
    --s0:#444444; --s1:#e08214; --s2:#8073ac;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
    font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
  .wrap { max-width:1120px; margin:0 auto; padding:24px 20px 60px; }
  h1 { font-size:22px; margin:0 0 2px; }
  h2 { font-size:15px; margin:26px 0 10px; text-transform:uppercase;
    letter-spacing:.04em; color:var(--muted); }
  .sub { color:var(--muted); margin:0 0 18px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px;
    padding:16px 18px; }
  .controls { display:flex; flex-wrap:wrap; gap:18px; align-items:center; }
  .controls label { font-weight:600; margin-right:6px; }
  select { padding:6px 8px; border:1px solid var(--line); border-radius:6px;
    background:#fff; font:inherit; }
  .seg { display:inline-flex; border:1px solid var(--line); border-radius:6px;
    overflow:hidden; }
  .seg button { padding:6px 12px; border:0; background:#fff; cursor:pointer;
    font:inherit; }
  .seg button.on { background:var(--ink); color:#fff; }
  .hint { color:var(--muted); font-size:13px; margin-left:auto; max-width:46ch;
    text-align:right; }

  #chart { margin-top:8px; }
  .row { display:grid; grid-template-columns:220px 1fr; align-items:center;
    gap:10px; padding:3px 0; cursor:crosshair; }
  .name { text-align:right; font-size:13px; color:#33373e; white-space:nowrap;
    overflow:hidden; text-overflow:ellipsis; }
  .name .src { color:var(--muted); font-size:11px; }
  .star { color:#caa300; }
  .track { position:relative; height:26px; background:#fff;
    border:1px solid var(--line); border-radius:4px; }
  .bar { position:absolute; border-radius:3px 0 0 3px; transition:width .15s; }
  .bar.avg { height:100%; top:0; }
  .bar.low { height:46%; top:27%; }
  .amd .avg{background:var(--amd-avg);} .amd .low{background:var(--amd-low);}
  .intel .avg{background:var(--intel-avg);} .intel .low{background:var(--intel-low);}
  .val { position:absolute; top:50%; transform:translateY(-50%); font-weight:700;
    font-size:12px; color:#222; white-space:nowrap; }
  .lowval { position:absolute; top:50%; transform:translate(-100%,-50%);
    font-size:11px; color:#fff; font-weight:700; }
  .refline { position:absolute; top:-2px; bottom:-2px; width:2px; background:#111;
    display:none; z-index:5; }
  .delta { position:absolute; top:50%; transform:translateY(-50%); font-size:11px;
    font-weight:700; padding:1px 5px; border-radius:9px; display:none;
    white-space:nowrap; }
  .delta.pos { background:#e7f6ec; color:#157347; }
  .delta.neg { background:#fdecec; color:#b42318; }
  .delta.ref { background:#111; color:#fff; }
  .row.active .name { font-weight:700; }
  .row.active .track { box-shadow:0 0 0 2px #111 inset; }

  /* normalized (multi-series) rows */
  .nrow { display:grid; grid-template-columns:220px 1fr; align-items:center;
    gap:10px; padding:5px 0; }
  .nrow .ntrack { position:relative; }
  .sbar { position:relative; height:7px; margin:1px 0; border-radius:0 3px 3px 0; }
  .sbar span { position:absolute; right:-2px; top:50%; transform:translate(100%,-50%);
    font-size:9px; color:#444; }
  .nref { position:absolute; top:0; bottom:0; width:2px; background:#c0392b; z-index:6; }

  table { border-collapse:collapse; width:100%; font-size:13px; }
  th,td { padding:6px 9px; border-bottom:1px solid var(--line); text-align:left; }
  th { cursor:pointer; user-select:none; background:#fafbfc; position:sticky; top:0; }
  th .arr { color:var(--muted); font-size:10px; }
  td.num { text-align:right; font-variant-numeric:tabular-nums; }
  .pill { display:inline-block; padding:1px 7px; border-radius:9px; font-size:11px;
    font-weight:600; }
  .pill.AMD { background:#fdecec; color:#b42318; }
  .pill.Intel { background:#e8f1fb; color:#1b5687; }
  #series-toggles { display:flex; flex-wrap:wrap; gap:6px 14px; max-width:560px; }
  #series-toggles label { display:inline-flex; align-items:center; gap:6px;
    font-weight:400; font-size:13px; cursor:pointer; }
  #series-toggles label.off { opacity:.45; }
  #series-toggles .sw { width:11px; height:11px; border-radius:3px; }
  #series-toggles small { color:var(--muted); }
  .legend { display:flex; gap:14px; font-size:12px; margin:6px 0 0; flex-wrap:wrap; }
  .legend i { display:inline-block; width:12px; height:12px; border-radius:3px;
    margin-right:4px; vertical-align:-1px; }
  .srcgrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr));
    gap:10px; }
  .srcgrid .s { border:1px solid var(--line); border-radius:8px; padding:10px 12px;
    min-width:0; overflow-wrap:anywhere; word-break:break-word; }
  .srcgrid .s b { font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12px;
    line-height:1.35; }
  .srcgrid .s a { color:#1b5687; text-decoration:none; }
  .srcgrid .s a:hover { text-decoration:underline; }
  .srcgrid .s small { color:var(--muted); }
  footer { color:var(--muted); font-size:12px; margin-top:30px; }
  code { background:#eef0f3; padding:1px 5px; border-radius:4px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Microsoft Flight Simulator 2024 — CPU Performance</h1>
  <p class="sub">Combined from Tom's Hardware (DX12, 1080p Ultra) and PCGH
    (CPU-limited scenes). Absolute FPS differ by site/scene — use
    <strong>Normalized</strong> mode to compare across sources.</p>

  <div class="card controls">
    <div><label>Mode</label>
      <span class="seg" id="mode">
        <button data-v="source">By source</button>
        <button data-v="norm" class="on">Normalized (all sites)</button>
      </span></div>
    <div id="ctl-source" class="controls" style="display:none; gap:18px">
      <div><label for="site">Site</label><select id="site"></select></div>
      <div><label for="view">View</label><select id="view"></select></div>
      <div><label>Metric</label>
        <span class="seg" id="metric">
          <button data-m="avg" class="on">Average FPS</button>
          <button data-m="low">1% Low</button>
        </span></div>
    </div>
    <div id="ctl-norm" class="controls" style="display:flex; gap:18px; align-items:flex-start">
      <div><label for="ref">100% reference CPU</label><select id="ref"></select>
        <div id="refnote" class="small" style="color:var(--muted); font-size:12px; margin-top:4px"></div></div>
      <div><label style="display:block; margin-bottom:4px">Bars</label>
        <span class="seg" id="normdisp">
          <button data-d="multi">Per dataset</button>
          <button data-d="avg" class="on">Averaged (1 bar)</button>
        </span></div>
      <div><label style="display:block; margin-bottom:4px">Datasets</label>
        <div id="series-toggles"></div></div>
    </div>
    <div class="hint" id="hint"></div>
  </div>

  <h2>Chart</h2>
  <div class="card"><div id="legend" class="legend"></div><div id="chart"></div></div>

  <h2>Sources</h2>
  <div class="srcgrid" id="sources"></div>

  <h2>Full data table</h2>
  <div class="card" style="overflow:auto; max-height:520px;">
    <table id="table"><thead></thead><tbody></tbody></table>
  </div>

  <footer>
    Same game across all charts, but re-measured over time and across sites, so a
    CPU's FPS drift between epochs/scenes and absolute numbers aren't comparable
    across sources. <b>By source</b> keeps things within one comparable set;
    <b>Normalized</b> rescales each series to a shared reference CPU.
    Generated from <code>msfs24_data.csv</code> + <code>pcgh_msfs24.csv</code> by
    <code>build_html.py</code>. Not affiliated with Tom's Hardware or PCGH.
  </footer>
</div>

<script>
const DATA = __DATA__;
const NORM_SERIES = __NORM__;   // [{name, color, site, group|null}]
const TH_EPOCH_CUTOFF = "2026-03";

const $ = s => document.querySelector(s);
let mode="norm", site=null, view=null, metric="avg", ref=null;
let enabled = NORM_SERIES.map(()=>true);   // which datasets are on in norm mode
let normAvg=true;                           // averaged single-bar vs per-dataset
const VENDOR={}; for(const r of DATA) if(!(r.cpu in VENDOR)) VENDOR[r.cpu]=r.vendor;

// Per-generation colors (AMD reds, Intel blues; 13th+14th share a color).
const GEN_COLOR={
  "Ryzen 3000":"#6e1714","Ryzen 5000":"#a32f26","Ryzen 7000":"#d6433b","Ryzen 9000":"#f47a63",
  "Core 11th":"#103a63","Core 12th":"#1f6fb0","Core 13/14th":"#3a9bdc","Core Ultra 2xx":"#7fc9ef"};
const GEN_ORDER=Object.keys(GEN_COLOR);
function genOf(cpu){
  if(cpu.startsWith("Ryzen")){
    const m=cpu.match(/Ryzen \d+ (\d)\d{3}/);
    return {"3":"Ryzen 3000","5":"Ryzen 5000","7":"Ryzen 7000","9":"Ryzen 9000"}[m?m[1]:""]||"Ryzen 7000";
  }
  if(cpu.includes("Core Ultra")) return "Core Ultra 2xx";
  const m=cpu.match(/Core i\d+-(\d{2})/); const g=m?m[1]:"";
  if(g==="11") return "Core 11th";
  if(g==="12") return "Core 12th";
  return "Core 13/14th";
}

// ---------- helpers ----------
function dedupNewest(rows){
  const best=new Map();
  for(const r of rows){ const c=best.get(r.cpu);
    if(!c || r.date>c.date) best.set(r.cpu,r); }
  return [...best.values()];
}
const SITES=[...new Set(DATA.map(r=>r.site))];
function groupsForSite(s){
  const gs=[...new Set(DATA.filter(r=>r.site===s).map(r=>r.group))];
  return gs.sort((a,b)=> minDate(s,a)<minDate(s,b)?-1:1);
}
function minDate(s,g){ return DATA.filter(r=>r.site===s&&r.group===g)
  .reduce((m,r)=> r.date<m?r.date:m, "9999"); }

function seriesMap(spec){           // {cpu: avg} for a normalized series
  let rows=DATA.filter(r=>r.site===spec.site);
  if(spec.group) rows=rows.filter(r=>r.group===spec.group);
  const m={}; for(const r of dedupNewest(rows)) m[r.cpu]=r.avg; return m;
}
function enabledSeries(){ return NORM_SERIES.filter((s,i)=>enabled[i]); }
function commonRefCpus(){
  const maps=enabledSeries().map(seriesMap);
  if(!maps.length) return [];
  return Object.keys(maps[0])
    .filter(c=>maps.every(m=>c in m))
    .sort((a,b)=> maps[0][b]-maps[0][a]);   // fastest (in first series) first
}

// ---------- controls ----------
$("#mode").addEventListener("click",e=>{
  const b=e.target.closest("button"); if(!b) return;
  mode=b.dataset.v;
  [...$("#mode").children].forEach(x=>x.classList.toggle("on",x===b));
  $("#ctl-source").style.display = mode==="source"?"flex":"none";
  $("#ctl-norm").style.display   = mode==="norm"?"flex":"none";
  render();
});
$("#metric").addEventListener("click",e=>{
  const b=e.target.closest("button"); if(!b) return;
  metric=b.dataset.m;
  [...$("#metric").children].forEach(x=>x.classList.toggle("on",x===b));
  render();
});
$("#normdisp").addEventListener("click",e=>{
  const b=e.target.closest("button"); if(!b) return;
  normAvg=b.dataset.d==="avg";
  [...$("#normdisp").children].forEach(x=>x.classList.toggle("on",x===b));
  renderNorm();
});
function buildSiteSelect(){
  site=SITES[0];
  $("#site").innerHTML=SITES.map(s=>`<option>${s}</option>`).join("");
  $("#site").onchange=()=>{ site=$("#site").value; buildViewSelect(); render(); };
  buildViewSelect();
}
function buildViewSelect(){
  const gs=groupsForSite(site);
  const lbl = site==="PCGH" ? "Scene" : "Epoch";
  const opts=[["combined","Combined — newest per CPU"],
    ...gs.map(g=>["g:"+g, lbl+": "+g]),
    ["all","All raw rows — no dedup"]];
  view="combined";
  $("#view").innerHTML=opts.map(([v,t])=>`<option value="${v}">${t}</option>`).join("");
  $("#view").onchange=()=>{ view=$("#view").value; render(); };
}
function buildSeriesToggles(){
  const box=$("#series-toggles");
  box.innerHTML=NORM_SERIES.map((s,i)=>`
    <label class="${enabled[i]?'':'off'}" data-i="${i}">
      <input type="checkbox" ${enabled[i]?'checked':''}>
      <span class="sw" style="background:${s.color}"></span>
      ${s.name} <small>(${s.span})</small>
    </label>`).join("");
  box.querySelectorAll("input").forEach(inp=>inp.onchange=e=>{
    const i=+e.target.closest("label").dataset.i;
    enabled[i]=e.target.checked;
    e.target.closest("label").classList.toggle("off",!enabled[i]);
    syncRefSelect(); renderNorm();
  });
}
function syncRefSelect(){
  const cpus=commonRefCpus();
  if(!cpus.includes(ref)) ref = cpus.includes("Ryzen 7 7800X3D")
    ? "Ryzen 7 7800X3D" : cpus[0] || null;
  $("#ref").innerHTML=cpus.map(c=>`<option ${c===ref?"selected":""}>${c}</option>`).join("");
  $("#ref").onchange=()=>{ ref=$("#ref").value; renderNorm(); };
  $("#refnote").textContent = cpus.length
    ? `${cpus.length} CPU(s) common to the enabled datasets`
    : "No CPU is common to all enabled datasets — disable a non-overlapping one.";
}

// ---------- dispatch ----------
function render(){ renderSources(); renderTable();
  if(mode==="norm") renderNorm(); else renderSource(); }

// ---------- by-source chart (dual bar + hover rebaseline) ----------
function sourceRows(){
  let rows=DATA.filter(r=>r.site===site);
  if(view==="all") return rows.slice();
  if(view==="combined") return dedupNewest(rows);
  return dedupNewest(rows.filter(r=>r.group===view.slice(2)));
}
function renderSource(){
  $("#legend").innerHTML="";
  const rows=sourceRows().filter(r=>r[metric]!=null)
    .sort((a,b)=>b[metric]-a[metric]);
  const axisMax=Math.max(...rows.map(r=>r.avg))*1.08;
  const dup=(view==="all");
  $("#hint").textContent=
    `${site} · ${rows.length} CPUs · ${metric==="avg"?"Average FPS":"1% Low"}`;
  const c=$("#chart"); c.innerHTML="";
  rows.forEach((r,i)=>{
    const wA=r.avg/axisMax*100, wL=(r.low??0)/axisMax*100;
    const row=document.createElement("div");
    row.className="row "+r.vendor.toLowerCase(); row.dataset.i=i;
    row.innerHTML=
      `<div class="name">${r.cpu}${r.x3d?' <span class="star">★</span>':''}`+
        (dup?` <span class="src">${r.date}</span>`:``)+`</div>
       <div class="track">
         <div class="bar avg" style="width:${wA}%"></div>
         ${r.low!=null?`<div class="bar low" style="width:${wL}%"></div>
            <div class="lowval" style="left:calc(${wL}% - 4px)">${fmt(r.low,0)}</div>`:``}
         <div class="val" style="left:calc(${wA}% + 6px)">${fmt(r.avg,1)}</div>
         <div class="refline"></div><div class="delta"></div>
       </div>`;
    row._data=r; row._barW=(r[metric]/axisMax*100);
    c.appendChild(row);
  });
  c.onmousemove=e=>{ const row=e.target.closest(".row");
    if(!row) return clearHover(); baseline(+row.dataset.i); };
  c.onmouseleave=clearHover;
}
function baseline(idx){
  const rows=[...$("#chart").children];
  const base=rows[idx]._data[metric];
  const axisMax=Math.max(...rows.map(r=>r._data.avg))*1.08;
  rows.forEach((row,i)=>{
    const v=row._data[metric], d=(v-base)/base*100;
    row.classList.toggle("active",i===idx);
    const line=row.querySelector(".refline");
    line.style.left=base/axisMax*100+"%"; line.style.display="block";
    const del=row.querySelector(".delta"); del.style.display="block";
    del.style.left=`calc(${row._barW}% + 6px)`;
    if(i===idx){ del.className="delta ref"; del.textContent="100%"; }
    else { del.className="delta "+(d>=0?"pos":"neg");
           del.textContent=(d>=0?"+":"")+d.toFixed(1)+"%"; }
    row.querySelector(".val").style.opacity=(i===idx)?1:0;
  });
}
function clearHover(){
  [...$("#chart").children].forEach(row=>{
    row.classList.remove("active");
    const rl=row.querySelector(".refline"); if(rl) rl.style.display="none";
    const dl=row.querySelector(".delta"); if(dl) dl.style.display="none";
    const vl=row.querySelector(".val"); if(vl) vl.style.opacity=1;
    const nr=row.querySelector(".nref"); if(nr) nr.style.display="";  // restore 100% line
  });
}

// Re-baseline the normalized-averaged chart: hovered CPU = 100%, others ±% vs it.
function avgBaseline(idx){
  const rows=[...$("#chart").children];
  const base=rows[idx]._v, axisMax=rows[idx]._axisMax;
  rows.forEach((row,i)=>{
    const v=row._v, d=(v-base)/base*100;
    row.classList.toggle("active",i===idx);
    row.querySelector(".nref").style.display="none";   // hide fixed ref while re-baselining
    const line=row.querySelector(".refline");
    line.style.left=base/axisMax*100+"%"; line.style.display="block";
    const del=row.querySelector(".delta"); del.style.display="block";
    del.style.left=`calc(${v/axisMax*100}% + 6px)`;
    if(i===idx){ del.className="delta ref"; del.textContent="100%"; }
    else { del.className="delta "+(d>=0?"pos":"neg");
           del.textContent=(d>=0?"+":"")+d.toFixed(1)+"%"; }
    row.querySelector(".val").style.opacity=(i===idx)?1:0;
  });
}

// ---------- normalized megachart ----------
let normInit=false;
function renderNorm(){
  if(!normInit){ buildSeriesToggles(); syncRefSelect(); normInit=true; }
  const c=$("#chart");
  const series=enabledSeries();
  if(!series.length || !ref){
    $("#legend").innerHTML=""; $("#hint").textContent="";
    c.innerHTML=`<p style="color:var(--muted)">Enable at least one dataset with a
      common reference CPU to draw the normalized chart.</p>`;
    return;
  }
  const maps=series.map(seriesMap);
  const norm=series.map((s,i)=>({...s,
    data:Object.fromEntries(Object.entries(maps[i]).map(([cp,v])=>[cp,v/maps[i][ref]*100]))}));
  $("#legend").innerHTML=norm.map(s=>
    `<span><i style="background:${s.color}"></i>${s.name}</span>`).join("");
  $("#hint").textContent=`${series.length} dataset(s) · each scaled so ${ref} = 100%`;

  const cpus=[...new Set(norm.flatMap(s=>Object.keys(s.data)))];
  const score=cp=>{ const v=norm.filter(s=>cp in s.data).map(s=>s.data[cp]);
    return v.reduce((a,b)=>a+b,0)/v.length; };
  const count=cp=>norm.filter(s=>cp in s.data).length;
  cpus.sort((a,b)=>score(b)-score(a));

  c.innerHTML="";
  if(normAvg){
    // One bar per CPU = mean of its normalized values across enabled datasets.
    const axisMax=Math.max(...cpus.map(score))*1.08;
    $("#hint").textContent+=" · 1 bar = mean across enabled datasets (·N = how many)";
    const gensPresent=GEN_ORDER.filter(g=>cpus.some(c=>genOf(c)===g));
    $("#legend").innerHTML=gensPresent.map(g=>
      `<span><i style="background:${GEN_COLOR[g]}"></i>${g}</span>`).join("")+
      `<span style="color:var(--muted)">red line = ${ref} (100%)</span>`;
    cpus.forEach((cpu,i)=>{
      const v=score(cpu), n=count(cpu), w=v/axisMax*100;
      const row=document.createElement("div"); row.className="row"; row.dataset.i=i;
      row.innerHTML=`<div class="name">${cpu}${cpu.toUpperCase().includes("X3D")?' <span class="star">★</span>':''}</div>
        <div class="track"><div class="nref" style="left:${100/axisMax*100}%"></div>
          <div class="bar avg" style="width:${w}%;background:${GEN_COLOR[genOf(cpu)]}"></div>
          <div class="val" style="left:calc(${w}% + 6px)">${v.toFixed(0)}<span style="color:var(--muted);font-weight:400"> ·${n}</span></div>
          <div class="refline"></div><div class="delta"></div>
        </div>`;
      row._v=v; row._axisMax=axisMax;
      c.appendChild(row);
    });
    // Hover any bar to re-baseline it to 100% and show others' relative ±%.
    c.onmousemove=e=>{ const row=e.target.closest(".row");
      if(!row) return clearHover(); avgBaseline(+row.dataset.i); };
    c.onmouseleave=clearHover;
    return;
  }
  c.onmousemove=null; c.onmouseleave=null;   // per-dataset layout: no hover
  const axisMax=Math.max(...norm.flatMap(s=>Object.values(s.data)))*1.06;
  cpus.forEach(cpu=>{
    const row=document.createElement("div"); row.className="nrow";
    const bars=norm.map(s=> s.data[cpu]==null?"":
      `<div class="sbar" style="width:${s.data[cpu]/axisMax*100}%;background:${s.color}">
         <span>${s.data[cpu].toFixed(0)}</span></div>`).join("");
    row.innerHTML=`<div class="name">${cpu}${cpu.toUpperCase().includes("X3D")?' <span class="star">★</span>':''}</div>
      <div class="ntrack"><div class="nref" style="left:${100/axisMax*100}%"></div>${bars}</div>`;
    c.appendChild(row);
  });
}

// ---------- sources + table ----------
function renderSources(){
  const map=new Map();
  for(const r of DATA){ const k=r.source;
    if(!map.has(k)) map.set(k,{site:r.site,date:r.date,group:r.group,url:r.url,n:0});
    map.get(k).n++; }
  const items=[...map.entries()].sort((a,b)=> a[1].date<b[1].date?1:-1);
  $("#sources").innerHTML=items.map(([src,m])=>{
    const title=m.url
      ? `<a href="${m.url}" target="_blank" rel="noopener noreferrer">${src} ↗</a>`
      : src;
    return `<div class="s"><div><b>${title}</b></div>
      <small>${m.site} · ${m.date}<br>${m.group} · ${m.n} CPUs</small></div>`;
  }).join("");
}
const COLS=[["cpu","CPU",0],["site","Site",0],["group","Epoch / Scene",0],
  ["avg","Avg",1],["low","1% Low",1],["p02","0.2% Low",1],
  ["date","Date",0],["source","Source",0]];
let sortKey="avg", sortDir=-1;
function renderTable(){
  const thead=$("#table thead"), tbody=$("#table tbody");
  thead.innerHTML="<tr>"+COLS.map(([k,l])=>{
    const a=k===sortKey?(sortDir<0?"▼":"▲"):"";
    return `<th data-k="${k}">${l} <span class="arr">${a}</span></th>`;}).join("")+"</tr>";
  thead.querySelectorAll("th").forEach(th=>th.onclick=()=>{
    const k=th.dataset.k;
    if(k===sortKey) sortDir*=-1; else{ sortKey=k; sortDir=COLS.find(c=>c[0]===k)[2]?-1:1; }
    renderTable(); });
  const rows=DATA.slice().sort((a,b)=>{
    let x=a[sortKey], y=b[sortKey];
    if(x==null)x=-Infinity; if(y==null)y=-Infinity;
    return (x<y?-1:x>y?1:0)*sortDir; });
  tbody.innerHTML=rows.map(r=>`<tr>
    <td>${r.cpu}${r.x3d?' <span class="star">★</span>':''}</td>
    <td>${r.site}</td><td>${r.group}</td>
    <td class="num">${fmt(r.avg,1)}</td>
    <td class="num">${r.low!=null?fmt(r.low,0):"–"}</td>
    <td class="num">${r.p02!=null?fmt(r.p02,0):"–"}</td>
    <td>${r.date}</td><td>${r.source}</td></tr>`).join("");
}
function fmt(x,d){ return Number(x).toFixed(d); }

buildSiteSelect(); render();
</script>
</body>
</html>
"""


# One normalized series per (site, group), so every dataset — old Tom's epochs
# included — is individually toggleable. Colors: Tom's = blues (newer darker),
# PCGH = warm tones.
PALETTE = {
    "Tom's Hardware": ["#9ecae1", "#4292c6", "#08519c", "#062f6b"],
    "PCGH": ["#8073ac", "#e08214", "#b35806", "#542788"],
    "ComputerBase": ["#2ca25f", "#006d2c"],
}
SHORT = {"Tom's Hardware": "TH", "PCGH": "PCGH", "ComputerBase": "CB"}
SITE_ORDER = ["Tom's Hardware", "PCGH", "ComputerBase"]


def build_norm_series(rows):
    series = []
    for site in [s for s in SITE_ORDER if any(r["site"] == s for r in rows)]:
        srows = [r for r in rows if r["site"] == site]
        groups = sorted({r["group"] for r in srows},
                        key=lambda g: min(r["date"] for r in srows
                                          if r["group"] == g))
        for i, g in enumerate(groups):
            dates = sorted({r["date"] for r in srows if r["group"] == g})
            span = dates[0] if len(dates) == 1 else f"{dates[0]} → {dates[-1]}"
            series.append({
                "name": f"{SHORT[site]} · {g}",
                "color": PALETTE[site][i % len(PALETTE[site])],
                "site": site, "group": g, "span": span,
            })
    return series


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--th", default="msfs24_data.csv")
    ap.add_argument("--pcgh", default="pcgh_msfs24.csv")
    ap.add_argument("--cbase", default="computerbase_msfs24.csv")
    ap.add_argument("--out", default="index.html")
    args = ap.parse_args()

    rows = load(args.th, "Tom's Hardware", "epoch") + load(args.pcgh, "PCGH", "scene")
    if os.path.exists(args.cbase):
        rows += load(args.cbase, "ComputerBase", "scene")
    norm_series = build_norm_series(rows)

    html = (TEMPLATE
            .replace("__DATA__", json.dumps(rows, separators=(",", ":"),
                                            ensure_ascii=False))
            .replace("__NORM__", json.dumps(norm_series, ensure_ascii=False)))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    from collections import Counter
    by_site = Counter(r["site"] for r in rows)
    breakdown = ", ".join(f"{n} {s}" for s, n in by_site.items())
    print(f"Wrote {args.out}  ({len(rows)} rows: {breakdown}; "
          f"{len(norm_series)} normalized datasets)")


if __name__ == "__main__":
    main()
