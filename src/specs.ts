/* /specs — the build guide.
 *
 * A plain page, not part of the SPA: no routing, no charts, no shared state with
 * main.ts beyond the theme. It renders public/builds.json, which make_build_table.py
 * writes from build_specs.csv + build_prices.csv in the same pass that fills the PNG
 * card — so the page and the card cannot disagree about a price.
 *
 * Nothing here recomputes the index. Both figures arrive already fitted; this file
 * only formats them.
 */
import "./specs.css";

type Item = {
  slot: string;
  part: string;
  eur: number | null;
  src: string | null;
};

type Build = {
  res: string;
  tier: string;
  vendor: string;
  cpu: string;
  ci: number | null;
  cd: boolean;
  cbest: boolean;
  cn: number;
  socket: string | null;
  gpu: string;
  gi: number | null;
  gd: boolean;
  gbest: boolean;
  gn: number;
  vram: number | null;
  ram: string;
  sto: string;
  eur: number | null;
  approx: boolean;
  items: Item[];
};

type NotPicked = {
  part: string;
  eur: number;
  gi: number;
  gd: boolean;
  why: string;
  vram: number | null;
};

type Price = { part: string; eur: number; src: string };

type Named = { part: string; eur: number };

type CatCpu = {
  part: string;
  vendor: string | null;
  socket: string;
  eur: number;
  cov: number;
  idx: Record<string, number>;        // by memory kind: DDR4 / DDR5
  derived: Record<string, boolean>;
  cooler: Named;
  mobo: Record<string, Named>;
};

type CatGpu = {
  part: string;
  vendor: string | null;
  eur: number;
  cov: number;
  idx: Record<string, number>;        // by resolution
  derived: boolean;
  vram: number | null;
  psu: Named;
};

type Catalogue = {
  cpus: CatCpu[];
  gpus: CatGpu[];
  memory: { part: string; kind: string; eur: number; min?: boolean }[];
  storage: Named[];
  case: Named | null;
  blend_cpu: Record<string, number>;
  excluded: { part: string; why: string }[];
};

type Doc = {
  priced_on: string | null;
  currency?: string;
  region?: string;
  source?: string;        // named by the generator from the sources actually present
  resolutions: string[];
  tiers: string[];
  vendors: string[];
  builds: Build[];
  not_picked: NotPicked[];
  prices: Price[];
  catalogue: Catalogue;
};

const RES_LABEL: Record<string, string> = {
  "1080p": "1920 × 1080",
  "1440p": "2560 × 1440",
  "4K": "3840 × 2160",
};

// What each resolution is actually limited by — the reason the picks differ at all.
const RES_NOTE: Record<string, string> = {
  "1080p": "The GPU field compresses to a 5.5× spread here, so the CPU is the limit — " +
    "which is why this ladder tops out below the flagships.",
  "1440p": "The balanced case: GPU decides most of it, but a slow CPU is still felt.",
  "4K": "The spread opens to 17× and the GPU decides everything, so this is the only " +
    "block that reaches a 5090.",
};

const TIER_LABEL: Record<string, string> = { entry: "Entry", mid: "Mid", high: "High End" };
const TIER_NOTE: Record<string, string> = {
  entry: "The cheapest build still worth putting money into",
  mid: "Where the money starts buying frames again",
  high: "The measured ceiling, not the most expensive parts on sale",
};
const VENDOR_LABEL: Record<string, string> = { amd: "AMD", nv: "Nvidia / Intel" };

// Figures quoted in the prose, filled from the price list rather than typed into the
// copy — the numbers move every time the CSV is refreshed, the sentences do not.
// [element id, part, whether to name the part as well as price it]
const PROSE_PRICES: [string, string, boolean][] = [
  ["p-ddr5", "32GB DDR5-6000", false],
  ["p-ddr4", "32GB DDR4-3200", false],
  ["p-9070xt", "RX 9070 XT", true],
  ["p-5070ti", "RTX 5070 Ti", true],
  ["p-5060", "RTX 5060", true],
  ["p-9060xt8", "RX 9060 XT 8GB", false],
  ["p-9060xt16", "RX 9060 XT 16GB", false],
  ["p-285k", "Core Ultra 9 285K", true],
  ["p-250k", "Core Ultra 5 250K Plus", true],
  ["p-14600k", "Core i5-14600K", true],
];

