#!/usr/bin/env python3
"""
Build the data bundle the web app consumes.

Reads the transcribed/scraped review CSVs (Tom's Hardware by `epoch`, PCGH and
ComputerBase by `scene`), unifies them into one row list, derives the per-dataset
normalized-series metadata, and carries the static per-CPU spec table — then
writes it all to a single public/data.json that the Vite frontend fetches.

This is the *data* half of the old build_html.py: the presentation (HTML/CSS/TS)
now lives as real source files under index.html + src/, bundled by Vite.

Usage:
    python build_data.py                 # writes public/data.json
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--th", default="msfs24_data.csv")
    ap.add_argument("--pcgh", default="pcgh_msfs24.csv")
    ap.add_argument("--cbase", default="computerbase_msfs24.csv")
    ap.add_argument("--out", default="public/data.json")
    args = ap.parse_args()

    rows = load(args.th, "Tom's Hardware", "epoch") + load(args.pcgh, "PCGH", "scene")
    if os.path.exists(args.cbase):
        rows += load(args.cbase, "ComputerBase", "scene")
    norm_series = build_norm_series(rows)

    bundle = {"rows": rows, "norm": norm_series, "specs": SPECS}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(bundle, f, separators=(",", ":"), ensure_ascii=False)

    from collections import Counter
    by_site = Counter(r["site"] for r in rows)
    breakdown = ", ".join(f"{n} {s}" for s, n in by_site.items())
    print(f"Wrote {args.out}  ({len(rows)} rows: {breakdown}; "
          f"{len(norm_series)} normalized datasets)")


if __name__ == "__main__":
    main()
