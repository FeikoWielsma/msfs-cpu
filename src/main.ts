/* MSFS 2024 CPU benchmark — app logic (TypeScript port of the original vanilla build). */
import "./style.css";

// ---------- data shapes ----------
interface Row {
  cpu: string;
  vendor: string;
  x3d: boolean;
  avg: number;
  low: number | null;
  p02: number | null;
  source: string;
  date: string;
  site: string;
  group: string;
  url: string;
  title: string;
}
interface NormSeries {
  name: string;
  color: string;
  site: string;
  group: string;
  span: string;
}
interface Spec {
  socket: string;
  arch: string;
  p: number;
  e: number;
  t: number;
  ccd: number;
  l3: number;
  vcache: boolean;
  clk: number;
}
interface AppData {
  rows: Row[];
  norm: NormSeries[];
  specs: Record<string, Spec>;
}
type SeriesWithData = NormSeries & { data: Record<string, number> };
interface IndexRow {
  cpu: string;
  vendor: string;
  x3d: boolean;
  raw: number;
  n: number;
  idx: number;
}

type Tab = "ranking" | "source";
type Metric = "avg" | "low";
type Brand = "all" | "AMD" | "Intel";

// Static presentation config (was window.TWEAKS inlined by the old generator).
const TWEAKS = { theme: "light", bars: "generation", density: "compact" } as const;

// ---------- data (populated by boot() once data.json is fetched) ----------
let DATA: Row[] = [];
let NORM_SERIES: NormSeries[] = [];
let SPECS: Record<string, Spec> = {};
const VENDOR: Record<string, string> = {};
let SITES: string[] = [];
let enabled: boolean[] = [];

// ---------- tiny helpers ----------
const $ = <T extends HTMLElement = HTMLElement>(s: string): T => document.querySelector(s) as T;
const el = (t: string, c?: string): HTMLElement => {
  const e = document.createElement(t);
  if (c) e.className = c;
  return e;
};
const fmt = (x: number, d: number): string => x.toFixed(d);
const isX3D = (c: string): boolean => /x3d/i.test(c);

// Compact core-config string from a spec, e.g. "8P+16E·32T", "8C/16T", "16C/32T·2CCD".
function coreStr(sp?: Partial<Spec>): string {
  if (!sp || sp.p == null) return "";
  if ((sp.e ?? 0) > 0) return `${sp.p}P+${sp.e}E·${sp.t}T`;
  let s = `${sp.p}C/${sp.t}T`;
  if ((sp.ccd ?? 1) > 1) s += `·${sp.ccd}CCD`;
  return s;
}

// ---------- state ----------
let tab: Tab = "ranking"; // ranking | source
let metric: Metric = "avg"; // avg | low
let brand: Brand = "all"; // all | AMD | Intel
let x3dOnly = false;
let selectedSockets: Set<string> = new Set();
let baseline: string | null = null; // pinned CPU (null = auto: leader = 100)
// by-source
let site = "";
let view = "combined";
// redesign preview state
let layout: "stacked" | "split" | "tip" | "tinted" = "tinted";
let showSocket = true;
let showCores = true;

// generation colours (for the "Gen" bar-colour tweak)
const GEN_COLOR: Record<string, string> = {
  "Ryzen 3000": "#6e1714", "Ryzen 5000": "#a32f26", "Ryzen 7000": "#d6433b", "Ryzen 9000": "#f47a63",
  "Core 11th": "#103a63", "Core 12th": "#1f6fb0", "Core 13/14th": "#3a9bdc", "Core Ultra 2xx": "#7fc9ef",
};
const GEN_ORDER = Object.keys(GEN_COLOR);
function genOf(cpu: string): string {
  if (cpu.startsWith("Ryzen")) {
    const m = cpu.match(/Ryzen \d+ (\d)\d{3}/);
    const map: Record<string, string> = { "3": "Ryzen 3000", "5": "Ryzen 5000", "7": "Ryzen 7000", "9": "Ryzen 9000" };
    return map[m ? m[1] : ""] || "Ryzen 7000";
  }
  if (cpu.includes("Core Ultra")) return "Core Ultra 2xx";
  const m = cpu.match(/Core i\d+-(\d{2})/);
  const g = m ? m[1] : "";
  if (g === "11") return "Core 11th";
  if (g === "12") return "Core 12th";
  return "Core 13/14th";
}

// ---------- data helpers ----------
function dedupNewest(rows: Row[]): Row[] {
  const best = new Map<string, Row>();
  for (const r of rows) { const c = best.get(r.cpu); if (!c || r.date > c.date) best.set(r.cpu, r); }
  return [...best.values()];
}
function groupsForSite(s: string): string[] {
  const gs = [...new Set(DATA.filter(r => r.site === s).map(r => r.group))];
  return gs.sort((a, b) => (minDate(s, a) < minDate(s, b) ? -1 : 1));
}
function minDate(s: string, g: string): string {
  return DATA.filter(r => r.site === s && r.group === g).reduce((m, r) => (r.date < m ? r.date : m), "9999");
}

function seriesData(spec: NormSeries, field: Metric): Record<string, number> {
  let rows = DATA.filter(r => r.site === spec.site && (!spec.group || r.group === spec.group));
  rows = dedupNewest(rows);
  const m: Record<string, number> = {};
  for (const r of rows) { const v = r[field]; if (v != null) m[r.cpu] = v; }
  return m;
}
function enabledSeries(): NormSeries[] { return NORM_SERIES.filter((_s, i) => enabled[i]); }

// Two-way additive fit in log space: log(value) = datasetOffset + cpuEffect.
function twowayFit(series: SeriesWithData[], cpus: string[], ref: string): Record<string, number> {
  const a = series.map(() => 0);
  const b: Record<string, number> = {};
  cpus.forEach(c => (b[c] = 0));
  for (let it = 0; it < 200; it++) {
    series.forEach((s, i) => {
      const e = Object.entries(s.data);
      a[i] = e.reduce((t, [c, v]) => t + Math.log(v) - b[c], 0) / e.length;
    });
    cpus.forEach(c => {
      const obs = series.map((s, i): [SeriesWithData, number] => [s, i]).filter(([s]) => c in s.data);
      b[c] = obs.reduce((t, [s, i]) => t + Math.log(s.data[c]) - a[i], 0) / obs.length;
    });
  }
  const out: Record<string, number> = {};
  const base = b[ref];
  cpus.forEach(c => (out[c] = Math.exp(b[c] - base) * 100));
  return out;
}