// The shareable PNGs, rendered by make_tierlist_cards.py into public/cards/.
const CARDS: { file: string; title: string; note: string; compact?: string }[] = [
  { file: "msfs24_build_specs.png", title: "Build specs",
    note: "This page, as one image" },
  { file: "msfs24_spec_table.png", title: "Spec table",
    note: "Minimum / recommended / ideal" },
  { file: "msfs24_cpu_tierlist.png", title: "CPU tier list",
    note: "S–E, grouped by generation and V-Cache",
    compact: "msfs24_cpu_tierlist_compact.png" },
  { file: "msfs24_gpu_tierlist_1080p.png", title: "GPU tier list · 1080p",
    note: "Normalised on its own", compact: "msfs24_gpu_tierlist_1080p_compact.png" },
  { file: "msfs24_gpu_tierlist.png", title: "GPU tier list · 1440p",
    note: "Normalised on its own", compact: "msfs24_gpu_tierlist_compact.png" },
  { file: "msfs24_gpu_tierlist_4k.png", title: "GPU tier list · 4K",
    note: "Normalised on its own", compact: "msfs24_gpu_tierlist_4k_compact.png" },
];

let theme = localStorage.getItem("msfs-theme") || "dark";
let DOC: Doc | null = null;
let res = "1440p";

const $ = <T extends HTMLElement>(sel: string) => document.querySelector<T>(sel);
const eur = (n: number) => "€" + n.toLocaleString("en-US");
const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// ---------- chips ----------

/** Index chip. `kind` picks the colour; a derived figure is outlined and carries a °,
 *  so an interpolated number never sits next to a measured one looking identical. */
function chip(v: number | null, kind: "c" | "g", derived: boolean, n: number): string {
  if (v === null) return "";
  const what = kind === "c" ? "CPU" : "GPU";
  const how = derived ? "derived, not directly measured"
    : n > 0 ? `measured across ${n} dataset${n === 1 ? "" : "s"}`
    : "measured";
  return `<span class="ix ${kind}${derived ? " d" : ""}" title="${what} Performance Index ` +
    `${v} — ${how}">${v}${derived ? "°" : ""}</span>`;
}

/** Where a price came from, shown only when it is not an ordinary retail lookup — so a
 *  grey import or a leftover estimate is visible rather than sitting among real prices
 *  looking identical. The two retail sources are unremarkable and stay unmarked. */
const RETAIL = ["tweakers", "pcpp"];
function srcTag(src: string | null): string {
  if (!src || RETAIL.includes(src)) return "";
  return `<span class="src" title="${esc(src)} — not an ordinary retail price">` +
    `${esc(src)}</span>`;
}

/** VRAM tag, but only when the number is a compromise. 8 GB reads as critical and
 *  10–12 GB as caution, the same ramp the GPU tier cards use — a thin card has to
 *  look thin rather than slip past as a bargain. */
function vramTag(vram: number | null): string {
  if (vram === null || vram > 12) return "";
  return `<span class="vr ${vram <= 8 ? "v8" : "v12"}">${vram} GB</span>`;
}

// ---------- builds ----------

