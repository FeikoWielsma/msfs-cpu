/* /limited — which half of the frame is holding the frame rate.
 *
 * A toy with real inputs. The slider stops are the fitted indices from builds.json (the
 * same numbers /specs prints); what turns an index into milliseconds is a hand-picked
 * anchor per location, below. So the order of the chips is measured and the absolute
 * frame rates are illustration.
 *
 * One clock drives everything. Frames are generated in real time at whatever length the
 * model gives them, the graph plots each one as it completes, and the scene repaints
 * only when a frame completes — so 24 FPS on the sliders looks like 24 FPS on screen.
 */
import "./limited.css";

type Loc = "airport" | "cruise" | "vfr";
type Res = "1080p" | "1440p" | "4K";
type Ctx = CanvasRenderingContext2D;

type Cat = { part: string; idx: Record<string, number> };
type Stop = { part: string; short: string; slug: string; idx: Record<string, number>;
              vram?: number; pcie?: string; alt?: { part: string; vram?: number; pcie?: string } };
type Step = { part: string; short: string };
type Frame = { t: number; cpu: number; gpu: number; frame: number };

// ---------- the model ----------

/* cpuMs: MainThread milliseconds for a CPU at index 100 here. The CPU index is fitted to
 * CPU-bound FPS, so time scales with 100 / index — a 9800X3D (97) lands on the anchor, a
 * Ryzen 5 5600 (51) at about twice it. gpuMul scales the per-resolution GPU anchor for how
 * heavy the location is to draw. jitter/spikes only make the trace look alive: spikes are
 * MainThread hitches per second (AI traffic, scenery streaming). workers is everything
 * off the MainThread, for the usage panel only: how many threads, and how busy each is on
 * a top chip — a couple of light helpers at an airport, a wide spread of scenery decoding
 * under photogrammetry. All of it is judgement. */
const LOCS: Record<Loc, {
  label: string; sub: string; name: string; note: string;
  cpuMs: number; gpuMul: number; jitter: number; spikes: number; spikeMs: number;
  workers: { n: number; load: number; burst: number }; vram: number; addonCpu: number;
}> = {
  airport: { label: "Airport", sub: "on the ground", name: "Busy airport",
    note: "Hundreds of AI aircraft and ground vehicles for the MainThread to move",
    cpuMs: 12.6, gpuMul: 0.85, jitter: 0.07, spikes: 0.6, spikeMs: 7,
    workers: { n: 3, load: 0.3, burst: 0.15 }, vram: 1.0, addonCpu: 1 },
  cruise: { label: "Cruise", sub: "FL350", name: "Cruise at FL350",
    note: "Next to nothing to simulate, a sky full of volumetric cloud to draw",
    cpuMs: 5.8, gpuMul: 1.25, jitter: 0.035, spikes: 0.05, spikeMs: 3,
    workers: { n: 2, load: 0.14, burst: 0.05 }, vram: 0.4, addonCpu: 0.35 },
  vfr: { label: "VFR", sub: "1,500 ft", name: "Low and slow VFR",
    note: "Photogrammetry and trees streaming in underneath — some of both",
    cpuMs: 8.7, gpuMul: 1.0, jitter: 0.05, spikes: 0.3, spikeMs: 5,
    workers: { n: 10, load: 0.3, burst: 0.25 }, vram: 1.2, addonCpu: 0.5 },
};

/* GPU milliseconds for a card at index 100 (the 5090) per resolution. Tom's Hardware has
 * the RX 9070 — index 72 at 1440p, 56 at 4K — at 80.8 and 47.1 FPS, which puts index 100
 * at 8.9 and 11.9 ms; the 5090's own 82.6 FPS at 4K agrees. Their 1080p run is CPU-bound,
 * so that anchor is extrapolated from how the 1440p-to-4K step scales with pixel count. */
const GPU_MS: Record<Res, number> = { "1080p": 7.2, "1440p": 8.9, "4K": 11.9 };

/* VRAM. Each card's real memory and PCIe link come from gpu_data.json; how much the sim
 * wants is guessed — render targets per resolution, scenery per location (LOCS.vram), then
 * the two sliders. Sized so an 8 GB card runs out at 1440p High the moment you add an
 * airliner, a 12 GB card goes at Ultra with a payware airport and GSX, and even a 16 GB
 * card just spills over with everything maxed at an airport at 1440p or 4K — no amount of
 * VRAM on this page makes "max it all" free. Away from the airport most addons unload. */
const VRAM_BASE: Record<Res, number> = { "1080p": 3.2, "1440p": 3.8, "4K": 4.6 };
const TEXTURES = [
  { part: "Low", short: "Low", gb: 0.6 },
  { part: "Medium", short: "Medium", gb: 1.6 },
  { part: "High", short: "High", gb: 2.8 },
  { part: "Ultra", short: "Ultra", gb: 4.8 },
];
/* Addons cost memory and MainThread time. cpuMs is extra MainThread at index 100 at an
 * airport, scaled per location by LOCS.addonCpu — a payware airport and GSX do little at
 * FL350, a study-level airliner's systems still run. workers is extra helper-thread load. */
const ADDONS = [
  // gb is at an airport; away is what stays loaded in cruise or VFR — the aircraft and a
  // little global stuff, since airport scenery, GSX and its traffic unload once you leave.
  { part: "Stock sim", short: "Stock", gb: 0, away: 0, cpuMs: 0, workers: 0 },
  { part: "Study-level airliner", short: "Airliner", gb: 0.8, away: 0.8, cpuMs: 1.2, workers: 0.03 },
  { part: "+ Payware airport", short: "Airport", gb: 1.9, away: 0.8, cpuMs: 2.8, workers: 0.05 },
  { part: "+ GSX and AI traffic", short: "GSX", gb: 2.9, away: 0.9, cpuMs: 5.2, workers: 0.08 },
  { part: "Everything at once", short: "All", gb: 6.5, away: 1.6, cpuMs: 8, workers: 0.12 },
];

/* How much a narrow link makes paging hurt: bandwidth in PCIe 3.0 lanes, against a 5.0 x16
 * slot. A 4.0 x8 card (3050) pays twice what a 5.0 x16 one does. */
function linkFactor(pcie: string): number {
  const m = /(\d)\.0×(\d+)/.exec(pcie);
  if (!m) return 1;
  return Math.sqrt(64 / (Number(m[2]) * 2 ** (Number(m[1]) - 3)));
}

const CPU_PICKS: [string, string][] = [
  ["Ryzen 5 5600", "5600"], ["Ryzen 5 7600X", "7600X"], ["Ryzen 7 5800X3D", "5800X3D"],
  ["Core i5-14600K", "14600K"], ["Ryzen 7 7800X3D", "7800X3D"], ["Ryzen 7 9800X3D", "9800X3D"],
];
/* A third field names a smaller-memory sibling the page can toggle to. The toggle keeps the
 * bigger card's index: same silicon, and the measured gap between the two is memory running
 * out — which this page models itself, so taking the smaller card's index would count it twice. */
const GPU_PICKS: [string, string, string?][] = [
  ["RTX 3050", "3050"], ["RTX 5060", "5060"], ["RX 9060 XT 16GB", "9060 XT", "RX 9060 XT 8GB"],
  ["RTX 5070", "5070"], ["RTX 5070 Ti", "5070 Ti"], ["RX 9070", "9070"], ["RX 9070 XT", "9070 XT"],
  ["RTX 5090", "5090"],
];
const RESES: Res[] = ["1080p", "1440p", "4K"];

