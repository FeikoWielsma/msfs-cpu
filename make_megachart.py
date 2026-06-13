#!/usr/bin/env python3
"""
Normalized cross-source "megachart": Tom's Hardware + PCGH MSFS 2024 results on
one axis, each dataset scaled so a chosen reference CPU = 100%.

Absolute FPS aren't comparable across sites/scenes, but normalizing every
dataset to the same reference CPU turns them into a relative index that can be
compared (assuming the reference's standing is representative).

Datasets = one per (site, group): the three Tom's epochs plus the two PCGH
scenes — i.e. every dataset, old ones included (matches msfs24.html).

Two layouts:
  default        grouped bars, one per dataset per CPU
  --averaged     one bar per CPU = mean of its normalized values across the
                 datasets that contain it, colored by vendor, with a "·N" count

Usage:
    python make_megachart.py --averaged
    python make_megachart.py                       # per-dataset grouped bars
    python make_megachart.py --ref "Ryzen 7 9800X3D" --out custom.png
"""

import argparse
import csv
import os
import re

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# Per-generation colors: AMD = reds (older→darker), Intel = blues (older→darker).
# 13th + 14th gen share a color (same architecture). Order = legend order.
GEN_COLOR = {
    "Ryzen 3000": "#6e1714", "Ryzen 5000": "#a32f26",
    "Ryzen 7000": "#d6433b", "Ryzen 9000": "#f47a63",
    "Core 11th": "#103a63", "Core 12th": "#1f6fb0",
    "Core 13/14th": "#3a9bdc", "Core Ultra 2xx": "#7fc9ef",
}
GEN_ORDER = list(GEN_COLOR)

# Per-dataset colors (for the non-averaged layout): Tom's blues, PCGH warm,
# ComputerBase greens.
PALETTE = {"Tom's Hardware": ["#9ecae1", "#4292c6", "#08519c"],
           "PCGH": ["#8073ac", "#e08214"],
           "ComputerBase": ["#2ca25f", "#006d2c"]}
SITE_ORDER = ["Tom's Hardware", "PCGH", "ComputerBase"]


def gen_of(cpu):
    """Map a CPU name to a generation key in GEN_COLOR."""
    if cpu.startswith("Ryzen"):
        m = re.search(r"Ryzen \d+ (\d)\d{3}", cpu)
        return {"3": "Ryzen 3000", "5": "Ryzen 5000",
                "7": "Ryzen 7000", "9": "Ryzen 9000"}.get(
                    m.group(1) if m else "", "Ryzen 7000")
    if "Core Ultra" in cpu:
        return "Core Ultra 2xx"
    m = re.search(r"Core i\d+-(\d{2})", cpu)
    g = m.group(1) if m else ""
    if g == "11":
        return "Core 11th"
    if g == "12":
        return "Core 12th"
    return "Core 13/14th"


def load(path, site, group_col):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({"cpu": r["cpu"], "vendor": r["vendor"],
                         "avg": float(r["avg_fps"]), "date": r["review_date"],
                         "site": site, "group": r[group_col]})
    return rows


def dedup_newest(rows):
    best = {}
    for r in rows:
        c = best.get(r["cpu"])
        if c is None or r["date"] > c["date"]:
            best[r["cpu"]] = r
    return {cpu: r["avg"] for cpu, r in best.items()}


def build_datasets(rows):
    """[(name, color, {cpu: avg})] — one per (site, group), chronological."""
    out = []
    for site in [s for s in SITE_ORDER if any(r["site"] == s for r in rows)]:
        srows = [r for r in rows if r["site"] == site]
        groups = sorted({r["group"] for r in srows},
                        key=lambda g: min(r["date"] for r in srows
                                          if r["group"] == g))
        short = {"Tom's Hardware": "TH", "PCGH": "PCGH",
                 "ComputerBase": "CB"}[site]
        for i, g in enumerate(groups):
            out.append((f"{short} · {g}", PALETTE[site][i % len(PALETTE[site])],
                        dedup_newest([r for r in srows if r["group"] == g])))
    return out


