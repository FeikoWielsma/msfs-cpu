#!/usr/bin/env python3
"""
Tom's Hardware MSFS 2024 CPU benchmark charts.

Reads the raw, per-review master data (every CPU x review row) scraped from
the Tom's Hardware screenshots (Flight Simulator 24, DX12, In-Game,
1920x1080 Ultra) and renders horizontal bar charts of Average FPS + 1% Low.

The same CPU was re-benchmarked across several reviews as the game/drivers
changed, so each row carries a review_date and an `epoch` (a group of reviews
that are mutually consistent). Two output modes:

    combined  (default)  one chart, newest data per CPU across all epochs
    epochs    (--by-epoch)  one chart per epoch, using that epoch's own numbers

Usage:
    python plot_msfs24.py                      # combined chart
    python plot_msfs24.py --by-epoch           # one PNG per epoch
"""

import argparse
import csv
import re

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# Vendor color scheme (Average bar = full color, 1% Low = darker overlay).
COLORS = {
    "AMD":   {"avg": "#d6433b", "low": "#8f211b"},   # red
    "Intel": {"avg": "#2f8fd6", "low": "#1b5687"},   # blue
}

# Reviews on/after this date form the current, mutually-consistent test epoch
# (spring 2026). Earlier reviews used older game/driver builds, so in the
# COMBINED chart a CPU whose newest data predates this is flagged.
EPOCH_CUTOFF = "2026-03"


def load_data(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["avg_fps"] = float(r["avg_fps"])
            r["low_1pct"] = float(r["low_1pct"])
            r["is_x3d"] = r["is_x3d"] == "1"
            rows.append(r)
    return rows


def dedup_newest(rows):
    """Collapse to one row per CPU, keeping the most recent review_date."""
    best = {}
    for r in rows:
        cur = best.get(r["cpu"])
        if cur is None or r["review_date"] > cur["review_date"]:
            best[r["cpu"]] = r
    return list(best.values())


def make_plot(rows, out_path, title, subtitle, mark_stale=False):
    rows = sorted(rows, key=lambda x: x["avg_fps"])  # fastest at the top
    avg = [r["avg_fps"] for r in rows]
    low = [r["low_1pct"] for r in rows]
    avg_c = [COLORS[r["vendor"]]["avg"] for r in rows]
    low_c = [COLORS[r["vendor"]]["low"] for r in rows]
    # A CPU is "stale" if its newest data predates the current test epoch.
    stale = [r.get("review_date", "") < EPOCH_CUTOFF for r in rows]

    y = range(len(rows))
    fig, ax = plt.subplots(figsize=(12, 0.45 * len(rows) + 2))

    # Average = full-height bar; 1% Low = narrower darker bar overlaid on top.
    edge = [("0.25" if (mark_stale and s) else "none") for s in stale]
    ax.barh(y, avg, height=0.78, color=avg_c, zorder=2,
            edgecolor=edge, linewidth=1.2, linestyle=(0, (3, 2)))
    ax.barh(y, low, height=0.40, color=low_c, zorder=3)

    # Value labels: Average at bar end, 1% Low at end of inner bar.
    for i, r in enumerate(rows):
        ax.text(r["avg_fps"] + 1.0, i, f"{r['avg_fps']:.1f}",
                va="center", ha="left", fontsize=9, fontweight="bold",
                color="#222222", zorder=4)
        ax.text(r["low_1pct"] - 1.5, i, f"{r['low_1pct']:.0f}",
                va="center", ha="right", fontsize=8, color="white",
                fontweight="bold", zorder=4)

    ax.set_yticks(list(y))

    # Mark X3D parts with a star; optionally append the (older) test date.
    def ylabel(r, s):
        txt = f"{r['cpu']} ★" if r["is_x3d"] else r["cpu"]
        if mark_stale and s:
            txt += f"  ({r['review_date']})"
        return txt

    ax.set_yticklabels([ylabel(r, s) for r, s in zip(rows, stale)], fontsize=9)
    ax.set_xlim(0, max(avg) * 1.12)
    ax.set_xlabel("FPS", fontsize=10)
    if mark_stale:
        subtitle += "\nDashed outline = value from an older re-test (date shown)"
    ax.set_title(f"{title}\n{subtitle}", fontsize=13, fontweight="bold", loc="left")
    ax.grid(axis="x", linestyle=":", alpha=0.4, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    legend = [
        Patch(facecolor=COLORS["AMD"]["avg"], label="AMD – Average FPS"),
        Patch(facecolor=COLORS["AMD"]["low"], label="AMD – 1% Low"),
        Patch(facecolor=COLORS["Intel"]["avg"], label="Intel – Average FPS"),
        Patch(facecolor=COLORS["Intel"]["low"], label="Intel – 1% Low"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=8, framealpha=0.9)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}  ({len(rows)} CPUs)")


TITLE = "Microsoft Flight Simulator 2024 — CPU Performance"
BASE_SUB = "DX12, In-Game, 1920x1080 Ultra"


def plot_combined(rows, out_path, mark_stale, title=None, subtitle=None):
    make_plot(dedup_newest(rows), out_path, title or TITLE,
              subtitle or f"{BASE_SUB}  (combined Tom's Hardware data, newest per CPU)",
              mark_stale=mark_stale)


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def plot_groups(rows, out_prefix, group_col="epoch", group_label="test epoch",
                title=None, subtitle=None):
    """One chart per distinct value of group_col, ordered by earliest date."""
    base_sub = subtitle if subtitle is not None else BASE_SUB
    groups = sorted({r[group_col] for r in rows},
                    key=lambda g: min(r["review_date"] for r in rows
                                      if r[group_col] == g))
    for g in groups:
        gr = [r for r in rows if r[group_col] == g]
        dates = sorted({r["review_date"] for r in gr})
        span = dates[0] if len(dates) == 1 else f"{dates[0]} → {dates[-1]}"
        # Within a group reviews are consistent; for any overlap keep the newest.
        make_plot(dedup_newest(gr), f"{out_prefix}_{slugify(g)}.png",
                  title or TITLE, f"{base_sub}  —  {group_label}: {g}  ({span})",
                  mark_stale=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="msfs24_data.csv")
    p.add_argument("--out", default="msfs24_combined.png",
                   help="Output path for the combined chart.")
    p.add_argument("--by-epoch", action="store_true",
                   help="Emit one PNG per group (see --group-col) instead of a "
                        "single combined chart.")
    p.add_argument("--epoch-prefix", default="msfs24_epoch",
                   help="Filename prefix for per-group PNGs "
                        "(e.g. msfs24_epoch_2026-spring.png).")
    p.add_argument("--group-col", default="epoch",
                   help="Column to group per-group charts by (default: epoch; "
                        "use 'scene' for PCGH data).")
    p.add_argument("--group-label", default="test epoch",
                   help="Human label for the group in subtitles "
                        "(default: 'test epoch').")
    p.add_argument("--mark-stale", action=argparse.BooleanOptionalAction,
                   default=True,
                   help="In the combined chart, outline + date-label CPUs whose "
                        "newest data is from an older epoch (default: on).")
    p.add_argument("--title", help="Override the chart title.")
    p.add_argument("--subtitle", help="Override the chart subtitle.")
    args = p.parse_args()

    rows = load_data(args.csv)
    if args.by_epoch:
        plot_groups(rows, args.epoch_prefix, group_col=args.group_col,
                    group_label=args.group_label, title=args.title,
                    subtitle=args.subtitle)
    else:
        plot_combined(rows, args.out, args.mark_stale,
                      title=args.title, subtitle=args.subtitle)


if __name__ == "__main__":
    main()