/* Logical processors as Task Manager lists them, keyed by slug. pThreads is how many sit
 * on performance cores: the scheduler keeps the MainThread there, so the 14600K's E-cores
 * only ever see helper work. */
const TOPO: Record<string, { cores: number; threads: number; pThreads: number }> = {
  "5600": { cores: 6, threads: 12, pThreads: 12 },
  "7600x": { cores: 6, threads: 12, pThreads: 12 },
  "5800x3d": { cores: 8, threads: 16, pThreads: 16 },
  "14600k": { cores: 14, threads: 20, pThreads: 12 },
  "7800x3d": { cores: 8, threads: 16, pThreads: 16 },
  "9800x3d": { cores: 8, threads: 16, pThreads: 16 },
};

const WINDOW = 5000;      // graph span, ms
const EASE = 0.3;         // seconds for the model to settle after a slider move

const state = { loc: "airport" as Loc, res: "1440p" as Res, cpu: 0, gpu: 0, tex: 2, addon: 0, small: false };

// The memory the selected card actually has: its smaller sibling when toggled to one.
const mem = (i: number): { part: string; vram?: number; pcie?: string } =>
  (state.small && GPUS[i].alt) || GPUS[i];
let CPUS: Stop[] = [];
let GPUS: Stop[] = [];

const cpuIndex = (s: Stop): number => Math.max(...Object.values(s.idx));
const gpuIndex = (s: Stop, res: Res): number => s.idx[res] ?? 1;
const addonGb = (i: number): number => (state.loc === "airport" ? ADDONS[i].gb : ADDONS[i].away);

function vram(): { parts: number[]; used: number; cap: number; over: number; e: number; link: number } {
  const g = mem(state.gpu);
  const parts = [VRAM_BASE[state.res], LOCS[state.loc].vram, TEXTURES[state.tex].gb, addonGb(state.addon)];
  const used = parts.reduce((a, b) => a + b, 0), cap = g.vram ?? 16;
  const over = Math.max(0, used - cap);
  return { parts, used, cap, over, e: over / cap, link: linkFactor(g.pcie ?? "") };
}

const targetCpu = (): number =>
  (LOCS[state.loc].cpuMs + ADDONS[state.addon].cpuMs * LOCS[state.loc].addonCpu) * 100 / cpuIndex(CPUS[state.cpu]);
// Over VRAM, every frame that touches a paged-out texture waits on the bus.
const targetGpu = (): number => {
  const v = vram();
  return GPU_MS[state.res] * LOCS[state.loc].gpuMul * 100 / gpuIndex(GPUS[state.gpu], state.res)
    * (1 + 5 * v.e * v.link);
};

function gauss(): number {
  const u = 1 - Math.random(), v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

// ---------- frame clock ----------

const cur = { cpu: 0, gpu: 0 };           // eased means the frames are drawn around
const frames: Frame[] = [];
let pending = { start: 0, cpu: 0, gpu: 0, frame: 16 };

function makeFrame(start: number): typeof pending {
  const L = LOCS[state.loc];
  let cpu = cur.cpu * (1 + L.jitter * gauss());
  const len = Math.max(cur.cpu, cur.gpu) / 1000;
  if (Math.random() < L.spikes * (1 + state.addon * 0.35) * len)
    cpu += L.spikeMs * (cur.cpu / L.cpuMs) * (0.5 + Math.random());
  let gpu = cur.gpu * (1 + L.jitter * 0.5 * gauss());
  const v = vram();
  if (v.over > 0 && Math.random() < Math.min(12, (3 + 40 * v.e) * v.link) * len)
    gpu += (25 + Math.random() * 65) * Math.sqrt(v.link);             // a paging stall
  cpu = Math.max(1, cpu);
  const g = Math.max(1, gpu);
  return { start, cpu, gpu: g, frame: Math.max(cpu, g) };
}

// ---------- scene ----------

const hash = (n: number): number => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
const mod = (a: number, b: number): number => ((a % b) + b) % b;

function poly(c: Ctx, p: number[], fill: string | CanvasGradient): void {
  c.beginPath();
  c.moveTo(p[0], p[1]);
  for (let i = 2; i < p.length; i += 2) c.lineTo(p[i], p[i + 1]);
  c.closePath();
  c.fillStyle = fill;
  c.fill();
}

function glow(c: Ctx, x: number, y: number, r: number, rgb: string, a = 1): void {
  const g = c.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, `rgba(${rgb},${a})`);
  g.addColorStop(0.25, `rgba(${rgb},${a * 0.45})`);
  g.addColorStop(1, `rgba(${rgb},0)`);
  c.fillStyle = g;
  c.fillRect(x - r, y - r, r * 2, r * 2);
}

function dot(c: Ctx, x: number, y: number, r: number, fill: string): void {
  c.beginPath();
  c.arc(x, y, r, 0, Math.PI * 2);
  c.fillStyle = fill;
  c.fill();
}

/* An airliner in side view, nose towards +x before `dir` flips it. Units are roughly
 * metres-ish; `sc` maps them to pixels. */
function jet(c: Ctx, x: number, y: number, sc: number, dir: 1 | -1, tail: string, gear: boolean): void {
  c.save();
  c.translate(x, y);
  c.scale(sc * dir, sc);
  poly(c, [-52, -2, -72, -9, -66, 1, -48, 2], "#9aa3b5");                 // far stabiliser
  poly(c, [-40, -6, -60, -36, -69, -36, -63, -4], tail);                 // fin
  c.beginPath();                                                         // fuselage
  c.moveTo(-64, -3);
  c.lineTo(46, -7);
  c.quadraticCurveTo(62, -6, 65, 0);
  c.quadraticCurveTo(62, 6, 46, 7);
  c.lineTo(-46, 7);
  c.closePath();
  c.fillStyle = "#e3e8f0";
  c.fill();
  poly(c, [-46, 3, 46, 3, 58, 5, 46, 7, -46, 7], "#b6bfcd");             // belly shade
  poly(c, [54, -4, 61, -3, 62, 0, 53, -1], "#1c2233");                   // windscreen
  c.fillStyle = "#ffd89a";
  for (let i = -40; i < 44; i += 5.5) c.fillRect(i, -2.6, 2, 2);         // cabin windows
  poly(c, [4, 2, -22, 14, -12, 14, 20, 3], "#c2cad8");                   // wing
  c.beginPath();
  c.ellipse(4, 10, 11, 4.6, 0, 0, Math.PI * 2);                          // engine
  c.fillStyle = "#8a93a7";
  c.fill();
  c.beginPath();
  c.ellipse(14.5, 10, 2, 4, 0, 0, Math.PI * 2);
  c.fillStyle = "#2a303e";
  c.fill();
  if (gear) {
    c.strokeStyle = "#555c6b";
    c.lineWidth = 1.6;
    c.beginPath();
    c.moveTo(40, 6); c.lineTo(40, 14);
    c.moveTo(-8, 6); c.lineTo(-8, 14);
    c.stroke();
    dot(c, 40, 15, 2.6, "#15171d");
    dot(c, -8, 15, 3, "#15171d");
  }
  c.restore();
}