// ---- architectural "common sense" prior ---------------------------------
// Within one Intel microarchitecture, a higher-tier / higher-clocked / higher-
// binned part has strictly more cores, cache or clock, so in a CPU-bound game
// it can't be slower than a lesser sibling (a 14900KS can't trail a 14900K; a
// thinly-tested Core Ultra 5 235 can't outrank the 285K). Sparsely-covered SKUs
// get noisy cross-source scores that sometimes violate this. We snap each family
// back to its known order with a weighted isotonic regression (monotonic least-
// squares fit in log space, weighted by how many datasets cover each CPU), so
// well-tested parts barely move and thin ones fall into line. We deliberately do
// NOT constrain across architectures, nor AMD — there the spec ladder doesn't
// track gaming order (the 7800X3D beats the 7950X3D; V-Cache and single- vs
// dual-CCD upend it). Where the data genuinely can't separate same-silicon
// siblings they tie, which is the honest answer; the sort shows the newer first.
const BIN: Record<string, number> = { KS: 5, K: 4, KF: 4, F: 3, T: 1 };
function archKey(cpu: string): [string, number[]] | null {
  // [familyKey, rankTuple] (bigger tuple = faster) or null
  let m: RegExpMatchArray | null;
  if ((m = cpu.match(/^Core i(\d)-(1[1234])(\d)\d{2}([A-Z]*)$/)))
    return [
      +m[2] <= 11 ? "intel-rocket" : +m[2] === 12 ? "intel-alder" : "intel-raptor",
      [+m[1], +m[3], +m[2], BIN[m[4]] ?? 2],
    ]; // tier, sub-tier, gen, bin
  if ((m = cpu.match(/^Core Ultra (\d) (\d{3})([A-Z]*)/)))
    return ["intel-arrow", [+m[1], +m[2], BIN[m[3]] ?? 2]];
  return null;
}
const archCmp = (a: number[], b: number[]): number => {
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] - b[i];
  return 0;
};
function applyArchPrior(raw: Record<string, number>, series: SeriesWithData[]): void {
  const weight = (cp: string): number => Math.max(series.filter(s => cp in s.data).length, 1);
  const fams: Record<string, { cpu: string; key: number[] }[]> = {};
  for (const cpu of Object.keys(raw)) {
    const k = archKey(cpu);
    if (k) (fams[k[0]] ??= []).push({ cpu, key: k[1] });
  }
  for (const members of Object.values(fams)) {
    members.sort((x, y) => archCmp(x.key, y.key)); // weakest first
    const blocks: { v: number; w: number; cpus: string[] }[] = []; // pool adjacent violators (PAVA)
    for (const it of members) {
      blocks.push({ v: Math.log(raw[it.cpu]), w: weight(it.cpu), cpus: [it.cpu] });
      while (blocks.length >= 2 && blocks[blocks.length - 2].v > blocks[blocks.length - 1].v) {
        const b2 = blocks.pop()!, b1 = blocks.pop()!;
        blocks.push({
          v: (b1.v * b1.w + b2.v * b2.w) / (b1.w + b2.w),
          w: b1.w + b2.w, cpus: [...b1.cpus, ...b2.cpus],
        });
      }
    }
    for (const blk of blocks) for (const cpu of blk.cpus) raw[cpu] = Math.exp(blk.v);
  }
}
// Among equal scores (a tied isotonic block), show the architecturally higher part first.
function archTiebreak(a: string, b: string): number {
  const ka = archKey(a), kb = archKey(b);
  return ka && kb && ka[0] === kb[0] ? archCmp(kb[1], ka[1]) : 0;
}

// Same-silicon, clock-only sibling pairs [faster, slower]. These don't cross a
// tier the per-family prior can use (AMD is otherwise left to the data), but the
// ordering is physically guaranteed — identical die, higher clock — so we floor
// the faster part just above the slower, carrying the head-to-head margin where
// it's larger, else nudging it marginally ahead (0.2%) rather than inventing one.
const CLOCK_PAIRS: [string, string][] = [
  ["Ryzen 7 5800X3D", "Ryzen 7 5700X3D"], // Vermeer + V-Cache, clock bump
  ["Ryzen 5 7600X", "Ryzen 5 7500F"], // Raphael, clock bump
];
function applyClockPairs(raw: Record<string, number>, series: SeriesWithData[]): void {
  for (const [fast, slow] of CLOCK_PAIRS) {
    if (!(fast in raw) || !(slow in raw)) continue;
    const ratios = series.filter(s => fast in s.data && slow in s.data).map(s => s.data[fast] / s.data[slow]);
    const r = ratios.length ? Math.exp(ratios.reduce((t, x) => t + Math.log(x), 0) / ratios.length) : 1;
    raw[fast] = Math.max(raw[fast], raw[slow] * Math.max(r, 1.002));
  }
}

function enabledData(field: Metric): { valid: SeriesWithData[]; cpus: string[] } {
  const valid: SeriesWithData[] = enabledSeries()
    .map(s => ({ ...s, data: seriesData(s, field) }))
    .filter(s => Object.keys(s.data).length);
  const cpus = [...new Set(valid.flatMap(s => Object.keys(s.data)))];
  return { valid, cpus };
}
// Pre-prior cross-source fit (no sanity overrides) — used by the factor analysis,
// which wants what the measurements actually say, not the sanitised ranking.
function fitRaw(field: Metric): Record<string, number> {
  const { valid, cpus } = enabledData(field);
  return cpus.length ? twowayFit(valid, cpus, cpus[0]) : {};
}