function buildCard(b: Build): string {
  const ven = b.vendor === "amd" ? "amd" : "nv";
  const total = b.eur === null
    ? `<span class="total none">—</span>`
    : `<span class="total">${b.approx ? "~" : ""}${eur(b.eur)}</span>`;

  const rows = [
    { label: "CPU", value: b.cpu, tint: b.vendor === "amd" ? "amd" : "intel",
      extra: chip(b.ci, "c", b.cd, b.cn), best: b.cbest,
      sub: b.socket ? b.socket : "" },
    { label: "GPU", value: b.gpu, tint: ven,
      extra: vramTag(b.vram) + chip(b.gi, "g", b.gd, b.gn), best: b.gbest, sub: "" },
    { label: "Memory", value: b.ram, tint: "", extra: "", best: false, sub: "" },
    { label: "Storage", value: b.sto, tint: "", extra: "", best: false, sub: "" },
  ];

  const body = rows.map(r => `
    <div class="brow${r.best ? " best" : ""}">
      <span class="blabel">${r.label}</span>
      <span class="bval ${r.tint}">${esc(r.value)}
        ${r.sub ? `<span class="bsub">${esc(r.sub)}</span>` : ""}
        ${r.extra}
        ${r.best ? `<span class="tick" title="Better index per euro of the two columns">✔</span>` : ""}
      </span>
    </div>`).join("");

  const bom = b.items.map(i => `
    <tr>
      <th>${esc(i.slot)}</th>
      <td>${esc(i.part)}${srcTag(i.src)}</td>
      <td class="num">${i.eur === null ? "—" : eur(i.eur)}</td>
    </tr>`).join("");

  return `
    <article class="build ${ven}">
      <div class="bhead">
        <span class="ven">${VENDOR_LABEL[b.vendor] || b.vendor}</span>
        ${total}
      </div>
      ${body}
      <details class="bom">
        <summary>Full parts list</summary>
        <table>
          ${bom}
          <tr class="sum"><th></th><td>Complete build</td>
            <td class="num">${b.eur === null ? "—" : (b.approx ? "~" : "") + eur(b.eur)}</td></tr>
        </table>
      </details>
    </article>`;
}

function renderBuilds(): void {
  const host = $("#builds");
  if (!host || !DOC) return;
  const doc = DOC;

  host.innerHTML = doc.tiers.map(tier => {
    const cards = doc.vendors
      .map(v => doc.builds.find(b => b.res === res && b.tier === tier && b.vendor === v))
      .filter((b): b is Build => !!b)
      .map(buildCard)
      .join("");
    if (!cards) return "";
    return `
      <section class="tier">
        <h2>${TIER_LABEL[tier] || tier}<span>${TIER_NOTE[tier] || ""}</span></h2>
        <div class="pair">${cards}</div>
      </section>`;
  }).join("");

  const note = $("#resNote");
  if (note) note.textContent = RES_NOTE[res] || "";
}

function renderNotPicked(): void {
  const host = $("#notPicked");
  if (!host || !DOC) return;
  host.innerHTML = DOC.not_picked.map(n => `
    <div class="np ${/^RX /.test(n.part) ? "amd" : "nv"}">
      <span class="np-part">${esc(n.part)}${vramTag(n.vram)}</span>
      ${chip(n.gi, "g", n.gd, 0)}
      <span class="np-eur">${eur(n.eur)}</span>
      <span class="np-why">${esc(n.why)}</span>
    </div>`).join("");
}

function renderPrices(): void {
  const table = $<HTMLTableElement>("#priceTable");
  if (!table || !DOC) return;
  const rows = [...DOC.prices].sort((a, b) => b.eur - a.eur);
  table.innerHTML =
    `<thead><tr><th>Part</th><th class="num">EUR</th></tr></thead><tbody>` +
    rows.map(p => `<tr><td>${esc(p.part)}${srcTag(p.src)}</td>` +
      `<td class="num">${eur(p.eur)}</td></tr>`).join("") +
    `</tbody>`;
  const count = $("#priceCount");
  if (count) count.textContent = `${rows.length} parts`;
}

function renderProse(): void {
  if (!DOC) return;
  const byPart = new Map(DOC.prices.map(p => [p.part, p.eur]));
  for (const [id, part, named] of PROSE_PRICES) {
    const price = byPart.get(part);
    const el = document.getElementById(id);
    // a part that has fallen out of the price list leaves the copy as authored rather
    // than blanking a sentence mid-way
    if (!el || price === undefined) continue;
    el.textContent = named ? `${part} at ${eur(price)}` : eur(price);
  }
}

