# MSFS 2024 CPU Performance — combined charts

An interactive static site that consolidates **Microsoft Flight Simulator 2024**
CPU benchmark results from multiple reviews into one place, with normalization so
results from different sites/test passes can be compared.

**Live:** https://msfs.razortek.nl

Built with **Vite + TypeScript** (frontend) and a small **Python** data step.
Hosted on GitHub Pages, deployed automatically by GitHub Actions.

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

## Project layout

```
build_data.py          # data step: CSVs → public/data.json (rows + norm series + specs)
index.html             # Vite entry (markup only)
src/main.ts            # app logic (TypeScript), fetches data.json
src/style.css          # styles
public/                # copied verbatim into dist/ (data.json, CNAME)
.github/workflows/     # GitHub Pages deploy (Actions)
*.csv                  # the transcribed/scraped source data
plot_msfs24.py, make_megachart.py   # standalone matplotlib chart generators (PNGs)
```

The frontend never inlines data — `src/main.ts` fetches `data.json` at runtime,
so the presentation (HTML/CSS/TS) and the data pipeline are fully decoupled.

## Developing

Requires [bun](https://bun.sh) and Python 3.

```sh
bun install            # one-time
bun run data           # regenerate public/data.json from the CSVs
bun run dev            # Vite dev server with HMR
bun run build          # data step + tsc type-check + production bundle → dist/
bun run preview        # serve the production build locally
```

`bun run build` regenerates `data.json`, type-checks, and bundles, so the CSVs are
the single source of truth. The standalone PNG charts are generated separately:

```sh
python plot_msfs24.py --by-epoch     # Tom's per-epoch PNGs
python make_megachart.py --averaged  # normalized megachart PNG
```

Data lives in `msfs24_data.csv` (Tom's, transcribed from chart screenshots),
`pcgh_msfs24.csv` (scraped from saved PCGH pages by `scrape_pcgh.py`) and
`computerbase_msfs24.csv` (scraped by `scrape_computerbase.py`).

## Deployment

Pushing to `main` triggers `.github/workflows/deploy.yml`, which runs the build
on CI and publishes `dist/` to GitHub Pages. The custom domain (`msfs.razortek.nl`)
is set by `public/CNAME`. **One-time setup:** in the repo's *Settings → Pages*, set
**Source** to **GitHub Actions** (instead of "Deploy from a branch").

## Data sources & attribution

Benchmark numbers are from **Tom's Hardware**, **PC Games Hardware (PCGH)** and
**ComputerBase** reviews, transcribed/scraped into the CSVs here. This repo
contains only those factual data points and our own generated charts — **not** the
original review articles, chart images, or saved pages (those are gitignored and
not republished). Not affiliated with or endorsed by any of these outlets.
