# Netherlands price refresh — 2026-10-17

Refreshed 62 of 74 price keys, including all 36 distinct components required by
the 18 curated builds. Build components are dated 2026-10-17. Other countries'
observations were not refreshed or converted from EUR.

Luna collected and imported the first 41 keys before its usage quota was exhausted.
The parent continued from its saved observations and completed the build dependencies.
Committed provenance is in `build_price_observations.json`: actual observation times,
source and product URLs, observed model, currency, stock and selection rationale.
Raw browser captures and exact before-update backups remain local in `.price-refresh/`.

## Source and selection checks

- PCPartPicker NL rendered tables supplied most observations. Filtered, price-sorted
  GPU results corrected an initial popularity-page RTX 5080 quote from €2,999 to
  €1,699. Do not treat the first unfiltered page as a market-wide minimum.
- The RTX 5090's unusually large increase was reviewed: Luna observed an in-stock
  sorted-class minimum of €7,858; a direct Megekko category check showed available
  cards at €8,799 and €8,899. The lower, verified PCPP observation was retained.
- Direct Megekko product pages supplied the [270K Plus at €323.90](https://www.megekko.nl/product/15748/311161/Socket-1851-Processoren/Intel-Core-Ultra-7-270K-Plus)
  and [5800X3D Anniversary Edition at €359](https://www.megekko.nl/product/4278/10432/Socket-AM4-Processoren/AMD-Ryzen-7-5800X3D-10th-Anniversary-Edition-processor).
  Visible prices, product identity and own-stock availability were checked in the browser.
- Generic board, PSU, cooler, case and storage keys now have concrete recorded models.
  They are representative approved selections, not a claim to have searched every shop.
  The two 750W keys use the same MSI A750GL; the two LGA1700 DDR5 board keys use the
  same MSI B760 Gaming Plus WiFi. Stock clocks are assumed. The LGA1851 selection
  needs an appropriate BIOS for the chosen CPU, as with any existing-board/Plus pairing.
- The case observation uses a LANCOOL 216 with included fans. Its manufacturer lists
  [392mm GPU space and water-cooling positioning](https://lian-li.com/product/lancool-216/).
  Check the exact purchased components and radiator arrangement before ordering.
- No price-source challenge was bypassed. Megekko's linked [monitoring policy](https://www.megekko.nl/info/scrapers)
  was discovered after the focused checks; it requests at most one automated request
  per hour. No further retailer price requests were made after reading it. It is not
  included in the automated PCPP target runner.

## Unrefreshed references

Core Ultra 5 250K Plus, Ryzen 5 5500X3D, Ryzen 5 7500X3D, Ryzen 7 7700X3D,
RX 9070 GRE, RX 7600 XT, RX 7700 XT, RX 7800 XT, RX 7900 XT, RX 7900 XTX,
RTX 4080 and RTX 4090 retain their original dates. Their stale NL observations are
excluded from budget-generator choices and from current-value comparisons. The
reference table keeps them with dates; the global oldest-observation stamp is not
advanced to pretend they were checked today.

## Repeatability and validation

`bun run prices` now loads `tools/price-collection.json`: 38 saved category/model
targets, native category queries, exact group product identities and two manual
retailer fallbacks. Existing browser custom configuration is retained. A runnable
local collection config can override the repo default. Same-page fixed-key reads
reuse the loaded page; page/query requests retain the one-minute floor and stop
on challenges. Source permissions and retailer-specific policies remain separate.

Validation: eight Python import/regeneration/rollback/config tests, JavaScript
setup/matching/export tests, an offline browser test of native query replay and
shared-page aliases, TypeScript and the production Vite build. The build PNG was
re-rendered and visually checked; the renderer now expands its height probe instead
of silently clipping a tall card.