function renderCards(): void {
  const host = $("#cards");
  if (!host) return;
  host.innerHTML = CARDS.map(c => `
    <figure class="cardlink">
      <a href="/cards/${c.file}" target="_blank" rel="noopener">
        <img src="/cards/${c.file}" alt="${esc(c.title)}" loading="lazy">
      </a>
      <figcaption>
        <b>${esc(c.title)}</b>
        <span>${esc(c.note)}</span>
        ${c.compact
          ? `<a class="alt" href="/cards/${c.compact}" target="_blank" rel="noopener">compact ↗</a>`
          : ""}
      </figcaption>
    </figure>`).join("");
}

// ---------- build generator ----------
//
// Brute force: ~15 CPUs x ~16 GPUs x 2 memory kinds is a few hundred combinations, so
// there is nothing to be clever about. The value is in what it refuses to do — spend
// the last of a budget on a point of index, or put an 8 GB card above 1080p.

/** Score worth nothing extra: within this, take the cheaper build. */
const TOL = 1.0;
/** What counts as a real step up when reporting the next one. */
const STEP = 3.0;

const CPU_VENDORS = ["AMD", "Intel"];
const GPU_VENDORS = ["AMD", "Nvidia", "Intel"];
const VENDOR_CLASS: Record<string, string> = {
  AMD: "amd", Intel: "intel", Nvidia: "nvidia",
};

type GenState = {
  budget: number;
  cpu: Set<string>;
  gpu: Set<string>;
  allow8: boolean;
};

type Cand = {
  score: number;
  eur: number;
  cpu: CatCpu;
  gpu: CatGpu;
  mem: { part: string; kind: string; eur: number; min?: boolean };
  ci: number;
  gi: number;
  cd: boolean;
};

const gen: GenState = {
  budget: 1500,
  cpu: new Set(CPU_VENDORS),
  gpu: new Set(GPU_VENDORS),
  allow8: false,
};

/** VRAM policy, matching the hand-picked builds: 16 GB is the floor above 1080p, where
 *  a thin card does not degrade gently. 10–12 GB is a 1080p compromise, 8 GB only if
 *  you have said you will accept one. */
function vramOk(g: CatGpu, atRes: string, allow8: boolean): boolean {
  const v = g.vram ?? 0;
  if (v >= 16) return true;
  if (atRes !== "1080p") return false;
  return v > 8 || allow8;
}

function candidates(doc: Doc, atRes: string, st: GenState): Cand[] {
  const C = doc.catalogue;
  const w = C.blend_cpu[atRes];
  const store = C.storage.length
    ? C.storage.reduce((a, b) => (b.eur < a.eur ? b : a)) : null;
  if (w === undefined || !store || !C.case) return [];

  const out: Cand[] = [];
  for (const cpu of C.cpus) {
    if (!cpu.vendor || !st.cpu.has(cpu.vendor)) continue;
    for (const mem of C.memory) {
      // 16 GB kits are minimum-spec only. Capacity is not scored — nothing in the index
      // knows how much memory a build has — so as an ordinary option the cheapest kit
      // would win every build, and a €5,000 machine would come back with 16 GB.
      if (mem.min && !st.allow8) continue;
      const ci = cpu.idx[mem.kind];
      const board = cpu.mobo[mem.kind];
      if (ci === undefined || !board) continue;      // socket cannot take this memory
      const platform = cpu.eur + mem.eur + board.eur + cpu.cooler.eur
        + C.case.eur + store.eur;
      for (const gpu of C.gpus) {
        if (!gpu.vendor || !st.gpu.has(gpu.vendor)) continue;
        if (!vramOk(gpu, atRes, st.allow8)) continue;
        const gi = gpu.idx[atRes];
        if (gi === undefined) continue;
        out.push({
          // weighted geometric mean: an unbalanced build is punished rather than
          // averaged out, which an arithmetic mean would not do
          score: Math.pow(ci, w) * Math.pow(gi, 1 - w),
          eur: platform + gpu.eur + gpu.psu.eur,
          cpu, gpu, mem, ci, gi, cd: !!cpu.derived[mem.kind],
        });
      }
    }
  }
  return out;
}

