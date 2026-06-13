#!/usr/bin/env python3
"""
Scrape the Flight Simulator 2024 CPU results out of saved PCGH (pcgh.de)
benchmark HTML pages.

The pages are saved Svelte apps. The numbers live in the rendered DOM as
<span class="bar-text">98,9</span> (German decimal comma) inside per-CPU
chartRows; each CPU row carries up to three bars: Average FPS, P1 low, P0.2 low.

Only the *active* game's chart is present in a saved page, and it is the first
chart on the page. All these pages were saved with MSFS 2024 selected, so
chart 0 is the FS2024 chart. PCGH used two different FS scenes over time
("Flight Simulator 24 – New York" early 2025, "Flight Simulator 2024" later) —
both are captured and tagged via the `scene` column so they can be separated /
deduped downstream.

Output schema is a superset of msfs24_data.csv (so plot_msfs24.py can chart it):
extra columns p02_low / scene / site. No deduplication is done here.

Usage:
    python scrape_pcgh.py                       # globs pcgh.de/*.html
    python scrape_pcgh.py file1.html file2.html
    python scrape_pcgh.py --out pcgh_msfs24.csv
"""

import argparse
import csv
import glob
import os
import re
import sys

SITE = "PCGH"


def first_chart(doc):
    """Return rows [(cpu_name, [vals...])] of the first (active) chart only."""
    rows = []
    for ch in re.split(r'<div class="chartRow', doc)[1:]:
        nm = re.search(r'itemName[^>]*title="([^"]+)"', ch)
        vals = re.findall(r'bar-text[^>]*>([0-9,]+)', ch)
        if nm and vals:
            rows.append((nm.group(1).strip(),
                         [float(v.replace(",", ".")) for v in vals]))
    out, prev, nbars = [], None, None
    for name, nums in rows:
        if nbars is None:
            nbars = len(nums)                            # game chart = avg/P1/P0.2
        # A new chart starts when the bar count changes (trailing single-bar /
        # index sub-charts) or the leader value rises again.
        if len(nums) != nbars or (prev is not None and nums[0] > prev + 0.01):
            break
        out.append((name, nums))
        prev = nums[0]
    return out


def meta(doc):
    d = re.search(r'"datePublished":"(\d{4}-\d{2}-\d{2})', doc)
    scene = re.search(
        r'<label[^>]*>(?:<input[^>]*>)?\s*(Flight Simulator[^<]*?)\s*</label>', doc)
    return (d.group(1) if d else ""),(scene.group(1).strip() if scene else "Flight Simulator")


def slug(path):
    base = os.path.splitext(os.path.basename(path))[0].lower()
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
    return "pcgh_" + base


# Config-variant markers we discard entirely; anything else in trailing parens
# (e.g. "105 W") is folded into the base CPU name.
DROP_VARIANTS = ("65 W", "cTDP", "Turbo GM", "CU")


def fold_variant(cpu):
    """Canonical CPU name, or None to drop a config variant."""
    m = re.search(r"\(([^)]*)\)\s*$", cpu)
    if m:
        if any(d in m.group(1) for d in DROP_VARIANTS):
            return None
        cpu = re.sub(r"\s*\([^)]*\)\s*$", "", cpu)   # fold e.g. "(105 W)"
    return cpu.strip()


def clean_cpu(name):
    return re.sub(r"^(AMD|Intel)\s+", "", name).strip()


def records_for(path):
    doc = open(path, encoding="utf-8", errors="replace").read()
    rows = first_chart(doc)
    date, scene = meta(doc)
    src = slug(path)
    recs, seen = [], set()
    for name, nums in rows:
        cpu = fold_variant(clean_cpu(name))
        if cpu is None or cpu in seen:      # dropped variant, or already folded
            continue
        seen.add(cpu)
        recs.append({
            "cpu": cpu,
            "vendor": "AMD" if "Ryzen" in name else "Intel",
            "is_x3d": "1" if "X3D" in cpu.upper() else "0",
            "avg_fps": f"{nums[0]:.1f}",
            "low_1pct": f"{nums[1]:.0f}" if len(nums) > 1 else "",
            "p02_low": f"{nums[2]:.0f}" if len(nums) > 2 else "",
            "source": src,
            "review_date": date,
            "scene": scene,
            "site": SITE,
        })
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*",
                    help="Saved PCGH HTML files (default: pcgh.de/*.html)")
    ap.add_argument("--out", default="pcgh_msfs24.csv")
    args = ap.parse_args()

    files = args.files or sorted(glob.glob("pcgh.de/*.html"))
    if not files:
        sys.exit("No PCGH HTML files found.")

    all_recs = []
    for f in files:
        recs = records_for(f)
        if not recs:
            print(f"  ! {f}: no chart rows found — skipped")
            continue
        print(f"  {os.path.basename(f)}: {len(recs)} CPUs · {recs[0]['review_date']} "
              f"· {recs[0]['scene']} · leader {recs[0]['cpu']} {recs[0]['avg_fps']}")
        all_recs += recs

    cols = ["cpu", "vendor", "is_x3d", "avg_fps", "low_1pct", "p02_low",
            "source", "review_date", "scene", "site"]
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(all_recs)
    print(f"Wrote {args.out}  ({len(all_recs)} rows from {len(files)} files)")


if __name__ == "__main__":
    main()