function airport(c: Ctx, w: number, h: number, t: number): void {
  const s = h / 360, hy = h * 0.56;

  const sky = c.createLinearGradient(0, 0, 0, hy);
  sky.addColorStop(0, "#060a1c");
  sky.addColorStop(0.5, "#1b2150");
  sky.addColorStop(0.82, "#5d4470");
  sky.addColorStop(1, "#e3915e");
  c.fillStyle = sky;
  c.fillRect(0, 0, w, hy);

  for (let i = 0; i < 46; i++) {
    const a = Math.max(0, 0.35 + 0.3 * Math.sin(t * (0.8 + hash(i) * 2) + i * 3)) * (1 - hash(i + 7) * 0.6);
    c.fillStyle = `rgba(255,255,255,${a.toFixed(3)})`;
    c.fillRect(hash(i + 1) * w, hash(i + 2) * hy * 0.45, 1.3 * s, 1.3 * s);
  }

  // far city
  for (let i = 0; i < 34; i++) {
    const bw = (10 + hash(i + 11) * 22) * s, bh = (8 + hash(i + 12) ** 2 * 60) * s;
    const x = (i / 34) * w * 1.05 - 10 * s;
    c.fillStyle = "#1a1c38";
    c.fillRect(x, hy - bh, bw, bh);
    c.fillStyle = "rgba(255,206,140,.55)";
    for (let r = 0; r < bh / (6 * s) - 1; r++)
      for (let q = 0; q < bw / (6 * s) - 1; q++)
        if (hash(i * 97 + r * 13 + q) > 0.72) c.fillRect(x + (2 + q * 6) * s, hy - bh + (3 + r * 6) * s, 1.6 * s, 1.6 * s);
  }

  const gnd = c.createLinearGradient(0, hy, 0, h);
  gnd.addColorStop(0, "#2b2e40");
  gnd.addColorStop(1, "#0d0f16");
  c.fillStyle = gnd;
  c.fillRect(0, hy, w, h - hy);

  // runway lights along the horizon
  for (let i = 0; i < 70; i++) {
    const on = 0.55 + 0.45 * Math.sin(t * 2 + i * 0.9);
    c.fillStyle = i % 2 ? `rgba(255,214,150,${on})` : `rgba(120,170,255,${on})`;
    c.fillRect((i / 70) * w, hy + 3 * s, 1.5 * s, 1.5 * s);
  }

  // terminal
  const tx0 = w * 0.03, tx1 = w * 0.64, ty = hy - 30 * s;
  c.fillStyle = "#20253f";
  c.fillRect(tx0, ty, tx1 - tx0, 36 * s);
  c.fillStyle = "#394070";
  c.fillRect(tx0, ty, tx1 - tx0, 2.5 * s);
  c.fillStyle = "rgba(245,190,110,.62)";
  c.fillRect(tx0, ty + 7 * s, tx1 - tx0, 11 * s);
  c.fillStyle = "#20253f";
  for (let x = tx0; x < tx1; x += 14 * s) c.fillRect(x, ty + 7 * s, 1.5 * s, 11 * s);

  // tower
  const tw = w * 0.82;
  c.fillStyle = "#262b4a";
  c.fillRect(tw - 5 * s, hy - 100 * s, 10 * s, 104 * s);
  poly(c, [tw - 19 * s, hy - 122 * s, tw + 19 * s, hy - 122 * s, tw + 14 * s, hy - 100 * s, tw - 14 * s, hy - 100 * s], "#454d8a");
  c.fillStyle = "rgba(150,225,255,.95)";
  c.fillRect(tw - 15 * s, hy - 118 * s, 30 * s, 8 * s);
  c.fillStyle = "#1a1e36";
  c.fillRect(tw - 20 * s, hy - 125 * s, 40 * s, 3.5 * s);
  c.fillRect(tw - 0.8 * s, hy - 140 * s, 1.6 * s, 15 * s);
  const radar = Math.abs(Math.cos(t * 2.4)) * 10 * s;
  c.fillStyle = "#8a93b8";
  c.fillRect(tw + 12 * s - radar / 2, hy - 130 * s, radar, 3 * s);
  if (mod(t, 1.4) < 0.7) { glow(c, tw, hy - 141 * s, 10 * s, "255,60,60"); dot(c, tw, hy - 141 * s, 1.6 * s, "#ff5a5a"); }

  // parked at the gates
  const gates: [number, string][] = [[0.13, "#1f6fd1"], [0.32, "#c93b3b"], [0.51, "#2f9e6e"]];
  for (const [gx, livery] of gates) {
    c.fillStyle = "#171b30";
    c.fillRect(w * gx - 4 * s, ty + 18 * s, 22 * s, 5 * s);             // jet bridge
    jet(c, w * gx, hy + 10 * s, 0.42 * s, -1, livery, true);
  }

  // taxiway: centreline and blue edge lights
  const qx = (u: number, a: number, b: number, k: number): number => (1 - u) ** 2 * a + 2 * (1 - u) * u * k + u * u * b;
  c.strokeStyle = "rgba(234,179,8,.8)";
  c.lineWidth = 1.6 * s;
  c.setLineDash([10 * s, 8 * s]);
  c.beginPath();
  c.moveTo(0, h * 0.8);
  c.quadraticCurveTo(w * 0.5, h * 0.66, w, h * 0.76);
  c.stroke();
  c.setLineDash([]);
  for (let i = 0; i <= 24; i++) {
    const u = i / 24, x = qx(u, 0, w, w * 0.5), y = qx(u, h * 0.8, h * 0.76, h * 0.66);
    for (const off of [-16, 16]) { glow(c, x, y + off * s, 4 * s, "90,150,255", 0.9); }
  }

  // taxiing airliner
  const px = mod(t * 34 * s, w + 300 * s) - 150 * s, py = hy + 42 * s;
  jet(c, px, py, 0.8 * s, 1, "#1f6fd1", true);
  if (mod(t, 1) < 0.5) glow(c, px, py - 8 * s, 9 * s, "255,70,60");
  if (mod(t, 1.3) < 0.07) glow(c, px - 10 * s, py + 12 * s, 14 * s, "255,255,255");

  // arrival on final
  const p = mod(t, 11) / 11;
  c.globalAlpha = p > 0.88 ? (1 - p) / 0.12 : 1;
  const ax = w * (0.04 + p * 0.5), ay = h * 0.1 + (hy - 22 * s - h * 0.1) * p, asc = (0.22 + p * 0.22) * s;
  jet(c, ax, ay, asc, 1, "#c93b3b", true);
  glow(c, ax + 58 * asc, ay + 5 * asc, 26 * s, "255,248,220");
  c.globalAlpha = 1;

  // baggage train in the foreground, fastest thing on screen
  const bx = w + 60 * s - mod(t * 70 * s, w + 320 * s), by = h * 0.92;
  c.fillStyle = "#e2a72e";
  c.fillRect(bx, by - 10 * s, 22 * s, 10 * s);
  c.fillStyle = "#2a2f3d";
  c.fillRect(bx + 12 * s, by - 18 * s, 9 * s, 8 * s);
  for (let k = 0; k < 3; k++) {
    c.fillStyle = "#5b6272";
    c.fillRect(bx + (26 + k * 22) * s, by - 9 * s, 18 * s, 9 * s);
    dot(c, bx + (29 + k * 22) * s, by + 1 * s, 2.4 * s, "#0b0c10");
    dot(c, bx + (41 + k * 22) * s, by + 1 * s, 2.4 * s, "#0b0c10");
  }
  dot(c, bx + 4 * s, by + 1 * s, 2.6 * s, "#0b0c10");
  dot(c, bx + 18 * s, by + 1 * s, 2.6 * s, "#0b0c10");
  if (mod(t, 0.8) < 0.4) glow(c, bx + 16 * s, by - 20 * s, 9 * s, "255,190,40");
}