/** Best score the budget reaches, then the cheapest build that ties it. */
function pick(cands: Cand[], budget: number): Cand | null {
  const afford = cands.filter(c => c.eur <= budget);
  if (!afford.length) return null;
  const top = Math.max(...afford.map(c => c.score));
  return afford.filter(c => c.score >= top - TOL)
    .reduce((a, b) => (b.eur < a.eur ? b : a));
}

/** Where a value sits in its own ladder, 0–1. Used only to notice a lopsided build. */
function rankOf(v: number, all: number[]): number {
  const lo = Math.min(...all), hi = Math.max(...all);
  return hi > lo ? (v - lo) / (hi - lo) : 1;
}

type GenResult =
  | { ok: false; reason: "vendors" }
  | { ok: false; reason: "vram" }
  | { ok: false; reason: "budget"; floor: number }
  | { ok: true; best: Cand; total: number; sto: Named; mem: { part: string; eur: number };
      items: Item[];
      next: Cand | null; headroom: number; lopsided: string | null };

function generate(doc: Doc, atRes: string, st: GenState): GenResult {
  const C = doc.catalogue;
  const cands = candidates(doc, atRes, st);
  if (!cands.length) {
    // Distinguish "you turned off the only vendor that makes one" from "every card
    // that vendor makes is under the VRAM floor for this resolution" — the second is
    // the interesting one, and it is what happens to Arc above 1080p.
    const loose = candidates(doc, atRes, { ...st, allow8: true })
      .concat(candidates(doc, "1080p", { ...st, allow8: true }));
    return { ok: false, reason: loose.length ? "vram" : "vendors" };
  }

  const best = pick(cands, st.budget);
  if (!best) {
    return { ok: false, reason: "budget",
             floor: Math.min(...cands.map(c => c.eur)) };
  }

  // Leftover first buys its way back off minimum spec. "Minimum" means the generator may
  // drop to 16 GB when the budget demands it, not that it should leave 16 GB in a machine
  // that can afford 32 — and since capacity is not scored, only the money can decide.
  let total = best.eur, mem = best.mem;
  if (mem.min) {
    const full = C.memory
      .filter(m => !m.min && m.kind === mem.kind && m.eur > mem.eur)
      .sort((a, b) => a.eur - b.eur)[0];
    if (full && total + (full.eur - mem.eur) <= st.budget) {
      total += full.eur - mem.eur;
      mem = full;
    }
  }

  // Then storage. It buys no frames — it is simply the only thing left on the list that
  // money improves, so the build uses the budget rather than banking it.
  const small = C.storage.reduce((a, b) => (b.eur < a.eur ? b : a));
  const large = C.storage.reduce((a, b) => (b.eur > a.eur ? b : a));
  let sto = small;
  if (large !== small && total + (large.eur - small.eur) <= st.budget) {
    total += large.eur - small.eur;
    sto = large;
  }

  // The next real step up, re-picked at its own price so the step is itself balanced
  // rather than the cheapest chip that happens to clear the threshold.
  const upto = cands.filter(c => c.score >= best.score + STEP).map(c => c.eur);
  const next = upto.length ? pick(cands, Math.min(...upto)) : null;

  // A build can be the best its budget reaches and still be lopsided — most visibly at
  // 4K, where the GPU carries 80% of the score and a huge card outruns a cheap chip.
  const cpuRank = rankOf(best.ci, cands.map(c => c.ci));
  const gpuRank = rankOf(best.gi, cands.map(c => c.gi));
  let lopsided: string | null = null;
  if (gpuRank - cpuRank > 0.45) {
    lopsided = "The card is far ahead of the chip here. MSFS leans on the CPU even at " +
      "high resolutions, so in dense scenery this build will be waiting on the " +
      "processor — a bigger budget should go there first.";
  } else if (cpuRank - gpuRank > 0.45) {
    lopsided = "The chip is far ahead of the card. That is the right way round for " +
      "add-on-heavy flying, but the next money belongs on the GPU.";
  }

  const board = best.cpu.mobo[best.mem.kind];
  const items: Item[] = [
    { slot: "CPU", part: best.cpu.part, eur: best.cpu.eur, src: null },
    { slot: "GPU", part: best.gpu.part, eur: best.gpu.eur, src: null },
    { slot: "Memory", part: mem.part, eur: mem.eur, src: null },
    { slot: "Storage", part: sto.part, eur: sto.eur, src: null },
    { slot: "Motherboard", part: board.part, eur: board.eur, src: null },
    { slot: "Power supply", part: best.gpu.psu.part, eur: best.gpu.psu.eur, src: null },
    { slot: "CPU cooler", part: best.cpu.cooler.part, eur: best.cpu.cooler.eur, src: null },
  ];
  if (C.case) items.push({ slot: "Case", part: C.case.part, eur: C.case.eur, src: null });

  return { ok: true, best, total, sto, mem, items, next,
           headroom: st.budget - total, lopsided };
}

