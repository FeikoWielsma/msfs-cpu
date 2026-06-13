# MSFS 2024 CPU Performance — combined charts

An interactive, single-file static page that consolidates **Microsoft Flight
Simulator 2024** CPU benchmark results from multiple reviews into one place,
with normalization so results from different sites/test passes can be compared.

**Live:** https://msfs.razortek.nl

## What it does

- **By source** — browse one comparable dataset at a time (a Tom's Hardware test
  *epoch* or a PCGH *scene*); hover any bar to make it the 100% baseline and read
  every other CPU's relative ±%.
- **Normalized (all sites)** — Tom's epochs + PCGH scenes on one axis, each scaled
  so a chosen reference CPU (default Ryzen 7 7800X3D) = 100%. Toggle datasets on/off
  live; average them into one bar per CPU, colored by CPU generation.

Absolute FPS are **not** comparable across sites/scenes (different scenes,
settings, resolutions) — that's exactly why the normalized view exists.

## Regenerating

The page (`index.html`) is fully self-contained — data and styling are inlined,
so hosting needs nothing but the one file.

```sh
python build_html.py                 # rebuild index.html from the CSVs
python plot_msfs24.py --by-epoch     # Tom's per-epoch PNGs
python make_megachart.py --averaged  # normalized megachart PNG
```

Data lives in `msfs24_data.csv` (Tom's, transcribed from chart screenshots) and
`pcgh_msfs24.csv` (scraped from saved PCGH pages by `scrape_pcgh.py`).

## Data sources & attribution

Benchmark numbers are from **Tom's Hardware** and **PC Games Hardware (PCGH)**
reviews, transcribed/scraped into the CSVs here. This repo contains only those
factual data points and our own generated charts — **not** the original review
articles, chart images, or saved pages (those are gitignored and not
republished). Not affiliated with or endorsed by either outlet.