function puff(c: Ctx, x: number, y: number, r: number, top: string, base: string): void {
  const lobes: [number, number, number][] = [[-0.62, 0.18, 0.68], [0, -0.12, 1], [0.7, 0.2, 0.64]];
  for (const [dx, dy, dr] of lobes) {
    const cx = x + dx * r, cy = y + dy * r, rr = dr * r;
    const g = c.createRadialGradient(cx - rr * 0.3, cy - rr * 0.5, rr * 0.1, cx, cy, rr);
    g.addColorStop(0, top);
    g.addColorStop(1, base);
    dot(c, cx, cy, rr, g as unknown as string);
  }
}

function cloudLayer(c: Ctx, w: number, y: number, off: number, tile: number, n: number,
                    r: number, top: string, base: string, seed: number): void {
  const o = mod(off, tile);
  for (let k = -1; k * tile - o < w + r * 2; k++) {
    for (let i = 0; i < n; i++) {
      const px = k * tile - o + (i / n) * tile + hash(seed + i) * (tile / n) * 0.6;
      const py = y + (hash(seed + i + 40) - 0.5) * r * 0.5;
      puff(c, px, py, r * (0.7 + hash(seed + i + 80) * 0.6), top, base);
    }
  }
}

function cruise(c: Ctx, w: number, h: number, t: number): void {
  const s = h / 360;

  const sky = c.createLinearGradient(0, 0, 0, h * 0.62);
  sky.addColorStop(0, "#06173a");
  sky.addColorStop(0.45, "#1b4f93");
  sky.addColorStop(0.8, "#6fa8dc");
  sky.addColorStop(1, "#cfe6f7");
  c.fillStyle = sky;
  c.fillRect(0, 0, w, h);
  glow(c, w * 0.78, h * 0.17, 150 * s, "255,244,214", 0.95);
  dot(c, w * 0.78, h * 0.17, 9 * s, "#fffdf4");

  c.fillStyle = "#c3d5e8";
  c.fillRect(0, h * 0.6, w, h * 0.4);
  cloudLayer(c, w, h * 0.6, t * 8 * s, 520 * s, 8, 34 * s, "#f4f8fc", "#b4c9df", 11);
  cloudLayer(c, w, h * 0.71, t * 22 * s, 640 * s, 7, 52 * s, "#ffffff", "#c9d8e9", 23);
  cloudLayer(c, w, h * 0.86, t * 58 * s, 820 * s, 6, 80 * s, "#ffffff", "#d6e2ef", 37);

  // wing, seen from a cabin window; forward is to the right
  c.save();
  c.translate(w * 1.02, h * 0.95);
  c.rotate(Math.sin(t * 1.1) * 0.008);
  c.translate(-w * 1.02, -h * 0.95);
  const wg = c.createLinearGradient(0, h * 0.55, 0, h);
  wg.addColorStop(0, "#f1f4f8");
  wg.addColorStop(1, "#8e9bb0");
  poly(c, [w * 1.05, h * 0.8, w * 0.34, h * 0.585, w * 0.3, h * 0.615, w * 1.05, h * 1.08], wg);
  poly(c, [w * 0.34, h * 0.585, w * 0.307, h * 0.47, w * 0.292, h * 0.476, w * 0.3, h * 0.615], "#dfe5ee");
  c.strokeStyle = "rgba(60,70,90,.3)";
  c.lineWidth = 1 * s;
  c.beginPath();
  c.moveTo(w * 0.42, h * 0.645); c.lineTo(w * 1.05, h * 0.99);
  for (const u of [0.5, 0.64, 0.8]) { c.moveTo(w * u, h * (0.6 + (u - 0.34) * 0.3)); c.lineTo(w * (u - 0.02), h * (0.66 + (u - 0.34) * 0.5)); }
  c.stroke();
  const eg = c.createLinearGradient(0, h * 0.88, 0, h * 1.1);
  eg.addColorStop(0, "#b5bfcd");
  eg.addColorStop(1, "#5d6678");
  c.beginPath();
  c.ellipse(w * 0.8, h * 0.99, 74 * s, 34 * s, -0.1, 0, Math.PI * 2);
  c.fillStyle = eg;
  c.fill();
  c.beginPath();
  c.ellipse(w * 0.8 + 66 * s, h * 0.98, 12 * s, 29 * s, -0.1, 0, Math.PI * 2);
  c.fillStyle = "#23272f";
  c.fill();
  glow(c, w * 0.3, h * 0.475, 9 * s, "60,255,120");
  if (mod(t, 1.2) < 0.06) glow(c, w * 0.3, h * 0.48, 40 * s, "255,255,255");
  c.restore();

  const v = c.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.45, w / 2, h / 2, Math.max(w, h) * 0.75);
  v.addColorStop(0, "rgba(0,0,20,0)");
  v.addColorStop(1, "rgba(0,0,20,.32)");
  c.fillStyle = v;
  c.fillRect(0, 0, w, h);
}

function ridge(c: Ctx, w: number, h: number, base: number, amp: number, off: number,
               color: string, seed: number, s: number): void {
  c.beginPath();
  c.moveTo(0, h);
  for (let x = 0; x <= w + 8 * s; x += 8 * s) {
    const u = (x + off) / (140 * s);
    c.lineTo(x, base - amp * (0.55 + 0.3 * Math.sin(u + seed) + 0.15 * Math.sin(u * 2.7 + seed * 3)));
  }
  c.lineTo(w, h);
  c.closePath();
  c.fillStyle = color;
  c.fill();
}

const FIELDS = ["#7fae4f", "#a7c05a", "#5e8e3b", "#c8b56a", "#8cb758", "#6f9f45"];

function fieldRow(c: Ctx, w: number, y: number, rh: number, off: number, seed: number): void {
  const n = 14, widths: number[] = [];
  let len = 0;
  for (let i = 0; i < n; i++) { const fw = (0.5 + hash(seed + i) * 0.9) * rh * 4; widths.push(fw); len += fw; }
  let x = -mod(off, len);
  for (let i = 0; x < w; i++) {
    const k = i % n, fw = widths[k];
    c.fillStyle = FIELDS[Math.floor(hash(seed + k + 50) * FIELDS.length)];
    c.fillRect(x, y, fw + 0.5, rh);
    c.fillStyle = "rgba(40,70,30,.5)";
    c.fillRect(x, y, Math.max(1, rh * 0.06), rh);
    if (hash(seed + k + 90) > 0.45)
      for (let j = 0; j < 3; j++) dot(c, x + rh * 0.05, y + rh * (0.2 + j * 0.3), rh * 0.13, "#355e2a");
    if (hash(seed + k + 130) > 0.78) {
      const hx = x + fw * 0.45, hh = rh * 0.34, hy = y + rh * 0.4;
      c.fillStyle = "#efe6d6";
      c.fillRect(hx, hy, hh * 1.4, hh);
      poly(c, [hx - hh * 0.15, hy, hx + hh * 0.7, hy - hh * 0.6, hx + hh * 1.55, hy], "#b8493a");
    }
    x += fw;
  }
  c.fillStyle = "rgba(40,70,30,.4)";
  c.fillRect(0, y, w, Math.max(1, rh * 0.05));
}