// ---------- generator UI ----------

function vendorChips(host: HTMLElement | null, list: string[], set: Set<string>): void {
  if (!host) return;
  host.innerHTML = list.map(v =>
    `<button class="vchip ${VENDOR_CLASS[v]}${set.has(v) ? " on" : ""}" data-v="${v}"
       aria-pressed="${set.has(v)}">${v}</button>`).join("");
  host.querySelectorAll<HTMLButtonElement>("button").forEach(btn => {
    btn.addEventListener("click", () => {
      const v = btn.dataset.v!;
      // never let the last one be turned off — an empty set can only return nothing
      if (set.has(v) && set.size > 1) set.delete(v);
      else set.add(v);
      btn.classList.toggle("on", set.has(v));
      btn.setAttribute("aria-pressed", String(set.has(v)));
      syncGenUrl();
      runGenerator();
    });
  });
}

function genCard(r: Extract<GenResult, { ok: true }>): string {
  const b = r.best;
  const ven = b.gpu.vendor === "AMD" ? "amd" : "nv";
  const rows = [
    { label: "CPU", value: b.cpu.part, tint: b.cpu.vendor === "AMD" ? "amd" : "intel",
      extra: chip(b.ci, "c", b.cd, b.cpu.cov), sub: b.cpu.socket },
    { label: "GPU", value: b.gpu.part, tint: VENDOR_CLASS[b.gpu.vendor || ""] || "",
      extra: vramTag(b.gpu.vram) + chip(b.gi, "g", b.gpu.derived, b.gpu.cov), sub: "" },
    { label: "Memory", value: r.mem.part, tint: "", extra: "", sub: "" },
    { label: "Storage", value: r.sto.part, tint: "", extra: "", sub: "" },
  ];
  const body = rows.map(row => `
    <div class="brow">
      <span class="blabel">${row.label}</span>
      <span class="bval ${row.tint}">${esc(row.value)}
        ${row.sub ? `<span class="bsub">${esc(row.sub)}</span>` : ""}
        ${row.extra}
      </span>
    </div>`).join("");

  const bom = r.items.map(i => `
    <tr><th>${esc(i.slot)}</th><td>${esc(i.part)}</td>
      <td class="num">${i.eur === null ? "—" : eur(i.eur)}</td></tr>`).join("");

  const notes: string[] = [];
  if (r.headroom >= 40) {
    notes.push(r.next
      ? `<b>${eur(r.headroom)} left over.</b> Nothing between here and
         <b>${eur(r.next.eur)}</b> improves on it — that is where the next real step is.`
      : `<b>${eur(r.headroom)} left over.</b> Nothing in the list improves on this build
         at this resolution, at any price. Spend it on a monitor, a yoke or a headset.`);
  } else if (r.next) {
    notes.push(`<b>${eur(r.next.eur - r.total)} more</b> would reach a
      ${esc(r.next.cpu.part)} with a ${esc(r.next.gpu.part)} —
      ${Math.round(r.next.score - r.best.score)} points better.`);
  }
  if (r.lopsided) notes.push(r.lopsided);

  return `
    <article class="build gen-build ${ven}">
      <div class="bhead">
        <span class="ven">Best build${b.cpu.vendor && b.gpu.vendor
          && b.cpu.vendor !== b.gpu.vendor ? ` · ${esc(b.cpu.vendor)} + ${esc(b.gpu.vendor)}`
          : b.cpu.vendor ? ` · ${esc(b.cpu.vendor)}` : ``}</span>
        <span class="total">${eur(r.total)}</span>
      </div>
      ${body}
      <details class="bom" open>
        <summary>Full parts list</summary>
        <table>${bom}
          <tr class="sum"><th></th><td>Complete build</td>
            <td class="num">${eur(r.total)}</td></tr>
        </table>
      </details>
      ${notes.length ? `<div class="gen-notes">${notes.map(n => `<p>${n}</p>`).join("")}</div>` : ""}
    </article>`;
}