// returns sorted [{cpu, vendor, x3d, raw, idx, n}]
function computeIndex(field: Metric): IndexRow[] {
  const { valid, cpus } = enabledData(field);
  if (!cpus.length) return [];
  const raw = twowayFit(valid, cpus, cpus[0]);
  applyArchPrior(raw, valid);
  applyClockPairs(raw, valid);
  const cnt = (cp: string): number => valid.filter(s => cp in s.data).length;
  const arr: IndexRow[] = cpus.map(cp => ({ cpu: cp, vendor: VENDOR[cp], x3d: isX3D(cp), raw: raw[cp], n: cnt(cp), idx: 0 }));
  arr.sort((x, y) => (Math.abs(y.raw - x.raw) > 1e-9 ? y.raw - x.raw : archTiebreak(x.cpu, y.cpu)));
  const anchor = baseline && baseline in raw ? raw[baseline] : arr[0].raw;
  arr.forEach(o => (o.idx = (o.raw / anchor) * 100));
  return arr;
}

function matchFilter(cpu: string, vendor: string): boolean {
  if (brand !== "all" && vendor !== brand) return false;
  if (x3dOnly && !isX3D(cpu)) return false;
  const sp = SPECS[cpu];
  if (selectedSockets.size > 0 && (!sp || !selectedSockets.has(sp.socket))) return false;
  return true;
}

// ---------- bar colour ----------
function fillStyle(cpu: string): string {
  const mode = document.documentElement.dataset.bars;
  if (mode === "generation") return `background:${GEN_COLOR[genOf(cpu)]}`;
  return ""; // vendor handled by class; mono uses default
}
function vendorClass(vendor: string): string {
  return document.documentElement.dataset.bars === "vendor" ? "vendor-" + vendor.toLowerCase() : "";
}

// ---------- shared bar row ----------
// Socket badge (vendor-tinted) + core-config badge + 3D V-Cache badge.
function badges(cpu: string, vendor: string): string {
  const sp = SPECS[cpu];
  let h = "";
  if (sp) {
    const tint = vendor === "AMD" ? "amd" : "intel";
    h += `<span class="badge sock ${tint}" title="${sp.arch} · ${sp.l3} MB L3 · up to ${sp.clk.toFixed(1)} GHz">${sp.socket}</span>`;
    const cs = coreStr(sp);
    if (cs) h += `<span class="badge cores" title="${sp.arch}">${cs}</span>`;
  }
  if (isX3D(cpu)) h += `<span class="badge x3d" title="3D V-Cache">3D</span>`;
  return h;
}

// redesign span helpers
function socketSpan(cpu: string, vendor: string): string {
  const sp = SPECS[cpu];
  if (!sp) return "";
  const tint = vendor === "AMD" ? "amd" : "intel";
  return `<span class="badge sock ${tint} b-sock" title="${sp.arch} · ${sp.l3} MB L3 · up to ${sp.clk.toFixed(1)} GHz">${sp.socket}</span>`;
}
function coresSpan(cpu: string): string {
  const sp = SPECS[cpu];
  if (!sp) return "";
  const cs = coreStr(sp);
  return cs ? `<span class="badge cores b-cores" title="${sp.arch}">${cs}</span>` : "";
}
function x3dSpan(_cpu: string): string {
  return "";
}
function baseSpan(o: { cpu: string }): string {
  return o.cpu === baseline ? `<span class="delta base b-base">baseline</span>` : "";
}

// ---------- render: ranking ----------
function renderRanking(): void {
  const all = computeIndex(metric);
  const visible = all.filter(o => matchFilter(o.cpu, o.vendor));
  setBaselineBar();

  const c = $("#chart");
  c.innerHTML = "";
  if (!enabledSeries().length) { c.innerHTML = `<div class="empty">Enable at least one dataset in <b>Advanced</b> to build the index.</div>`; return; }
  if (!visible.length) { c.innerHTML = `<div class="empty">No CPUs match these filters.</div>`; return; }

  // axis covers leader (or pinned-baseline overshoot) and 100 ref line
  const maxIdx = Math.max(...all.map(o => o.idx));
  // axis tops out at the leader so its bar always fills the track. maxIdx is the
  // leader's index: 100 when it's the anchor, >100 when a slower baseline is pinned.
  const axisMax = maxIdx;
  const redrawDelta = baseline != null;

  visible.forEach((o, i) => {
    const w = (o.idx / axisMax) * 100;
    const row = el("div", "barrow " + vendorClass(o.vendor));
    row.dataset.cpu = o.cpu;
    if (o.cpu === baseline) row.classList.add("pinned");

    const ref = maxIdx > 100 ? `<div class="reftick" style="left:${(100 / axisMax) * 100}%"></div>` : "";

    if (layout === "stacked") {
      const d = o.idx - 100;
      let deltaHtml = "";
      if (o.cpu === baseline) deltaHtml = `<span class="delta base">100% · baseline</span>`;
      else if (redrawDelta) deltaHtml = `<span class="delta ${d >= 0 ? "pos" : "neg"}">${d >= 0 ? "+" : ""}${d.toFixed(1)}%</span>`;
      row.innerHTML =
        `<div class="br-top">
             <span class="rank num">${i + 1}</span>
             <span class="cpu">${o.cpu}</span>
             <span class="meta">${badges(o.cpu, o.vendor)}</span>
             <span class="val">
               ${deltaHtml}
               <span class="big num">${o.idx.toFixed(0)}<span class="unit">%</span></span>
               <span class="sub num">·${o.n}</span>
             </span>
           </div>
           <div class="track">
             ${ref}
             <div class="fill" style="width:${w}%;${fillStyle(o.cpu)}"></div>
           </div>`;
    } else if (layout === "split") {
      row.innerHTML =
        `<span class="cpu">${o.cpu}</span><span class="metacell">${socketSpan(o.cpu, o.vendor)}${x3dSpan(o.cpu)}</span>${coresSpan(o.cpu)}${baseSpan(o)}
         <div class="track">${ref}<div class="fill" style="width:${w}%;${fillStyle(o.cpu)}"></div></div>
         <span class="val"><span class="big num">${o.idx.toFixed(0)}<span class="unit">%</span></span></span>`;
    } else if (layout === "tip") {
      const inside = w > 16;
      const tip = `<span class="tipval${inside ? "" : " outside"}">${o.idx.toFixed(0)}%</span>`;
      row.innerHTML =
        `<span class="cpu">${o.cpu}</span><span class="metacell">${socketSpan(o.cpu, o.vendor)}${x3dSpan(o.cpu)}</span>${coresSpan(o.cpu)}${baseSpan(o)}
         <div class="track">${ref}<div class="fill" style="width:${w}%;${fillStyle(o.cpu)}">${inside ? tip : ""}</div>${inside ? "" : tip}</div>`;
    } else if (layout === "tinted") {
      const cap = `<div class="heatcap" style="left:calc(${w}% - 3px);background:${GEN_COLOR[genOf(o.cpu)]}"></div>`;
      row.innerHTML =
        `<div class="heatrow">
           <div class="heatfill" style="width:${w}%;background:${GEN_COLOR[genOf(o.cpu)]}"></div>${cap}${ref}
           <div class="heat-tip-val num" style="left:${w}%;">${o.idx.toFixed(0)}%</div>
           <div class="heatcontent">
             <span class="cpu" style="display: flex; align-items: baseline; gap: 6px;">
               <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${o.cpu}</span>
               <span class="sub num" style="font-size: 11px; color: var(--muted); font-weight: 500; flex: none;">·${o.n}</span>
             </span>
             <span class="metacell">${socketSpan(o.cpu, o.vendor)}${x3dSpan(o.cpu)}</span>${coresSpan(o.cpu)}${baseSpan(o)}
           </div>
         </div>`;
    }

    row.addEventListener("click", () => toggleBaseline(o.cpu));
    c.appendChild(row);
  });
}