def normalize(datasets, ref):
    missing = [n for n, _, d in datasets if ref not in d]
    if missing:
        raise SystemExit(f"Reference '{ref}' not in: {missing}")
    return [(n, c, {cpu: v / d[ref] * 100 for cpu, v in d.items()})
            for n, c, d in datasets]


def gen_predecessor(cpu):
    """Map an Intel 14th-gen SKU to its 13th-gen predecessor (same silicon)."""
    m = re.match(r"^(Core i\d-)14(\d{3}[A-Z]*)$", cpu)
    return m.group(1) + "13" + m.group(2) if m else None


def apply_gen_floor(scores, maps):
    """Floor each 14th-gen part at its 13th-gen twin's score, carrying the margin
    measured where both were tested head-to-head. A 14th-gen part is a clock-bumped
    rebadge of its 13th-gen twin, so it can't be slower — this corrects cross-source
    noise without inventing a lead the shared tests don't show. Ratios survive the
    per-dataset normalization (a constant scale cancels)."""
    import math
    for cpu in list(scores):
        pred = gen_predecessor(cpu)
        if not pred or pred not in scores:
            continue
        ratios = [m[cpu] / m[pred] for m in maps if cpu in m and pred in m]
        r = math.exp(sum(math.log(x) for x in ratios) / len(ratios)) if ratios else 1.0
        scores[cpu] = max(scores[cpu], scores[pred] * max(r, 1.0))


def twoway_means(norm, ref):
    """Two-way additive fit in log space: log(value) = dataset_offset + cpu_effect.

    A plain mean across the datasets that happen to contain each CPU is biased
    when sources test different CPU sets: a CPU gets penalised merely for
    appearing in a stingier source (and dodges the penalty if it doesn't).
    Fitting a per-dataset offset absorbs each source's overall level, so the
    CPU effect is comparable even with missing cells. Result is rescaled so the
    reference CPU = 100, then the generation-monotonic prior is applied.
    """
    import math
    data = [(c, d) for _, c, d in norm]  # we only need the {cpu: value} maps
    cpus = set().union(*[d.keys() for d in (m for _, m in data)])
    a = [0.0] * len(data)                       # per-dataset offsets
    b = {c: 0.0 for c in cpus}                  # per-CPU effects
    for _ in range(200):                        # alternating least squares
        for i, (_, d) in enumerate(data):
            a[i] = sum(math.log(v) - b[c] for c, v in d.items()) / len(d)
        for c in cpus:
            obs = [(i, d[c]) for i, (_, d) in enumerate(data) if c in d]
            b[c] = sum(math.log(v) - a[i] for i, v in obs) / len(obs)
    base = b[ref]                               # anchor so ref == 100
    out = {c: math.exp(b[c] - base) * 100 for c in cpus}
    apply_gen_floor(out, [d for _, d in data])
    return out


def ranked_cpus(norm, ref):
    fit = twoway_means(norm, ref)
    mean = fit.__getitem__
    return sorted(fit, key=mean), mean  # ascending: slowest at bottom of barh