function runGenerator(): void {
  const host = $("#genResult");
  if (!host || !DOC) return;
  const r = generate(DOC, res, gen);

  if (!r.ok) {
    const msg =
      r.reason === "vendors"
        ? `No parts match those vendors at <b>${esc(res)}</b>. Turn one back on.`
      : r.reason === "vram"
        ? `Every card from those vendors is under <b>16 GB</b>, which this page only
           allows at 1080p — above it a thin card falls off a cliff rather than
           degrading. Add another GPU vendor, or drop to 1080p.`
        : `Nothing sensible fits ${eur(gen.budget)} at <b>${esc(res)}</b>. The cheapest
           complete build here is <b>${eur(r.floor)}</b>${res === "1080p" && !gen.allow8
             ? `, or less with 8 GB cards allowed` : ``}.`;
    host.innerHTML = `<p class="gen-fail">${msg}</p>`;
    return;
  }
  host.innerHTML = genCard(r);

  const w = DOC.catalogue.blend_cpu[res];
  const weights = $("#genWeights");
  if (weights && w !== undefined) {
    weights.textContent = `${Math.round(w * 100)}% CPU / ${Math.round((1 - w) * 100)}% ` +
      `GPU at ${res}`;
  }
}

/** Generator state lives in the query string, so a build is linkable. The resolution
 *  stays in the hash, where it already was. */
function syncGenUrl(): void {
  const p = new URLSearchParams();
  p.set("budget", String(gen.budget));
  if (gen.cpu.size !== CPU_VENDORS.length) p.set("cpu", [...gen.cpu].join(","));
  if (gen.gpu.size !== GPU_VENDORS.length) p.set("gpu", [...gen.gpu].join(","));
  if (gen.allow8) p.set("vram8", "1");
  history.replaceState(null, "", `?${p}${location.hash}`);
}

function readGenUrl(): void {
  const p = new URLSearchParams(location.search);
  const b = Number(p.get("budget"));
  if (Number.isFinite(b) && b > 0) gen.budget = Math.round(b);
  for (const [key, all, set] of [
    ["cpu", CPU_VENDORS, gen.cpu], ["gpu", GPU_VENDORS, gen.gpu],
  ] as [string, string[], Set<string>][]) {
    const raw = p.get(key);
    if (!raw) continue;
    const want = raw.split(",").map(s => s.trim().toLowerCase());
    const hit = all.filter(v => want.includes(v.toLowerCase()));
    if (hit.length) { set.clear(); hit.forEach(v => set.add(v)); }
  }
  gen.allow8 = p.get("vram8") === "1";
}