function setBaselineBar(): void {
  const bar = $("#baselineBar");
  if (baseline) { bar.classList.add("on"); $("#baselineName").textContent = baseline; }
  else bar.classList.remove("on");
}
function toggleBaseline(cpu: string): void {
  baseline = baseline === cpu ? null : cpu;
  render();
}

// ---------- render: by source ----------
function sourceRows(): Row[] {
  const rows = DATA.filter(r => r.site === site);
  if (view === "all") return rows.slice();
  if (view === "combined") return dedupNewest(rows);
  return dedupNewest(rows.filter(r => r.group === view.slice(2)));
}
function renderSource(): void {
  setBaselineBar();
  const rows = sourceRows()
    .filter(r => r[metric] != null && matchFilter(r.cpu, r.vendor))
    .sort((a, b) => b[metric]! - a[metric]!);
  const c = $("#chart");
  c.innerHTML = "";
  $("#chartSub").textContent = `${site} · ${rows.length} CPUs`;
  if (!rows.length) { c.innerHTML = `<div class="empty">No CPUs match these filters.</div>`; return; }
  const axisMax = Math.max(...rows.map(r => r.avg)); // leader fills the track
  const baseRow = baseline ? rows.find(r => r.cpu === baseline) : undefined;
  const base = baseRow ? baseRow[metric] : null;

  rows.forEach((r, i) => {
    const wA = (r.avg / axisMax) * 100, wL = ((r.low ?? 0) / axisMax) * 100;
    const row = el("div", "barrow " + vendorClass(r.vendor));
    row.dataset.cpu = r.cpu;
    if (r.cpu === baseline) row.classList.add("pinned");
    let deltaHtml = "";
    if (base != null) {
      if (r.cpu === baseline) deltaHtml = `<span class="delta base">baseline</span>`;
      else { const d = ((r[metric]! - base) / base) * 100; deltaHtml = `<span class="delta ${d >= 0 ? "pos" : "neg"}">${d >= 0 ? "+" : ""}${d.toFixed(1)}%</span>`; }
    }

    if (layout === "stacked") {
      row.innerHTML =
        `<div class="br-top">
             <span class="rank num">${i + 1}</span>
             <span class="cpu">${r.cpu}</span>
             <span class="meta">${badges(r.cpu, r.vendor)}</span>
             <span class="val">
               ${deltaHtml}
               <span class="big num">${fmt(r.avg, 1)}</span>
               ${r.low != null ? `<span class="sub num">${fmt(r.low, 0)} low</span>` : ""}
             </span>
           </div>
           <div class="track dual">
             <div class="seg-track avg"></div><div class="seg-track low"></div>
             <div class="fill avg" style="width:${wA}%;${fillStyle(r.cpu)}"></div>
             ${r.low != null ? `<div class="fill low" style="width:${wL}%;${fillStyle(r.cpu)}"></div>` : ""}
           </div>`;
    } else if (layout === "split") {
      row.innerHTML =
        `<span class="cpu">${r.cpu}</span><span class="metacell">${socketSpan(r.cpu, r.vendor)}${x3dSpan(r.cpu)}</span>${coresSpan(r.cpu)}${baseSpan(r)}
         <div class="track dual">
           <div class="seg-track avg"></div><div class="seg-track low"></div>
           <div class="fill avg" style="width:${wA}%;${fillStyle(r.cpu)}"></div>
           ${r.low != null ? `<div class="fill low" style="width:${wL}%;${fillStyle(r.cpu)}"></div>` : ""}
         </div>
         <span class="val">
           <span class="big num">${fmt(r.avg, 1)}</span>
           ${r.low != null ? `<span class="sub num">${fmt(r.low, 0)} low</span>` : ""}
         </span>`;
    } else if (layout === "tip") {
      const inside = wA > 20;
      const valStr = r.low != null ? `${fmt(r.avg, 1)}/${fmt(r.low, 0)}` : fmt(r.avg, 1);
      const tip = `<span class="tipval${inside ? "" : " outside"}" style="font-size: 10px; line-height: 1.1;">${valStr}</span>`;
      row.innerHTML =
        `<span class="cpu">${r.cpu}</span><span class="metacell">${socketSpan(r.cpu, r.vendor)}${x3dSpan(r.cpu)}</span>${coresSpan(r.cpu)}${baseSpan(r)}
         <div class="track dual">
           <div class="seg-track avg"></div><div class="seg-track low"></div>
           <div class="fill avg" style="width:${wA}%;${fillStyle(r.cpu)}">${inside ? tip : ""}</div>
           ${inside ? "" : tip}
           ${r.low != null ? `<div class="fill low" style="width:${wL}%;${fillStyle(r.cpu)}"></div>` : ""}
         </div>`;
    } else if (layout === "tinted") {
      const capA = `<div class="heatcap avg" style="left:calc(${wA}% - 3px);background:${GEN_COLOR[genOf(r.cpu)]}"></div>`;
      row.innerHTML =
        `<div class="heatrow dual">
           <div class="heatfill avg" style="width:${wA}%;background:${GEN_COLOR[genOf(r.cpu)]};opacity:0.18;"></div>
           ${r.low != null ? `<div class="heatfill low" style="width:${wL}%;background:${GEN_COLOR[genOf(r.cpu)]};opacity:0.08;top:50%;bottom:0;"></div>` : ""}
           ${capA}
           <div class="heat-val-tip num" style="left:${wA}%;">${fmt(r.avg, 1)}${r.low != null ? ` / ${fmt(r.low, 0)}` : ""}</div>
           <div class="heatcontent">
             <span class="cpu">${r.cpu}</span><span class="metacell">${socketSpan(r.cpu, r.vendor)}${x3dSpan(r.cpu)}</span>${coresSpan(r.cpu)}${baseSpan(r)}
           </div>
         </div>`;
    }

    row.addEventListener("click", () => toggleBaseline(r.cpu));
    c.appendChild(row);
  });
}

