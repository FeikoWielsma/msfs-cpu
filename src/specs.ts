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

type Doc = {
  priced_on: string | null;
  resolutions: string[];
  tiers: string[];
  vendors: string[];
  builds: Build[];
  not_picked: NotPicked[];
  prices: Price[];
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
      <td>${esc(i.part)}${i.src && i.src !== "tweakers"
        ? `<span class="src" title="${esc(i.src)} — not a Tweakers.net retail price">${esc(i.src)}</span>`
        : ""}</td>
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
    rows.map(p => `<tr><td>${esc(p.part)}${p.src !== "tweakers"
      ? `<span class="src" title="${esc(p.src)} — not a Tweakers.net retail price">${esc(p.src)}</span>`
      : ""}</td><td class="num">${eur(p.eur)}</td></tr>`).join("") +
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
      ? `Prices: <b>EUR, Netherlands, Tweakers.net, ${esc(doc.priced_on)}</b> — ` +
        `hand-maintained, so check before buying.`
      : `Prices are hand-maintained and undated — check before buying.`;
  }
  const pon = $("#pon");
  if (pon) pon.textContent = doc.priced_on || "an unrecorded date";

  renderResSeg();
  renderBuilds();
  renderNotPicked();
  renderPrices();
  renderProse();

  window.addEventListener("hashchange", () => {
    const r = resFromHash(doc.resolutions);
    if (!r || r === res) return;
    res = r;
    renderResSeg();
    renderBuilds();
  });
}

boot();