function wireGenerator(): void {
  if (!DOC) return;
  const num = $<HTMLInputElement>("#genBudget");
  const range = $<HTMLInputElement>("#genRange");
  const allow8 = $<HTMLInputElement>("#genAllow8");

  // Slider bounds come from the parts bin, not from a guess: the floor is the cheapest
  // complete build anyone could compose, the ceiling the dearest.
  const all = candidates(DOC, "1080p",
    { budget: Infinity, cpu: new Set(CPU_VENDORS), gpu: new Set(GPU_VENDORS), allow8: true });
  if (all.length && range) {
    const lo = Math.floor(Math.min(...all.map(c => c.eur)) / 50) * 50;
    const hi = Math.ceil(Math.max(...all.map(c => c.eur)) / 100) * 100;
    range.min = String(lo);
    range.max = String(hi);
    gen.budget = Math.min(Math.max(gen.budget, lo), hi);
  }
  if (num) num.value = String(gen.budget);
  if (range) range.value = String(gen.budget);
  if (allow8) allow8.checked = gen.allow8;

  const setBudget = (v: number, echo: HTMLInputElement | null) => {
    if (!Number.isFinite(v)) return;
    gen.budget = Math.max(0, Math.round(v));
    if (echo) echo.value = String(gen.budget);
    syncGenUrl();
    runGenerator();
  };
  range?.addEventListener("input", () => setBudget(Number(range.value), num));
  num?.addEventListener("input", () => {
    const v = Number(num.value);
    if (range && Number.isFinite(v)) range.value = String(v);
    setBudget(v, null);
  });
  allow8?.addEventListener("change", () => {
    gen.allow8 = allow8.checked;
    syncGenUrl();
    runGenerator();
  });

  vendorChips($("#genCpu"), CPU_VENDORS, gen.cpu);
  vendorChips($("#genGpu"), GPU_VENDORS, gen.gpu);
  runGenerator();
}

// ---------- resolution control ----------

/** #1440p in the URL, so a resolution is linkable. Matched case-insensitively
 *  because "4K" is capitalised in the data and nobody types it that way. */
function resFromHash(available: string[]): string | null {
  const want = decodeURIComponent(location.hash.replace(/^#/, "")).toLowerCase();
  return available.find(r => r.toLowerCase() === want) || null;
}

function renderResSeg(): void {
  const seg = $("#resSeg");
  if (!seg || !DOC) return;
  seg.innerHTML = DOC.resolutions.map(r =>
    `<button data-res="${r}" class="${r === res ? "on" : ""}">${r}` +
    `<small>${RES_LABEL[r] || ""}</small></button>`).join("");
  seg.querySelectorAll<HTMLButtonElement>("button").forEach(btn => {
    // set the hash only — the hashchange handler is the single place that re-renders,
    // so the control and a pasted #4K link go down exactly the same path
    btn.addEventListener("click", () => { location.hash = btn.dataset.res || res; });
  });
}

// ---------- boot ----------

function wireTheme(): void {
  const btn = $("#themeToggleBtn");
  if (!btn) return;
  btn.textContent = theme;
  btn.addEventListener("click", () => {
    theme = theme === "dark" ? "light" : "dark";
    localStorage.setItem("msfs-theme", theme);
    document.documentElement.dataset.theme = theme;
    btn.textContent = theme;
  });
}

async function boot(): Promise<void> {
  wireTheme();
  renderCards();

  let doc: Doc;
  try {
    const r = await fetch("/builds.json", { cache: "no-cache" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    doc = await r.json();
  } catch (err) {
    const host = $("#builds");
    if (host) {
      host.innerHTML = `<p class="fail">Could not load the build data
        (${esc(String(err))}). The benchmark data is still on
        <a href="/">the main page</a>.</p>`;
    }
    return;
  }
  DOC = doc;

  res = resFromHash(doc.resolutions) || (doc.resolutions.includes("1440p")
    ? "1440p" : doc.resolutions[0]);

  const stamp = $("#stamp");
  if (stamp) {
    stamp.innerHTML = doc.priced_on
      ? `Prices: <b>${esc(doc.currency || "EUR")}, ${esc(doc.region || "Netherlands")}, ` +
        `${esc(doc.source || "retail")}, ${esc(doc.priced_on)}</b> — check before buying.`
      : `Prices are hand-maintained and undated — check before buying.`;
  }
  const pon = $("#pon");
  if (pon) pon.textContent = doc.priced_on || "an unrecorded date";

  renderResSeg();
  renderBuilds();
  renderNotPicked();
  renderPrices();
  renderProse();
  readGenUrl();
  wireGenerator();

  window.addEventListener("hashchange", () => {
    const r = resFromHash(doc.resolutions);
    if (!r || r === res) return;
    res = r;
    renderResSeg();
    renderBuilds();
    runGenerator();          // the generator reads the same resolution control
  });
}

boot();