def plot_averaged(norm, vendor, ref, out_path):
    cpus, mean = ranked_cpus(norm, ref)
    vals = [mean(c) for c in cpus]
    cnts = [sum(c in d for _, _, d in norm) for c in cpus]
    gens = [gen_of(c) for c in cpus]
    colors = [GEN_COLOR[g] for g in gens]

    y = range(len(cpus))
    fig, ax = plt.subplots(figsize=(11, 0.34 * len(cpus) + 2))
    ax.barh(y, vals, color=colors, height=0.78, zorder=2)
    for i, (v, n) in enumerate(zip(vals, cnts)):
        ax.text(v + 0.6, i, f"{v:.1f}", va="center", ha="left",
                fontsize=8, fontweight="bold", color="#222", zorder=4)
        ax.text(v - 0.6, i, f"·{n}", va="center", ha="right",
                fontsize=7.5, color="white", fontweight="bold", zorder=4)

    ax.axvline(100, color="#c0392b", lw=1.4, zorder=3)
    ax.text(100, len(cpus) - 0.3, f"  100% = {ref}", color="#c0392b",
            fontsize=9, fontweight="bold", va="top")
    ax.set_yticks(list(y))
    ax.set_yticklabels([f"{c} ★" if "X3D" in c.upper() else c for c in cpus],
                       fontsize=8)
    ax.set_xlim(0, max(vals) * 1.10)
    ax.set_xlabel(f"Mean performance relative to {ref}  (%)", fontsize=10)
    ax.set_title("Microsoft Flight Simulator 2024 — Normalized CPU Megachart "
                 "(averaged)\nTwo-way fit (per-dataset offset + CPU effect) over "
                 "Tom's epochs + PCGH scenes · ·N = datasets covering each CPU",
                 fontsize=13, fontweight="bold", loc="left")
    ax.grid(axis="x", linestyle=":", alpha=0.4, zorder=0)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    present = [g for g in GEN_ORDER if g in set(gens)]
    ax.legend(handles=[Patch(facecolor=GEN_COLOR[g], label=g) for g in present],
              loc="lower right", fontsize=8.5, framealpha=0.95, ncol=2,
              title="Generation")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}  ({len(cpus)} CPUs, averaged over {len(norm)} datasets)")


def plot_per_dataset(norm, ref, out_path):
    cpus, _ = ranked_cpus(norm)
    n_ser, h = len(norm), 0.82 / len(norm)
    y = range(len(cpus))
    fig, ax = plt.subplots(figsize=(12, 0.46 * len(cpus) + 2))
    for si, (name, color, d) in enumerate(norm):
        offs = [i + ((n_ser - 1) / 2 - si) * h for i in y]
        pts = [(o, d[c]) for o, c in zip(offs, cpus) if c in d]
        ax.barh([o for o, _ in pts], [v for _, v in pts], height=h,
                color=color, label=name, zorder=2)
    ax.axvline(100, color="#c0392b", lw=1.4, zorder=3)
    ax.text(100, len(cpus) - 0.3, f"  100% = {ref}", color="#c0392b",
            fontsize=9, fontweight="bold", va="top")
    ax.set_yticks(list(y))
    ax.set_yticklabels(cpus, fontsize=8)
    ax.set_xlim(0, max(max(d.values()) for _, _, d in norm) * 1.08)
    ax.set_xlabel(f"Performance relative to {ref}  (%)", fontsize=10)
    ax.set_title("Microsoft Flight Simulator 2024 — Normalized CPU Megachart\n"
                 "Tom's epochs + PCGH scenes, each scaled to the reference CPU",
                 fontsize=13, fontweight="bold", loc="left")
    ax.grid(axis="x", linestyle=":", alpha=0.4, zorder=0)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(loc="lower right", fontsize=9, framealpha=0.95, title="Dataset")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}  ({len(cpus)} CPUs, {len(norm)} datasets)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--th", default="msfs24_data.csv")
    p.add_argument("--pcgh", default="pcgh_msfs24.csv")
    p.add_argument("--cbase", default="computerbase_msfs24.csv")
    p.add_argument("--ref", default="Ryzen 7 7800X3D")
    p.add_argument("--averaged", action="store_true",
                   help="One averaged bar per CPU instead of per-dataset bars.")
    p.add_argument("--out")
    args = p.parse_args()

    rows = load(args.th, "Tom's Hardware", "epoch") + load(args.pcgh, "PCGH", "scene")
    if os.path.exists(args.cbase):
        rows += load(args.cbase, "ComputerBase", "scene")
    vendor = {}
    for r in rows:
        vendor.setdefault(r["cpu"], r["vendor"])
    norm = normalize(build_datasets(rows), args.ref)

    if args.averaged:
        plot_averaged(norm, vendor, args.ref,
                      args.out or "msfs24_megachart_avg.png")
    else:
        plot_per_dataset(norm, args.ref, args.out or "msfs24_megachart.png")


if __name__ == "__main__":
    main()