function cessna(c: Ctx, x: number, y: number, sc: number, t: number): void {
  c.save();
  c.translate(x, y);
  c.rotate(Math.sin(t * 1.1) * 0.025);
  c.scale(sc, sc);
  poly(c, [-38, -2, -52, -5, -52, 1, -36, 2], "#cfd6df");                // stabiliser
  poly(c, [-36, -5, -50, -25, -57, -25, -53, -2], "#f4f6f9");            // fin
  poly(c, [-48.5, -21, -50, -25, -57, -25, -56, -21], "#c8372d");
  c.beginPath();                                                          // fuselage
  c.moveTo(-53, -3);
  c.lineTo(-10, -9);
  c.lineTo(18, -10);
  c.quadraticCurveTo(28, -9, 30, -2);
  c.lineTo(30, 4);
  c.quadraticCurveTo(24, 8, 10, 8);
  c.lineTo(-14, 6);
  c.closePath();
  c.fillStyle = "#f4f6f9";
  c.fill();
  poly(c, [-50, -1.5, 29, 0, 29, 2.5, -40, 2], "#1f5fa8");                // stripe
  poly(c, [-6, -8.5, 12, -9.5, 18, -2.5, -6, -2.5], "#2b3a4d");          // windows
  poly(c, [-14, -13, 22, -13, 24, -10, -14, -10], "#e6ebf1");            // high wing
  c.strokeStyle = "#9aa3ae";
  c.lineWidth = 1.2;
  c.beginPath();
  c.moveTo(2, -10); c.lineTo(-4, 4);
  c.moveTo(6, 8); c.lineTo(10, 15);
  c.moveTo(-16, 6); c.lineTo(-18, 15);
  c.stroke();
  dot(c, 10, 15.5, 2.6, "#2a2a2a");
  dot(c, -18, 15.5, 2.6, "#2a2a2a");
  c.beginPath();
  c.ellipse(32.5, 1, 2, 17, 0, 0, Math.PI * 2);                           // prop disc
  c.fillStyle = "rgba(40,40,40,.16)";
  c.fill();
  const blade = 17 * Math.cos(t * 47);
  c.fillStyle = "rgba(30,30,30,.65)";
  c.fillRect(31.7, 1 - Math.abs(blade), 1.6, Math.abs(blade) * 2);
  dot(c, 31.5, 1, 3, "#c8372d");
  if (mod(t, 1.1) < 0.06) glow(c, 0, -13, 22, "255,255,255");
  c.restore();
}

function vfr(c: Ctx, w: number, h: number, t: number): void {
  const s = h / 360, hy = h * 0.46;

  const sky = c.createLinearGradient(0, 0, 0, hy);
  sky.addColorStop(0, "#3d8fd6");
  sky.addColorStop(0.7, "#8cc4ec");
  sky.addColorStop(1, "#d8ecf7");
  c.fillStyle = sky;
  c.fillRect(0, 0, w, hy + 30 * s);
  cloudLayer(c, w, h * 0.14, t * 5 * s, 760 * s, 3, 24 * s, "#ffffff", "#d3e2ef", 7);

  ridge(c, w, h, hy + 4 * s, 26 * s, t * 3 * s, "#8eaeb6", 1, s);
  ridge(c, w, h, hy + 28 * s, 22 * s, t * 9 * s, "#79a067", 4, s);

  let y = hy + 26 * s;
  [14, 20, 30, 44, 66, 96].forEach((rh, i) => {
    fieldRow(c, w, y, rh * s, t * rh * 2.4 * s, 200 + i * 31);
    y += rh * s;
  });

  // hedgerow trees rushing past right under the camera
  const tile = 300 * s, o = mod(t * 170 * s, tile);
  for (let k = 0; k * tile - o < w + 60 * s; k++) {
    for (let j = 0; j < 4; j++) {
      const tx = k * tile - o + j * 26 * s + hash(k * 7 + j) * 12 * s;
      const tr = (18 + hash(k * 3 + j) * 12) * s;
      dot(c, tx, h + 4 * s, tr, "#2d5024");
      dot(c, tx - tr * 0.3, h - tr * 0.2, tr * 0.6, "#3a6630");
    }
  }

  cessna(c, w * 0.42, h * 0.3 + Math.sin(t * 1.4) * 4 * s, 1.6 * s, t);
}

const SCENES: Record<Loc, (c: Ctx, w: number, h: number, t: number) => void> = { airport, cruise, vfr };

// ---------- canvas plumbing ----------

function fit(cv: HTMLCanvasElement, cx: Ctx): { w: number; h: number } {
  const r = cv.getBoundingClientRect();
  const d = Math.min(2, window.devicePixelRatio || 1);
  const W = Math.round(r.width * d), H = Math.round(r.height * d);
  if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
  cx.setTransform(d, 0, 0, d, 0, 0);
  return { w: r.width, h: r.height };
}

// ---------- graph ----------

let col = { cpu: "", gpu: "", line: "", muted: "", ink: "" };
let hatchCpu: CanvasPattern | null = null;
let hatchGpu: CanvasPattern | null = null;
let yMax = 40;
const avg = { cpu: 0, gpu: 0, frame: 0 };

function hatch(color: string): CanvasPattern | null {
  const p = document.createElement("canvas");
  p.width = p.height = 6;
  const x = p.getContext("2d")!;
  x.strokeStyle = color;
  x.lineWidth = 1.1;
  x.beginPath();
  x.moveTo(-1, 7); x.lineTo(7, -1);
  x.moveTo(-1, 1); x.lineTo(1, -1);
  x.moveTo(5, 7); x.lineTo(7, 5);
  x.stroke();
  return x.createPattern(p, "repeat");
}

function readColors(): void {
  const cs = getComputedStyle(document.documentElement);
  const v = (n: string): string => cs.getPropertyValue(n).trim();
  col = { cpu: v("--idx-cpu"), gpu: v("--idx-gpu"), line: v("--line"), muted: v("--muted"), ink: v("--ink-2") };
  hatchCpu = hatch(col.cpu);
  hatchGpu = hatch(col.gpu);
}

