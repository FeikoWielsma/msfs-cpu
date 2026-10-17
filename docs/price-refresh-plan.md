# A smaller price-refresh job

Local workflow implemented after this proposal: run `python tools/refresh_prices.py`
or `bun run prices`. See [usage](../tools/README.md#local-refresh-command). It uses the
existing browser userscript and a dated JSON handoff; no feed adapter was added.

## Goal

The user's main difficulty is collecting the prices from the sites, rather than merging the resulting files. Reduce collection effort and repeat setup first. This is a proposed workflow, not an implemented collector. Source-access research is in [price-source-research.md](price-source-research.md).

## What the repo currently has

- `build_prices.csv`: 74 parts, dated 2026-07-26 (83 days old on 2026-10-17).
- `build_prices_regions.csv`: 59 parts across seven regions; 15 canonical parts are absent from this export.
- `tools/pcpp-price-capture.user.js` already supports saved targets, category watchlists, parametric lists, sequential navigation and stopping on challenges. Building another crawler would duplicate it.
- Captures persist between runs. The missing-price indicator checks existence, not freshness. Single-region export labels the export with today's date even if observations are old. Wide export collapses region observation dates into one newest date per part. Neither export is a reliable refresh manifest.
- `make_build_table.py` already regenerates totals, build JSON and card HTML. `build_specs.csv` contains curated choices that a price refresh alone does not reconsider. The browser's budget generator searches the priced catalogue independently.

## Recommended collection strategy

1. Start with Netherlands prices; make additional regions independent refresh jobs. Seven regions multiply visits and review work. Keep their real dates visible rather than suggesting that an NL refresh refreshed everything.
2. Investigate one authorized feed for a small set of NL retailers before investing in another web collector. Awin documents publisher feed downloads, but access, retailer participation and component coverage are not yet established. Compare its coverage against the 74 existing keys. A feed's minimum is only the lowest price among participating covered shops, not a market-wide minimum.
3. For gaps, keep a persistent collection checklist with direct source/list links and exact model or approved-model groups. Where a source permits it, favor an explicit export covering many parts over separate product-page visits. PCPartPicker's current export and reuse permission still need verification. Do not extend automated navigation on the assumption that slower means permitted.
4. Keep human judgement for approved PSU, board, storage and cooler models. Match feed rows by stable SKU/EAN or explicit mappings; do not select an arbitrary cheapest product with roughly matching specifications. Keep shipping, VAT, stock and marketplace treatment explicit.

## The intended recurring workflow

- Run a local refresh command: reuse authorized feed downloads when unchanged, ingest changed feeds, and show only unresolved/stale items that need a human visit.
- Review one report: price changes, missing stock, ambiguous identities, coverage and before/after build totals. Flag large changes for review; never accept an ambiguous match just because its price looks plausible.
- Apply accepted observations to both CSV consumers from one dataset, regenerate outputs, and inspect the curated builds for better-value alternatives at comparable totals. Suggest swaps using the existing budget-generator rules; keep curated choices reviewable.

Store observation dates per part and region, source/product URL, stock, identity and price basis. A failed refresh must retain the old observation and its date, and mark it stale. Updating a few parts must never advance one global freshness stamp for all parts. Raw capture should preserve provenance and warnings rather than relying on the existing lossy wide CSV.

## First implementation slice

Check authorized feed eligibility and real NL hardware coverage, then build one adapter against an actual sample. Measure how many of the 74 keys it resolves accurately. Persist mappings so future refreshes reuse the work. Add a capture/import manifest and unresolved-item checklist around that adapter; preserve manual fallback for uncovered parts.

If no suitable authorized feed is available, keep collection user driven and prioritize persistent lists plus verified built-in exports. This can reduce repeated work, but it is not unattended updating. Scheduled local freshness checks can prompt a refresh without contacting any price site.

No fresh prices were collected, no source accounts were created or contacted, and no production data or collector behavior was changed during this investigation.
