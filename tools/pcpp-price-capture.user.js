// ==UserScript==
// @name         PCPP price capture
// @namespace    msfs.razortek.nl
// @version      1.0.0
// @description  Capture PCPartPicker prices from your own saved lists and filters, across regions, at human pace — for keeping build_prices.csv current.
// @author       Razortek
// @match        *://pcpartpicker.com/*
// @match        *://*.pcpartpicker.com/*
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_registerMenuCommand
// @grant        GM_setClipboard
// @run-at       document-idle
// @noframes
// ==/UserScript==

/*
 * WHAT THIS IS
 *
 * A reading aid, not a crawler. It scrapes the page you are already looking at, in your
 * own browser, at a pace a person could type at — the point is to stop transcribing
 * forty prices by hand into build_prices.csv, in one currency, once a month.
 *
 * HOW TO USE IT WITHOUT ANNOYING PCPP
 *
 * Make ONE saved part list on PCPartPicker containing every part you track, then add it
 * here as a target with the regions you care about. The same list path works on every
 * regional subdomain, so a full multi-currency refresh is one page load per region —
 * about twenty — rather than one per part per region, which would be hundreds. That is
 * the whole design: fewer, richer pages.
 *
 *   1. Build the list at pcpartpicker.com/list/ and save it. Copy its /list/xxxxx path.
 *   2. Open the panel (the ⛽ button, bottom right) → "Add this page" while on it.
 *   3. Tick the regions you want. Hit Run.
 *   4. Export → paste into your CSV.
 *
 * It walks one tab, sequentially, with a randomised delay of several seconds between
 * loads, and it STOPS on anything that looks like a bot check rather than trying to get
 * around one. If you hit a challenge, solve it yourself and press Run again. There is no
 * user-agent fiddling, no proxy rotation and no parallel fetching here, deliberately —
 * if PCPP does not want this traffic, the correct response is to stop, and the script is
 * built to do that. Their data is theirs; keep the volume low and keep it personal.
 *
 * WHAT IT READS
 *
 * Part lists (/list/…) give every row in one visit. Product tables (/products/…, with
 * your filters in the URL) give the filtered rows. A single product page (/product/…)
 * gives the cheapest merchant. Rows are found structurally — any table row carrying a
 * name and something that parses as money — so a PCPP class rename does not break it.
 * If the automatic read ever picks the wrong cell, "Teach" lets you click the right one
 * and stores a selector for that page shape.
 */