function drawGraph(cv: HTMLCanvasElement, c: Ctx, now: number, dt: number): void {
  const { w, h } = fit(cv, c);
  const narrow = w < 480;
  const L = narrow ? 42 : 52, R = narrow ? 52 : 62, T = 8, B = 6;
  const pw = w - L - R, ph = h - T - B;
  if (pw <= 0) return;

  let peak = 0;
  for (const f of frames) if (f.t > now - WINDOW) peak = Math.max(peak, f.frame);
  const target = [20, 40, 60, 80, 120, 160, 240].find((m) => m >= peak * 1.1) ?? 240;
  yMax += (target - yMax) * Math.min(1, dt * 3);

  const X = (t: number): number => L + pw * (1 - (now - t) / WINDOW);
  const Y = (ms: number): number => T + ph * (1 - ms / yMax);

  c.clearRect(0, 0, w, h);

  // frame-rate guides, thinned so labels never collide
  c.font = `600 ${narrow ? 9.5 : 10.5}px "Open Sans", sans-serif`;
  c.textBaseline = "middle";
  let lastY = -Infinity;
  for (const fps of [10, 15, 20, 30, 60, 120, 240]) {
    const y = Y(1000 / fps);
    if (y < T + 6 || y - lastY < 20) continue;
    lastY = y;
    c.strokeStyle = col.line;
    c.lineWidth = 1;
    c.setLineDash(fps === 30 || fps === 60 ? [] : [3, 4]);
    c.beginPath();
    c.moveTo(L, Math.round(y) + 0.5);
    c.lineTo(L + pw, Math.round(y) + 0.5);
    c.stroke();
    c.fillStyle = col.muted;
    c.textAlign = "right";
    c.fillText(`${fps} FPS`, L - 8, y);
  }
  c.setLineDash([]);
  c.strokeStyle = col.line;
  c.beginPath();
  c.moveTo(L, T + ph + 0.5);
  c.lineTo(L + pw, T + ph + 0.5);
  c.stroke();

  c.save();
  c.beginPath();
  c.rect(L, T, pw, ph);
  c.clip();

  // the faster half's idle time: from its own line up to the frame
  for (const f of frames) {
    const x1 = X(f.t), x0 = X(f.t - f.frame);
    if (x1 < L) continue;
    const lo = Math.min(f.cpu, f.gpu);
    if (f.frame - lo < 0.05) continue;
    const pat = f.cpu > f.gpu ? hatchGpu : hatchCpu;
    const top = Y(f.frame), bot = Y(lo);
    c.globalAlpha = 0.09;
    c.fillStyle = f.cpu > f.gpu ? col.gpu : col.cpu;
    c.fillRect(x0, top, x1 - x0 + 0.4, bot - top);
    if (pat) {
      c.globalAlpha = 0.55;
      c.fillStyle = pat;
      c.fillRect(x0, top, x1 - x0 + 0.4, bot - top);
    }
  }
  c.globalAlpha = 1;

  c.lineWidth = 1.8;
  c.lineJoin = "round";
  for (const k of ["gpu", "cpu"] as const) {
    c.strokeStyle = col[k];
    c.beginPath();
    let started = false;
    for (const f of frames) {
      const x = X(f.t - f.frame / 2);
      if (x < L - 20) continue;
      if (started) c.lineTo(x, Y(f[k]));
      else { c.moveTo(x, Y(f[k])); started = true; }
    }
    c.stroke();
  }
  c.restore();

  // live values at the right edge, nudged apart when the lines cross
  if (avg.frame > 0) {
    let yc = Y(avg.cpu), yg = Y(avg.gpu);
    if (Math.abs(yc - yg) < 14) {
      const mid = (yc + yg) / 2, up = yc < yg ? -7 : 7;
      yc = mid + up; yg = mid - up;
    }
    c.textAlign = "left";
    c.font = `700 ${narrow ? 10.5 : 11.5}px "Open Sans", sans-serif`;
    c.fillStyle = col.cpu;
    c.fillText(`${avg.cpu.toFixed(1)} ms`, L + pw + 8, Math.min(h - 8, Math.max(T + 6, yc)));
    c.fillStyle = col.gpu;
    c.fillText(`${avg.gpu.toFixed(1)} ms`, L + pw + 8, Math.min(h - 8, Math.max(T + 6, yg)));
  }
}

// ---------- usage panel ----------

/* What Task Manager would read, sampled every half second as it roughly does. The point
 * it has to make: the MainThread is one thread, and Windows keeps moving it, so a chip
 * that is the limit can read as a quarter busy with no core at 100%. */
const HIST = 24;          // samples per thread graph (12 s)
const usage = { hist: [] as number[][], mt: 0, cpu: 0, gpu: 0, peak: 0 };

const topo = (): { cores: number; threads: number; pThreads: number } =>
  TOPO[CPUS[state.cpu].slug] ?? { cores: 8, threads: 16, pThreads: 16 };

function sampleUsage(): void {
  const spec = topo(), T = spec.threads;
  if (usage.hist.length !== T) {
    usage.hist = Array.from({ length: T }, () => new Array<number>(HIST).fill(0));
    usage.mt = 0;
  }
  if (avg.frame <= 0) return;
  const L = LOCS[state.loc];
  const load = Array.from({ length: T }, () => 0.01 + Math.random() * 0.03);   // the rest of Windows

  // The MainThread is busy for its share of every frame. Within one sample it hops
  // between performance cores a few times, so its time is split across them.
  const busy = Math.min(1, avg.cpu / avg.frame);
  const hops = 1 + Math.floor(Math.random() * 3);
  for (let k = 0; k < hops; k++) {
    if (k > 0) usage.mt = Math.floor(Math.random() * spec.pThreads);
    load[usage.mt] += busy / hops;
  }

  // Helpers — AI, audio, the driver's render thread, scenery decoding — spread evenly.
  // A slower chip spends longer on the same work.
  const slow = 90 / cpuIndex(CPUS[state.cpu]);
  const n = Math.min(L.workers.n, T - 1);
  for (let k = 0; k < n; k++) {
    const i = Math.floor(((k + 0.5) / n) * T);
    load[i] += (L.workers.load + ADDONS[state.addon].workers) * slow * (0.7 + Math.random() * 0.6)
      + (Math.random() < 0.3 ? L.workers.burst * Math.random() * 2 : 0);
  }

  let sum = 0, peak = 0;
  for (let i = 0; i < T; i++) {
    const v = Math.min(1, load[i]);
    usage.hist[i].push(v);
    usage.hist[i].shift();
    sum += v;
    peak = Math.max(peak, v);
  }
  usage.cpu = sum / T;
  usage.peak = peak;
  usage.gpu = Math.min(0.99, (avg.gpu / avg.frame) * (0.96 + Math.random() * 0.04));
}

function drawCores(cv: HTMLCanvasElement, c: Ctx): void {
  const T = usage.hist.length;
  if (!T) return;
  const spec = topo();
  const width = cv.getBoundingClientRect().width;
  // Widest column count that divides the thread count evenly, so rows come out full.
  const fits = Math.floor(width / 58);
  let cols = 4;
  for (let k = Math.min(10, T); k >= 4; k--) if (T % k === 0 && k <= fits) { cols = k; break; }
  const rows = Math.ceil(T / cols), gap = 6, cellH = width < 480 ? 40 : 48;
  const want = `${rows * cellH + (rows - 1) * gap}px`;
  if (cv.style.height !== want) cv.style.height = want;
  const { w, h } = fit(cv, c);
  const cw = (w - gap * (cols - 1)) / cols;
  c.clearRect(0, 0, w, h);
  c.font = '700 9.5px "Open Sans", sans-serif';
  c.textBaseline = "top";
  c.textAlign = "left";

  for (let i = 0; i < T; i++) {
    const x = (i % cols) * (cw + gap), y = Math.floor(i / cols) * (cellH + gap);
    const hist = usage.hist[i];
    const px = (j: number): number => x + (j / (HIST - 1)) * cw;
    const py = (v: number): number => y + cellH - 1 - v * (cellH - 3);
    c.beginPath();
    c.moveTo(x, y + cellH);
    hist.forEach((v, j) => c.lineTo(px(j), py(v)));
    c.lineTo(x + cw, y + cellH);
    c.closePath();
    c.globalAlpha = 0.2;
    c.fillStyle = col.cpu;
    c.fill();
    c.globalAlpha = 1;
    c.beginPath();
    hist.forEach((v, j) => (j ? c.lineTo(px(j), py(v)) : c.moveTo(px(j), py(v))));
    c.strokeStyle = col.cpu;
    c.lineWidth = 1.2;
    c.stroke();
    const here = i === usage.mt;
    c.strokeStyle = here ? col.ink : col.line;
    c.lineWidth = here ? 2 : 1;
    c.strokeRect(x + (here ? 1 : 0.5), y + (here ? 1 : 0.5), cw - (here ? 2 : 1), cellH - (here ? 2 : 1));
    if (i >= spec.pThreads) {
      c.fillStyle = col.muted;
      c.fillText("E", x + 4, y + 3);
    }
  }
}

// ---------- controls ----------

const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;

