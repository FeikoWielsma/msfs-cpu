#!/usr/bin/env python3
"""
Scrape Flight Simulator 2024 CPU results from a saved ComputerBase
"Gaming-Benchmarks" HTML page.

ComputerBase renders each chart as a <div id="diagramm-...-fps-durchschnitt">
(average) and "...-fps-1-prozent-perzentil" (1% percentile low). Each CPU is a
<li class="chart__row"> with the name in .chart__item (sometimes wrapped in
<strong><u> for the reviewed chip), a config sub-label, and the value in
<div class="chart__label" data-value="78.2">.

NB: ComputerBase flags its own FS2024 results as inconsistent / crash-prone and
excludes them from their ratings; rows carrying that warning get note="unreliable".
Output schema matches pcgh_msfs24.csv (+ note column).

Usage:
    python scrape_computerbase.py            # default 9900X3D review file
    python scrape_computerbase.py file.html --out computerbase_msfs24.csv
"""

import argparse
import csv
import html
import re
import sys

SITE = "ComputerBase"
SCENE = "Flight Simulator 2024"
REVIEW_DATE = "2025-04-07"
DEFAULT_FILE = ("computerbase.de/AMD Ryzen 9 9900X3D im Test_ "
                "Gaming-Benchmarks - ComputerBase.html")


def parse_chart(doc, idsub):
    """{cpu_name: (value, note)} for one FS2024 chart."""
    i = doc.find(f'id="diagramm-microsoft-flight-simulator-2024-fps-{idsub}"')
    if i < 0:
        return {}
    j = doc.find('id="diagramm-', i + 10)
    seg = doc[i: j if j > 0 else i + 30000]
    out = {}
    for row in re.split(r'<li class="chart__row">', seg)[1:]:
        item = re.search(r'chart__item">(.*?)(?:<br|<span class="chart__item-title-addtl)',
                         row, re.S)
        val = re.search(r'data-value="([0-9.]+)"', row)
        if not (item and val):
            continue
        name = html.unescape(re.sub(r"<[^>]+>", "", item.group(1))).strip()
        if not name:
            continue
        note = "unreliable" if "chart__comment" in row else ""
        out[name] = (float(val.group(1)), note)
    return out


# Config-variant markers we discard; other trailing parens fold into the base name.
DROP_VARIANTS = ("65 W", "cTDP", "Turbo GM", "CU")


def fold_variant(cpu):
    """Canonical CPU name, or None to drop a config variant."""
    m = re.search(r"\(([^)]*)\)\s*$", cpu)
    if m:
        if any(d in m.group(1) for d in DROP_VARIANTS):
            return None
        cpu = re.sub(r"\s*\([^)]*\)\s*$", "", cpu)
    return cpu.strip()


def article_url(doc):
    m = (re.search(r'<meta property="og:url" content="([^"]+)"', doc)
         or re.search(r'<link rel="canonical" href="([^"]+)"', doc))
    return m.group(1) if m else ""


def article_title(doc):
    m = (re.search(r'<meta property="og:title" content="([^"]+)"', doc)
         or re.search(r"<title>([^<]*)</title>", doc))
    t = re.sub(r"\s*-\s*ComputerBase\s*$", "", m.group(1)).strip() if m else ""
    return html.unescape(t)


def records(path):
    doc = open(path, encoding="utf-8", errors="replace").read()
    avg = parse_chart(doc, "durchschnitt")
    low = parse_chart(doc, "1-prozent-perzentil")
    url, title = article_url(doc), article_title(doc)
    recs, seen = [], set()
    for name, (a, note) in avg.items():
        cpu = fold_variant(re.sub(r"^(AMD|Intel)\s+", "", name))
        if cpu is None or cpu in seen:
            continue
        seen.add(cpu)
        lo = low.get(name, (None, ""))[0]
        recs.append({
            "cpu": cpu,
            "vendor": "AMD" if "Ryzen" in name else "Intel",
            "is_x3d": "1" if "X3D" in cpu.upper() else "0",
            "avg_fps": f"{a:.1f}",
            "low_1pct": f"{lo:.1f}" if lo is not None else "",
            "p02_low": "",
            "source": "computerbase_9900x3d_review",
            "review_date": REVIEW_DATE,
            "scene": SCENE,
            "site": SITE,
            "note": note,
            "url": url,
            "title": title,
        })
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", default=DEFAULT_FILE)
    ap.add_argument("--out", default="computerbase_msfs24.csv")
    args = ap.parse_args()

    recs = records(args.file)
    if not recs:
        sys.exit("No FS2024 rows found — check the file / chart ids.")
    cols = ["cpu", "vendor", "is_x3d", "avg_fps", "low_1pct", "p02_low",
            "source", "review_date", "scene", "site", "note", "url", "title"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(recs)
    n_unrel = sum(1 for r in recs if r["note"])
    print(f"Wrote {args.out}  ({len(recs)} CPUs, {n_unrel} flagged unreliable; "
          f"leader {recs[0]['cpu']} {recs[0]['avg_fps']})")


if __name__ == "__main__":
    main()
