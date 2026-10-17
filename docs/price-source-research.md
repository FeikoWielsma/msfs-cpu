# Price refresh source options

Checked 2026-10-17 against primary sources. This is an engineering recommendation based on published access policies, not a legal determination or a guarantee against account/IP restrictions.

## Recommendation

Automate the local work first: a refresh checklist, imports of intentionally exported data, exact part matching, validation, reviewable price changes, and regeneration. Keep external retrieval human initiated until a source explicitly supports the intended access. A delay between requests reduces load; it does not grant permission.

For eventual unattended updates, investigate an approved merchant/affiliate feed rather than a crawler. Do not make Tweakers scraping the default route. Do not treat undocumented endpoints, browser cookies, or a working userscript as evidence of permission.

## PCPartPicker

- The [current robots.txt](https://pcpartpicker.com/robots.txt) disallows `/api/` and `/list/markup/`, includes a 60-second crawl delay for the general agent rule, and separately disallows several named automation agents. These are crawler directives, not an API contract or permission to republish prices.
- Fetching [the terms page](https://pcpartpicker.com/tos/) returned HTTP 403 during this research. The alternative `/terms-of-service/` URL was also unavailable. Therefore the current terms have **not** been verified; do not state that any particular script or request cadence is allowed.
- No current public, supported API documentation was established from accessible first-party material. This is an uncertainty, not proof that no API or commercial agreement exists.
- A promising near-term workflow is importing a user-requested export from the site's own sharing/export UI, if that UI is available for the user's list. Verify the actual current export controls and permitted reuse before depending on this. No first-party export documentation was accessible during this check, so format availability is not established here.

## Tweakers Pricewatch

- Its [copyright notice](https://tweakers.net/info/auteursrecht/) expressly reserves content/database rights, limits ordinary use to personal, noncommercial use, and prohibits automated screen scraping/text and data mining subject to a stated research exception. This makes an unattended Pricewatch collector a poor fit without explicit permission.
- Its [Pricewatch FAQ](https://tweakers.net/info/faq/pricewatch/) says shops provide product feeds, which Tweakers checks multiple times hourly when changed. Price alerts are an offered feature. The FAQ describes inbound shop feeds; it does **not** document an outbound public price API.
- The [Pricewatch Manager terms](https://tweakers.net/info/pricewatch/) also restrict copying and publication beyond personal use without written permission. These terms address merchant customers, so they should not be presented as the sole terms governing an ordinary visitor.
- No supported outbound Pricewatch API was established. Publicly reachable AJAX endpoints are not evidence of authorized external automation. A user-triggered DOM extractor still performs automated extraction; running it in a logged-in browser does not resolve the policy concern.

## Direct retailer observation: Megekko

Its [scraper/crawler policy](https://www.megekko.nl/info/scrapers), checked during
the live refresh on 2026-10-17, asks monitors to make at most one automated request
per hour to avoid automatic blocking. Do not add it to the PCPP runner or assume
PCPP's one-minute cadence applies to it. The local importer accepts documented
NL retailer quotes; it does not fetch those pages. This session read two exact CPU
listings and checked a GPU category before discovering the linked policy; further
retailer collection stopped once it was read. Preserve the actual observation
dates and source URLs rather than scheduling repeated page checks.

## Official feed alternative: Awin

- Awin's [publisher feed overview](https://help.awin.com/developers/docs/product-feed-publisher-guide-intro) describes feeds containing product details, prices, discounts and shipping information, expressly intended for publisher uses including price comparisons.
- Its [feed-list download documentation](https://help.awin.com/developers/docs/product-feed-list-download) explicitly supports scripted downloads, API-key access, feed URLs and update timestamps. Accessible feeds come from joined advertisers or advertisers allowing promotion before joining. Polling the list and downloading only changed feeds is documented practice.
- This is a credible access mechanism, **not a verified supplier choice for this project**. Publisher eligibility, acceptance, suitable Netherlands merchants, exact SKU coverage, and advertiser-specific usage/retention obligations remain to be checked. No account was created or advertiser contacted.

## Suggested implementation boundary

Use one local importer contract for human-entered quotes, verified user exports, and approved feeds. Store exact identity, region/currency, shop/source URL, price, stock condition, shipping treatment, and observation timestamp. Reject ambiguous matches and unexpected currency/region changes; preview differences before applying. Preserve old observations when a refresh fails and display them as stale instead of advancing their dates.

Start with the refresh/import/review tooling already possible offline. Add a feed adapter only after access and relevant merchant coverage have been established. If a permitted HTTP adapter is later added, honor its documented limits and `Retry-After`, cache unchanged results, and stop on access denials rather than attempting to bypass them. These operational safeguards complement permission; they do not replace it.