function seg<T extends string>(el: HTMLElement, items: [T, string, string?][], get: () => T, set: (v: T) => void): void {
  el.innerHTML = items.map(([v, label, sub]) =>
    `<button type="button" data-v="${v}">${label}${sub ? `<small>${sub}</small>` : ""}</button>`).join("");
  const sync = (): void => el.querySelectorAll<HTMLButtonElement>("button")
    .forEach((b) => b.classList.toggle("on", b.dataset.v === get()));
  el.addEventListener("click", (e) => {
    const b = (e.target as HTMLElement).closest("button");
    if (!b) return;
    set(b.dataset.v as T);
    sync();
  });
  sync();
}

function slider(el: HTMLElement, label: string, stops: Step[], badge: (i: number) => string,
                get: () => number, set: (i: number) => void,
                title: (i: number) => string = (i) => stops[i].part): () => void {
  const n = stops.length;
  el.innerHTML = `
    <div class="sl-head"><span class="ctl-label">${label}</span><span class="sl-ix"></span></div>
    <div class="sl-name"></div>
    <input type="range" min="0" max="${n - 1}" step="1" aria-label="${label}">
    <div class="ticks${n > 6 ? " dense" : ""}">${stops.map((s, i) =>
      `<button type="button" data-i="${i}" style="--p:${i / (n - 1)}">${s.short}</button>`).join("")}</div>`;
  const input = el.querySelector("input")!;
  const name = el.querySelector<HTMLElement>(".sl-name")!;
  const ix = el.querySelector<HTMLElement>(".sl-ix")!;
  const ticks = el.querySelectorAll<HTMLButtonElement>(".ticks button");
  const render = (): void => {
    const i = get();
    input.value = String(i);
    name.textContent = title(i);
    ix.textContent = badge(i);
    ticks.forEach((b) => b.classList.toggle("on", Number(b.dataset.i) === i));
  };
  input.addEventListener("input", () => { set(Number(input.value)); render(); });
  ticks.forEach((b) => b.addEventListener("click", () => { set(Number(b.dataset.i)); render(); }));
  render();
  return render;
}

function pick(cat: Cat[], picks: [string, string, string?][]): Stop[] {
  const out: Stop[] = [];
  for (const [part, short] of picks) {
    const c = cat.find((x) => x.part === part);
    if (c) out.push({ part, short, slug: short.toLowerCase().replace(/[^a-z0-9]/g, ""), idx: c.idx });
  }
  return out;
}

function readUrl(): void {
  const q = new URLSearchParams(location.search);
  const at = q.get("at"), res = q.get("res");
  if (at && at in LOCS) state.loc = at as Loc;
  if (res && (RESES as string[]).includes(res)) state.res = res as Res;
  const ci = CPUS.findIndex((s) => s.slug === q.get("cpu"));
  const gi = GPUS.findIndex((s) => s.slug === q.get("gpu"));
  if (ci >= 0) state.cpu = ci;
  if (gi >= 0) state.gpu = gi;
  const ti = TEXTURES.findIndex((s) => s.short.toLowerCase() === q.get("tex"));
  const ai = ADDONS.findIndex((s) => s.short.toLowerCase() === q.get("addons"));
  if (ti >= 0) state.tex = ti;
  if (ai >= 0) state.addon = ai;
  state.small = q.get("mem") === "small";
}

function writeUrl(): void {
  const q = new URLSearchParams({
    at: state.loc, res: state.res, cpu: CPUS[state.cpu].slug, gpu: GPUS[state.gpu].slug,
    tex: TEXTURES[state.tex].short.toLowerCase(), addons: ADDONS[state.addon].short.toLowerCase(),
  });
  if (state.small && GPUS[state.gpu].alt) q.set("mem", "small");
  history.replaceState(null, "", `?${q}`);
}

function wireTheme(): void {
  let theme = localStorage.getItem("msfs-theme") || "dark";
  const btn = $("themeToggleBtn");
  btn.textContent = theme;
  btn.addEventListener("click", () => {
    theme = theme === "dark" ? "light" : "dark";
    localStorage.setItem("msfs-theme", theme);
    document.documentElement.dataset.theme = theme;
    btn.textContent = theme;
    readColors();
  });
}

// ---------- boot ----------