// ---------- legend ----------
function renderLegend(): void {
  const lg = $("#legend");
  const mode = document.documentElement.dataset.bars;
  if (tab === "ranking") {
    let items = "";
    if (mode === "generation") {
      const all = computeIndex(metric).filter(o => matchFilter(o.cpu, o.vendor));
      const present = GEN_ORDER.filter(g => all.some(o => genOf(o.cpu) === g));
      items = present.map(g => `<span><i style="background:${GEN_COLOR[g]}"></i>${g}</span>`).join("");
    } else if (mode === "vendor") {
      items = `<span><i style="background:var(--amd)"></i>AMD</span><span><i style="background:var(--intel)"></i>Intel</span>`;
    }
    lg.innerHTML = items;
  } else {
    lg.innerHTML = mode === "vendor"
      ? `<span><i style="background:var(--amd)"></i>AMD</span><span><i style="background:var(--intel)"></i>Intel</span><span style="opacity:.7">Upper bar = avg · lower = 1% low</span>`
      : `<span style="opacity:.7">Upper bar = average FPS · lower bar = 1% low</span>`;
  }
}

// ---------- factor analysis ----------
// Each factor isolates one variable via matched pairs [faster, slower] that are
// otherwise alike. Effect = mean % gap from the raw cross-source fit on the
// current metric, so it's what the measurements say, before the sanity priors.
interface FactorDef { name: string; sub: string; pairs: [string, string][]; }
interface FactorRow extends FactorDef { eff: number; ds: { a: string; b: string; pct: number }[]; }
const FACTORS: FactorDef[] = [
  { name: "3D V-Cache", sub: "+64 MB stacked L3 — same cores & architecture",
    pairs: [["Ryzen 7 9800X3D", "Ryzen 7 9700X"], ["Ryzen 7 7800X3D", "Ryzen 7 7700X"],
            ["Ryzen 5 7600X3D", "Ryzen 5 7600X"], ["Ryzen 7 5800X3D", "Ryzen 7 5800X"]] },
  { name: "Newer architecture", sub: "Zen 3 → 4 → 5, 8-core X3D — IPC + clock + cache",
    pairs: [["Ryzen 7 9800X3D", "Ryzen 7 7800X3D"], ["Ryzen 7 7800X3D", "Ryzen 7 5800X3D"]] },
  { name: "8 cores vs 6", sub: "+2 cores, architecture & cache held constant",
    pairs: [["Ryzen 7 7800X3D", "Ryzen 5 7600X3D"], ["Ryzen 7 7700X", "Ryzen 5 7600X"],
            ["Ryzen 7 9700X", "Ryzen 5 9600X"]] },
  { name: "16 cores / 2nd CCD vs 8", sub: "dual-CCD flagship vs the 8-core X3D",
    pairs: [["Ryzen 9 9950X3D", "Ryzen 7 9800X3D"], ["Ryzen 9 7950X3D", "Ryzen 7 7800X3D"]] },
  { name: "Higher clock", sub: "identical silicon, more MHz",
    pairs: [["Ryzen 7 9850X3D", "Ryzen 7 9800X3D"], ["Core i9-14900KS", "Core i9-14900K"]] },
  { name: "Best X3D vs best Intel", sub: "8-core X3D vs the Intel flagships",
    pairs: [["Ryzen 7 9800X3D", "Core i9-14900K"], ["Ryzen 7 9800X3D", "Core Ultra 9 285K"]] },
];
const shortName = (c: string): string => c.replace(/^Ryzen \d+ /, "").replace(/^Core (Ultra \d+|i\d)[- ]/, "");

