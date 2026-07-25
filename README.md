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
tierlist_card_*.html   # the shareable tier-list cards (rendered to PNG)
make_tierlist_*.py     # tier-list data generator + PNG renderer
msfs24_*tierlist*      # the generated tier lists (text + PNG)
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

## Shareable tier lists

For posting in Discord and the like, the index is also boiled down to S/A/B/C/D/E
tier lists — as plain text (`msfs24_tierlist.txt`, `msfs24_gpu_tierlist.txt`, both
paste-ready in one message) and as PNG cards rendered from HTML+CSS in the site's
own style:

```sh
python make_tierlist_clusters.py     # gpu_data.json → cluster rows in the GPU card
python make_build_table.py           # the two build CSVs → rows in the build card
python make_tierlist_cards.py        # all cards → PNGs (needs Chrome + Pillow)
python make_tierlist_cards.py 4K     # just the variants matching "4K"
```

`msfs_index.py` holds the shared index maths — the Python counterpart of the two-way
log fit in `src/main.ts`, including the Intel arch prior and the clock-pair floors.
Both generators import it, so there is one implementation to keep in step with the
site. If the site's normalisation changes, change it here too or the cards will
quietly disagree with the ranking.

### Build table

`msfs24_build_specs.png` is a resolution × tier × vendor matrix of complete builds
with prices. Two CSVs drive it and they are the only files to edit:

- **`build_specs.csv`** — the picks, one row per build. GPU choices are measured
  against that row's resolution; CPU choices are judgement, since CPU reviews run at
  low resolution to isolate the chip and there is only one CPU ladder.
- **`build_prices.csv`** — `part,eur` plus `priced_on` and per-tier PSU/case/mobo
  bundles. **EUR, Netherlands, hand-maintained.** Refresh the figures and bump
  `priced_on`; the generator warns past 60 days.

`make_build_table.py` is deliberately noisy. A part with no price renders as a dash
rather than a wrong total, an unrecognised part name is reported as a likely typo, and
a socket/memory mismatch (DDR4 next to an AM5 chip) fails the check.

The PNGs are written to `public/cards/`, which Vite copies verbatim into `dist/`, so
the normal Pages deploy publishes them — no extra workflow step. They are then
linkable and embeddable straight from the site:

```
https://msfs.razortek.nl/cards/msfs24_cpu_tierlist.png
https://msfs.razortek.nl/cards/msfs24_cpu_tierlist_compact.png
https://msfs.razortek.nl/cards/msfs24_gpu_tierlist_1080p.png          (+ _compact)
https://msfs.razortek.nl/cards/msfs24_gpu_tierlist.png                (1440p, + _compact)
https://msfs.razortek.nl/cards/msfs24_gpu_tierlist_4k.png             (+ _compact)
```

They are committed rather than rendered on CI, since the render needs a browser — so
after editing a card, re-run `make_tierlist_cards.py` and commit the PNGs.

Each card renders in two variants. The **detail** one carries the full prose and is
meant to be opened; the **compact** one is built for Discord's inline preview, which
is roughly 550×400 — so a tall portrait image gets height-limited and shown ~290px
wide, where 13px text lands at about 4px on screen. The compact cards stay under
0.727 aspect to be width-limited instead, and drop the prose for larger type.
`make_tierlist_cards.py` measures each card's height instead of hardcoding it, and
warns if a compact variant creeps back over the aspect limit.

The GPU card covers **1080p / 1440p / 4K** (green / blue / red), each normalised on
its own — the numbers never compare across resolutions. Tier bands are a fixed share
of the fastest card and identical on all three, which is the point: 1080p puts four
cards in S, 4K puts one there and eleven in E.

The CPU tier list groups by generation and V-Cache rather than listing every SKU; the
GPU one merges cards within 5 index points into a single row, since most GPUs here
come from one test pass and small gaps are not real differences.

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