async function boot(): Promise<void> {
  wireTheme();
  // GPUs come from gpu_index, not the catalogue: the catalogue only holds priced parts.
  // VRAM and PCIe link per card come from gpu_data.json's spec table.
  let doc: { catalogue: { cpus: Cat[] }; gpu_index: Record<string, Record<string, number>> };
  let specs: Record<string, { vram: number; pcie: string }>;
  try {
    const [b, g] = await Promise.all([fetch("/builds.json"), fetch("/gpu_data.json")]);
    doc = await b.json();
    specs = (await g.json()).specs ?? {};
  } catch {
    $("stage").innerHTML = `<p class="fail">Could not load the index data (builds.json).</p>`;
    return;
  }
  CPUS = pick(doc.catalogue.cpus, CPU_PICKS).sort((a, b) => cpuIndex(a) - cpuIndex(b));
  const gpuCat: Cat[] = GPU_PICKS.map(([part]) => ({
    part,
    idx: Object.fromEntries(RESES.flatMap((r) => {
      const v = doc.gpu_index?.[r]?.[part];
      return v == null ? [] : [[r, v]];
    })),
  })).filter((g) => Object.keys(g.idx).length === RESES.length);
  GPUS = pick(gpuCat, GPU_PICKS).sort((a, b) => gpuIndex(a, "1440p") - gpuIndex(b, "1440p"));
  for (const g of GPUS) { g.vram = specs[g.part]?.vram; g.pcie = specs[g.part]?.pcie; }
  for (const [part, , alt] of GPU_PICKS) {
    const g = GPUS.find((x) => x.part === part);
    if (g && alt && specs[alt]) g.alt = { part: alt, vram: specs[alt].vram, pcie: specs[alt].pcie };
  }
  if (CPUS.length < 2 || GPUS.length < 2) {
    $("stage").innerHTML = `<p class="fail">The index data is missing the chips this page uses.</p>`;
    return;
  }
  state.cpu = Math.max(0, CPUS.findIndex((s) => s.slug === "5600"));
  state.gpu = Math.max(0, GPUS.findIndex((s) => s.slug === "9070"));
  readUrl();

  const locName = $("locName"), locNote = $("locNote");
  const showLoc = (): void => { locName.textContent = LOCS[state.loc].name; locNote.textContent = LOCS[state.loc].note; };
  showLoc();

  const vramBox = $("vramBox"), vramRead = $("vramRead"), vcap = $("vcap"), hudVram = $("hudVram");
  const segs = ["base", "loc", "tex", "add"].map((k) => vramBox.querySelector<HTMLElement>(`.seg-${k}`)!);
  const segOver = vramBox.querySelector<HTMLElement>(".seg-over")!;
  const showVram = (): void => {
    const v = vram();
    const scale = Math.max(v.cap * 1.25, v.used * 1.06);
    const pct = (gb: number): string => `${(gb / scale) * 100}%`;
    let at = 0;
    v.parts.forEach((gb, i) => { segs[i].style.left = pct(at); segs[i].style.width = pct(gb); at += gb; });
    segOver.style.left = pct(v.cap);
    segOver.style.width = pct(v.over);
    vcap.style.left = pct(v.cap);
    vcap.firstElementChild!.textContent = `${v.cap} GB`;
    const over = v.over > 0;
    vramBox.classList.toggle("over", over);
    vramRead.textContent = over
      ? `${v.used.toFixed(1)} GB · ${v.over.toFixed(1)} GB over`
      : `${v.used.toFixed(1)} of ${v.cap} GB`;
    hudVram.textContent = `VRAM ${v.used.toFixed(1)} / ${v.cap} GB`;
    hudVram.classList.toggle("over", over);
  };
  const changed = (): void => { writeUrl(); showVram(); };
  let renderAddon = (): void => {};                   // its badge depends on the location

  seg(
    $("locSeg"),
    (Object.keys(LOCS) as Loc[]).map((k) => [k, LOCS[k].label, LOCS[k].sub] as [Loc, string, string]),
    () => state.loc,
    (v) => { state.loc = v; showLoc(); renderAddon(); changed(); },
  );
  let renderGpu = (): void => {};
  seg(
    $("resSeg"),
    RESES.map((r) => [r, r] as [Res, string]),
    () => state.res,
    (v) => { state.res = v; renderGpu(); changed(); },
  );
  slider($("cpuField"), "CPU", CPUS, (i) => `Index ${cpuIndex(CPUS[i])}`,
    () => state.cpu, (i) => { state.cpu = i; changed(); });
  const memSeg = document.createElement("div");
  memSeg.className = "seg mem-seg";
  renderGpu = slider($("gpuField"), "GPU", GPUS,
    (i) => `Index ${gpuIndex(GPUS[i], state.res)} · ${mem(i).vram ?? "?"} GB`,
    () => state.gpu, (i) => { state.gpu = i; memSeg.hidden = !GPUS[i].alt; changed(); },
    (i) => mem(i).part);
  const twin = GPUS.find((g) => g.alt);
  if (twin?.alt) {
    $("gpuField").append(memSeg);
    seg(memSeg, [["big", `${twin.vram} GB`], ["small", `${twin.alt.vram} GB`]],
      () => (state.small ? "small" : "big"),
      (v) => { state.small = v === "small"; renderGpu(); changed(); });
  }
  memSeg.hidden = !GPUS[state.gpu].alt;
  slider($("texField"), "Textures", TEXTURES, (i) => `+${TEXTURES[i].gb.toFixed(1)} GB`,
    () => state.tex, (i) => { state.tex = i; changed(); });
  renderAddon = slider($("addonField"), "Addons", ADDONS,
    (i) => (i ? `+${addonGb(i).toFixed(1)} GB · MainThread` : "nothing extra"),
    () => state.addon, (i) => { state.addon = i; changed(); });
  showVram();

  readColors();
  new MutationObserver(readColors).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  const sceneCv = $<HTMLCanvasElement>("scene"), graphCv = $<HTMLCanvasElement>("graph");
  const sc = sceneCv.getContext("2d")!, gc = graphCv.getContext("2d")!;
  const fpsEl = $("fps"), limEl = $("lim"), msCpu = $("msCpu"), msGpu = $("msGpu"), idleEl = $("idle");
  const usageEl = $<HTMLDetailsElement>("usage"), coresCv = $<HTMLCanvasElement>("cores");
  const cc = coresCv.getContext("2d")!;
  const uCpu = $("uCpu"), uGpu = $("uGpu"), uCpuBar = $("uCpuBar"), uGpuBar = $("uGpuBar");
  const uTopo = $("uTopo"), uNow = $("uNow");

  const showUsage = (): void => {
    if (!usageEl.open) return;
    const spec = topo(), c = Math.round(usage.cpu * 100), g = Math.round(usage.gpu * 100);
    uCpu.textContent = `${c}%`;
    uGpu.textContent = `${g}%`;
    uCpuBar.style.width = `${c}%`;
    uGpuBar.style.width = `${g}%`;
    uTopo.textContent = `${CPUS[state.cpu].part} · ${spec.cores} cores, ${spec.threads} logical processors`
      + (spec.pThreads < spec.threads ? " (E = efficiency core)" : "");
    const cpuLim = avg.cpu >= avg.gpu;
    uNow.innerHTML = `Right now: <b>CPU ${c}%</b> overall, busiest thread ${Math.round(usage.peak * 100)}%,
      <b>GPU ${g}%</b> — and the frame is <b class="${cpuLim ? "c" : "g"}">limited by
      ${cpuLim ? "the MainThread" : "the GPU"}</b>.`;
    drawCores(coresCv, cc);
  };
  usageEl.addEventListener("toggle", showUsage);
  if (location.hash === "#usage") usageEl.open = true;          // linkable from Discord
  let lastUsage = 0;

  cur.cpu = targetCpu();
  cur.gpu = targetGpu();
  let last = performance.now(), lastHud = 0, shownLoc: Loc | null = null;
  pending = makeFrame(last);

  const hud = (now: number): void => {
    let n = 0, cs = 0, gs = 0, fs = 0;
    for (let i = frames.length - 1; i >= 0 && frames[i].t > now - 700; i--) {
      n++; cs += frames[i].cpu; gs += frames[i].gpu; fs += frames[i].frame;
    }
    if (!n) return;
    avg.cpu = cs / n; avg.gpu = gs / n; avg.frame = fs / n;
    const cpuLim = avg.cpu >= avg.gpu;
    fpsEl.textContent = String(Math.round(1000 / avg.frame));
    limEl.textContent = cpuLim ? "Limited by MainThread" : "Limited by GPU";
    limEl.className = `hud-lim ${cpuLim ? "cpu" : "gpu"}`;
    msCpu.textContent = `${avg.cpu.toFixed(1)} ms`;
    msGpu.textContent = `${avg.gpu.toFixed(1)} ms`;
    const wait = Math.abs(avg.cpu - avg.gpu);
    const v = vram();
    idleEl.innerHTML = v.over > 0
      ? `<b class="over">Out of VRAM.</b> ${v.over.toFixed(1)} GB does not fit on the ${v.cap} GB card, so it
         spills into system RAM over a PCIe ${GPUS[state.gpu].pcie ?? ""} link. Frames wait for it to come back —
         that is the stutter. Lower textures or addons, or pick a card with more memory.`
      : wait < 1
      ? `Both halves finish within a millisecond of each other — upgrading just one buys almost nothing,
         because the other becomes the limit straight away. Only upgrading both moves the frame rate.`
      : `${cpuLim ? '<b class="g">GPU</b>' : '<b class="c">MainThread</b>'} waits <b>${wait.toFixed(1)} ms</b>
         of every ${avg.frame.toFixed(1)} ms frame — a faster ${cpuLim ? "graphics card" : "CPU"} would just wait longer.`;
  };

  const tick = (now: number): void => {
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    const k = 1 - Math.exp(-dt / EASE);
    cur.cpu += (targetCpu() - cur.cpu) * k;
    cur.gpu += (targetGpu() - cur.gpu) * k;

    if (now - pending.start > 400) pending = makeFrame(now);   // tab was hidden
    let done: Frame | null = null;
    for (let guard = 0; pending.start + pending.frame <= now && guard < 400; guard++) {
      const end = pending.start + pending.frame;
      done = { t: end, cpu: pending.cpu, gpu: pending.gpu, frame: pending.frame };
      frames.push(done);
      pending = makeFrame(end);
    }
    while (frames.length && frames[0].t < now - WINDOW - 1000) frames.shift();

    // The scene only moves when a frame lands — that is the whole point of it.
    if (done || shownLoc !== state.loc) {
      const { w, h } = fit(sceneCv, sc);
      if (w > 0 && h > 0) SCENES[state.loc](sc, w, h, (done ? done.t : now) / 1000);
      shownLoc = state.loc;
    }
    if (now - lastHud > 200) { hud(now); lastHud = now; }
    if (now - lastUsage > 500) { sampleUsage(); showUsage(); lastUsage = now; }
    drawGraph(graphCv, gc, now, dt);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

boot();