function renderAnalysis(): void {
  const raw = fitRaw(metric);
  const has = (c: string): boolean => c in raw;
  const rows: FactorRow[] = FACTORS.map((f): FactorRow | null => {
    const ds = f.pairs.filter(([a, b]) => has(a) && has(b)).map(([a, b]) => ({ a, b, pct: (raw[a] / raw[b] - 1) * 100 }));
    if (!ds.length) return null;
    return { ...f, eff: ds.reduce((t, d) => t + d.pct, 0) / ds.length, ds };
  }).filter((r): r is FactorRow => r !== null);
  const box = $("#factorTable");
  if (!rows.length) { box.innerHTML = `<div class="empty">Enable a dataset to compute the factors.</div>`; return; }
  const maxAbs = Math.max(1, ...rows.map(r => Math.abs(r.eff)));
  const cls = (e: number): string => (e >= 2 ? "pos" : e <= -2 ? "neg" : "flat");
  const sign = (e: number): string => (e >= 0 ? "+" : "") + e.toFixed(1) + "%";
  const ex = (ds: FactorRow["ds"]): string =>
    ds.map(d => `<b>${shortName(d.a)}</b> vs ${shortName(d.b)} ${(d.pct >= 0 ? "+" : "")}${d.pct.toFixed(0)}%`).join(" &nbsp;·&nbsp; ");
  box.innerHTML = `<div class="factors">` + rows.map(r => {
    const w = (Math.abs(r.eff) / maxAbs) * 50, left = r.eff >= 0 ? 50 : 50 - w;
    return `<div class="frow">
        <div><div class="fname">${r.name}</div><div class="fsub">${r.sub}</div></div>
        <div class="feffect ${cls(r.eff)}">${sign(r.eff)}</div>
        <div class="fbar"><div class="fbar-zero"></div>
          <div class="fbar-fill ${r.eff >= 0 ? "pos" : "neg"}" style="left:${left}%;width:${w}%"></div></div>
        <div class="fex">${ex(r.ds)}</div>
      </div>`;
  }).join("") + `</div>`;
  const metricLbl = metric === "avg" ? "average FPS" : "1% lows";
  $("#analysisIntro").innerHTML = `Each row isolates <b>one variable</b> by comparing CPUs that are
      otherwise matched — same vendor, similar cores, ± one thing — using the measured cross-source fit
      on <b>${metricLbl}</b>. Bars are relative; the % is the average gap across the listed pairs.`;
  $("#analysisNote").innerHTML = `<b>Takeaway:</b> MSFS&nbsp;2024 lives on a <b>big L3 cache and a few
      fast cores</b>. 3D V-Cache is by far the biggest lever and a newer Zen generation helps a lot.
      Core count <b>scales up to about eight, then reverses</b> — a second CCD (16-core parts) and Intel's
      E-cores mostly sit idle or add cross-die latency, so the 16-core X3D chips trail the 8-core ones.
      Clock speed barely moves the needle. Net: the sweet spot is an <b>8-core X3D</b> (a 6-core X3D is
      the value pick). Switch the metric to <b>1% Low</b> to watch the cache advantage grow.`;
}

// ---------- sources + table ----------
function renderSources(): void {
  const map = new Map<string, { site: string; date: string; group: string; url: string; title: string; n: number }>();
  for (const r of DATA) {
    const k = r.source;
    if (!map.has(k)) map.set(k, { site: r.site, date: r.date, group: r.group, url: r.url, title: r.title, n: 0 });
    map.get(k)!.n++;
  }
  const items = [...map.entries()].sort((a, b) => (a[1].date < b[1].date ? 1 : -1));
  $("#srcCount").textContent = items.length + " reviews";
  $("#sources").innerHTML = items.map(([src, m]) => {
    const label = m.title || src;
    const head = m.url ? `<a href="${m.url}" target="_blank" rel="noopener noreferrer">${label} ↗</a>` : label;
    return `<div class="s"><b>${head}</b><small>${m.site} · ${m.date} · ${m.group} · ${m.n} CPUs</small></div>`;
  }).join("");
}

// Each measurement row, enriched with the CPU's specs. get() → cell html,
// sort() → sort value, num → right-aligned/numeric (default sort descending).
const spec = (cpu: string): Partial<Spec> => SPECS[cpu] ?? {};
interface Col { k: string; l: string; num?: boolean; mono?: boolean; get: (r: Row) => string | number; sort: (r: Row) => string | number; }
const COLS: Col[] = [
  { k: "cpu", l: "CPU", get: r => `${r.cpu}${r.x3d ? ' <span class="badge x3d">3D</span>' : ""}`, sort: r => r.cpu },
  { k: "socket", l: "Socket", get: r => spec(r.cpu).socket || "–", sort: r => spec(r.cpu).socket || "" },
  { k: "arch", l: "Arch", get: r => spec(r.cpu).arch || "–", sort: r => spec(r.cpu).arch || "" },
  { k: "config", l: "Cores", mono: true, get: r => coreStr(spec(r.cpu)) || "–", sort: r => (spec(r.cpu).p || 0) + (spec(r.cpu).e || 0) },
  { k: "t", l: "Threads", num: true, get: r => spec(r.cpu).t ?? "–", sort: r => spec(r.cpu).t ?? -1 },
  { k: "l3", l: "L3 MB", num: true, get: r => spec(r.cpu).l3 ?? "–", sort: r => spec(r.cpu).l3 ?? -1 },
  { k: "clk", l: "Boost", num: true, get: r => { const c = spec(r.cpu).clk; return c != null ? c.toFixed(1) : "–"; }, sort: r => spec(r.cpu).clk ?? -1 },
  { k: "avg", l: "Avg", num: true, get: r => fmt(r.avg, 1), sort: r => r.avg },
  { k: "low", l: "1% Low", num: true, get: r => (r.low != null ? fmt(r.low, 0) : "–"), sort: r => r.low ?? -Infinity },
  { k: "p02", l: "0.2% Low", num: true, get: r => (r.p02 != null ? fmt(r.p02, 0) : "–"), sort: r => r.p02 ?? -Infinity },
  { k: "site", l: "Site", get: r => r.site, sort: r => r.site },
  { k: "group", l: "Scene / Epoch", get: r => r.group, sort: r => r.group },
  { k: "date", l: "Date", get: r => r.date, sort: r => r.date },
];
let sortKey = "avg", sortDir = -1;
const tFilter = { socket: "all", arch: "all", x3d: false, q: "" };