(function () {
  'use strict';

  // ---------------------------------------------------------------- constants

  // PCPP's regional subdomains and the currency each one quotes in. '' is the US site.
  // Taken from the hreflang block PCPP itself publishes on every page.
  const REGIONS = [
    ['', 'USD', 'United States'], ['uk', 'GBP', 'United Kingdom'],
    ['nl', 'EUR', 'Netherlands'], ['de', 'EUR', 'Germany'],
    ['be', 'EUR', 'Belgium'], ['fr', 'EUR', 'France'],
    ['it', 'EUR', 'Italy'], ['es', 'EUR', 'Spain'],
    ['ie', 'EUR', 'Ireland'], ['at', 'EUR', 'Austria'],
    ['fi', 'EUR', 'Finland'], ['pt', 'EUR', 'Portugal'],
    ['sk', 'EUR', 'Slovakia'], ['ca', 'CAD', 'Canada'],
    ['au', 'AUD', 'Australia'], ['nz', 'NZD', 'New Zealand'],
    ['se', 'SEK', 'Sweden'], ['no', 'NOK', 'Norway'],
    ['dk', 'DKK', 'Denmark'], ['pl', 'PLN', 'Poland'],
    ['cz', 'CZK', 'Czechia'], ['hu', 'HUF', 'Hungary'],
    ['ro', 'RON', 'Romania'], ['sa', 'SAR', 'Saudi Arabia'],
  ];
  const REGION_CUR = Object.fromEntries(REGIONS.map(r => [r[0], r[1]]));
  const REGION_NAME = Object.fromEntries(REGIONS.map(r => [r[0], r[2]]));

  // Symbol → code, for when the page's own markup is more specific than the region
  // default (a US page quoting CAD, say). Longest first so 'CA$' beats '$'.
  const SYMBOLS = [
    ['A$', 'AUD'], ['C$', 'CAD'], ['CA$', 'CAD'], ['NZ$', 'NZD'], ['R$', 'BRL'],
    ['US$', 'USD'], ['CHF', 'CHF'], ['SEK', 'SEK'], ['NOK', 'NOK'], ['DKK', 'DKK'],
    ['PLN', 'PLN'], ['CZK', 'CZK'], ['HUF', 'HUF'], ['RON', 'RON'], ['SAR', 'SAR'],
    ['zł', 'PLN'], ['Kč', 'CZK'], ['Ft', 'HUF'], ['lei', 'RON'], ['kr', null],
    ['€', 'EUR'], ['£', 'GBP'], ['$', 'USD'], ['¥', 'JPY'], ['₹', 'INR'],
  ];

  // Politeness. The floor is not configurable downward on purpose.
  const MIN_DELAY_MS = 6000;
  const DEFAULT_DELAY_MS = 12000;
  const JITTER_MS = 5000;
  const MAX_MISSES = 3;          // consecutive empty pages before the walk gives up

  // A page that is challenging us. We stop; we do not try to satisfy it.
  const CHALLENGE = /just a moment|attention required|checking your browser|unusual traffic|access denied|are you a robot|verify you are human|cf-browser-verification/i;

  const KEY = {
    targets: 'pcpp_targets',
    prices: 'pcpp_prices',
    walk: 'pcpp_walk',
    opts: 'pcpp_opts',
    taught: 'pcpp_taught',
  };

  // ---------------------------------------------------------------- storage

  const load = (k, fallback) => {
    try {
      const raw = GM_getValue(k, null);
      return raw == null ? fallback : (typeof raw === 'string' ? JSON.parse(raw) : raw);
    } catch (e) { return fallback; }
  };
  const save = (k, v) => GM_setValue(k, JSON.stringify(v));

  let targets = load(KEY.targets, []);
  let prices = load(KEY.prices, {});     // { partKey: { CUR: {eur, region, at, url} } }
  let opts = Object.assign({ delay: DEFAULT_DELAY_MS, autoOpen: false }, load(KEY.opts, {}));
  let taught = load(KEY.taught, {});     // { pageShape: {row, name, price} }

  // ---------------------------------------------------------------- helpers

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const txt = el => (el ? el.textContent : '').replace(/\s+/g, ' ').trim();
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const nowISO = () => new Date().toISOString().slice(0, 10);

  /** The regional subdomain of the page we are on: '' for the US site. */
  function currentRegion() {
    const m = location.hostname.match(/^([a-z]{2})\.pcpartpicker\.com$/i);
    return m && REGION_CUR[m[1].toLowerCase()] !== undefined ? m[1].toLowerCase() : '';
  }

  function regionUrl(region, path) {
    const host = region ? `${region}.pcpartpicker.com` : 'pcpartpicker.com';
    return `https://${host}${path}`;
  }

  /** '/list/abc' — the part of the URL that is the same on every regional site. */
  const pathOf = (u = location.href) => {
    try { const x = new URL(u); return x.pathname + x.search + x.hash; }
    catch (e) { return '/'; }
  };

  // ---------------------------------------------------------------- money

  /**
   * Parse a price out of arbitrary page text.
   *
   * The hard part is the separators: "€1.234,56" and "$1,234.56" are the same number
   * written by different countries. The rule used here is that the LAST separator with
   * one or two digits behind it is the decimal point, and everything else is grouping.
   * A lone separator with exactly three digits behind it is grouping, not a decimal —
   * "1.234" is one thousand two hundred, which is the reading that matters for hardware.
   *
   * Returns {amount, currency} or null.
   */
  function parseMoney(raw, regionCur) {
    if (!raw) return null;
    const s = String(raw).replace(/ /g, ' ').trim();
    if (/^(free|n\/?a|-|—)$/i.test(s)) return null;

    const num = s.match(/\d[\d.,\s']*\d|\d/);
    if (!num) return null;

    let cur = null;
    for (const [sym, code] of SYMBOLS) {
      if (s.includes(sym)) {
        // 'kr' is Swedish, Norwegian and Danish — only the region can say which
        cur = code || regionCur || null;
        break;
      }
    }
    const iso = s.match(/\b(USD|EUR|GBP|CAD|AUD|NZD|SEK|NOK|DKK|PLN|CZK|HUF|RON|SAR|CHF|JPY|INR|BRL)\b/);
    if (iso) cur = iso[1];
    if (!cur) cur = regionCur || null;

    let t = num[0].replace(/[\s']/g, '');
    const lastDot = t.lastIndexOf('.'), lastComma = t.lastIndexOf(',');
    const last = Math.max(lastDot, lastComma);
    if (last === -1) {
      t = t.replace(/[.,]/g, '');
    } else {
      const decimals = t.length - last - 1;
      if (decimals === 3 && (t.match(/[.,]/g) || []).length === 1) {
        t = t.replace(/[.,]/g, '');              // 1.234 → grouping
      } else if (decimals >= 1 && decimals <= 2) {
        t = t.slice(0, last).replace(/[.,]/g, '') + '.' + t.slice(last + 1);
      } else {
        t = t.replace(/[.,]/g, '');
      }
    }
    const amount = parseFloat(t);
    if (!isFinite(amount) || amount <= 0) return null;
    return { amount, currency: cur };
  }

  const looksLikeMoney = s => /[$€£¥₹]|\b(USD|EUR|GBP|CAD|AUD|NZD|SEK|NOK|DKK|PLN|CZK|HUF|RON|SAR)\b|zł|Kč|\bkr\b|\bFt\b|\blei\b/i.test(s || '');

  // ---------------------------------------------------------------- scraping

  // PCPP's own markup, as it actually is. Both row shapes share tr.tr__product but agree
  // on very little else, so both are handled explicitly. Verified against saved pages.
  //
  //   Product table (/products/video-card/ and search results)
  //     td.td__name  > .td__nameWrapper > p     the name (a rating <div> sits beside it)
  //     td.td__price "$444.99" + an Add <button>
  //                  .td__price--out-of-stock wraps the price when it is not buyable,
  //                  and the price is still printed — capturing it blind would record a
  //                  number nobody can pay
  //
  //   Part list (/list/…)
  //     td.td__component    > a[href*="/products/cpu/"]   which slot this row fills
  //     td.td__name         > a                           the name — no nameWrapper here
  //     td.td__base / __promo / __shipping / __tax        the price broken out
  //     td.td__price        > a                           the total that matters
  //     td.td__availability.td__availability--inStock
  //   Every cell on a list row also carries an <h6> column label for the mobile layout.
  const PCPP = {
    row: 'tr.tr__product',
    name: 'td.td__name .td__nameWrapper p, td.td__name .td__nameWrapper, td.td__name a',
    link: 'td.td__name a[href*="/product/"]',
    spec: 'td.td__spec',
    price: 'td.td__price',
    oosProducts: '.td__price--out-of-stock, .label--out-of-stock',
    availability: 'td.td__availability',
    component: 'td.td__component a[href*="/products/"]',
  };

  /** Cell text with the furniture stripped out — the Add button, the "Out of stock"
   *  label and the mobile <h6> column headings all live inside the price cell and would
   *  otherwise land in the parse. */
  function priceText(cell) {
    const c = cell.cloneNode(true);
    $$('button, .label--out-of-stock, .specLabel, h6', c).forEach(el => el.remove());
    return txt(c);
  }

  /**
   * The product name, with anything another extension has injected taken back out.
   *
   * PCPP's name cell is a popular place to hang things: the PSU tier-list userscript
   * puts a "Tier B+" badge inside it, and a page read through that extension would
   * otherwise record a part called "ASRock PRO-750GTier B+". Only PCPP's own text is
   * wanted, so known badges and any element carrying a badge-ish class are dropped.
   */
  function nameText(row, sel) {
    const el = row.querySelector(sel);
    if (!el) return '';
    const c = el.cloneNode(true);
    $$('.psu-tier-badge, [class*="tier-badge"], [class*="-badge"], .specLabel, h6, script, style',
       c).forEach(e => e.remove());
    return txt(c);
  }

  /** Is this row's price one you could actually pay right now? The two page shapes say
   *  so in different places, and neither says it in the price itself. */
  function inStock(row, priceCell) {
    const avail = row.querySelector(PCPP.availability);
    if (avail) {
      if (avail.classList.contains('td__availability--inStock')) return true;
      const t = txt(avail).replace(/^Availability\s*/i, '');
      if (t) return !/out of stock|unavailable|back\s?order/i.test(t);
    }
    if (priceCell && priceCell.querySelector(PCPP.oosProducts)) return false;
    return true;
  }

  /**
   * Pull {name, amount, currency, stock} out of whatever table this page is showing.
   *
   * PCPP's own classes are tried first because they carry meaning nothing else does —
   * which cell is the price, and whether that price is even buyable. The structural
   * pass behind it (find the rightmost cell that parses as money) is the safety net for
   * the day those classes are renamed, and Teach is the safety net behind that.
   */
  function scrapeRows() {
    const region = currentRegion();
    const cur = REGION_CUR[region] || null;
    const rule = taught[pageShape()];

    let rows = [];
    if (rule && rule.row) rows = $$(rule.row);
    if (!rows.length) rows = $$(PCPP.row);
    if (!rows.length) {
      for (const sel of ['#partlist tr', '.partlist tr', 'table tbody tr', 'table tr']) {
        rows = $$(sel).filter(r => r.querySelector('td, th'));
        if (rows.length) break;
      }
    }

    const out = [];
    for (const row of rows) {
      if (row.closest('thead')) continue;
      const cells = $$('td, th', row);
      if (cells.length < 2) continue;

      let priceCell = row.querySelector((rule && rule.price) || PCPP.price);
      let price = priceCell ? parseMoney(priceText(priceCell), cur) : null;
      if (!price) {
        // rightmost money-looking cell — PCPP puts price last, any "was" price left of it
        for (let i = cells.length - 1; i >= 0; i--) {
          const t = priceText(cells[i]);
          if (!looksLikeMoney(t)) continue;
          const p = parseMoney(t, cur);
          if (p) { priceCell = cells[i]; price = p; break; }
        }
      }
      if (!price) continue;                 // no seller: the cell holds only an Add button

      let name = nameText(row, (rule && rule.name) || PCPP.name);
      if (!name) {
        const links = $$('a', row).map(txt).filter(Boolean);
        name = links.sort((a, b) => b.length - a.length)[0] || '';
      }
      if (!name) {
        const cand = cells.filter(c => c !== priceCell).map(txt).filter(Boolean);
        name = cand.sort((a, b) => b.length - a.length)[0] || '';
      }
      name = name.replace(/\s*\(.*?\bwas\b.*?\)\s*/gi, '').replace(/\s*\(\d+\)\s*$/, '').trim();
      if (!name || name.length < 3) continue;
      if (/^(total|subtotal|shipping|tax|base total|promo|discount)/i.test(name)) continue;

      // An out-of-stock row still prints a price. It is not a price you can pay, so it
      // is carried with a flag and left out of exports unless you ask for it.
      const stock = inStock(row, priceCell);
      const compEl = row.querySelector(PCPP.component);
      const slot = compEl ? txt(compEl) : null;
      const linkEl = row.querySelector(PCPP.link);
      const product = linkEl ? linkEl.href.replace(/[?#].*$/, '') : null;
      // Spec columns, label stripped. On a product table these carry what the name
      // leaves out — a video card's Name cell says "Gigabyte GAMING OC" and its Chipset
      // column says which GPU that actually is.
      const specs = $$(PCPP.spec, row).map(td => {
        const c = td.cloneNode(true);
        $$('.specLabel, h6', c).forEach(el => el.remove());
        return txt(c);
      }).filter(Boolean);

      out.push({ name, amount: price.amount, currency: price.currency || cur, stock, slot,
                 product, specs });
    }

    // De-duplicate on the product URL, not the name: a product table shows several
    // different cards under one name cell, so keying by name would quietly merge them
    // and keep whichever happened to be cheapest.
    const byKey = new Map();
    for (const r of out) {
      const k = (r.product || r.name).toLowerCase();
      const prev = byKey.get(k);
      if (!prev) { byKey.set(k, r); continue; }
      if (r.stock !== prev.stock) { if (r.stock) byKey.set(k, r); continue; }
      if (r.amount < prev.amount) byKey.set(k, r);
    }
    const rowsOut = [...byKey.values()];

    // Names are stored as keys, so two different products may not share one — the second
    // would overwrite the first and quietly report one part's price for another. PCPP
    // displays clashes constantly: two colours of the same cooler, or a whole page of
    // video cards whose name cell says only "Asus DUAL" with the chipset in its own
    // column. Spec columns are folded in until the clash is gone, and only for the rows
    // that clash, so an unambiguous part keeps its plain name.
    const clashes = () => {
      const groups = new Map();
      rowsOut.forEach(r => {
        const k = r.name.toLowerCase();
        if (!groups.has(k)) groups.set(k, []);
        groups.get(k).push(r);
      });
      return [...groups.values()].filter(g => g.length > 1);
    };
    for (let depth = 0; depth < 4; depth++) {
      const bad = clashes();
      if (!bad.length) break;
      // depth 0 goes in front: a video card reads better as "Radeon RX 9070 XT Asus DUAL"
      bad.forEach(g => g.forEach(r => {
        const extra = r.specs[depth];
        if (extra) r.name = depth === 0 ? `${extra} ${r.name}` : `${r.name} ${extra}`;
      }));
    }
    // Still identical after four specs: fall back to PCPP's own product id, which is
    // ugly but unique, rather than losing a row.
    clashes().forEach(g => g.forEach(r => {
      const tag = r.product && r.product.match(/\/product\/([^/]+)/);
      if (tag) r.name = `${r.name} [${tag[1]}]`;
    }));
    return rowsOut;
  }

  /** A coarse identifier for "pages that look like this", for taught selectors. */
  function pageShape() {
    const p = location.pathname;
    if (/^\/list\//.test(p)) return 'list';
    if (/^\/products\//.test(p)) return 'products';
    if (/^\/product\//.test(p)) return 'product';
    if (/^\/user\//.test(p)) return 'user';
    return 'other';
  }

  function isChallenged() {
    if (CHALLENGE.test(document.title)) return true;
    const h = txt($('h1')) + ' ' + txt($('h2'));
    return CHALLENGE.test(h);
  }

  // ---------------------------------------------------------------- capture

  /**
   * Store what this page is showing. `filter` is the target's optional name regex —
   * a products page with your filters may still list twenty cards when you want one.
   */
  function capture(target) {
    if (isChallenged()) return { challenged: true, n: 0 };
    const region = currentRegion();
    const cur = REGION_CUR[region] || 'UNKNOWN';
    let rows = scrapeRows();

    if (target && target.match) {
      let re = null;
      try { re = new RegExp(target.match, 'i'); } catch (e) { re = null; }
      if (re) rows = rows.filter(r => re.test(r.name));
    }
    // A single-part target takes the cheapest match, not all twenty rows of a filter.
    if (target && target.single && rows.length > 1) {
      rows = [rows.reduce((a, b) => (b.amount < a.amount ? b : a))];
    }

    const stamp = nowISO(), url = location.href;
    for (const r of rows) {
      const key = (target && target.single && target.label) ? target.label : r.name;
      const cc = r.currency || cur;
      const amount = Math.round(r.amount * 100) / 100;
      prices[key] = prices[key] || {};

      // A flagship card that is out of stock everywhere collects marketplace listings at
      // ten times its real price, and PCPP shows the cheapest of those. Nothing in the
      // page marks such a number as nonsense, so the only cheap check available is the
      // one you already have: what this part cost last time. A large jump is not
      // rejected — prices do move — it is flagged and kept out of exports until seen.
      const prev = prices[key][cc];
      let suspect = null;
      if (prev && prev.amount > 0 && !prev.suspect) {
        const ratio = amount / prev.amount;
        if (ratio > 3 || ratio < 1 / 3) suspect = prev.amount;
      }
      prices[key][cc] = {
        amount, region, at: stamp, url, seen: r.name,
        stock: r.stock !== false, slot: r.slot || null,
        suspect: suspect,      // the previous figure, when this one jumped hard
        product: r.product || null,
      };
    }
    if (rows.length) save(KEY.prices, prices);
    return { challenged: false, n: rows.length };
  }

  // ---------------------------------------------------------------- the walk

  /** Queue entry: {region, path, label, match, single}. */
  function buildQueue() {
    const q = [];
    for (const t of targets) {
      if (t.off) continue;
      const regions = (t.regions && t.regions.length) ? t.regions : [currentRegion()];
      for (const r of regions) {
        q.push({ region: r, path: t.path, label: t.label, match: t.match, single: !!t.single });
      }
    }
    return q;
  }

  function startWalk() {
    const queue = buildQueue();
    if (!queue.length) { toast('Nothing to run — add a target first.'); return; }
    save(KEY.walk, { queue, i: 0, misses: 0, started: Date.now(), running: true, log: [] });
    hop(0);
  }

  function stopWalk(why) {
    const w = load(KEY.walk, null);
    if (w) { w.running = false; w.stopped = why || 'stopped'; save(KEY.walk, w); }
    render();
  }

  /** Go to queue[i], unless we are already there. */
  function hop(i) {
    const w = load(KEY.walk, null);
    if (!w || !w.running) return;
    const step = w.queue[i];
    if (!step) { stopWalk('done'); toast('Finished.'); return; }
    const url = regionUrl(step.region, step.path);
    if (pathOf(url) === pathOf() && currentRegion() === step.region) {
      onArrived();
    } else {
      location.href = url;
    }
  }

  /** Called on every page load: if a walk is running and this is its current step,
   *  capture and schedule the next hop. */
  async function onArrived() {
    const w = load(KEY.walk, null);
    if (!w || !w.running) return;
    const step = w.queue[w.i];
    if (!step) { stopWalk('done'); return; }
    if (pathOf(regionUrl(step.region, step.path)) !== pathOf()
        || currentRegion() !== step.region) {
      return;                       // a page we navigated to by hand; leave the walk be
    }

    // let a client-rendered table settle before reading it
    await waitForRows(8000);
    const res = capture(step);

    if (res.challenged) {
      w.running = false;
      w.stopped = 'challenged';
      save(KEY.walk, w);
      render();
      toast('PCPP is showing a check. Stopped — solve it yourself, then press Run.', 12000);
      return;
    }
    w.log.push({ region: step.region, path: step.path, n: res.n });
    w.misses = res.n ? 0 : w.misses + 1;
    if (w.misses >= MAX_MISSES) {
      w.running = false;
      w.stopped = 'nothing found on ' + MAX_MISSES + ' pages in a row';
      save(KEY.walk, w);
      render();
      toast('Read nothing on several pages running — stopped. Try Teach.', 10000);
      return;
    }

    w.i += 1;
    const wait = Math.round(Math.max(MIN_DELAY_MS, opts.delay) + Math.random() * JITTER_MS);
    w.nextAt = Date.now() + wait;
    save(KEY.walk, w);
    render();
    countdown(wait, () => hop(w.i));
  }

  /** Product tables render client-side; give them a moment before deciding a page is
   *  empty. Resolves as soon as anything scrapes. */
  async function waitForRows(limitMs) {
    const until = Date.now() + limitMs;
    while (Date.now() < until) {
      if (scrapeRows().length) return true;
      await sleep(400);
    }
    return false;
  }

  let tick = null;
  function countdown(ms, done) {
    clearInterval(tick);
    const end = Date.now() + ms;
    tick = setInterval(() => {
      const left = end - Date.now();
      const w = load(KEY.walk, null);
      if (!w || !w.running) { clearInterval(tick); render(); return; }
      if (left <= 0) { clearInterval(tick); done(); return; }
      const el = ui && ui.status;
      if (el) el.textContent = `next in ${Math.ceil(left / 1000)}s — step ${w.i + 1}/${w.queue.length}`;
    }, 250);
  }

  // ---------------------------------------------------------------- teach

  let teaching = null;
  function startTeach() {
    toast('Click the PRICE of any row, then its NAME.', 8000);
    teaching = { stage: 'price' };
    document.addEventListener('click', onTeachClick, true);
  }

  function onTeachClick(e) {
    if (!teaching) return;
    if (ui && ui.host.contains(e.target)) return;
    e.preventDefault(); e.stopPropagation();
    const cell = e.target.closest('td, th') || e.target;
    const row = cell.closest('tr') || cell.parentElement;
    if (!row) return;

    if (teaching.stage === 'price') {
      teaching.row = row;
      teaching.price = relSelector(row, cell);
      teaching.stage = 'name';
      toast('Now click the NAME in that same row.', 8000);
      return;
    }
    const shape = pageShape();
    taught[shape] = {
      row: rowSelector(teaching.row),
      price: teaching.price,
      name: relSelector(teaching.row, cell),
    };
    save(KEY.taught, taught);
    document.removeEventListener('click', onTeachClick, true);
    teaching = null;
    toast(`Learned this ${shape} page. Read ${scrapeRows().length} rows.`, 6000);
    render();
  }

  function rowSelector(row) {
    const cls = [...row.classList].filter(c => !/^(is-|js-)/.test(c));
    if (cls.length) return row.tagName.toLowerCase() + '.' + cls.join('.');
    const p = row.parentElement;
    const pc = p && [...p.classList][0];
    return (pc ? '.' + pc + ' > ' : '') + row.tagName.toLowerCase();
  }

  function relSelector(row, cell) {
    const cls = [...cell.classList].filter(c => !/^(is-|js-)/.test(c));
    if (cls.length) return '.' + cls.join('.');
    const cells = $$('td, th', row);
    const i = cells.indexOf(cell);
    return i >= 0 ? `td:nth-child(${i + 1}), th:nth-child(${i + 1})` : 'td';
  }

  // ---------------------------------------------------------------- export

  function currencies() {
    const set = new Set();
    Object.values(prices).forEach(byCur => Object.keys(byCur).forEach(c => set.add(c)));
    return [...set].sort();
  }

  const csvCell = s => /[",\n]/.test(s) ? `"${String(s).replace(/"/g, '""')}"` : String(s);

  // Two ways a captured number can be real but wrong to publish: the listing is not
  // buyable, or it jumped so far since last time that it is probably a marketplace
  // outlier. Neither lands in an export silently — each is left out and named in the
  // header, or (with the box ticked) exported with the row marked.
  const doubt = row => !row ? 'missing'
    : row.stock === false ? 'out of stock'
    : row.suspect ? `was ${row.suspect}` : null;
  const usable = row => row && (!doubt(row) || opts.includeOOS);

  /** build_prices.csv shape, for one currency: part,<cur>,src */
  function exportOne(cur) {
    const rows = [], skipped = [];
    Object.keys(prices).sort().forEach(part => {
      const row = prices[part][cur];
      if (!row) return;
      const why = doubt(row);
      if (why && !opts.includeOOS) { skipped.push(`${part} (${why})`); return; }
      const tag = row.stock === false ? ':oos' : row.suspect ? ':check' : '';
      rows.push([csvCell(part), row.amount, `pcpp:${row.region || 'us'}${tag}`].join(','));
    });
    const head = [`# PCPartPicker ${cur}, captured ${nowISO()} — check before trusting.`];
    if (skipped.length) {
      head.push(`# ${skipped.length} left out: ${skipped.join('; ')}`);
    }
    return head.concat(`part,${cur.toLowerCase()},src`, rows).join('\n') + '\n';
  }

  /** Every currency as columns, for keeping several CSVs in step. */
  function exportWide() {
    const curs = currencies();
    const lines = [['part', ...curs, 'slot', 'captured'].map(csvCell).join(',')];
    Object.keys(prices).sort().forEach(part => {
      const byCur = prices[part];
      const at = Object.values(byCur).map(v => v.at).sort().pop() || '';
      const slot = (Object.values(byCur).find(v => v.slot) || {}).slot || '';
      lines.push([csvCell(part),
                  ...curs.map(c => (usable(byCur[c]) ? byCur[c].amount : '')),
                  csvCell(slot), at].join(','));
    });
    return lines.join('\n') + '\n';
  }

  function copy(text, what) {
    GM_setClipboard(text, 'text');
    toast(`${what} copied — ${text.split('\n').length - 1} lines.`);
  }

  // ---------------------------------------------------------------- UI

  let ui = null;

  const CSS = `
  :host { all: initial; }
  .wrap { position: fixed; right: 16px; bottom: 16px; z-index: 2147483000;
    font: 13px/1.45 -apple-system, "Segoe UI", Roboto, sans-serif; color: #e8eaf0; }
  .fab { width: 46px; height: 46px; border-radius: 50%; border: 1px solid #2a2f3d;
    background: #12151d; color: #4cc2ff; font-size: 19px; cursor: pointer;
    box-shadow: 0 6px 24px rgba(0,0,0,.45); display: grid; place-items: center; }
  .fab:hover { border-color: #4cc2ff; }
  .panel { width: min(94vw, 460px); max-height: min(84vh, 720px); overflow: auto;
    background: #0d0f15; border: 1px solid #232838; border-radius: 10px;
    box-shadow: 0 18px 60px rgba(0,0,0,.6); padding: 14px 15px; margin-bottom: 10px; }
  h2 { margin: 0 0 2px; font-size: 15px; font-weight: 700; letter-spacing: .01em; }
  .sub { color: #7d8494; font-size: 11.5px; margin-bottom: 12px; }
  .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .row + .row { margin-top: 8px; }
  button.b { background: #171b26; border: 1px solid #2a2f3d; color: #e8eaf0;
    border-radius: 6px; padding: 6px 11px; cursor: pointer; font-size: 12.5px; }
  button.b:hover { border-color: #4cc2ff; }
  button.b.go { background: #0d4f6e; border-color: #1c7aa3; color: #cdefff; }
  button.b.stop { background: #4a1520; border-color: #7c2333; color: #ffc7cf; }
  input, select { background: #12151d; border: 1px solid #2a2f3d; color: #e8eaf0;
    border-radius: 6px; padding: 5px 7px; font: inherit; font-size: 12.5px; }
  input[type=text] { flex: 1; min-width: 90px; }
  .sec { margin-top: 14px; padding-top: 11px; border-top: 1px solid #1d2230; }
  .sec h3 { margin: 0 0 7px; font-size: 11px; text-transform: uppercase;
    letter-spacing: .07em; color: #7d8494; font-weight: 700; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  td, th { text-align: left; padding: 3px 6px 3px 0; vertical-align: top; }
  th { color: #7d8494; font-weight: 600; font-size: 10.5px; text-transform: uppercase; }
  tr + tr td { border-top: 1px solid #171b26; }
  .n { text-align: right; white-space: nowrap; }
  .t { display: flex; gap: 6px; align-items: baseline; padding: 5px 0;
    border-top: 1px solid #171b26; }
  .t b { font-weight: 600; }
  .t .p { color: #7d8494; font-size: 11px; word-break: break-all; flex: 1; }
  .t button { background: none; border: 0; color: #7d8494; cursor: pointer; padding: 0 3px; }
  .t button:hover { color: #ff8f9d; }
  .regs { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 6px; }
  .regs label { display: flex; align-items: center; gap: 3px; font-size: 11px;
    background: #12151d; border: 1px solid #232838; border-radius: 4px; padding: 2px 5px;
    cursor: pointer; }
  .regs input { width: 12px; height: 12px; }
  .status { color: #4cc2ff; font-size: 11.5px; min-height: 15px; }
  .note { color: #7d8494; font-size: 11px; margin-top: 8px; }
  .toast { position: fixed; right: 16px; bottom: 74px; max-width: 360px;
    background: #12151d; border: 1px solid #2a2f3d; border-left: 3px solid #4cc2ff;
    border-radius: 6px; padding: 9px 12px; font-size: 12.5px; z-index: 2147483001; }
  `;

  function mountUI() {
    const host = document.createElement('div');
    host.id = 'pcpp-capture-host';
    (document.body || document.documentElement).appendChild(host);
    const root = host.attachShadow({ mode: 'open' });
    const style = document.createElement('style');
    style.textContent = CSS;
    root.appendChild(style);

    const wrap = document.createElement('div');
    wrap.className = 'wrap';
    root.appendChild(wrap);

    const panel = document.createElement('div');
    panel.className = 'panel';
    panel.style.display = opts.autoOpen ? 'block' : 'none';

    const fab = document.createElement('button');
    fab.className = 'fab';
    fab.title = 'PCPP price capture';
    fab.textContent = '€';
    fab.addEventListener('click', () => {
      panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
      render();
    });

    panel.addEventListener('click', onPanelClick);
    panel.addEventListener('change', onPanelChange);

    wrap.appendChild(panel);
    wrap.appendChild(fab);
    ui = { host, root, wrap, panel, fab, status: null };
    render();
  }

  function toast(msg, ms = 5000) {
    if (!ui) return;
    const t = document.createElement('div');
    t.className = 'toast';
    t.textContent = msg;
    ui.root.appendChild(t);
    setTimeout(() => t.remove(), ms);
  }

  function render() {
    if (!ui || ui.panel.style.display === 'none') return;
    const w = load(KEY.walk, null);
    const region = currentRegion();
    const cur = REGION_CUR[region] || '?';
    const seen = scrapeRows();
    const p = ui.panel;
    p.textContent = '';

    const h = document.createElement('div');
    h.innerHTML = `
      <h2>PCPP price capture</h2>
      <div class="sub">${REGION_NAME[region] || 'Unknown region'} · ${cur} ·
        this page reads <b>${seen.length}</b> row${seen.length === 1 ? '' : 's'}</div>
      <div class="row">
        <button class="b go" data-a="run">${w && w.running ? 'Restart' : 'Run'}</button>
        <button class="b stop" data-a="stop">Stop</button>
        <button class="b" data-a="grab">Capture this page</button>
        <button class="b" data-a="teach">Teach</button>
      </div>
      <div class="row"><div class="status">${w && w.running
        ? `running — step ${w.i + 1}/${w.queue.length}`
        : (w && w.stopped ? `idle (${w.stopped})` : 'idle')}</div></div>

      <div class="sec">
        <h3>Targets</h3>
        <div class="row">
          <input type="text" id="lbl" placeholder="label (e.g. tracked parts)">
          <button class="b" data-a="add">Add this page</button>
        </div>
        <div class="note">One saved part list with everything on it is the whole trick:
          each region is then a single page load.</div>
        <div id="tlist"></div>
      </div>

      <div class="sec">
        <h3>Captured — ${Object.keys(prices).length} parts, ${currencies().join(' ') || 'none'}</h3>
        <div id="plist"></div>
        <div class="row" style="margin-top:9px">
          <select id="expcur">${currencies().map(c => `<option>${c}</option>`).join('')}</select>
          <button class="b" data-a="exp1">Copy CSV</button>
          <button class="b" data-a="expw">Copy all currencies</button>
          <button class="b" data-a="clear">Clear</button>
        </div>
        <div class="row"><label style="font-size:11.5px;color:#7d8494">
          <input type="checkbox" id="oos" ${opts.includeOOS ? 'checked' : ''}>
          export doubtful prices too — out of stock <b>!</b>, big jump <b>?</b></label></div>
      </div>

      <div class="sec">
        <h3>Pace</h3>
        <div class="row">
          <input type="number" id="delay" min="${MIN_DELAY_MS / 1000}" step="1"
            value="${Math.round(Math.max(MIN_DELAY_MS, opts.delay) / 1000)}" style="width:64px">
          <span class="sub" style="margin:0">seconds between page loads, plus jitter.
            Floor ${MIN_DELAY_MS / 1000}s.</span>
        </div>
        <div class="note">Stops by itself on a bot check. If you hit one, solve it in the
          page and press Run — the script will not try to get around it.</div>
      </div>`;
    p.appendChild(h);
    ui.status = p.querySelector('.status');

    // targets
    const tl = p.querySelector('#tlist');
    if (!targets.length) {
      tl.innerHTML = `<div class="note">No targets yet. Open your saved list or a filtered
        product page, give it a label and press "Add this page".</div>`;
    }
    targets.forEach((t, i) => {
      const d = document.createElement('div');
      d.className = 't';
      d.innerHTML = `
        <input type="checkbox" ${t.off ? '' : 'checked'} data-off="${i}" title="include in Run">
        <b>${escapeHtml(t.label || '(unnamed)')}</b>
        <span class="p">${escapeHtml(t.path)}</span>
        <button data-del="${i}" title="remove">✕</button>`;
      const regs = document.createElement('div');
      regs.className = 'regs';
      regs.innerHTML = REGIONS.map(([r, c]) =>
        `<label><input type="checkbox" data-reg="${i}" value="${r}"
          ${(t.regions || []).includes(r) ? 'checked' : ''}>${r || 'us'} ${c}</label>`).join('');
      tl.appendChild(d);
      tl.appendChild(regs);
    });

    // captured
    const pl = p.querySelector('#plist');
    const parts = Object.keys(prices).sort();
    if (!parts.length) {
      pl.innerHTML = `<div class="note">Nothing captured yet.</div>`;
    } else {
      const curs = currencies();
      const cell = v => !v ? '·'
        : v.stock === false ? `${v.amount} <b title="out of stock">!</b>`
        : v.suspect ? `${v.amount} <b title="was ${v.suspect} — check it">?</b>`
        : v.amount;
      pl.innerHTML = `<table><tr><th>Part</th>${curs.map(c => `<th class="n">${c}</th>`).join('')}</tr>` +
        parts.slice(0, 60).map(part => `<tr><td>${escapeHtml(part)}</td>` +
          curs.map(c => `<td class="n">${cell(prices[part][c])}</td>`).join('') +
          `</tr>`).join('') + `</table>` +
        (parts.length > 60 ? `<div class="note">…and ${parts.length - 60} more.</div>` : '');
    }

    // listeners are bound once, at mount — binding them here would stack another pair
    // on every re-render and fire each handler as many times as the panel had drawn
  }

  const escapeHtml = s => String(s).replace(/[&<>"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function onPanelClick(e) {
    const a = e.target.dataset && e.target.dataset.a;
    const del = e.target.dataset && e.target.dataset.del;
    if (del !== undefined && del !== '') {
      targets.splice(Number(del), 1); save(KEY.targets, targets); render(); return;
    }
    if (!a) return;
    if (a === 'run') startWalk();
    if (a === 'stop') { clearInterval(tick); stopWalk('stopped by you'); }
    if (a === 'grab') {
      const r = capture(null);
      toast(r.challenged ? 'That is a bot check, not a page of prices.'
                         : `Captured ${r.n} row${r.n === 1 ? '' : 's'}.`);
      render();
    }
    if (a === 'teach') startTeach();
    if (a === 'add') {
      const lbl = ui.panel.querySelector('#lbl').value.trim();
      targets.push({ label: lbl || document.title.slice(0, 40), path: pathOf(),
                     regions: [currentRegion()], single: false, match: '' });
      save(KEY.targets, targets); render();
    }
    if (a === 'exp1') {
      const c = ui.panel.querySelector('#expcur').value;
      if (c) copy(exportOne(c), `${c} CSV`);
    }
    if (a === 'expw') copy(exportWide(), 'All-currency CSV');
    if (a === 'clear') {
      if (confirm('Throw away every captured price?')) {
        prices = {}; save(KEY.prices, prices); render();
      }
    }
  }

  function onPanelChange(e) {
    const d = e.target.dataset || {};
    if (d.off !== undefined) {
      targets[Number(d.off)].off = !e.target.checked;
      save(KEY.targets, targets); return;
    }
    if (d.reg !== undefined) {
      const t = targets[Number(d.reg)];
      t.regions = t.regions || [];
      const v = e.target.value;
      if (e.target.checked) { if (!t.regions.includes(v)) t.regions.push(v); }
      else t.regions = t.regions.filter(x => x !== v);
      save(KEY.targets, targets); return;
    }
    if (e.target.id === 'oos') {
      opts.includeOOS = e.target.checked;
      save(KEY.opts, opts); render(); return;
    }
    if (e.target.id === 'delay') {
      opts.delay = Math.max(MIN_DELAY_MS, Number(e.target.value) * 1000 || DEFAULT_DELAY_MS);
      save(KEY.opts, opts);
    }
  }

  // ---------------------------------------------------------------- boot

  GM_registerMenuCommand('Open PCPP price capture', () => {
    if (ui) { ui.panel.style.display = 'block'; render(); }
  });
  GM_registerMenuCommand('Copy all-currency CSV', () => copy(exportWide(), 'CSV'));

  // A handle for the console, and what the test harness drives: if a page ever reads
  // wrong, `__pcppCapture.rows()` shows exactly what the scraper sees before Teach.
  window.__pcppCapture = {
    rows: scrapeRows, money: parseMoney, shape: pageShape, region: currentRegion,
    prices: () => prices,
  };

  function boot() {
    mountUI();
    const w = load(KEY.walk, null);
    if (w && w.running) {
      opts.autoOpen = true;
      ui.panel.style.display = 'block';
      onArrived();
    }
    render();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
