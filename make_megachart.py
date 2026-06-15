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


BIN = {"KS": 5, "K": 4, "KF": 4, "F": 3, "T": 1}


def arch_key(cpu):
    """[family, rank tuple] (bigger = faster) for an Intel SKU, else None.

    13th+14th gen are one microarch (Raptor Lake); Core Ultra 2xx is Arrow Lake.
    AMD and cross-architecture comparisons are left to the data on purpose."""
    m = re.match(r"^Core i(\d)-(1[1234])(\d)\d{2}([A-Z]*)$", cpu)
    if m:
        fam = ("intel-rocket" if int(m.group(2)) <= 11
               else "intel-alder" if int(m.group(2)) == 12 else "intel-raptor")
        return fam, (int(m.group(1)), int(m.group(3)), int(m.group(2)), BIN.get(m.group(4), 2))
    m = re.match(r"^Core Ultra (\d) (\d{3})([A-Z]*)", cpu)
    if m:
        return "intel-arrow", (int(m.group(1)), int(m.group(2)), BIN.get(m.group(3), 2))
    return None


def apply_arch_prior(scores, maps):
    """Within each Intel microarchitecture, enforce that a higher-tier / higher-
    binned part isn't ranked below a lesser sibling — it has strictly more cores,
    cache or clock, so it can't be slower in a CPU-bound game. A thinly-tested SKU
    can land out of order from cross-source noise; a coverage-weighted isotonic
    regression (PAVA, in log space) snaps the family back into order while leaving
    well-tested parts near their data. Not applied across architectures or to AMD,
    where the spec ladder doesn't track gaming order (the 7800X3D beats the 7950X3D)."""
    import math
    weight = lambda cp: max(sum(cp in m for m in maps), 1)
    fams = {}
    for cpu in scores:
        k = arch_key(cpu)
        if k:
            fams.setdefault(k[0], []).append((k[1], cpu))
    for members in fams.values():
        members.sort()                                  # weakest first
        blocks = []                                     # pool adjacent violators
        for _, cpu in members:
            blocks.append([math.log(scores[cpu]), weight(cpu), [cpu]])
            while len(blocks) >= 2 and blocks[-2][0] > blocks[-1][0]:
                v2, w2, c2 = blocks.pop()
                v1, w1, c1 = blocks.pop()
                blocks.append([(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, c1 + c2])
        for v, _, cps in blocks:
            for cpu in cps:
                scores[cpu] = math.exp(v)


# Same-silicon, clock-only sibling pairs (faster, slower). AMD's ladder is left to
# the data, but these are physically guaranteed (identical die, higher clock), so
# the faster part is floored just above the slower — carrying the head-to-head
# margin where it's larger, else a marginal 0.2% rather than an invented number.
CLOCK_PAIRS = [
    ("Ryzen 7 5800X3D", "Ryzen 7 5700X3D"),  # Vermeer + V-Cache, clock bump
    ("Ryzen 5 7600X", "Ryzen 5 7500F"),      # Raphael, clock bump
]


def apply_clock_pairs(scores, maps):
    import math
    for fast, slow in CLOCK_PAIRS:
        if fast not in scores or slow not in scores:
            continue
        ratios = [m[fast] / m[slow] for m in maps if fast in m and slow in m]
        r = math.exp(sum(math.log(x) for x in ratios) / len(ratios)) if ratios else 1.0
        scores[fast] = max(scores[fast], scores[slow] * max(r, 1.002))


def twoway_means(norm, ref):
    """Two-way additive fit in log space: log(value) = dataset_offset + cpu_effect.

    A plain mean across the datasets that happen to contain each CPU is biased
    when sources test different CPU sets: a CPU gets penalised merely for
    appearing in a stingier source (and dodges the penalty if it doesn't).
    Fitting a per-dataset offset absorbs each source's overall level, so the
    CPU effect is comparable even with missing cells. Result is rescaled so the
    reference CPU = 100, then the architectural sanity prior is applied.
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
    maps = [d for _, d in data]
    apply_arch_prior(out, maps)
    apply_clock_pairs(out, maps)
    return out


def ranked_cpus(norm, ref):
    fit = twoway_means(norm, ref)
    mean = fit.__getitem__
    # ascending (slowest at bottom of barh); tied isotonic siblings ordered by
    # architectural rank so the higher part sits above its twin deterministically.
    def sort_key(c):
        k = arch_key(c)
        return (fit[c], k[0] if k else "", k[1] if k else ())
    return sorted(fit, key=sort_key), mean


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
    ax.set_title("Microsoft Flight Simulator 2024 — Normalized CPU Megachart (averaged)",
                 fontsize=13, fontweight="bold", loc="left", pad=26)
    ax.annotate("Two-way fit (per-dataset offset + CPU effect) over Tom's epochs +\n"
                "PCGH scenes · ·N = datasets covering each CPU",
                xy=(0, 1), xycoords="axes fraction", xytext=(0, 6),
                textcoords="offset points", va="bottom", ha="left",
                fontsize=9.5, color="#555")
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