function tableRows(): Row[] {
  return DATA.filter(r => {
    const s = spec(r.cpu);
    if (tFilter.socket !== "all" && s.socket !== tFilter.socket) return false;
    if (tFilter.arch !== "all" && s.arch !== tFilter.arch) return false;
    if (tFilter.x3d && !r.x3d) return false;
    if (tFilter.q && !r.cpu.toLowerCase().includes(tFilter.q)) return false;
    return true;
  });
}
function renderTable(): void {
  const col = COLS.find(c => c.k === sortKey) || COLS[0];
  const rows = tableRows().sort((a, b) => {
    const x: number | string = col.sort(a), y: number | string = col.sort(b);
    return (x < y ? -1 : x > y ? 1 : 0) * sortDir;
  });
  $("#rowCount").textContent = rows.length === DATA.length ? `${DATA.length} rows` : `${rows.length} of ${DATA.length} rows`;
  const thead = $("#table thead"), tbody = $("#table tbody");
  thead.innerHTML = "<tr>" + COLS.map(c => {
    const a = c.k === sortKey ? (sortDir < 0 ? "▼" : "▲") : "";
    return `<th data-k="${c.k}" class="${c.num ? "tnum" : ""}">${c.l} <span class="arr">${a}</span></th>`;
  }).join("") + "</tr>";
  thead.querySelectorAll("th").forEach(th => (th.onclick = () => {
    const k = th.dataset.k!;
    if (k === sortKey) sortDir *= -1;
    else { sortKey = k; sortDir = COLS.find(c => c.k === k)!.num ? -1 : 1; }
    renderTable();
  }));
  tbody.innerHTML = rows.map(r => "<tr>" + COLS.map(c =>
    `<td class="${c.num ? "tnum num" : ""}${c.mono ? " num" : ""}">${c.get(r)}</td>`).join("") + "</tr>").join("");
}
function buildTableFilters(): void {
  const order = (vals: (string | undefined)[], pref: string[]): string[] =>
    [...new Set(vals)].filter((x): x is string => Boolean(x))
      .sort((a, b) => (pref.indexOf(a) + 1 || 99) - (pref.indexOf(b) + 1 || 99) || (a < b ? -1 : 1));
  const sockets = order(DATA.map(r => spec(r.cpu).socket), ["AM5", "AM4", "LGA1851", "LGA1700", "LGA1200"]);
  const archs = order(DATA.map(r => spec(r.cpu).arch),
    ["Zen 5", "Zen 4", "Zen 3", "Zen 2", "Arrow Lake", "Raptor Lake", "Alder Lake", "Rocket Lake"]);
  $("#tSocket").innerHTML = `<option value="all">All sockets</option>` + sockets.map(s => `<option>${s}</option>`).join("");
  $("#tArch").innerHTML = `<option value="all">All archs</option>` + archs.map(s => `<option>${s}</option>`).join("");
  $<HTMLSelectElement>("#tSocket").onchange = e => { tFilter.socket = (e.target as HTMLSelectElement).value; renderTable(); };
  $<HTMLSelectElement>("#tArch").onchange = e => { tFilter.arch = (e.target as HTMLSelectElement).value; renderTable(); };
  $<HTMLInputElement>("#tX3D").onchange = e => { tFilter.x3d = (e.target as HTMLInputElement).checked; renderTable(); };
  $("#tSearch").addEventListener("input", e => { tFilter.q = (e.target as HTMLInputElement).value.trim().toLowerCase(); renderTable(); });
}
function buildMainSocketFilter(): void {
  const order = (vals: (string | undefined)[], pref: string[]): string[] =>
    [...new Set(vals)].filter((x): x is string => Boolean(x))
      .sort((a, b) => (pref.indexOf(a) + 1 || 99) - (pref.indexOf(b) + 1 || 99) || (a < b ? -1 : 1));
  const sockets = order(DATA.map(r => spec(r.cpu).socket), ["AM5", "AM4", "LGA1851", "LGA1700", "LGA1200"]);
  const container = $("#brandChips");
  sockets.forEach(s => {
    const btn = el("button", "chip") as HTMLButtonElement;
    btn.dataset.socket = s;
    btn.textContent = s;
    container.appendChild(btn);
  });
}

// ---------- datasets (advanced) ----------
function buildDatasetList(): void {
  const box = $("#dsList");
  box.innerHTML = NORM_SERIES.map((s, i) => `
      <label class="ds-item ${enabled[i] ? "" : "off"}" data-i="${i}">
        <input type="checkbox" ${enabled[i] ? "checked" : ""}>
        <span class="sw" style="background:${s.color}"></span>
        <span>${s.name}</span>
        <span class="ds-meta">${s.span}</span>
      </label>`).join("");
  box.querySelectorAll("input").forEach(inp => (inp.onchange = e => {
    const lbl = (e.target as HTMLElement).closest("label") as HTMLElement;
    const i = +(lbl.dataset.i ?? 0);
    enabled[i] = (e.target as HTMLInputElement).checked;
    lbl.classList.toggle("off", !enabled[i]);
    // if pinned baseline drops out of the data, clear it
    render();
  }));
}

// ---------- by-source selects ----------
function buildSiteSelect(): void {
  site = SITES[0];
  $("#site").innerHTML = SITES.map(s => `<option>${s}</option>`).join("");
  $<HTMLSelectElement>("#site").onchange = () => { site = $<HTMLSelectElement>("#site").value; buildViewSelect(); render(); };
  buildViewSelect();
}
function buildViewSelect(): void {
  const gs = groupsForSite(site);
  const lbl = site === "PCGH" ? "Scene" : site === "ComputerBase" ? "Scene" : "Epoch";
  $("#viewLabel").textContent = lbl;
  const opts: [string, string][] = [["combined", "Newest per CPU"], ...gs.map((g): [string, string] => ["g:" + g, g]), ["all", "All raw rows"]];
  view = "combined";
  $("#view").innerHTML = opts.map(([v, t]) => `<option value="${v}">${t}</option>`).join("");
  $<HTMLSelectElement>("#view").onchange = () => { view = $<HTMLSelectElement>("#view").value; render(); };
}

