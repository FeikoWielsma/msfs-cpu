#!/usr/bin/env python3
"""
Generate a self-contained, static HTML view of the MSFS 2024 CPU data from all
sources (Tom's Hardware + PCGH + ComputerBase).

Reads msfs24_data.csv (Tom's, grouped by `epoch`), pcgh_msfs24.csv (PCGH, by
`scene`) and computerbase_msfs24.csv (ComputerBase, by `scene`), unifies them,
and inlines everything — data, styling and logic — into one index.html:

  * "Performance Index": the default cross-source ranking. Each enabled review
    is rescaled onto a shared 0-100 scale with a two-way additive fit (per-dataset
    offset + per-CPU effect), so a CPU's score reflects its own speed, not which
    reviewer happened to test it. Tap any CPU to make it the 100% baseline.
  * "By source": browse one comparable dataset at a time (a Tom's epoch or a
    PCGH/ComputerBase scene), avg + 1% low bars, tap to re-baseline.
  * Sources & methodology panel + full raw data table.

UI/UX redesign from a Claude Design handoff (mobile-first, single-gesture
compare). Usage:
    python build_html.py            # writes index.html
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
                "title": r.get("title", ""),
            })
    return out


# One normalized series per (site, group), so every dataset is individually
# toggleable. Colors: Tom's = blues (newer darker), PCGH = warm, CB = greens.
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


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en" data-theme="light" data-density="comfortable" data-bars="vendor">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>MSFS 2024 — Best CPUs</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:#f3f2ee; --card:#ffffff; --card-2:#faf9f6;
    --ink:#15171c; --ink-2:#3b414a; --muted:#717784; --faint:#9aa0ab;
    --line:#e6e3dc; --line-2:#efece6;
    --amd:#cf3a36; --amd-deep:#8c1f1b;
    --intel:#2b6cd4; --intel-deep:#1a4a98;
    --accent:#15171c; --on-accent:#ffffff;
    --track:#ebe8e1; --hover:#f6f4ef; --pin-bg:#fbf7ee;
    --pos:#157347; --pos-bg:#e6f4ec; --neg:#bc3328; --neg-bg:#fbe9e7;
    --shadow:0 1px 2px rgba(20,23,28,.04), 0 8px 24px -16px rgba(20,23,28,.22);
    --radius:14px;
  }
  html[data-theme="dark"] {
    --bg:#0e1116; --card:#161a21; --card-2:#1b2027;
    --ink:#edeff2; --ink-2:#c7ccd4; --muted:#8b919b; --faint:#666d78;
    --line:#262c35; --line-2:#20262e;
    --amd:#f1645f; --amd-deep:#c33b36;
    --intel:#5f9bff; --intel-deep:#2e6ad0;
    --accent:#edeff2; --on-accent:#0e1116;
    --track:#222933; --hover:#1c222a; --pin-bg:#1f2630;
    --pos:#4cc38a; --pos-bg:#15301f; --neg:#f4756b; --neg-bg:#371b1a;
    --shadow:0 1px 2px rgba(0,0,0,.3), 0 10px 30px -18px rgba(0,0,0,.7);
  }
  * { box-sizing:border-box; }
  html, body { margin:0; }
  body {
    background:var(--bg); color:var(--ink);
    font-family:"Schibsted Grotesk", -apple-system, "Segoe UI", Roboto, sans-serif;
    font-size:15px; line-height:1.5; -webkit-font-smoothing:antialiased;
    font-variant-numeric:tabular-nums;
  }
  .num { font-family:"JetBrains Mono", ui-monospace, Menlo, Consolas, monospace; font-variant-numeric:tabular-nums; }
  .app { max-width:880px; margin:0 auto; padding:max(20px, env(safe-area-inset-top)) 18px 80px; }
  a { color:var(--intel-deep); }
  html[data-theme="dark"] a { color:var(--intel); }

  /* ---------- masthead ---------- */
  .kicker { font-size:12.5px; font-weight:600; letter-spacing:.08em; text-transform:uppercase;
    color:var(--muted); }
  h1 { font-size:clamp(26px, 6vw, 40px); line-height:1.05; letter-spacing:-.02em;
    font-weight:800; margin:8px 0 0; text-wrap:balance; }
  .lede { color:var(--ink-2); margin:12px 0 0; max-width:60ch; font-size:15.5px; }
  .lede b { color:var(--ink); font-weight:600; }

  /* ---------- top pick ---------- */
  .toppick { margin-top:22px; background:var(--card); border:1px solid var(--line);
    border-radius:var(--radius); padding:16px 18px; box-shadow:var(--shadow);
    display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
  .toppick .tp-rank { font-size:11px; font-weight:700; letter-spacing:.07em; text-transform:uppercase;
    color:var(--muted); display:flex; align-items:center; gap:7px; }
  .tp-medal { width:22px; height:22px; border-radius:50%; display:grid; place-items:center;
    background:var(--accent); color:var(--on-accent); font-size:12px; }
  .toppick .tp-main { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; flex:1; min-width:0; }
  .toppick .tp-cpu { font-size:clamp(19px,4.5vw,24px); font-weight:700; letter-spacing:-.01em; }
  .toppick .tp-score { margin-left:auto; text-align:right; }
  .toppick .tp-score b { font-size:26px; font-weight:700; }
  .toppick .tp-score span { display:block; font-size:11.5px; color:var(--muted); }

  /* ---------- tabs ---------- */
  .tabs { display:flex; gap:4px; margin:26px 0 0; background:var(--track);
    padding:4px; border-radius:12px; width:fit-content; max-width:100%; }
  .tabs button { appearance:none; border:0; background:transparent; cursor:pointer;
    font:inherit; font-weight:600; color:var(--ink-2); padding:9px 18px; border-radius:9px;
    white-space:nowrap; transition:background .15s, color .15s; }
  .tabs button.on { background:var(--card); color:var(--ink); box-shadow:var(--shadow); }

  /* ---------- controls ---------- */
  .controls { margin-top:14px; display:flex; flex-direction:column; gap:12px; }
  .ctl-row { display:flex; flex-wrap:wrap; align-items:center; gap:10px 14px; }
  .ctl-group { display:flex; align-items:center; gap:8px; min-width:0; }
  .ctl-label { font-size:12px; font-weight:600; letter-spacing:.04em; text-transform:uppercase;
    color:var(--muted); }

  .seg { display:inline-flex; background:var(--track); padding:3px; border-radius:10px; gap:2px; }
  .seg button { appearance:none; border:0; background:transparent; cursor:pointer; font:inherit;
    font-size:14px; font-weight:600; color:var(--ink-2); padding:7px 13px; border-radius:8px;
    white-space:nowrap; transition:background .15s,color .15s; }
  .seg button.on { background:var(--card); color:var(--ink); box-shadow:var(--shadow); }

  .chips { display:flex; gap:7px; flex-wrap:wrap; }
  .chip { appearance:none; cursor:pointer; font:inherit; font-size:13.5px; font-weight:600;
    border:1px solid var(--line); background:var(--card); color:var(--ink-2);
    padding:7px 13px; border-radius:999px; display:inline-flex; align-items:center; gap:6px;
    transition:.14s; }
  .chip:hover { border-color:var(--faint); }
  .chip .dot { width:9px; height:9px; border-radius:50%; }
  .chip.on { background:var(--accent); color:var(--on-accent); border-color:var(--accent); }
  .chip.on.amd { background:var(--amd); border-color:var(--amd); color:#fff; }
  .chip.on.intel { background:var(--intel); border-color:var(--intel); color:#fff; }

  .search { position:relative; flex:1; min-width:160px; max-width:280px; }
  .search input { width:100%; font:inherit; font-size:14px; padding:9px 12px 9px 34px;
    border:1px solid var(--line); border-radius:10px; background:var(--card); color:var(--ink); }
  .search input:focus { outline:none; border-color:var(--faint); box-shadow:0 0 0 3px var(--hover); }
  .search svg { position:absolute; left:11px; top:50%; transform:translateY(-50%);
    width:15px; height:15px; stroke:var(--faint); fill:none; }

  select { font:inherit; font-size:14px; font-weight:500; padding:8px 30px 8px 11px;
    border:1px solid var(--line); border-radius:10px; background:var(--card); color:var(--ink);
    appearance:none; cursor:pointer;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 4l4 4 4-4' stroke='%23717784' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
    background-repeat:no-repeat; background-position:right 10px center; }

  /* advanced expander */
  .adv { border:1px dashed var(--line); border-radius:12px; }
  .adv > summary { cursor:pointer; list-style:none; padding:11px 14px; font-size:13.5px;
    font-weight:600; color:var(--ink-2); display:flex; align-items:center; gap:8px; }
  .adv > summary::-webkit-details-marker { display:none; }
  .adv > summary::before { content:"›"; font-size:18px; color:var(--muted); transition:transform .2s;
    display:inline-block; }
  .adv[open] > summary::before { transform:rotate(90deg); }
  .adv .adv-body { padding:2px 16px 16px; }
  .adv .ds-note { font-size:13px; color:var(--muted); margin:0 0 12px; max-width:62ch; }
  .ds-list { display:flex; flex-direction:column; gap:8px; }
  .ds-item { display:flex; align-items:center; gap:10px; font-size:13.5px; cursor:pointer;
    padding:8px 10px; border-radius:9px; border:1px solid var(--line-2); transition:.14s; }
  .ds-item:hover { background:var(--hover); }
  .ds-item.off { opacity:.42; }
  .ds-item input { width:16px; height:16px; accent-color:var(--accent); cursor:pointer; }
  .ds-item .sw { width:11px; height:11px; border-radius:3px; flex:none; }
  .ds-item .ds-meta { color:var(--muted); font-size:12px; margin-left:auto; white-space:nowrap; }

  /* ---------- chart ---------- */
  .chart-head { margin:20px 0 6px; display:flex; align-items:baseline; gap:10px 14px; flex-wrap:wrap; }
  .chart-head h2 { font-size:13px; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
    color:var(--muted); margin:0; }
  .chart-head .ch-sub { font-size:13px; color:var(--muted); }
  .baseline-bar { margin-left:auto; display:none; align-items:center; gap:9px; font-size:13px;
    color:var(--ink-2); }
  .baseline-bar.on { display:flex; }
  .baseline-bar b { color:var(--ink); font-weight:600; }
  .btn-reset { appearance:none; border:1px solid var(--line); background:var(--card); cursor:pointer;
    font:inherit; font-size:12.5px; font-weight:600; color:var(--ink-2); padding:5px 11px;
    border-radius:8px; }
  .btn-reset:hover { border-color:var(--faint); }

  .legend { display:flex; gap:7px 16px; flex-wrap:wrap; font-size:12.5px; color:var(--muted);
    margin:2px 0 10px; }
  .legend i { display:inline-block; width:11px; height:11px; border-radius:3px; margin-right:5px;
    vertical-align:-1px; }

  .chart { background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
    box-shadow:var(--shadow); padding:8px; }
  .barrow { display:flex; flex-direction:column; gap:7px; padding:11px 12px; border-radius:11px;
    cursor:pointer; transition:background .14s; position:relative; }
  html[data-density="compact"] .barrow { padding:7px 12px; gap:5px; }
  .barrow + .barrow { border-top:1px solid var(--line-2); }
  .barrow:hover { background:var(--hover); }
  .barrow:hover + .barrow { border-top-color:transparent; }
  .barrow.pinned { background:var(--pin-bg); box-shadow:inset 0 0 0 1.5px var(--accent); }
  .barrow.pinned + .barrow { border-top-color:transparent; }
  .barrow.dim { opacity:.5; }

  .br-top { display:flex; align-items:center; gap:10px; }
  .rank { font-size:12.5px; font-weight:700; color:var(--faint); min-width:1.7em; text-align:right; flex:none; }
  .cpu { font-weight:600; font-size:15px; letter-spacing:-.005em; white-space:nowrap;
    overflow:hidden; text-overflow:ellipsis; min-width:0; }
  html[data-density="compact"] .cpu { font-size:14px; }
  .badge { font-size:10px; font-weight:700; letter-spacing:.03em; padding:2px 6px; border-radius:5px;
    vertical-align:1px; margin-left:6px; }
  .badge.x3d { background:var(--pos-bg); color:var(--pos); }
  .badge.vendor { margin-left:6px; }
  .badge.amd { background:rgba(207,58,54,.13); color:var(--amd-deep); }
  .badge.intel { background:rgba(43,108,212,.14); color:var(--intel-deep); }
  html[data-theme="dark"] .badge.amd { color:var(--amd); }
  html[data-theme="dark"] .badge.intel { color:var(--intel); }

  .val { margin-left:auto; display:flex; align-items:baseline; gap:8px; flex:none; }
  .val .big { font-size:17px; font-weight:700; }
  .val .unit { font-size:12px; color:var(--muted); font-weight:600; margin-left:1px; }
  .val .sub { font-size:12px; color:var(--muted); }
  .delta { font-size:11.5px; font-weight:700; padding:2px 7px; border-radius:999px; white-space:nowrap; }
  .delta.pos { background:var(--pos-bg); color:var(--pos); }
  .delta.neg { background:var(--neg-bg); color:var(--neg); }
  .delta.base { background:var(--accent); color:var(--on-accent); }

  .track { position:relative; height:12px; background:var(--track); border-radius:7px; }
  html[data-density="compact"] .track { height:9px; }
  .fill { position:absolute; left:0; top:0; height:100%; border-radius:7px; min-width:3px;
    transition:width .35s cubic-bezier(.2,.7,.2,1); background:var(--accent); }
  .vendor-amd .fill, .fill.amd { background:linear-gradient(90deg, var(--amd-deep), var(--amd)); }
  .vendor-intel .fill, .fill.intel { background:linear-gradient(90deg, var(--intel-deep), var(--intel)); }
  .reftick { position:absolute; top:-4px; bottom:-4px; width:2px; background:var(--ink);
    opacity:.32; border-radius:2px; }

  /* dual (by-source) track */
  .track.dual { height:26px; background:transparent; }
  html[data-density="compact"] .track.dual { height:22px; }
  .track.dual .seg-track { position:absolute; left:0; right:0; background:var(--track); border-radius:6px; }
  .track.dual .seg-track.avg { top:0; height:13px; }
  .track.dual .seg-track.low { bottom:0; height:9px; }
  html[data-density="compact"] .track.dual .seg-track.avg { height:11px; }
  html[data-density="compact"] .track.dual .seg-track.low { height:8px; }
  .track.dual .fill.avg { height:13px; top:0; border-radius:6px; }
  .track.dual .fill.low { height:9px; top:auto; bottom:0; border-radius:6px; opacity:.62; }
  html[data-density="compact"] .track.dual .fill.avg { height:11px; }
  html[data-density="compact"] .track.dual .fill.low { height:8px; }
  .seg-lab { position:absolute; font-size:10px; font-weight:700; color:var(--muted);
    transform:translate(8px,-50%); white-space:nowrap; }
  .seg-lab.avg { top:7px; } .seg-lab.low { bottom:4px; }
  html[data-density="compact"] .seg-lab.avg { top:6px; }

  .empty { padding:32px 16px; text-align:center; color:var(--muted); }

  /* ---------- panels ---------- */
  .panel { margin-top:14px; background:var(--card); border:1px solid var(--line);
    border-radius:var(--radius); overflow:hidden; }
  .panel > summary { cursor:pointer; list-style:none; padding:15px 18px; font-weight:700;
    font-size:15px; display:flex; align-items:center; gap:10px; }
  .panel > summary::-webkit-details-marker { display:none; }
  .panel > summary::after { content:"›"; margin-left:auto; font-size:20px; color:var(--muted);
    transition:transform .2s; }
  .panel[open] > summary::after { transform:rotate(90deg); }
  .panel > summary .pcount { font-size:12.5px; font-weight:600; color:var(--muted);
    background:var(--track); padding:2px 9px; border-radius:999px; }
  .panel-body { padding:4px 18px 20px; }

  .methodology { font-size:13.5px; color:var(--ink-2); max-width:68ch; line-height:1.6; }
  .methodology b { color:var(--ink); }
  .srcgrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:10px;
    margin-top:16px; }
  .srcgrid .s { border:1px solid var(--line); border-radius:11px; padding:12px 13px; min-width:0;
    background:var(--card-2); }
  .srcgrid .s b { font-size:13.5px; line-height:1.35; display:block; }
  .srcgrid .s b a { text-decoration:none; } .srcgrid .s b a:hover { text-decoration:underline; }
  .srcgrid .s small { color:var(--muted); font-size:12px; display:block; margin-top:5px; }

  .tablewrap { overflow:auto; border-radius:10px; border:1px solid var(--line); margin-top:4px;
    -webkit-overflow-scrolling:touch; max-height:520px; }
  table { border-collapse:collapse; width:100%; font-size:13px; min-width:560px; }
  th, td { padding:8px 11px; border-bottom:1px solid var(--line-2); text-align:left; white-space:nowrap; }
  thead th { position:sticky; top:0; background:var(--card-2); cursor:pointer; user-select:none;
    font-size:11.5px; letter-spacing:.04em; text-transform:uppercase; color:var(--muted); z-index:2; }
  th .arr { font-size:9px; }
  td.tnum { text-align:right; }
  tbody tr:hover { background:var(--hover); }
  .pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700; }
  .pill.AMD { background:rgba(207,58,54,.13); color:var(--amd-deep); }
  .pill.Intel { background:rgba(43,108,212,.14); color:var(--intel-deep); }
  html[data-theme="dark"] .pill.AMD { color:var(--amd); }
  html[data-theme="dark"] .pill.Intel { color:var(--intel); }

  footer { margin-top:30px; color:var(--muted); font-size:12.5px; line-height:1.6; }
  footer code { background:var(--track); padding:1px 6px; border-radius:5px; font-size:11.5px; }

  @media (max-width:560px) {
    .app { padding:18px 14px 90px; }
    .toppick .tp-score { margin-left:0; text-align:left; }
    .toppick .tp-score b { font-size:22px; }
    .val .sub { display:none; }
    .chart { padding:4px; }
    .barrow { padding:11px 9px; }
  }
  @media (prefers-reduced-motion: reduce) { .fill { transition:none; } }
</style>
</head>
<body>
<div class="app">
  <header>
    <h1>Which CPU runs MSFS&nbsp;2024 best?</h1>
    <p class="lede">A combined ranking from <b>Tom's Hardware</b>, <b>PCGH</b> and <b>ComputerBase</b>.
      Because each site tests different scenes, raw FPS aren't comparable — so the default
      <b>Performance&nbsp;Index</b> rescales every review onto one shared 0–100 scale. Tap any chip to
      compare against it.</p>
  </header>

  <nav class="tabs" id="tabs">
    <button data-tab="ranking" class="on">Performance Index</button>
    <button data-tab="source">By source</button>
  </nav>

  <section class="controls">
    <!-- shared filter row -->
    <div class="ctl-row">
      <div class="chips" id="brandChips">
        <button class="chip on" data-brand="all">All</button>
        <button class="chip" data-brand="AMD"><span class="dot" style="background:var(--amd)"></span>AMD</button>
        <button class="chip" data-brand="Intel"><span class="dot" style="background:var(--intel)"></span>Intel</button>
        <button class="chip" data-x3d="1">★ 3D V-Cache</button>
      </div>
      <div class="seg" id="metricSeg">
        <button data-m="avg" class="on">Average FPS</button>
        <button data-m="low">1% Low</button>
      </div>
      <div class="search">
        <svg viewBox="0 0 24 24" stroke-width="2"><circle cx="11" cy="11" r="7"></circle><path d="M21 21l-4.3-4.3"></path></svg>
        <input id="search" type="search" placeholder="Find a CPU…" autocomplete="off">
      </div>
    </div>

    <!-- by-source context row -->
    <div class="ctl-row" id="sourceCtl" style="display:none">
      <div class="ctl-group"><span class="ctl-label">Site</span><select id="site"></select></div>
      <div class="ctl-group"><span class="ctl-label" id="viewLabel">Scene</span><select id="view"></select></div>
    </div>

    <!-- advanced (ranking) -->
    <details class="adv" id="advPanel">
      <summary>Advanced — choose which reviews feed the index</summary>
      <div class="adv-body">
        <p class="ds-note">The index blends the datasets below with a two-way fit (each source's
          overall difficulty is factored out, so a CPU isn't penalised for being tested by a harsher
          reviewer). Toggle datasets to see how the ranking shifts.</p>
        <div class="ds-list" id="dsList"></div>
      </div>
    </details>
  </section>

  <div class="chart-head">
    <h2 id="chartTitle">Performance Index</h2>
    <span class="ch-sub" id="chartSub"></span>
    <div class="baseline-bar" id="baselineBar">
      <span>Comparing vs <b id="baselineName"></b></span>
      <button class="btn-reset" id="resetBaseline">Reset</button>
    </div>
  </div>
  <div class="legend" id="legend"></div>
  <div class="chart" id="chart"></div>

  <details class="panel" id="srcPanel">
    <summary>Sources &amp; methodology <span class="pcount" id="srcCount"></span></summary>
    <div class="panel-body">
      <p class="methodology">
        Same game, but re-measured over time and across sites, so a CPU's FPS drift between
        epochs and scenes — absolute numbers <b>aren't comparable across sources</b>.
        <b>By source</b> keeps you inside one comparable set. The <b>Performance Index</b> rescales
        every enabled dataset onto a shared scale using a two-way additive fit (per-dataset offset +
        per-CPU effect), so a CPU's score reflects its own speed, not which reviewer happened to test it.
        <b>·N</b> next to a score is how many datasets cover that CPU.
        One hard prior is applied: an Intel <b>14th-gen part is a clock-bumped rebadge of its 13th-gen
        twin</b> (same silicon — a 14600K can't be slower than a 13600K), so each is floored at its
        predecessor's score, carrying the margin measured where both were tested head-to-head. This
        only corrects cross-source noise; it never invents a lead that the shared tests don't show.
      </p>
      <div class="srcgrid" id="sources"></div>
    </div>
  </details>

  <details class="panel" id="tablePanel">
    <summary>Full data table <span class="pcount" id="rowCount"></span></summary>
    <div class="panel-body">
      <div class="tablewrap"><table id="table"><thead></thead><tbody></tbody></table></div>
    </div>
  </details>

  <footer id="footer">
    Combined from <b>Tom's Hardware</b>, <b>PCGH</b> and <b>ComputerBase</b> reviews,
    transcribed/scraped into <code>msfs24_data.csv</code>, <code>pcgh_msfs24.csv</code> and
    <code>computerbase_msfs24.csv</code>, then rendered to this single self-contained file by
    <code>build_html.py</code>. Absolute FPS aren't comparable across sources — the
    Performance Index normalises them. Not affiliated with Tom's Hardware, PCGH or ComputerBase.
  </footer>
</div>

<script>
window.DATA = __DATA__;
window.NORM_SERIES = __NORM__;
window.TWEAKS = {"theme": "light", "bars": "generation", "density": "compact"};
</script>
<script>
/* MSFS 2024 CPU benchmark — redesigned app logic (vanilla). */
(function () {
  "use strict";
  const DATA = window.DATA, NORM_SERIES = window.NORM_SERIES;
  const $ = s => document.querySelector(s);
  const el = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };
  const fmt = (x, d) => Number(x).toFixed(d);
  const isX3D = c => /x3d/i.test(c);

  // ---------- state ----------
  let tab = "ranking";          // ranking | source
  let metric = "avg";           // avg | low
  let brand = "all";            // all | AMD | Intel
  let x3dOnly = false;
  let query = "";
  let baseline = null;          // pinned CPU (null = auto: leader = 100)
  let enabled = NORM_SERIES.map(() => true);
  // by-source
  let site = null, view = "combined";

  const VENDOR = {}; for (const r of DATA) if (!(r.cpu in VENDOR)) VENDOR[r.cpu] = r.vendor;
  const SITES = [...new Set(DATA.map(r => r.site))];

  // generation colours (for the "Gen" bar-colour tweak)
  const GEN_COLOR = {
    "Ryzen 3000": "#6e1714", "Ryzen 5000": "#a32f26", "Ryzen 7000": "#d6433b", "Ryzen 9000": "#f47a63",
    "Core 11th": "#103a63", "Core 12th": "#1f6fb0", "Core 13/14th": "#3a9bdc", "Core Ultra 2xx": "#7fc9ef"
  };
  const GEN_ORDER = Object.keys(GEN_COLOR);
  function genOf(cpu) {
    if (cpu.startsWith("Ryzen")) {
      const m = cpu.match(/Ryzen \d+ (\d)\d{3}/);
      return { "3": "Ryzen 3000", "5": "Ryzen 5000", "7": "Ryzen 7000", "9": "Ryzen 9000" }[m ? m[1] : ""] || "Ryzen 7000";
    }
    if (cpu.includes("Core Ultra")) return "Core Ultra 2xx";
    const m = cpu.match(/Core i\d+-(\d{2})/); const g = m ? m[1] : "";
    if (g === "11") return "Core 11th";
    if (g === "12") return "Core 12th";
    return "Core 13/14th";
  }

  // ---------- data helpers ----------
  function dedupNewest(rows) {
    const best = new Map();
    for (const r of rows) { const c = best.get(r.cpu); if (!c || r.date > c.date) best.set(r.cpu, r); }
    return [...best.values()];
  }
  function groupsForSite(s) {
    const gs = [...new Set(DATA.filter(r => r.site === s).map(r => r.group))];
    return gs.sort((a, b) => minDate(s, a) < minDate(s, b) ? -1 : 1);
  }
  function minDate(s, g) { return DATA.filter(r => r.site === s && r.group === g).reduce((m, r) => r.date < m ? r.date : m, "9999"); }

  function seriesData(spec, field) {
    let rows = DATA.filter(r => r.site === spec.site && (!spec.group || r.group === spec.group));
    rows = dedupNewest(rows);
    const m = {}; for (const r of rows) if (r[field] != null) m[r.cpu] = r[field];
    return m;
  }
  function enabledSeries() { return NORM_SERIES.filter((s, i) => enabled[i]); }

  // Two-way additive fit in log space: log(value) = datasetOffset + cpuEffect.
  function twowayFit(series, cpus, ref) {
    const a = series.map(() => 0), b = {}; cpus.forEach(c => b[c] = 0);
    for (let it = 0; it < 200; it++) {
      series.forEach((s, i) => {
        const e = Object.entries(s.data);
        a[i] = e.reduce((t, [c, v]) => t + Math.log(v) - b[c], 0) / e.length;
      });
      cpus.forEach(c => {
        const obs = series.map((s, i) => [s, i]).filter(([s]) => c in s.data);
        b[c] = obs.reduce((t, [s, i]) => t + Math.log(s.data[c]) - a[i], 0) / obs.length;
      });
    }
    const out = {}, base = b[ref]; cpus.forEach(c => out[c] = Math.exp(b[c] - base) * 100);
    return out;
  }

  // returns sorted [{cpu, vendor, x3d, raw, idx, n}]
  // Same-tier Intel Raptor Lake Refresh (14th gen) is a clock-bumped rebadge of
  // the matching 13th-gen part — same silicon, so it cannot be slower at stock.
  // Map a 14th-gen SKU to its 13th-gen predecessor (Intel "Core i?-14xxx" only).
  function genPredecessor(cpu) {
    const m = cpu.match(/^(Core i\d-)14(\d{3}[A-Z]*)$/);
    return m ? m[1] + "13" + m[2] : null;
  }
  // Floor each newer SKU at its predecessor's score, carrying the margin actually
  // measured where both were tested head-to-head (geo-mean ratio). This stops a
  // cross-source blend from erasing a real, known clock advantage — without
  // inventing one: if no head-to-head exists, the floor is just "not slower".
  function applyGenFloor(raw, series) {
    for (const cpu of Object.keys(raw)) {
      const pred = genPredecessor(cpu);
      if (!pred || raw[pred] == null) continue;
      const ratios = series.filter(s => cpu in s.data && pred in s.data)
                           .map(s => s.data[cpu] / s.data[pred]);
      const r = ratios.length
        ? Math.exp(ratios.reduce((t, x) => t + Math.log(x), 0) / ratios.length) : 1;
      const floor = raw[pred] * Math.max(r, 1);
      if (raw[cpu] < floor) raw[cpu] = floor;
    }
  }

  function computeIndex(field) {
    const series = enabledSeries().map(s => ({ ...s, data: seriesData(s, field) }));
    const valid = series.filter(s => Object.keys(s.data).length);
    const cpus = [...new Set(valid.flatMap(s => Object.keys(s.data)))];
    if (!cpus.length) return [];
    const raw = twowayFit(valid, cpus, cpus[0]);
    applyGenFloor(raw, valid);
    const cnt = cp => valid.filter(s => cp in s.data).length;
    let arr = cpus.map(cp => ({ cpu: cp, vendor: VENDOR[cp], x3d: isX3D(cp), raw: raw[cp], n: cnt(cp) }));
    arr.sort((x, y) => y.raw - x.raw);
    const anchor = (baseline && raw[baseline] != null) ? raw[baseline] : arr[0].raw;
    arr.forEach(o => o.idx = o.raw / anchor * 100);
    return arr;
  }

  function matchFilter(cpu, vendor) {
    if (brand !== "all" && vendor !== brand) return false;
    if (x3dOnly && !isX3D(cpu)) return false;
    if (query && !cpu.toLowerCase().includes(query)) return false;
    return true;
  }

  // ---------- bar colour ----------
  function fillStyle(cpu, vendor) {
    const mode = document.documentElement.dataset.bars;
    if (mode === "generation") return `background:${GEN_COLOR[genOf(cpu)]}`;
    if (mode === "mono") return "";
    return ""; // vendor handled by class
  }
  function vendorClass(vendor) {
    return document.documentElement.dataset.bars === "vendor"
      ? "vendor-" + vendor.toLowerCase() : "";
  }

  // ---------- shared bar row ----------
  function badges(cpu, vendor, showVendor) {
    let h = "";
    if (showVendor) h += `<span class="badge vendor ${vendor.toLowerCase()}">${vendor}</span>`;
    if (isX3D(cpu)) h += `<span class="badge x3d">3D</span>`;
    return h;
  }

  // ---------- render: ranking ----------
  function renderRanking() {
    const all = computeIndex(metric);
    const visible = all.filter(o => matchFilter(o.cpu, o.vendor));
    setBaselineBar();

    const c = $("#chart"); c.innerHTML = "";
    if (!enabledSeries().length) { c.innerHTML = `<div class="empty">Enable at least one dataset in <b>Advanced</b> to build the index.</div>`; return; }
    if (!visible.length) { c.innerHTML = `<div class="empty">No CPUs match these filters.</div>`; return; }

    // axis covers leader (or pinned-baseline overshoot) and 100 ref line
    const maxIdx = Math.max(...all.map(o => o.idx));
    const axisMax = Math.max(100, maxIdx) * 1.06;
    const redrawDelta = baseline != null;

    visible.forEach((o, i) => {
      const w = o.idx / axisMax * 100;
      const row = el("div", "barrow " + vendorClass(o.vendor));
      row.dataset.cpu = o.cpu;
      if (o.cpu === baseline) row.classList.add("pinned");
      const d = o.idx - 100;
      let deltaHtml = "";
      if (o.cpu === baseline) deltaHtml = `<span class="delta base">100% · baseline</span>`;
      else if (redrawDelta) deltaHtml = `<span class="delta ${d >= 0 ? "pos" : "neg"}">${d >= 0 ? "+" : ""}${d.toFixed(1)}%</span>`;
      row.innerHTML =
        `<div class="br-top">
           <span class="rank num">${i + 1}</span>
           <span class="cpu">${o.cpu}${badges(o.cpu, o.vendor, true)}</span>
           <span class="val">
             ${deltaHtml}
             <span class="big num">${o.idx.toFixed(0)}<span class="unit">%</span></span>
             <span class="sub num">·${o.n}</span>
           </span>
         </div>
         <div class="track">
           ${(100 <= axisMax) ? `<div class="reftick" style="left:${100 / axisMax * 100}%"></div>` : ""}
           <div class="fill" style="width:${w}%;${fillStyle(o.cpu, o.vendor)}"></div>
         </div>`;
      row.addEventListener("click", () => toggleBaseline(o.cpu));
      c.appendChild(row);
    });
  }

  function setBaselineBar() {
    const bar = $("#baselineBar");
    if (baseline) { bar.classList.add("on"); $("#baselineName").textContent = baseline; }
    else bar.classList.remove("on");
  }
  function toggleBaseline(cpu) {
    baseline = (baseline === cpu) ? null : cpu;
    render();
  }

  // ---------- render: by source ----------
  function sourceRows() {
    let rows = DATA.filter(r => r.site === site);
    if (view === "all") return rows.slice();
    if (view === "combined") return dedupNewest(rows);
    return dedupNewest(rows.filter(r => r.group === view.slice(2)));
  }
  function renderSource() {
    setBaselineBar();
    const rows = sourceRows().filter(r => r[metric] != null && matchFilter(r.cpu, r.vendor))
      .sort((a, b) => b[metric] - a[metric]);
    const c = $("#chart"); c.innerHTML = "";
    $("#chartSub").textContent = `${site} · ${rows.length} CPUs`;
    if (!rows.length) { c.innerHTML = `<div class="empty">No CPUs match these filters.</div>`; return; }
    const axisMax = Math.max(...rows.map(r => r.avg)) * 1.08;
    const base = baseline ? (rows.find(r => r.cpu === baseline) || {})[metric] : null;

    rows.forEach((r, i) => {
      const wA = r.avg / axisMax * 100, wL = (r.low ?? 0) / axisMax * 100;
      const row = el("div", "barrow " + vendorClass(r.vendor));
      row.dataset.cpu = r.cpu;
      if (r.cpu === baseline) row.classList.add("pinned");
      let deltaHtml = "";
      if (base != null) {
        if (r.cpu === baseline) deltaHtml = `<span class="delta base">baseline</span>`;
        else { const d = (r[metric] - base) / base * 100; deltaHtml = `<span class="delta ${d >= 0 ? "pos" : "neg"}">${d >= 0 ? "+" : ""}${d.toFixed(1)}%</span>`; }
      }
      row.innerHTML =
        `<div class="br-top">
           <span class="rank num">${i + 1}</span>
           <span class="cpu">${r.cpu}${badges(r.cpu, r.vendor, true)}</span>
           <span class="val">
             ${deltaHtml}
             <span class="big num">${fmt(r.avg, 1)}</span>
             ${r.low != null ? `<span class="sub num">${fmt(r.low, 0)} low</span>` : ""}
           </span>
         </div>
         <div class="track dual">
           <div class="seg-track avg"></div><div class="seg-track low"></div>
           <div class="fill avg" style="width:${wA}%;${fillStyle(r.cpu, r.vendor)}"></div>
           ${r.low != null ? `<div class="fill low" style="width:${wL}%;${fillStyle(r.cpu, r.vendor)}"></div>` : ""}
         </div>`;
      row.addEventListener("click", () => toggleBaseline(r.cpu));
      c.appendChild(row);
    });
  }

  // ---------- legend ----------
  function renderLegend() {
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
      items += `<span><i style="background:var(--ink);opacity:.32"></i>100% reference${baseline ? " (" + baseline + ")" : " (leader)"}</span>`;
      lg.innerHTML = items;
    } else {
      lg.innerHTML = mode === "vendor"
        ? `<span><i style="background:var(--amd)"></i>AMD</span><span><i style="background:var(--intel)"></i>Intel</span><span style="opacity:.7">Upper bar = avg · lower = 1% low</span>`
        : `<span style="opacity:.7">Upper bar = average FPS · lower bar = 1% low</span>`;
    }
  }

  // ---------- sources + table ----------
  function renderSources() {
    const map = new Map();
    for (const r of DATA) {
      const k = r.source;
      if (!map.has(k)) map.set(k, { site: r.site, date: r.date, group: r.group, url: r.url, title: r.title, n: 0 });
      map.get(k).n++;
    }
    const items = [...map.entries()].sort((a, b) => a[1].date < b[1].date ? 1 : -1);
    $("#srcCount").textContent = items.length + " reviews";
    $("#sources").innerHTML = items.map(([src, m]) => {
      const label = m.title || src;
      const head = m.url ? `<a href="${m.url}" target="_blank" rel="noopener noreferrer">${label} ↗</a>` : label;
      return `<div class="s"><b>${head}</b><small>${m.site} · ${m.date} · ${m.group} · ${m.n} CPUs</small></div>`;
    }).join("");
  }

  const COLS = [["cpu", "CPU", 0], ["vendor", "Brand", 0], ["site", "Site", 0], ["group", "Epoch / Scene", 0],
    ["avg", "Avg", 1], ["low", "1% Low", 1], ["p02", "0.2% Low", 1], ["date", "Date", 0]];
  let sortKey = "avg", sortDir = -1;
  function renderTable() {
    $("#rowCount").textContent = DATA.length + " rows";
    const thead = $("#table thead"), tbody = $("#table tbody");
    thead.innerHTML = "<tr>" + COLS.map(([k, l]) => {
      const a = k === sortKey ? (sortDir < 0 ? "▼" : "▲") : "";
      return `<th data-k="${k}">${l} <span class="arr">${a}</span></th>`;
    }).join("") + "</tr>";
    thead.querySelectorAll("th").forEach(th => th.onclick = () => {
      const k = th.dataset.k;
      if (k === sortKey) sortDir *= -1; else { sortKey = k; sortDir = COLS.find(c => c[0] === k)[2] ? -1 : 1; }
      renderTable();
    });
    const rows = DATA.slice().sort((a, b) => {
      let x = a[sortKey], y = b[sortKey];
      if (x == null) x = -Infinity; if (y == null) y = -Infinity;
      return (x < y ? -1 : x > y ? 1 : 0) * sortDir;
    });
    tbody.innerHTML = rows.map(r => `<tr>
      <td>${r.cpu}${r.x3d ? ' <span class="badge x3d">3D</span>' : ""}</td>
      <td><span class="pill ${r.vendor}">${r.vendor}</span></td>
      <td>${r.site}</td><td>${r.group}</td>
      <td class="tnum num">${fmt(r.avg, 1)}</td>
      <td class="tnum num">${r.low != null ? fmt(r.low, 0) : "–"}</td>
      <td class="tnum num">${r.p02 != null ? fmt(r.p02, 0) : "–"}</td>
      <td>${r.date}</td></tr>`).join("");
  }

  // ---------- datasets (advanced) ----------
  function buildDatasetList() {
    const box = $("#dsList");
    box.innerHTML = NORM_SERIES.map((s, i) => `
      <label class="ds-item ${enabled[i] ? "" : "off"}" data-i="${i}">
        <input type="checkbox" ${enabled[i] ? "checked" : ""}>
        <span class="sw" style="background:${s.color}"></span>
        <span>${s.name}</span>
        <span class="ds-meta">${s.span}</span>
      </label>`).join("");
    box.querySelectorAll("input").forEach(inp => inp.onchange = e => {
      const i = +e.target.closest("label").dataset.i;
      enabled[i] = e.target.checked;
      e.target.closest("label").classList.toggle("off", !enabled[i]);
      // if pinned baseline drops out of the data, clear it
      render();
    });
  }

  // ---------- by-source selects ----------
  function buildSiteSelect() {
    site = SITES[0];
    $("#site").innerHTML = SITES.map(s => `<option>${s}</option>`).join("");
    $("#site").onchange = () => { site = $("#site").value; buildViewSelect(); render(); };
    buildViewSelect();
  }
  function buildViewSelect() {
    const gs = groupsForSite(site);
    const lbl = site === "PCGH" ? "Scene" : (site === "ComputerBase" ? "Scene" : "Epoch");
    $("#viewLabel").textContent = lbl;
    const opts = [["combined", "Newest per CPU"], ...gs.map(g => ["g:" + g, g]), ["all", "All raw rows"]];
    view = "combined";
    $("#view").innerHTML = opts.map(([v, t]) => `<option value="${v}">${t}</option>`).join("");
    $("#view").onchange = () => { view = $("#view").value; render(); };
  }

  // ---------- dispatch ----------
  function render() {
    renderLegend();
    if (tab === "ranking") {
      $("#chartTitle").textContent = "Performance Index";
      $("#chartSub").textContent = `${metric === "avg" ? "Average FPS" : "1% Low"} · ${enabledSeries().length} of ${NORM_SERIES.length} datasets · 100% = ${baseline || "leader"}`;
      renderRanking();
    } else {
      $("#chartTitle").textContent = "By source";
      renderSource();
    }
  }

  // ---------- controls wiring ----------
  $("#tabs").addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    tab = b.dataset.tab;
    [...$("#tabs").children].forEach(x => x.classList.toggle("on", x === b));
    $("#sourceCtl").style.display = tab === "source" ? "flex" : "none";
    $("#advPanel").style.display = tab === "ranking" ? "" : "none";
    baseline = null;
    render();
  });
  $("#metricSeg").addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    metric = b.dataset.m;
    [...$("#metricSeg").children].forEach(x => x.classList.toggle("on", x === b));
    render();
  });
  $("#brandChips").addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.x3d) {
      x3dOnly = !x3dOnly; b.classList.toggle("on", x3dOnly);
    } else {
      brand = b.dataset.brand;
      [...$("#brandChips").querySelectorAll("[data-brand]")].forEach(x => {
        x.classList.remove("on", "amd", "intel");
        if (x === b) { x.classList.add("on"); if (brand === "AMD") x.classList.add("amd"); if (brand === "Intel") x.classList.add("intel"); }
      });
    }
    render();
  });
  $("#search").addEventListener("input", e => { query = e.target.value.trim().toLowerCase(); render(); });
  $("#resetBaseline").addEventListener("click", () => { baseline = null; render(); });

  // ---------- tweaks ----------
  function applyTweaks() {
    const t = window.TWEAKS;
    document.documentElement.dataset.theme = t.theme;
    document.documentElement.dataset.bars = t.bars;
    document.documentElement.dataset.density = t.density;
  }

  // ---------- boot ----------
  applyTweaks();
  buildDatasetList();
  buildSiteSelect();
  renderSources();
  renderTable();
  render();
})();
</script>
</body>
</html>
"""


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
