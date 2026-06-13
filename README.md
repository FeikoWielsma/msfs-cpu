# MSFS 2024 CPU Performance — combined charts

An interactive, single-file static page that consolidates **Microsoft Flight
Simulator 2024** CPU benchmark results from multiple reviews into one place,
with normalization so results from different sites/test passes can be compared.

**Live:** https://msfs.razortek.nl

The page is mobile-first and leads with a plain-language ranking; the dataset
and methodology machinery is tucked into expanders.

## What it does

- **Performance Index** (default) — one combined ranking across all sources. Each
  enabled review is rescaled onto a shared 0–100 scale with a **two-way additive
  fit** (per-dataset offset + per-CPU effect), so a CPU's score reflects its own
  speed, not which reviewer happened to test it. Tap any CPU to make it the 100%
  baseline and read every other CPU's relative ±%. *Advanced* lets you toggle which
  reviews feed the index and watch the ranking shift.
- **By source** — browse one comparable dataset at a time (a Tom's Hardware test
  *epoch* or a PCGH/ComputerBase *scene*); average + 1% low bars, tap to re-baseline.

Absolute FPS are **not** comparable across sites/scenes (different scenes,
settings, resolutions) — that's exactly why the Performance Index exists.

## Regenerating

The page (`index.html`) is fully self-contained — data and styling are inlined,
so hosting needs nothing but the one file.

```sh
python build_html.py                 # rebuild index.html from the CSVs
python plot_msfs24.py --by-epoch     # Tom's per-epoch PNGs
python make_megachart.py --averaged  # normalized megachart PNG
```

Data lives in `msfs24_data.csv` (Tom's, transcribed from chart screenshots),
`pcgh_msfs24.csv` (scraped from saved PCGH pages by `scrape_pcgh.py`) and
`computerbase_msfs24.csv` (scraped by `scrape_computerbase.py`).

## Data sources & attribution

Benchmark numbers are from **Tom's Hardware**, **PC Games Hardware (PCGH)** and
**ComputerBase** reviews, transcribed/scraped into the CSVs here. This repo
contains only those factual data points and our own generated charts — **not** the
original review articles, chart images, or saved pages (those are gitignored and
not republished). Not affiliated with or endorsed by any of these outlets.
