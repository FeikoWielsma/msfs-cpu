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
  resolution?: string; // GPU only — "1440p" | "1080p" | "4K"
  url: string;
  title: string;
}
interface NormSeries {
  name: string;
  color: string;
  site: string;
  group: string;
  groups?: string[];   // GPU merged epoch — list of source-image group keys
  resolution?: string; // GPU only
  span: string;
}
interface Spec {
  // CPU fields
  socket: string;
  arch: string;
  p: number;
  e: number;
  t: number;
  ccd: number;
  l3: number;
  vcache: boolean;
  clk: number;
  // GPU fields
  vram?: number;   // GB
  pcie?: string;   // e.g. "5.0×8"
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

type Tab = "ranking" | "source" | "1080p Ultra" | "1440p Ultra" | "4K Ultra";
type GpuMode = "fps" | "index";
type Metric = "avg" | "low";
type Brand = "all" | "AMD" | "Intel" | "Nvidia";

let theme = localStorage.getItem("msfs-theme") || "dark";
const TWEAKS = { bars: "generation", density: "compact" } as const;

// ---------- data (populated by boot() once data.json is fetched) ----------
let DATA: Row[] = [];
let NORM_SERIES: NormSeries[] = [];
let SPECS: Record<string, Spec> = {};
let VENDOR: Record<string, string> = {};
let SITES: string[] = [];
let enabled: boolean[] = [];

let CPU_DATA: AppData | null = null;
let GPU_DATA: AppData | null = null;
let hardware: "cpu" | "gpu" = "cpu";
let gpuMode: GpuMode = "index";

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
// GPU filters are multi-select: vendors and VRAM buckets (10 & 12 GB share a bucket).
let selectedVendors: Set<string> = new Set();
let selectedVram: Set<string> = new Set();
const vramBucket = (v: number): string => (v === 10 || v === 12 ? "10–12" : String(v));
let baseline: string | null = null; // pinned CPU (null = auto: leader = 100)
// by-source
let site = "";
let view = "combined";
// redesign preview state
const layout = "tip";
let showSocket = true;
let showCores = true;

// generation colours (for the "Gen" bar-colour tweak)
const GEN_COLOR: Record<string, string> = {
  "Ryzen 3000": "#6e1714", "Ryzen 5000": "#a32f26", "Ryzen 7000": "#d6433b", "Ryzen 9000": "#f47a63",
  "Core 11th": "#103a63", "Core 12th": "#1f6fb0", "Core 13/14th": "#3a9bdc", "Core Ultra 2xx": "#7fc9ef",
  "RTX 30": "#3a6600", "RTX 40": "#568700", "RTX 50": "#76b900",
  "RX 6000": "#7a1715", "RX 7000": "#a32320", "RX 9000": "#e63935", "Arc B": "#0087c2", "Arc A": "#103a63"
};
const GEN_ORDER = Object.keys(GEN_COLOR);
function genOf(cpu: string): string {
  if (hardware === "gpu") {
    if (cpu.includes("RTX 5")) return "RTX 50";
    if (cpu.includes("RTX 4")) return "RTX 40";
    if (cpu.includes("RTX 3")) return "RTX 30";
    if (cpu.includes("RX 9")) return "RX 9000";
    if (cpu.includes("RX 7")) return "RX 7000";
    if (cpu.includes("RX 6")) return "RX 6000";
    if (cpu.includes("Arc B")) return "Arc B";
    if (cpu.includes("Arc A")) return "Arc A";
    return "RTX 40";
  }
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
function groupsForSite(s: string, resolution?: string): string[] {
  const gs = [...new Set(DATA.filter(r => r.site === s && (!resolution || r.resolution === resolution)).map(r => r.group))];
  return gs.sort((a, b) => (minDate(s, a) < minDate(s, b) ? -1 : 1));
}
function minDate(s: string, g: string): string {
  return DATA.filter(r => r.site === s && r.group === g).reduce((m, r) => (r.date < m ? r.date : m), "9999");
}

function seriesData(spec: NormSeries, field: Metric): Record<string, number> {
  const matchGroups = spec.groups ?? (spec.group ? [spec.group] : null);
  let rows = DATA.filter(r => r.site === spec.site && (!matchGroups || matchGroups.includes(r.group)));
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
  const sp = SPECS[cpu];
  if (hardware === "gpu") {
    if (selectedVendors.size > 0 && !selectedVendors.has(vendor)) return false;
    if (selectedVram.size > 0 && (sp?.vram == null || !selectedVram.has(vramBucket(sp.vram)))) return false;
    return true;
  }
  if (brand !== "all" && vendor !== brand) return false;
  if (x3dOnly && !isX3D(cpu)) return false;
  if (selectedSockets.size > 0 && (!sp || !selectedSockets.has(sp.socket))) return false;
  return true;
}

// ---------- bar colour ----------
function fillStyle(cpu: string): string {
  const mode = document.documentElement.dataset.bars;
  if (mode === "generation") return `background:${GEN_COLOR[genOf(cpu)] || "var(--line)"}`;
  return ""; // vendor handled by class; mono uses default
}
function vendorClass(vendor: string): string {
  return document.documentElement.dataset.bars === "vendor" ? "vendor-" + vendor.toLowerCase() : "";
}

// ---------- shared bar row ----------

// redesign span helpers
function socketSpan(cpu: string, vendor: string): string {
  const sp = SPECS[cpu];
  if (!sp) return "";
  const tint = vendor === "AMD" ? "amd" : vendor === "Intel" ? "intel" : "nvidia";
  if (hardware === "gpu") {
    return sp.vram ? `<span class="badge sock b-sock vram-${sp.vram}">${sp.vram}GB</span>` : "";
  }
  if (Object.keys(sp).length === 0) return "";
  return `<span class="badge sock ${tint} b-sock" title="${sp.arch} · ${sp.l3} MB L3 · up to ${sp.clk.toFixed(1)} GHz">${sp.socket}</span>`;
}

function coreStrSpan(cpu: string, inside: boolean): string {
  const sp = SPECS[cpu];
  if (!sp || Object.keys(sp).length === 0) return "";
  const cls = inside ? "bar-cores-inside" : "bar-cores-outside";
  if (hardware === "gpu") {
    return sp.pcie ? `<span class="bar-cores b-cores ${cls}">${sp.pcie}</span>` : "";
  }
  const cs = coreStr(sp);
  return cs ? `<span class="bar-cores b-cores ${cls}" title="${sp.arch}">${cs}</span>` : "";
}
function x3dSpan(_cpu: string): string {
  return "";
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

  visible.forEach((o) => {
    const w = (o.idx / axisMax) * 100;
    const row = el("div", "barrow " + vendorClass(o.vendor));
    row.dataset.cpu = o.cpu;
    if (o.cpu === baseline) row.classList.add("pinned");

    const ref = maxIdx > 100 ? `<div class="reftick" style="left:${(100 / axisMax) * 100}%"></div>` : "";

    {
      // Index is already %-normalised (baseline-relative when one is pinned), so no
      // +/- delta here — just the spec badges and the value tip.
      const inside = w > 16;
      const tip = inside
        ? `<span class="tipval">${o.idx.toFixed(0)}%</span>`
        : `<span class="tipval outside" style="left:${w}%;">${o.idx.toFixed(0)}%</span>`;
      row.innerHTML =
        `<span class="cpu">${o.cpu}</span><span class="metacell">${socketSpan(o.cpu, o.vendor)}${x3dSpan(o.cpu)}</span>
         <div class="track">${ref}
           ${coreStrSpan(o.cpu, false)}
           <div class="fill" style="width:${w}%;${fillStyle(o.cpu)}">
             ${inside ? tip : ""}
             ${coreStrSpan(o.cpu, true)}
           </div>
           ${inside ? "" : tip}
         </div>`;
    }

    row.addEventListener("click", () => toggleBaseline(o.cpu));
    c.appendChild(row);
  });
}

function setBaselineBar(): void {
  const bar = $("#baselineBar");
  document.documentElement.classList.toggle("cmp-on", baseline != null);
  if (baseline) {
    bar.classList.add("on");
    $("#baselineName").textContent = baseline;
  } else {
    bar.classList.remove("on");
  }
}
function toggleBaseline(cpu: string): void {
  baseline = baseline === cpu ? null : cpu;
  render();
}

// ---------- render: by source ----------
/* ... */
function sourceRows(): Row[] {
  if (hardware === "gpu") {
    const ns = NORM_SERIES.find(s => "g:" + s.group === view);
    if (!ns) return [];
    const matchGroups = ns.groups ?? [ns.group];
    return dedupNewest(DATA.filter(r => r.site === site && matchGroups.includes(r.group)));
  }
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
  $("#datasetCount").textContent = hardware === "gpu" ? `${rows.length} GPUs` : `${site} · ${rows.length} CPUs`;
  $("#datasetCount").style.display = "";
  if (!rows.length) { c.innerHTML = `<div class="empty">No CPUs match these filters.</div>`; return; }
  const axisMax = Math.max(...rows.map(r => r.avg)); // leader fills the track
  const baseRow = baseline ? rows.find(r => r.cpu === baseline) : undefined;
  const base = baseRow ? baseRow[metric] : null;

  rows.forEach((r) => {
    const wA = (r.avg / axisMax) * 100, wL = ((r.low ?? 0) / axisMax) * 100;
    const row = el("div", "barrow " + vendorClass(r.vendor));
    row.dataset.cpu = r.cpu;
    if (r.cpu === baseline) row.classList.add("pinned");
    let deltaHtml = "";
    if (base != null) {
      if (r.cpu === baseline) deltaHtml = `<span class="delta base">baseline</span>`;
      else { const d = ((r[metric]! - base) / base) * 100; deltaHtml = `<span class="delta ${d >= 0 ? "pos" : "neg"}">${d >= 0 ? "+" : ""}${d.toFixed(1)}%</span>`; }
    }

    {
      // Selected metric is the thick primary bar (carries the value + core label);
      // the other metric is a thin sliver below, an indication only — no text.
      const selAvg = metric === "avg";
      const wSel = selAvg ? wA : wL;
      const wOth = selAvg ? wL : wA;
      const othVal = selAvg ? r.low : r.avg;
      const inside = wSel > 20;
      const valStr = fmt(r[metric]!, selAvg ? 1 : 0);
      const tip = inside
        ? `<span class="tipval" style="font-size: 10px; line-height: 1.1;">${valStr}</span>`
        : `<span class="tipval outside" style="font-size: 10px; line-height: 1.1; left:${wSel}%;">${valStr}</span>`;
      row.innerHTML =
        `<span class="cpu">${r.cpu}</span><span class="metacell">${socketSpan(r.cpu, r.vendor)}${x3dSpan(r.cpu)}</span>
         <div class="track dual">
           <div class="seg-track sel"></div>${othVal != null ? `<div class="seg-track oth"></div>` : ""}
           ${coreStrSpan(r.cpu, false)}
           <div class="fill sel" style="width:${wSel}%;${fillStyle(r.cpu)}">
             ${inside ? tip : ""}
             ${coreStrSpan(r.cpu, true)}
           </div>
           ${inside ? "" : tip}
           ${othVal != null ? `<div class="fill oth" style="width:${wOth}%;${fillStyle(r.cpu)}"></div>` : ""}
         </div>${deltaHtml}`;
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

// GPU factor pairs [faster, slower], each isolating one variable on otherwise-alike cards.
// Effects are computed live from the cross-epoch fit at the current resolution, so the VRAM
// row in particular grows as you climb from 1080p to 4K.
const GPU_FACTORS: FactorDef[] = [
  { name: "More VRAM (16 GB vs 8 GB)", sub: "identical GPU, double the memory",
    pairs: [["RTX 5060 Ti 16GB", "RTX 5060 Ti 8GB"], ["RX 9060 XT 16GB", "RX 9060 XT 8GB"],
            ["RTX 4060 Ti 16GB", "RTX 4060 Ti 8GB"]] },
  { name: "One tier up", sub: "more shaders & bandwidth, same generation",
    pairs: [["RTX 5070 Ti", "RTX 5070"], ["RTX 5080", "RTX 5070 Ti"], ["RX 9070 XT", "RX 9070"]] },
  { name: "xx90 flagship", sub: "the top die vs the next card down",
    pairs: [["RTX 5090", "RTX 5080"], ["RTX 4090", "RTX 4080 Super"]] },
  { name: "Newer generation, same class", sub: "Ada → Blackwell at a matched tier",
    pairs: [["RTX 5070", "RTX 4070"], ["RTX 5080", "RTX 4080 Super"]] },
  { name: "Radeon vs GeForce", sub: "AMD's wide-memory cards vs their price rivals",
    pairs: [["RX 9070 XT", "RTX 5070 Ti"], ["RX 7900 XTX", "RTX 4080 Super"]] },
];
const gpuShort = (c: string): string => c.replace(/^(RTX|RX|Arc) /, "");

function renderAnalysis(): void {
  const isGpu = hardware === "gpu";
  const factorSet = isGpu ? GPU_FACTORS : FACTORS;
  const short = isGpu ? gpuShort : shortName;
  const raw = fitRaw(metric);
  const has = (c: string): boolean => c in raw;
  const rows: FactorRow[] = factorSet.map((f): FactorRow | null => {
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
    ds.map(d => `<b>${short(d.a)}</b> vs ${short(d.b)} ${(d.pct >= 0 ? "+" : "")}${d.pct.toFixed(0)}%`).join(" &nbsp;·&nbsp; ");
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
  if (isGpu) {
    const res = tab.split(" ")[0];
    $("#analysisIntro").innerHTML = `Each row isolates <b>one variable</b> by comparing GPUs that are
      otherwise alike — same tier, one thing changed — using the measured fit on <b>${metricLbl}</b>
      at <b>${res}</b>. Bars are relative; the % is the average gap across the listed pairs.`;
    $("#analysisNote").innerHTML = `<b>Takeaway:</b> MSFS&nbsp;2024 is a <b>VRAM test first</b>, and the
      penalty scales with resolution. At 4K an 8&nbsp;GB card can run roughly half its own 16&nbsp;GB
      twin's FPS — the 4060&nbsp;Ti 8GB all but collapses as the frame buffer fills and the GPU stalls —
      while at 1080p the same pair sits much closer. After memory it's raw class: stepping up a tier or
      to an <b>xx90 flagship</b> buys far more than a new generation at the same tier, where the gain is
      usually modest. And at matched tiers, AMD's wide-memory cards (<b>RX&nbsp;7900&nbsp;XTX,
      RX&nbsp;9070&nbsp;XT</b>) edge out their GeForce rivals. Switch the resolution tabs to watch the
      VRAM row swell as you climb to 4K.`;
    return;
  }
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
  const noun = hardware === "gpu" ? "GPUs" : "CPUs";

  if (hardware === "gpu") {
    // one entry per review (the three resolution images share a URL), counting the
    // distinct cards tested across all of them
    const map = new Map<string, { date: string; url: string; title: string; cpus: Set<string> }>();
    for (const r of DATA) {
      const key = r.url || r.title || r.source;
      let m = map.get(key);
      if (!m) { m = { date: r.date, url: r.url, title: r.title, cpus: new Set() }; map.set(key, m); }
      m.cpus.add(r.cpu);
      if (r.date > m.date) m.date = r.date;
    }
    const items = [...map.values()].sort((a, b) => (a.date < b.date ? 1 : -1));
    $("#srcCount").textContent = items.length + " reviews";
    $("#sources").innerHTML = items.map(m => {
      const label = m.title || "Tom's Hardware";
      const head = m.url ? `<a href="${m.url}" target="_blank" rel="noopener noreferrer">${label} ↗</a>` : label;
      return `<div class="s"><b>${head}</b><small>Tom's Hardware · ${m.date} · ${m.cpus.size} ${noun}</small></div>`;
    }).join("");
    return;
  }

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
    return `<div class="s"><b>${head}</b><small>${m.site} · ${m.date} · ${m.group} · ${m.n} ${noun}</small></div>`;
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
// GPU table columns — VRAM and PCIe stand in for socket/cores; resolution + epoch
// replace scene. No 3D-cache badge.
const GPU_COLS: Col[] = [
  { k: "cpu", l: "GPU", get: r => r.cpu, sort: r => r.cpu },
  { k: "vram", l: "VRAM", num: true, get: r => { const v = spec(r.cpu).vram; return v != null ? `${v} GB` : "–"; }, sort: r => spec(r.cpu).vram ?? -1 },
  { k: "pcie", l: "PCIe", get: r => spec(r.cpu).pcie || "–", sort: r => spec(r.cpu).pcie || "" },
  { k: "avg", l: "Avg", num: true, get: r => fmt(r.avg, 1), sort: r => r.avg },
  { k: "low", l: "1% Low", num: true, get: r => (r.low != null ? fmt(r.low, 0) : "–"), sort: r => r.low ?? -Infinity },
  { k: "resolution", l: "Res", get: r => r.resolution || "–", sort: r => r.resolution || "" },
  { k: "group", l: "Epoch", get: r => r.group.replace(/\.png$/, ""), sort: r => r.group },
  { k: "date", l: "Date", get: r => r.date, sort: r => r.date },
];
const cols = (): Col[] => (hardware === "gpu" ? GPU_COLS : COLS);
let sortKey = "avg", sortDir = -1;
const tFilter = { socket: "all", arch: "all", x3d: false, q: "" };

function tableRows(): Row[] {
  return DATA.filter(r => {
    if (hardware === "gpu") {
      if (tFilter.socket !== "all" && r.vendor !== tFilter.socket) return false;
      if (tFilter.arch !== "all" && r.resolution !== tFilter.arch) return false;
    } else {
      const s = spec(r.cpu);
      if (tFilter.socket !== "all" && s.socket !== tFilter.socket) return false;
      if (tFilter.arch !== "all" && s.arch !== tFilter.arch) return false;
      if (tFilter.x3d && !r.x3d) return false;
    }
    if (tFilter.q && !r.cpu.toLowerCase().includes(tFilter.q)) return false;
    return true;
  });
}
function renderTable(): void {
  const C = cols();
  const col = C.find(c => c.k === sortKey) || C[0];
  const rows = tableRows().sort((a, b) => {
    const x: number | string = col.sort(a), y: number | string = col.sort(b);
    return (x < y ? -1 : x > y ? 1 : 0) * sortDir;
  });
  $("#rowCount").textContent = rows.length === DATA.length ? `${DATA.length} rows` : `${rows.length} of ${DATA.length} rows`;
  const thead = $("#table thead"), tbody = $("#table tbody");
  thead.innerHTML = "<tr>" + C.map(c => {
    const a = c.k === sortKey ? (sortDir < 0 ? "▼" : "▲") : "";
    return `<th data-k="${c.k}" class="${c.num ? "tnum" : ""}">${c.l} <span class="arr">${a}</span></th>`;
  }).join("") + "</tr>";
  thead.querySelectorAll("th").forEach(th => (th.onclick = () => {
    const k = th.dataset.k!;
    if (k === sortKey) sortDir *= -1;
    else { sortKey = k; sortDir = C.find(c => c.k === k)!.num ? -1 : 1; }
    renderTable();
  }));
  tbody.innerHTML = rows.map(r => "<tr>" + C.map(c =>
    `<td class="${c.num ? "tnum num" : ""}${c.mono ? " num" : ""}">${c.get(r)}</td>`).join("") + "</tr>").join("");
}
function buildTableFilters(): void {
  // reset the two dropdown filters whenever the column set changes
  tFilter.socket = "all"; tFilter.arch = "all"; tFilter.x3d = false;
  const order = (vals: (string | undefined)[], pref: string[]): string[] =>
    [...new Set(vals)].filter((x): x is string => Boolean(x))
      .sort((a, b) => (pref.indexOf(a) + 1 || 99) - (pref.indexOf(b) + 1 || 99) || (a < b ? -1 : 1));

  if (hardware === "gpu") {
    $("#tSocketLabel").textContent = "Vendor";
    $("#tArchLabel").textContent = "Res";
    $("#tX3DWrap").style.display = "none";
    const vendors = order(DATA.map(r => r.vendor), ["Nvidia", "AMD", "Intel"]);
    const reses = order(DATA.map(r => r.resolution), ["1080p", "1440p", "4K"]);
    $("#tSocket").innerHTML = `<option value="all">All vendors</option>` + vendors.map(s => `<option>${s}</option>`).join("");
    $("#tArch").innerHTML = `<option value="all">All res</option>` + reses.map(s => `<option>${s}</option>`).join("");
  } else {
    $("#tSocketLabel").textContent = "Socket";
    $("#tArchLabel").textContent = "Arch";
    $("#tX3DWrap").style.display = "";
    const sockets = order(DATA.map(r => spec(r.cpu).socket), ["AM5", "AM4", "LGA1851", "LGA1700", "LGA1200"]);
    const archs = order(DATA.map(r => spec(r.cpu).arch),
      ["Zen 5", "Zen 4", "Zen 3", "Zen 2", "Arrow Lake", "Raptor Lake", "Alder Lake", "Rocket Lake"]);
    $("#tSocket").innerHTML = `<option value="all">All sockets</option>` + sockets.map(s => `<option>${s}</option>`).join("");
    $("#tArch").innerHTML = `<option value="all">All archs</option>` + archs.map(s => `<option>${s}</option>`).join("");
  }

  $<HTMLSelectElement>("#tSocket").onchange = e => { tFilter.socket = (e.target as HTMLSelectElement).value; renderTable(); };
  $<HTMLSelectElement>("#tArch").onchange = e => { tFilter.arch = (e.target as HTMLSelectElement).value; renderTable(); };
  $<HTMLInputElement>("#tX3D").onchange = e => { tFilter.x3d = (e.target as HTMLInputElement).checked; renderTable(); };
  $("#tSearch").addEventListener("input", e => { tFilter.q = (e.target as HTMLInputElement).value.trim().toLowerCase(); renderTable(); });
}
function buildMainSocketFilter(): void {
  const container = $("#brandChips");

  if (hardware === "gpu") {
    // multi-select vendors, then VRAM buckets — All clears everything
    const allOn = selectedVendors.size === 0 && selectedVram.size === 0;
    const vchip = (v: string, tint: string, dot: string): string =>
      `<button class="chip ${selectedVendors.has(v) ? "on " + tint : ""}" data-vendor="${v}"><span class="dot" style="background:${dot}"></span>${v}</button>`;
    container.innerHTML =
      `<button class="chip ${allOn ? "on" : ""}" data-all="1">All</button>` +
      vchip("Nvidia", "nvidia", "var(--nvidia, #76b900)") +
      vchip("AMD", "amd", "var(--amd)") +
      vchip("Intel", "intel", "var(--intel)");

    const buckets = [...new Set(DATA.map(r => { const v = spec(r.cpu).vram; return v != null ? vramBucket(v) : undefined; }))]
      .filter((x): x is string => Boolean(x))
      .sort((a, b) => parseInt(a) - parseInt(b));
    buckets.forEach(bk => {
      const btn = el("button", "chip") as HTMLButtonElement;
      btn.dataset.vram = bk;
      btn.textContent = bk === "10–12" ? "10–12 GB" : `${bk} GB`;
      if (selectedVram.has(bk)) btn.classList.add("on");
      container.appendChild(btn);
    });
    return;
  }

  let html = `<button class="chip ${brand === "all" ? "on" : ""}" data-brand="all">All</button>`;
  html += `<button class="chip ${brand === "AMD" ? "on amd" : ""}" data-brand="AMD"><span class="dot" style="background:var(--amd)"></span>AMD</button>`;
  html += `<button class="chip ${brand === "Intel" ? "on intel" : ""}" data-brand="Intel"><span class="dot" style="background:var(--intel)"></span>Intel</button>`;
  html += `<button class="chip ${x3dOnly ? "on" : ""}" data-x3d="1">X3D</button>`;
  container.innerHTML = html;

  const order = (vals: (string | undefined)[], pref: string[]): string[] =>
    [...new Set(vals)].filter((x): x is string => Boolean(x))
      .sort((a, b) => (pref.indexOf(a) + 1 || 99) - (pref.indexOf(b) + 1 || 99) || (a < b ? -1 : 1));
  const sockets = order(DATA.map(r => spec(r.cpu).socket), ["AM5", "AM4", "LGA1851", "LGA1700", "LGA1200"]);
  sockets.forEach(s => {
    const btn = el("button", "chip") as HTMLButtonElement;
    btn.dataset.socket = s;
    btn.textContent = s;
    if (selectedSockets.has(s)) btn.classList.add("on");
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
  let opts: [string, string][];
  if (hardware === "gpu") {
    const currentRes = tab.split(' ')[0];
    const gpuSeries = NORM_SERIES.filter(s => s.resolution === currentRes);
    $("#viewLabel").textContent = "Epoch";
    opts = gpuSeries.map(s => ["g:" + s.group, s.name] as [string, string]);
    view = opts[0]?.[0] ?? "";  // default: combined main epoch
  } else {
    const gs = groupsForSite(site);
    const lbl = site === "PCGH" ? "Scene" : site === "ComputerBase" ? "Scene" : "Epoch";
    $("#viewLabel").textContent = lbl;
    opts = [["combined", "Newest per CPU"], ...gs.map((g): [string, string] => ["g:" + g, g]), ["all", "All raw rows"]];
    view = "combined";
  }
  $("#view").innerHTML = opts.map(([v, t]) => `<option value="${v}" ${v === view ? "selected" : ""}>${t}</option>`).join("");
  $<HTMLSelectElement>("#view").onchange = () => { view = $<HTMLSelectElement>("#view").value; render(); };
}

// ---------- dispatch ----------
function render(): void {
  renderLegend();
  // expose the active view so the delta column only shows in raw (source/FPS) views
  const isRanking = hardware === "cpu" ? tab === "ranking" : gpuMode === "index";
  document.documentElement.dataset.view = isRanking ? "ranking" : "source";
  if (hardware === "cpu") {
    if (tab === "ranking") {
      $("#datasetCount").textContent = `${enabledSeries().length} of ${NORM_SERIES.length} datasets`;
      $("#datasetCount").style.display = "";
      renderRanking();
    } else {
      renderSource();
    }
    renderAnalysis();
  } else {
    // GPU mode
    const currentRes = tab.split(' ')[0]; // "1080p" | "1440p" | "4K"
    site = "Tom's Hardware";

    // always hide site selector (only one source for GPU)
    const siteEl = document.getElementById("site");
    if (siteEl?.parentElement) (siteEl.parentElement as HTMLElement).style.display = "none";

    const sourceCtl = document.getElementById("sourceCtl");

    // the factor analysis and the index both read the current resolution's epochs
    NORM_SERIES.forEach((s, i) => { enabled[i] = s.resolution === currentRes; });

    if (gpuMode === "index") {
      const n = enabledSeries().length;
      $("#datasetCount").textContent = `${n} epoch${n !== 1 ? "s" : ""}`;
      $("#datasetCount").style.display = "";
      if (sourceCtl) sourceCtl.style.display = "none";
      renderRanking();
    } else {
      if (sourceCtl) sourceCtl.style.display = "flex";
      renderSource();
    }
    renderAnalysis();
  }
}

// ---------- controls wiring ----------
function wireControls(): void {
  const hwToggle = document.getElementById("hwToggle");
  if (hwToggle) {
    hwToggle.addEventListener("click", e => {
      const b = (e.target as HTMLElement).closest("button");
      if (!b) return;
      [...hwToggle.children].forEach(x => x.classList.toggle("on", x === b));
      switchHardware(b.dataset.hw as "cpu" | "gpu");
    });
  }

  const gpuModeSeg = document.getElementById("gpuModeSeg");
  if (gpuModeSeg) {
    gpuModeSeg.addEventListener("click", e => {
      const b = (e.target as HTMLElement).closest("button");
      if (!b) return;
      gpuMode = b.dataset.gm as GpuMode;
      [...gpuModeSeg.children].forEach(x => x.classList.toggle("on", x === b));
      // rebuild epoch dropdown when switching back to FPS
      if (gpuMode === "fps") buildViewSelect();
      render();
    });
  }

  $("#tabs").addEventListener("click", e => {
    const b = (e.target as HTMLElement).closest("button");
    if (!b) return;
    tab = b.dataset.tab as Tab;
    [...$("#tabs").children].forEach(x => x.classList.toggle("on", x === b));

    const sourceCtl = document.getElementById("sourceCtl");
    if (sourceCtl) sourceCtl.style.display = (hardware === "cpu" && tab === "source") ? "flex" : "none";

    const advToggleBtn = document.getElementById("advToggleBtn");
    if (advToggleBtn) advToggleBtn.style.display = (hardware === "cpu" && tab === "ranking") ? "" : "none";

    if (hardware === "cpu" && tab === "source") {
      const advBodyPanel = document.getElementById("advBodyPanel");
      if (advBodyPanel) advBodyPanel.style.display = "none";
      if (advToggleBtn) advToggleBtn.classList.remove("on");
    }

    // rebuild epoch selector when GPU tab (resolution) changes
    if (hardware === "gpu" && gpuMode === "fps") buildViewSelect();

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

    if (hardware === "gpu") {
      const toggle = (set: Set<string>, key: string): void => { set.has(key) ? set.delete(key) : set.add(key); };
      if (b.dataset.all) { selectedVendors.clear(); selectedVram.clear(); }
      else if (b.dataset.vendor) toggle(selectedVendors, b.dataset.vendor);
      else if (b.dataset.vram) toggle(selectedVram, b.dataset.vram);

      const allOn = selectedVendors.size === 0 && selectedVram.size === 0;
      [...$("#brandChips").children].forEach(x => {
        const btn = x as HTMLButtonElement;
        if (btn.dataset.all) btn.classList.toggle("on", allOn);
        else if (btn.dataset.vendor) {
          const on = selectedVendors.has(btn.dataset.vendor);
          btn.classList.toggle("on", on);
          btn.classList.toggle("amd", on && btn.dataset.vendor === "AMD");
          btn.classList.toggle("intel", on && btn.dataset.vendor === "Intel");
          btn.classList.toggle("nvidia", on && btn.dataset.vendor === "Nvidia");
        } else if (btn.dataset.vram) btn.classList.toggle("on", selectedVram.has(btn.dataset.vram));
      });
      render();
      return;
    }

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
        btn.classList.toggle("nvidia", isMatch && brand === "Nvidia");
      } else if (btn.dataset.x3d) {
        btn.classList.toggle("on", x3dOnly);
      } else if (btn.dataset.socket) {
        btn.classList.toggle("on", btn.dataset.socket ? selectedSockets.has(btn.dataset.socket) : false);
      }
    });
    
    render();
  });
  $("#resetBaseline").addEventListener("click", () => { baseline = null; render(); });

  $("#showSocketToggle").addEventListener("change", e => {
    showSocket = (e.target as HTMLInputElement).checked;
    document.documentElement.classList.toggle("hide-socket", !showSocket);
  });

  $("#showCoresToggle").addEventListener("change", e => {
    showCores = (e.target as HTMLInputElement).checked;
    document.documentElement.classList.toggle("hide-cores", !showCores);
  });

  const themeToggle = $("#themeToggleBtn");
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      theme = theme === "dark" ? "light" : "dark";
      localStorage.setItem("msfs-theme", theme);
      document.documentElement.dataset.theme = theme;
      themeToggle.textContent = theme;
      render();
    });
  }
}

// ---------- tweaks ----------
function applyTweaks(): void {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.dataset.bars = TWEAKS.bars;
  root.dataset.density = TWEAKS.density;
  root.dataset.layout = layout;

  const themeToggle = $("#themeToggleBtn");
  if (themeToggle) {
    themeToggle.textContent = theme;
  }
}

// ---------- boot ----------
// /cpu and /gpu routing. Direct hits on those paths are turned into #cpu / #gpu by
// the Pages 404 fallback (public/404.html); here we read either form.
function hwFromUrl(): "cpu" | "gpu" {
  const seg = (location.hash.replace(/^#\/?/, "") || location.pathname.replace(/^\//, "").replace(/\/$/, "")).toLowerCase();
  return seg === "gpu" ? "gpu" : "cpu";
}
function setUrlForHw(hw: "cpu" | "gpu"): void {
  try { history.replaceState(null, "", `${import.meta.env.BASE_URL}${hw}`); } catch { /* ignore */ }
}

async function boot(): Promise<void> {
  const [cpuRes, gpuRes] = await Promise.all([
    fetch(`${import.meta.env.BASE_URL}data.json`, { cache: "no-cache" }),
    fetch(`${import.meta.env.BASE_URL}gpu_data.json`, { cache: "no-cache" })
  ]);
  CPU_DATA = await cpuRes.json();
  GPU_DATA = await gpuRes.json();

  applyTweaks();
  wireControls();
  switchHardware(hwFromUrl());
}

function switchHardware(hw: "cpu" | "gpu"): void {
  hardware = hw;
  setUrlForHw(hw);
  const hwToggle = document.getElementById("hwToggle");
  if (hwToggle) [...hwToggle.children].forEach(x => (x as HTMLElement).classList.toggle("on", (x as HTMLElement).dataset.hw === hw));
  const data = hw === "cpu" ? CPU_DATA! : GPU_DATA!;
  
  DATA = data.rows;
  NORM_SERIES = data.norm;
  SPECS = data.specs || {};
  
  VENDOR = {};
  for (const r of DATA) if (!(r.cpu in VENDOR)) VENDOR[r.cpu] = r.vendor;
  SITES = [...new Set(DATA.map(r => r.site))];
  enabled = NORM_SERIES.map(() => true);
  
  const h1 = document.querySelector("header h1");
  if (h1) h1.innerHTML = hw === "cpu" ? "Which CPU runs MSFS&nbsp;2024 best?" : "Which GPU runs MSFS&nbsp;2024 best?";

  const lede = document.querySelector("header .lede");
  if (lede) lede.innerHTML = hw === "cpu"
    ? `A combined ranking from Tom's Hardware, PCGH and ComputerBase. Each site tests different
       scenes, so their raw FPS numbers don't line up directly. The Performance Index puts every
       review on the same 0 to 100 scale so you can compare them. Tap any bar to compare against it.`
    : `GPU benchmarks from Tom's Hardware, collected across several reviews over time. Raw FPS doesn't
       carry across them because the game builds and test conditions change. The Performance Index puts
       every review on the same 0 to 100 scale. Tap any bar to compare against it.`;
  
  const tSearch = document.getElementById("tSearch") as HTMLInputElement;
  if (tSearch) tSearch.placeholder = hw === "cpu" ? "Filter CPUs…" : "Filter GPUs…";

  const methodology = document.getElementById("srcMethodology");
  if (methodology) methodology.innerHTML = hw === "cpu"
    ? `Same game, but re-measured over time and across sites, so a CPU's FPS drift between
        epochs and scenes — absolute numbers <b>aren't comparable across sources</b>.
        <b>By source</b> keeps you inside one comparable set. The <b>Performance Index</b> rescales
        every enabled dataset onto a shared scale using a two-way additive fit (per-dataset offset +
        per-CPU effect), so a CPU's score reflects its own speed, not which reviewer happened to test it.
        <b>·N</b> next to a score is how many datasets cover that CPU.
        One sanity prior is then applied <b>within each Intel microarchitecture</b>: a higher-tier or
        higher-binned part (a 14900KS over a 14900K, the Core Ultra 285K over a 235) has strictly more
        cores, cache or clock, so it can't be slower in a CPU-bound game. Where a thinly-tested SKU's
        noisy score violates that, a coverage-weighted <b>isotonic fit</b> snaps the family back into
        order — well-tested parts barely move, thin ones fall into line. It's deliberately not applied
        across architectures or to AMD's ladder, where the spec sheet doesn't track gaming order (the
        7800X3D beats the 7950X3D) — the lone exception being a few <b>same-die, clock-only pairs</b>
        (e.g. the 5800X3D over the 5700X3D) that are guaranteed by physics. Same-silicon siblings may
        legitimately tie.`
    : `All GPU numbers come from <b>Tom's Hardware's</b> Flight Simulator 2024 benchmark, re-run for
        each new card launch. Because the game build and test rig change between those runs, raw FPS
        <b>doesn't carry across them</b>. The <b>Performance Index</b> rescales every run onto a shared
        0–100 scale with a two-way additive fit (per-run offset + per-GPU effect), so a card's score
        reflects its own speed, not which launch-day driver and game build it happened to be tested on.
        Each resolution tab is normalised on its own, so the index is only comparable within a resolution.
        Sources below link to the original review each run was lifted from.`;

  const footer = document.getElementById("footer");
  if (footer) footer.innerHTML = hw === "cpu"
    ? `Combined from <b>Tom's Hardware</b>, <b>PCGH</b> and <b>ComputerBase</b> reviews,
       transcribed/scraped into <code>msfs24_data.csv</code>, <code>pcgh_msfs24.csv</code> and
       <code>computerbase_msfs24.csv</code>, unified by <code>build_data.py</code> into
       <code>data.json</code>, then rendered by this Vite + TypeScript app. Absolute FPS aren't
       comparable across sources — the Performance Index normalises them. Not affiliated with Tom's
       Hardware, PCGH or ComputerBase.<br>
       Made by <b>'Razortek'</b> from the Official MSFS Discord (<a href="https://discord.com/invite/msfs" target="_blank" rel="noopener">https://discord.com/invite/msfs</a>); you can direct opinions about this tool to <code>#hardware</code> there because he basically lives there.`
    : `GPU benchmarks transcribed from <b>Tom's Hardware's</b> Flight Simulator 2024 reviews into
       <code>msfs24_gpu_data.csv</code>, unified by <code>build_gpu_data.py</code> into
       <code>gpu_data.json</code>, then rendered by this Vite + TypeScript app. Raw FPS aren't
       comparable across test runs — the Performance Index normalises them per resolution. Not
       affiliated with Tom's Hardware.<br>
       Made by <b>'Razortek'</b> from the Official MSFS Discord (<a href="https://discord.com/invite/msfs" target="_blank" rel="noopener">https://discord.com/invite/msfs</a>); you can direct opinions about this tool to <code>#hardware</code> there because he basically lives there.`;

  const analysisPanel = document.getElementById("analysisPanel");
  if (analysisPanel) analysisPanel.style.display = "";
  
  const tabsContainer = document.getElementById("tabs");
  if (tabsContainer) {
    if (hw === "cpu") {
      tabsContainer.innerHTML = `
        <button data-tab="ranking" class="on">Performance Index</button>
        <button data-tab="source">By source</button>
      `;
      tab = "ranking";
    } else {
      tabsContainer.innerHTML = `
        <button data-tab="1080p Ultra">1080p</button>
        <button data-tab="1440p Ultra" class="on">1440p</button>
        <button data-tab="4K Ultra">4K</button>
      `;
      tab = "1440p Ultra";
    }
  }

  const gpuModeSeg = document.getElementById("gpuModeSeg");
  if (gpuModeSeg) {
    gpuModeSeg.style.display = hw === "gpu" ? "inline-flex" : "none";
  }

  const sourceCtl = document.getElementById("sourceCtl");
  if (sourceCtl) {
    sourceCtl.style.display = (hw === "cpu" && tab === "source") ? "flex" : "none";
  }
  
  const advToggleBtn = document.getElementById("advToggleBtn");
  if (advToggleBtn) {
    advToggleBtn.style.display = (hw === "cpu" && tab === "ranking") ? "" : "none";
  }
  
  // reset state
  brand = "all";
  x3dOnly = false;
  selectedSockets.clear();
  selectedVendors.clear();
  selectedVram.clear();
  sortKey = "avg"; sortDir = -1;
  baseline = null;
  
  // re-build UI
  buildDatasetList();
  buildSiteSelect();
  buildTableFilters();
  buildMainSocketFilter();
  renderSources();
  renderTable();
  render();
}

boot();