// ---------- dispatch ----------
function render(): void {
  renderLegend();
  if (tab === "ranking") {
    $("#chartTitle").textContent = "Performance Index";
    $("#chartSub").textContent = "";
    $("#datasetCount").textContent = `${enabledSeries().length} of ${NORM_SERIES.length} datasets`;
    $("#datasetCount").style.display = "";
    renderRanking();
  } else {
    $("#chartTitle").textContent = "By source";
    $("#datasetCount").textContent = "";
    $("#datasetCount").style.display = "none";
    renderSource();
  }
  renderAnalysis();
}

// ---------- controls wiring ----------
function wireControls(): void {
  $("#tabs").addEventListener("click", e => {
    const b = (e.target as HTMLElement).closest("button");
    if (!b) return;
    tab = b.dataset.tab as Tab;
    [...$("#tabs").children].forEach(x => x.classList.toggle("on", x === b));
    $("#sourceCtl").style.display = tab === "source" ? "flex" : "none";
    $("#advToggleBtn").style.display = tab === "ranking" ? "" : "none";
    if (tab === "source") {
      $("#advBodyPanel").style.display = "none";
      $("#advToggleBtn").classList.remove("on");
    }
    baseline = null;
    render();
  });
  $("#advToggleBtn").addEventListener("click", () => {
    const btn = $("#advToggleBtn");
    const panel = $("#advBodyPanel");
    const isOpen = btn.classList.toggle("on");
    panel.style.display = isOpen ? "block" : "none";
  });
  $("#metricSeg").addEventListener("click", e => {
    const b = (e.target as HTMLElement).closest("button");
    if (!b) return;
    metric = b.dataset.m as Metric;
    [...$("#metricSeg").children].forEach(x => x.classList.toggle("on", x === b));
    render();
  });
  $("#brandChips").addEventListener("click", e => {
    const b = (e.target as HTMLElement).closest("button");
    if (!b) return;
    
    if (b.dataset.brand === "all") {
      brand = "all";
      selectedSockets.clear();
      x3dOnly = false;
    } else if (b.dataset.brand) {
      const newBrand = b.dataset.brand as Brand;
      brand = brand === newBrand ? "all" : newBrand;
    } else if (b.dataset.x3d) {
      x3dOnly = !x3dOnly;
    } else if (b.dataset.socket) {
      const socket = b.dataset.socket;
      if (selectedSockets.has(socket)) {
        selectedSockets.delete(socket);
      } else {
        selectedSockets.add(socket);
      }
    }
    
    const chips = [...$("#brandChips").children];
    const hasActiveFilters = brand !== "all" || selectedSockets.size > 0 || x3dOnly;
    
    chips.forEach(x => {
      const btn = x as HTMLButtonElement;
      if (btn.dataset.brand === "all") {
        btn.classList.toggle("on", !hasActiveFilters);
      } else if (btn.dataset.brand) {
        const isMatch = btn.dataset.brand === brand;
        btn.classList.toggle("on", isMatch);
        btn.classList.toggle("amd", isMatch && brand === "AMD");
        btn.classList.toggle("intel", isMatch && brand === "Intel");
      } else if (btn.dataset.x3d) {
        btn.classList.toggle("on", x3dOnly);
      } else if (btn.dataset.socket) {
        btn.classList.toggle("on", btn.dataset.socket ? selectedSockets.has(btn.dataset.socket) : false);
      }
    });
    
    render();
  });
  $("#resetBaseline").addEventListener("click", () => { baseline = null; render(); });

  // redesign controls
  const NOTES = {
    stacked: "The original: CPU name + value on one line, a full-width bar beneath. Roomy, but every CPU costs two lines of height.",
    split: "Name and badges sit in a fixed-width column on the left so every bar starts at the same x — the bar fills the rest of the row, value pinned right. One line per CPU, still a wide bar, and bar-starts stay aligned for easy scanning.",
    tip: "Like Split, but the % rides the leading edge of its own bar instead of a separate column — the number tracks the length. Short bars flip the label outside so it stays readable.",
    tinted: "Densest. The whole row is the bar: a soft generation-tinted fill behind the label, with a crisp cap marking the exact value and the name + % overlaid in ink."
  };

  $("#layoutSeg").addEventListener("click", e => {
    const b = (e.target as HTMLElement).closest("button");
    if (!b) return;
    layout = b.dataset.layout as typeof layout;
    [...$("#layoutSeg").children].forEach(x => x.classList.toggle("on", x === b));
    const noteEl = $("#dbNote");
    if (noteEl) noteEl.innerHTML = NOTES[layout] || "";
    document.documentElement.dataset.layout = layout;
    render();
  });

  $("#showSocketToggle").addEventListener("change", e => {
    showSocket = (e.target as HTMLInputElement).checked;
    document.documentElement.classList.toggle("hide-socket", !showSocket);
  });

  $("#showCoresToggle").addEventListener("change", e => {
    showCores = (e.target as HTMLInputElement).checked;
    document.documentElement.classList.toggle("hide-cores", !showCores);
  });
}

// ---------- tweaks ----------
function applyTweaks(): void {
  const root = document.documentElement;
  root.dataset.theme = TWEAKS.theme;
  root.dataset.bars = TWEAKS.bars;
  root.dataset.density = TWEAKS.density;
  root.dataset.layout = layout;
}

// ---------- boot ----------
async function boot(): Promise<void> {
  const res = await fetch(`${import.meta.env.BASE_URL}data.json`, { cache: "no-cache" });
  const data = (await res.json()) as AppData;
  DATA = data.rows;
  NORM_SERIES = data.norm;
  SPECS = data.specs;
  for (const r of DATA) if (!(r.cpu in VENDOR)) VENDOR[r.cpu] = r.vendor;
  SITES = [...new Set(DATA.map(r => r.site))];
  enabled = NORM_SERIES.map(() => true);

  applyTweaks();
  wireControls();
  buildDatasetList();
  buildSiteSelect();
  buildTableFilters();
  buildMainSocketFilter();
  renderSources();
  renderTable();
  render();
}

boot();
