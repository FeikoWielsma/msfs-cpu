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


# Per-CPU specs for the badges + "what drives performance" analysis.
# Fields: socket, arch, p (P/perf cores), e (E-cores; 0 = none), t (threads),
# ccd (chiplets; 1 for monolithic/Intel), l3 (total MB incl. V-Cache), vc (3D
# V-Cache), clk (max boost GHz). Threads stored explicitly (SMT/HT/none vary).
def _spec(socket, arch, p, e, t, ccd, l3, vc, clk):
    return {"socket": socket, "arch": arch, "p": p, "e": e, "t": t,
            "ccd": ccd, "l3": l3, "vcache": vc, "clk": clk}


SPECS = {
    # ---- AMD AM4 · Zen 2 (3000) ----
    "Ryzen 5 3600":     _spec("AM4", "Zen 2", 6, 0, 12, 1, 32, False, 4.2),
    "Ryzen 7 3800XT":   _spec("AM4", "Zen 2", 8, 0, 16, 1, 32, False, 4.7),
    "Ryzen 9 3900X":    _spec("AM4", "Zen 2", 12, 0, 24, 2, 64, False, 4.6),
    "Ryzen 9 3950X":    _spec("AM4", "Zen 2", 16, 0, 32, 2, 64, False, 4.7),
    # ---- AMD AM4 · Zen 3 (5000) ----
    "Ryzen 5 5600":     _spec("AM4", "Zen 3", 6, 0, 12, 1, 32, False, 4.4),
    "Ryzen 5 5600X3D":  _spec("AM4", "Zen 3", 6, 0, 12, 1, 96, True, 4.4),
    "Ryzen 7 5800X":    _spec("AM4", "Zen 3", 8, 0, 16, 1, 32, False, 4.7),
    "Ryzen 7 5700X3D":  _spec("AM4", "Zen 3", 8, 0, 16, 1, 96, True, 4.1),
    "Ryzen 7 5800X3D":  _spec("AM4", "Zen 3", 8, 0, 16, 1, 96, True, 4.5),
    "Ryzen 9 5950X":    _spec("AM4", "Zen 3", 16, 0, 32, 2, 64, False, 4.9),
    # ---- AMD AM5 · Zen 4 (7000) ----
    "Ryzen 5 7500F":    _spec("AM5", "Zen 4", 6, 0, 12, 1, 32, False, 5.0),
    "Ryzen 5 7600X":    _spec("AM5", "Zen 4", 6, 0, 12, 1, 32, False, 5.3),
    "Ryzen 5 7500X3D":  _spec("AM5", "Zen 4", 6, 0, 12, 1, 96, True, 4.5),
    "Ryzen 5 7600X3D":  _spec("AM5", "Zen 4", 6, 0, 12, 1, 96, True, 4.7),
    "Ryzen 7 7700X":    _spec("AM5", "Zen 4", 8, 0, 16, 1, 32, False, 5.4),
    "Ryzen 7 7800X3D":  _spec("AM5", "Zen 4", 8, 0, 16, 1, 96, True, 5.0),
    "Ryzen 9 7900":     _spec("AM5", "Zen 4", 12, 0, 24, 2, 64, False, 5.4),
    "Ryzen 9 7900X3D":  _spec("AM5", "Zen 4", 12, 0, 24, 2, 128, True, 5.6),
    "Ryzen 9 7950X":    _spec("AM5", "Zen 4", 16, 0, 32, 2, 64, False, 5.7),
    "Ryzen 9 7950X3D":  _spec("AM5", "Zen 4", 16, 0, 32, 2, 128, True, 5.7),
    # ---- AMD AM5 · Zen 5 (9000) ----
    "Ryzen 5 9600X":    _spec("AM5", "Zen 5", 6, 0, 12, 1, 32, False, 5.4),
    "Ryzen 7 9700X":    _spec("AM5", "Zen 5", 8, 0, 16, 1, 32, False, 5.5),
    "Ryzen 7 9800X3D":  _spec("AM5", "Zen 5", 8, 0, 16, 1, 96, True, 5.2),
    "Ryzen 7 9850X3D":  _spec("AM5", "Zen 5", 8, 0, 16, 1, 96, True, 5.3),
    "Ryzen 9 9900X":    _spec("AM5", "Zen 5", 12, 0, 24, 2, 64, False, 5.6),
    "Ryzen 9 9900X3D":  _spec("AM5", "Zen 5", 12, 0, 24, 2, 128, True, 5.5),
    "Ryzen 9 9950X":    _spec("AM5", "Zen 5", 16, 0, 32, 2, 64, False, 5.7),
    "Ryzen 9 9950X3D":  _spec("AM5", "Zen 5", 16, 0, 32, 2, 128, True, 5.7),
    "Ryzen 9 9950X3D2": _spec("AM5", "Zen 5", 16, 0, 32, 2, 192, True, 5.6),  # "Dual Edition": V-Cache on both CCDs
    # ---- Intel LGA1200 · Rocket Lake (11th) ----
    "Core i9-11900K":   _spec("LGA1200", "Rocket Lake", 8, 0, 16, 1, 16, False, 5.3),
    # ---- Intel LGA1700 · Alder Lake (12th) ----
    "Core i5-12400F":   _spec("LGA1700", "Alder Lake", 6, 0, 12, 1, 18, False, 4.4),
    "Core i5-12600K":   _spec("LGA1700", "Alder Lake", 6, 4, 16, 1, 20, False, 4.9),
    "Core i7-12700K":   _spec("LGA1700", "Alder Lake", 8, 4, 20, 1, 25, False, 5.0),
    "Core i9-12900K":   _spec("LGA1700", "Alder Lake", 8, 8, 24, 1, 30, False, 5.2),
    # ---- Intel LGA1700 · Raptor Lake (13th / 14th) ----
    "Core i3-13100F":   _spec("LGA1700", "Raptor Lake", 4, 0, 8, 1, 12, False, 4.5),
    "Core i5-13400F":   _spec("LGA1700", "Raptor Lake", 6, 4, 16, 1, 20, False, 4.6),
    "Core i5-13600K":   _spec("LGA1700", "Raptor Lake", 6, 8, 20, 1, 24, False, 5.1),
    "Core i7-13700K":   _spec("LGA1700", "Raptor Lake", 8, 8, 24, 1, 30, False, 5.4),
    "Core i9-13900K":   _spec("LGA1700", "Raptor Lake", 8, 16, 32, 1, 36, False, 5.8),
    "Core i3-14100":    _spec("LGA1700", "Raptor Lake", 4, 0, 8, 1, 12, False, 4.7),
    "Core i5-14400":    _spec("LGA1700", "Raptor Lake", 6, 4, 16, 1, 20, False, 4.7),
    "Core i5-14400F":   _spec("LGA1700", "Raptor Lake", 6, 4, 16, 1, 20, False, 4.7),
    "Core i5-14600K":   _spec("LGA1700", "Raptor Lake", 6, 8, 20, 1, 24, False, 5.3),
    "Core i7-14700K":   _spec("LGA1700", "Raptor Lake", 8, 12, 28, 1, 33, False, 5.6),
    "Core i9-14900K":   _spec("LGA1700", "Raptor Lake", 8, 16, 32, 1, 36, False, 6.0),
    "Core i9-14900KS":  _spec("LGA1700", "Raptor Lake", 8, 16, 32, 1, 36, False, 6.2),
    # ---- Intel LGA1851 · Arrow Lake (Core Ultra 2xx; no Hyper-Threading) ----
    "Core Ultra 5 225":      _spec("LGA1851", "Arrow Lake", 6, 4, 10, 1, 20, False, 4.9),
    "Core Ultra 5 225F":     _spec("LGA1851", "Arrow Lake", 6, 4, 10, 1, 20, False, 4.9),
    "Core Ultra 5 235":      _spec("LGA1851", "Arrow Lake", 6, 8, 14, 1, 24, False, 5.0),
    "Core Ultra 5 245K":     _spec("LGA1851", "Arrow Lake", 6, 8, 14, 1, 24, False, 5.2),
    "Core Ultra 5 250K Plus": _spec("LGA1851", "Arrow Lake", 6, 12, 18, 1, 30, False, 5.3),
    "Core Ultra 7 265K":     _spec("LGA1851", "Arrow Lake", 8, 12, 20, 1, 30, False, 5.5),
    "Core Ultra 7 270K Plus": _spec("LGA1851", "Arrow Lake", 8, 16, 24, 1, 36, False, 5.5),
    "Core Ultra 9 285K":     _spec("LGA1851", "Arrow Lake", 8, 16, 24, 1, 36, False, 5.7),
}


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en" data-theme="light" data-density="comfortable" data-bars="vendor">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>MSFS 2024 — Best CPUs</title>
<script defer src="https://stats.feikowielsma.nl/script.js" data-website-id="b0988ab4-7b6a-4775-83a1-ff89fb549345"></script>
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
  .meta { display:flex; align-items:center; gap:5px; flex:none; }
  .badge { font-size:10px; font-weight:700; letter-spacing:.03em; padding:2px 6px; border-radius:5px;
    white-space:nowrap; vertical-align:1px; }
  .badge.x3d { background:var(--pos-bg); color:var(--pos); }
  .badge.sock { background:var(--track); color:var(--ink-2); }
  .badge.sock.amd { background:rgba(207,58,54,.13); color:var(--amd-deep); }
  .badge.sock.intel { background:rgba(43,108,212,.14); color:var(--intel-deep); }
  html[data-theme="dark"] .badge.sock.amd { color:var(--amd); }
  html[data-theme="dark"] .badge.sock.intel { color:var(--intel); }
  .badge.cores { background:transparent; color:var(--muted); border:1px solid var(--line);
    font-family:"JetBrains Mono", ui-monospace, monospace; font-weight:600; letter-spacing:0; }
  @media (max-width:520px) { .badge.cores { display:none; } }

  /* ---------- factor analysis ---------- */
  .factors { display:flex; flex-direction:column; gap:1px; background:var(--line-2);
    border:1px solid var(--line); border-radius:12px; overflow:hidden; margin-top:14px; }
  .frow { display:grid; grid-template-columns:1fr auto; column-gap:14px; align-items:baseline;
    padding:12px 15px; background:var(--card); }
  .frow .fname { font-weight:700; font-size:14.5px; }
  .frow .fsub { font-size:12px; color:var(--muted); margin-top:1px; }
  .frow .feffect { font-family:"JetBrains Mono", ui-monospace, monospace; font-weight:700;
    font-size:16px; text-align:right; white-space:nowrap; }
  .feffect.pos { color:var(--pos); } .feffect.neg { color:var(--neg); } .feffect.flat { color:var(--muted); }
  .fbar { grid-column:1 / -1; position:relative; height:7px; background:var(--track);
    border-radius:5px; margin-top:9px; }
  .fbar-zero { position:absolute; left:50%; top:-3px; bottom:-3px; width:2px; background:var(--faint); border-radius:2px; }
  .fbar-fill { position:absolute; top:0; height:100%; border-radius:5px; min-width:2px; }
  .fbar-fill.pos { background:linear-gradient(90deg, var(--pos), color-mix(in srgb, var(--pos) 55%, #fff)); }
  .fbar-fill.neg { background:linear-gradient(90deg, color-mix(in srgb, var(--neg) 55%, #fff), var(--neg)); }
  .frow .fex { grid-column:1 / -1; font-size:11.5px; color:var(--faint); margin-top:7px; line-height:1.5; }
  .frow .fex b { color:var(--ink-2); font-weight:600; }

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

  .tblfilters { display:flex; flex-wrap:wrap; align-items:center; gap:10px 14px; margin:2px 0 14px; }
  .tblfilters .ctl-group { gap:7px; }
  .tchk { display:inline-flex; align-items:center; gap:7px; font-size:13.5px; font-weight:600;
    color:var(--ink-2); cursor:pointer; }
  .tchk input { width:16px; height:16px; accent-color:var(--accent); cursor:pointer; }
  .tblfilters .search { max-width:220px; }
  .tablewrap { overflow:auto; border-radius:10px; border:1px solid var(--line); margin-top:4px;
    -webkit-overflow-scrolling:touch; max-height:520px; }
  table { border-collapse:collapse; width:100%; font-size:13px; min-width:720px; }
  th, td { padding:8px 11px; border-bottom:1px solid var(--line-2); text-align:left; white-space:nowrap; }
  thead th { position:sticky; top:0; background:var(--card-2); cursor:pointer; user-select:none;
    font-size:11.5px; letter-spacing:.04em; text-transform:uppercase; color:var(--muted); z-index:2; }
  thead th.tnum { text-align:right; }
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

  <details class="panel" id="analysisPanel" open>
    <summary>What actually drives MSFS&nbsp;2024 performance? <span class="pcount">from this data</span></summary>
    <div class="panel-body">
      <p class="methodology" id="analysisIntro"></p>
      <div id="factorTable"></div>
      <p class="methodology" id="analysisNote" style="margin-top:14px"></p>
    </div>
  </details>

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
        One sanity prior is then applied <b>within each Intel microarchitecture</b>: a higher-tier or
        higher-binned part (a 14900KS over a 14900K, the Core Ultra 285K over a 235) has strictly more
        cores, cache or clock, so it can't be slower in a CPU-bound game. Where a thinly-tested SKU's
        noisy score violates that, a coverage-weighted <b>isotonic fit</b> snaps the family back into
        order — well-tested parts barely move, thin ones fall into line. It's deliberately not applied
        across architectures or to AMD's ladder, where the spec sheet doesn't track gaming order (the
        7800X3D beats the 7950X3D) — the lone exception being a few <b>same-die, clock-only pairs</b>
        (e.g. the 5800X3D over the 5700X3D) that are guaranteed by physics. Same-silicon siblings may
        legitimately tie.
      </p>
      <div class="srcgrid" id="sources"></div>
    </div>
  </details>

  <details class="panel" id="tablePanel">
    <summary>Full data table <span class="pcount" id="rowCount"></span></summary>
    <div class="panel-body">
      <div class="tblfilters">
        <div class="ctl-group"><span class="ctl-label">Socket</span><select id="tSocket"></select></div>
        <div class="ctl-group"><span class="ctl-label">Arch</span><select id="tArch"></select></div>
        <label class="tchk"><input type="checkbox" id="tX3D"> X3D only</label>
        <div class="search">
          <svg viewBox="0 0 24 24" stroke-width="2"><circle cx="11" cy="11" r="7"></circle><path d="M21 21l-4.3-4.3"></path></svg>
          <input id="tSearch" type="search" placeholder="Filter CPUs…" autocomplete="off">
        </div>
      </div>
      <div class="tablewrap"><table id="table"><thead></thead><tbody></tbody></table></div>
    </div>
  </details>

  <footer id="footer">
    Combined from <b>Tom's Hardware</b>, <b>PCGH</b> and <b>ComputerBase</b> reviews,
    transcribed/scraped into <code>msfs24_data.csv</code>, <code>pcgh_msfs24.csv</code> and
    <code>computerbase_msfs24.csv</code>, then rendered to this single self-contained file by
    <code>build_html.py</code>. Absolute FPS aren't comparable across sources — the
    Performance Index normalises them. Not affiliated with Tom's Hardware, PCGH or ComputerBase.<br>
    Made by <b>'Razortek'</b> from the Official MSFS Discord (<a href="https://discord.com/invite/msfs" target="_blank" rel="noopener">https://discord.com/invite/msfs</a>); you can direct opinions about this tool to <code>#hardware</code> there because he basically lives there.
  </footer>
</div>

<script>
window.DATA = __DATA__;
window.NORM_SERIES = __NORM__;
window.SPECS = __SPECS__;
window.TWEAKS = {"theme": "light", "bars": "generation", "density": "compact"};
</script>
<script>
/* MSFS 2024 CPU benchmark — redesigned app logic (vanilla). */
(function () {
  "use strict";
  const DATA = window.DATA, NORM_SERIES = window.NORM_SERIES, SPECS = window.SPECS || {};
  const $ = s => document.querySelector(s);
  const el = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };
  const fmt = (x, d) => Number(x).toFixed(d);
  const isX3D = c => /x3d/i.test(c);

  // Compact core-config string from a spec, e.g. "8P+16E·32T", "8C/16T", "16C/32T·2CCD".
  function coreStr(sp) {
    if (!sp) return "";
    if (sp.e > 0) return `${sp.p}P+${sp.e}E·${sp.t}T`;
    let s = `${sp.p}C/${sp.t}T`;
    if (sp.ccd > 1) s += `·${sp.ccd}CCD`;
    return s;
  }

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
  const BIN = { KS: 5, K: 4, KF: 4, F: 3, T: 1 };
  function archKey(cpu) {            // [familyKey, rankTuple] (bigger tuple = faster) or null
    let m;
    if ((m = cpu.match(/^Core i(\d)-(1[1234])(\d)\d{2}([A-Z]*)$/)))
      return [+m[2] <= 11 ? "intel-rocket" : +m[2] === 12 ? "intel-alder" : "intel-raptor",
              [+m[1], +m[3], +m[2], BIN[m[4]] ?? 2]];   // tier, sub-tier, gen, bin
    if ((m = cpu.match(/^Core Ultra (\d) (\d{3})([A-Z]*)/)))
      return ["intel-arrow", [+m[1], +m[2], BIN[m[3]] ?? 2]];
    return null;
  }
  const archCmp = (a, b) => { for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] - b[i]; return 0; };
  function applyArchPrior(raw, series) {
    const weight = cp => Math.max(series.filter(s => cp in s.data).length, 1);
    const fams = {};
    for (const cpu of Object.keys(raw)) {
      const k = archKey(cpu); if (k) (fams[k[0]] ??= []).push({ cpu, key: k[1] });
    }
    for (const members of Object.values(fams)) {
      members.sort((x, y) => archCmp(x.key, y.key));        // weakest first
      const blocks = [];                                     // pool adjacent violators (PAVA)
      for (const it of members) {
        blocks.push({ v: Math.log(raw[it.cpu]), w: weight(it.cpu), cpus: [it.cpu] });
        while (blocks.length >= 2 && blocks[blocks.length - 2].v > blocks[blocks.length - 1].v) {
          const b2 = blocks.pop(), b1 = blocks.pop();
          blocks.push({ v: (b1.v * b1.w + b2.v * b2.w) / (b1.w + b2.w),
                        w: b1.w + b2.w, cpus: [...b1.cpus, ...b2.cpus] });
        }
      }
      for (const blk of blocks) for (const cpu of blk.cpus) raw[cpu] = Math.exp(blk.v);
    }
  }
  // Among equal scores (a tied isotonic block), show the architecturally higher part first.
  function archTiebreak(a, b) {
    const ka = archKey(a), kb = archKey(b);
    return (ka && kb && ka[0] === kb[0]) ? archCmp(kb[1], ka[1]) : 0;
  }

  // Same-silicon, clock-only sibling pairs [faster, slower]. These don't cross a
  // tier the per-family prior can use (AMD is otherwise left to the data), but the
  // ordering is physically guaranteed — identical die, higher clock — so we floor
  // the faster part just above the slower, carrying the head-to-head margin where
  // it's larger, else nudging it marginally ahead (0.2%) rather than inventing one.
  const CLOCK_PAIRS = [
    ["Ryzen 7 5800X3D", "Ryzen 7 5700X3D"],  // Vermeer + V-Cache, clock bump
    ["Ryzen 5 7600X", "Ryzen 5 7500F"],      // Raphael, clock bump
  ];
  function applyClockPairs(raw, series) {
    for (const [fast, slow] of CLOCK_PAIRS) {
      if (raw[fast] == null || raw[slow] == null) continue;
      const ratios = series.filter(s => fast in s.data && slow in s.data)
                           .map(s => s.data[fast] / s.data[slow]);
      const r = ratios.length
        ? Math.exp(ratios.reduce((t, x) => t + Math.log(x), 0) / ratios.length) : 1;
      raw[fast] = Math.max(raw[fast], raw[slow] * Math.max(r, 1.002));
    }
  }

  function enabledData(field) {
    const valid = enabledSeries().map(s => ({ ...s, data: seriesData(s, field) }))
                                 .filter(s => Object.keys(s.data).length);
    const cpus = [...new Set(valid.flatMap(s => Object.keys(s.data)))];
    return { valid, cpus };
  }
  // Pre-prior cross-source fit (no sanity overrides) — used by the factor analysis,
  // which wants what the measurements actually say, not the sanitised ranking.
  function fitRaw(field) {
    const { valid, cpus } = enabledData(field);
    return cpus.length ? twowayFit(valid, cpus, cpus[0]) : {};
  }

  // returns sorted [{cpu, vendor, x3d, raw, idx, n}]
  function computeIndex(field) {
    const { valid, cpus } = enabledData(field);
    if (!cpus.length) return [];
    const raw = twowayFit(valid, cpus, cpus[0]);
    applyArchPrior(raw, valid);
    applyClockPairs(raw, valid);
    const cnt = cp => valid.filter(s => cp in s.data).length;
    let arr = cpus.map(cp => ({ cpu: cp, vendor: VENDOR[cp], x3d: isX3D(cp), raw: raw[cp], n: cnt(cp) }));
    arr.sort((x, y) => Math.abs(y.raw - x.raw) > 1e-9 ? y.raw - x.raw : archTiebreak(x.cpu, y.cpu));
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
  // Socket badge (vendor-tinted) + core-config badge + 3D V-Cache badge.
  function badges(cpu, vendor) {
    const sp = SPECS[cpu]; let h = "";
    if (sp) {
      const tint = vendor === "AMD" ? "amd" : "intel";
      h += `<span class="badge sock ${tint}" title="${sp.arch} · ${sp.l3} MB L3 · up to ${sp.clk.toFixed(1)} GHz">${sp.socket}</span>`;
      const cs = coreStr(sp);
      if (cs) h += `<span class="badge cores" title="${sp.arch}">${cs}</span>`;
    }
    if (isX3D(cpu)) h += `<span class="badge x3d" title="3D V-Cache">3D</span>`;
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
    // axis tops out at the leader so its bar fills the track; a hair of headroom
    // only when everything sits at/under 100, to keep the 100% ref tick on-canvas.
    const axisMax = Math.max(100 * 1.02, maxIdx);
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
           <span class="cpu">${o.cpu}</span>
           <span class="meta">${badges(o.cpu, o.vendor)}</span>
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
    const axisMax = Math.max(...rows.map(r => r.avg));  // leader fills the track
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

  // ---------- factor analysis ----------
  // Each factor isolates one variable via matched pairs [faster, slower] that are
  // otherwise alike. Effect = mean % gap from the raw cross-source fit on the
  // current metric, so it's what the measurements say, before the sanity priors.
  const FACTORS = [
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
  const shortName = c => c.replace(/^Ryzen \d+ /, "").replace(/^Core (Ultra \d+|i\d)[- ]/, "");

  function renderAnalysis() {
    const raw = fitRaw(metric), has = c => raw[c] != null;
    const rows = FACTORS.map(f => {
      const ds = f.pairs.filter(([a, b]) => has(a) && has(b))
                        .map(([a, b]) => ({ a, b, pct: (raw[a] / raw[b] - 1) * 100 }));
      if (!ds.length) return null;
      return { ...f, eff: ds.reduce((t, d) => t + d.pct, 0) / ds.length, ds };
    }).filter(Boolean);
    const box = $("#factorTable");
    if (!rows.length) { box.innerHTML = `<div class="empty">Enable a dataset to compute the factors.</div>`; return; }
    const maxAbs = Math.max(1, ...rows.map(r => Math.abs(r.eff)));
    const cls = e => e >= 2 ? "pos" : e <= -2 ? "neg" : "flat";
    const sign = e => (e >= 0 ? "+" : "") + e.toFixed(1) + "%";
    const ex = ds => ds.map(d => `<b>${shortName(d.a)}</b> vs ${shortName(d.b)} ${(d.pct >= 0 ? "+" : "")}${d.pct.toFixed(0)}%`).join(" &nbsp;·&nbsp; ");
    box.innerHTML = `<div class="factors">` + rows.map(r => {
      const w = Math.abs(r.eff) / maxAbs * 50, left = r.eff >= 0 ? 50 : 50 - w;
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

  // Each measurement row, enriched with the CPU's specs. get() → cell html,
  // sort() → sort value, num → right-aligned/numeric (default sort descending).
  const sp = cpu => SPECS[cpu] || {};
  const COLS = [
    { k: "cpu", l: "CPU", get: r => `${r.cpu}${r.x3d ? ' <span class="badge x3d">3D</span>' : ""}`, sort: r => r.cpu },
    { k: "socket", l: "Socket", get: r => sp(r.cpu).socket || "–", sort: r => sp(r.cpu).socket || "" },
    { k: "arch", l: "Arch", get: r => sp(r.cpu).arch || "–", sort: r => sp(r.cpu).arch || "" },
    { k: "config", l: "Cores", mono: true, get: r => coreStr(sp(r.cpu)) || "–", sort: r => (sp(r.cpu).p || 0) + (sp(r.cpu).e || 0) },
    { k: "t", l: "Threads", num: true, get: r => sp(r.cpu).t ?? "–", sort: r => sp(r.cpu).t ?? -1 },
    { k: "l3", l: "L3 MB", num: true, get: r => sp(r.cpu).l3 ?? "–", sort: r => sp(r.cpu).l3 ?? -1 },
    { k: "clk", l: "Boost", num: true, get: r => sp(r.cpu).clk != null ? sp(r.cpu).clk.toFixed(1) : "–", sort: r => sp(r.cpu).clk ?? -1 },
    { k: "avg", l: "Avg", num: true, get: r => fmt(r.avg, 1), sort: r => r.avg },
    { k: "low", l: "1% Low", num: true, get: r => r.low != null ? fmt(r.low, 0) : "–", sort: r => r.low ?? -Infinity },
    { k: "p02", l: "0.2% Low", num: true, get: r => r.p02 != null ? fmt(r.p02, 0) : "–", sort: r => r.p02 ?? -Infinity },
    { k: "site", l: "Site", get: r => r.site, sort: r => r.site },
    { k: "group", l: "Scene / Epoch", get: r => r.group, sort: r => r.group },
    { k: "date", l: "Date", get: r => r.date, sort: r => r.date },
  ];
  let sortKey = "avg", sortDir = -1;
  const tFilter = { socket: "all", arch: "all", x3d: false, q: "" };

  function tableRows() {
    return DATA.filter(r => {
      const s = sp(r.cpu);
      if (tFilter.socket !== "all" && s.socket !== tFilter.socket) return false;
      if (tFilter.arch !== "all" && s.arch !== tFilter.arch) return false;
      if (tFilter.x3d && !r.x3d) return false;
      if (tFilter.q && !r.cpu.toLowerCase().includes(tFilter.q)) return false;
      return true;
    });
  }
  function renderTable() {
    const col = COLS.find(c => c.k === sortKey) || COLS[0];
    const rows = tableRows().sort((a, b) => {
      const x = col.sort(a), y = col.sort(b);
      return (x < y ? -1 : x > y ? 1 : 0) * sortDir;
    });
    $("#rowCount").textContent = rows.length === DATA.length
      ? `${DATA.length} rows` : `${rows.length} of ${DATA.length} rows`;
    const thead = $("#table thead"), tbody = $("#table tbody");
    thead.innerHTML = "<tr>" + COLS.map(c => {
      const a = c.k === sortKey ? (sortDir < 0 ? "▼" : "▲") : "";
      return `<th data-k="${c.k}" class="${c.num ? "tnum" : ""}">${c.l} <span class="arr">${a}</span></th>`;
    }).join("") + "</tr>";
    thead.querySelectorAll("th").forEach(th => th.onclick = () => {
      const k = th.dataset.k;
      if (k === sortKey) sortDir *= -1; else { sortKey = k; sortDir = COLS.find(c => c.k === k).num ? -1 : 1; }
      renderTable();
    });
    tbody.innerHTML = rows.map(r => "<tr>" + COLS.map(c =>
      `<td class="${c.num ? "tnum num" : ""}${c.mono ? " num" : ""}">${c.get(r)}</td>`).join("") + "</tr>").join("");
  }
  function buildTableFilters() {
    const order = (vals, pref) => [...new Set(vals)].filter(Boolean)
      .sort((a, b) => (pref.indexOf(a) + 1 || 99) - (pref.indexOf(b) + 1 || 99) || (a < b ? -1 : 1));
    const sockets = order(DATA.map(r => sp(r.cpu).socket), ["AM5", "AM4", "LGA1851", "LGA1700", "LGA1200"]);
    const archs = order(DATA.map(r => sp(r.cpu).arch),
      ["Zen 5", "Zen 4", "Zen 3", "Zen 2", "Arrow Lake", "Raptor Lake", "Alder Lake", "Rocket Lake"]);
    $("#tSocket").innerHTML = `<option value="all">All sockets</option>` + sockets.map(s => `<option>${s}</option>`).join("");
    $("#tArch").innerHTML = `<option value="all">All archs</option>` + archs.map(s => `<option>${s}</option>`).join("");
    $("#tSocket").onchange = e => { tFilter.socket = e.target.value; renderTable(); };
    $("#tArch").onchange = e => { tFilter.arch = e.target.value; renderTable(); };
    $("#tX3D").onchange = e => { tFilter.x3d = e.target.checked; renderTable(); };
    $("#tSearch").addEventListener("input", e => { tFilter.q = e.target.value.trim().toLowerCase(); renderTable(); });
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
    renderAnalysis();
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
  buildTableFilters();
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
            .replace("__NORM__", json.dumps(norm_series, ensure_ascii=False))
            .replace("__SPECS__", json.dumps(SPECS, separators=(",", ":"),
                                             ensure_ascii=False)))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    from collections import Counter
    by_site = Counter(r["site"] for r in rows)
    breakdown = ", ".join(f"{n} {s}" for s, n in by_site.items())
    print(f"Wrote {args.out}  ({len(rows)} rows: {breakdown}; "
          f"{len(norm_series)} normalized datasets)")


if __name__ == "__main__":
    main()
