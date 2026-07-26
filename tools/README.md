# PCPP price capture

A [Violentmonkey](https://violentmonkey.github.io/) userscript that reads PCPartPicker
prices off pages you are already looking at and hands them back as CSV — so
`build_prices.csv` can be refreshed without transcribing forty numbers by hand, and in
more than one currency.

**Install:** open `pcpp-price-capture.user.js` raw in a browser with Violentmonkey (or
Tampermonkey) installed and confirm. A **€** button appears bottom-right on any
PCPartPicker page.

## The one thing worth knowing

**Make a single saved part list containing every part you track.** The same `/list/xxxxx`
path works on every regional subdomain, so a full multi-currency refresh is *one page load
per region* — around twenty — instead of one per part per region, which would be hundreds.
Everything else here is built around that.

1. Build the list on PCPartPicker and save it. You want the `/list/xxxxx` URL.
2. Open it, hit **€ → Add this page**, give it a label.
3. Tick the regions you want on that target.
4. **Run.** It walks them one at a time, in one tab, and stops on its own.
5. **Copy CSV** for one currency, or **Copy all currencies** for a wide table.

A filtered product page (`/products/video-card/` with your filters in the URL) works as a
target too, and captures every row it lists.

## Being a good guest

This is a reading aid, not a crawler — it scrapes what your browser already loaded, at a
pace a person could type at. It walks **one tab, sequentially**, with a randomised delay
(floor six seconds, twelve by default), and it **stops** on anything that looks like a bot
check rather than trying to satisfy it. There is deliberately no user-agent fiddling, no
proxy rotation and no parallel fetching. If you hit a challenge, solve it yourself and
press Run again.

Keep the volume low and keep it personal. The data is PCPP's; scraping it wholesale would
be both rude and against their terms. One list, a handful of regions, once a month is the
intended shape.

## What it will not quietly get wrong

The failure this is built to avoid is a wrong number entering the CSV without anyone
noticing:

- **Out-of-stock listings** still print a price on PCPP. It is not a price you can pay, so
  it is captured, marked **!**, and left out of exports — with the header naming what was
  dropped.
- **Marketplace outliers.** A flagship card that is out of stock everywhere attracts
  listings at ten times its real price. Nothing in the page marks those as nonsense, so the
  check is the one you already have: a price that has moved more than 3× since the last
  capture is marked **?**, kept, and left out of exports until you have looked at it.
- **Same-name products.** A video-card table puts "Gigabyte GAMING OC" in the name cell and
  the actual chipset in its own column, and a cooler page lists the same model in two
  colours. Since the name is the storage key, a clash would mean one part silently
  reporting another's price — so rows are keyed on the product URL, and spec columns are
  folded into the name (product id as a last resort) only for the rows that actually
  clash. On real pages this was 12–19 collisions each; it is now none.
- **Other extensions' badges.** The name cell is a popular thing to decorate — the PSU
  tier-list userscript hangs a "Tier B+" badge inside it, which read as part of the product
  name (`ASRock PRO-750GTier B+`) until injected badges were stripped. If you write your
  own PCPP extension, add its class to `nameText()`.
- Both exclusions are overridable with one checkbox, and exported rows are then tagged
  `pcpp:us:oos` / `pcpp:us:check` rather than passing as ordinary prices.

## When PCPP changes its markup

The script knows PCPP's real classes (`tr.tr__product`, `td.td__name`, `td.td__price`,
`td.td__availability`, and the different row shape a part list uses) and falls back to a
structural read — the rightmost cell in a row that parses as money — when it does not find
them. If both miss, **Teach** lets you click the price and then the name of any row and
stores a selector for that page shape.

`__pcppCapture.rows()` in the console shows exactly what the scraper currently sees, which
is the fastest way to tell a markup change from an empty page.

## Currencies

The regional subdomain decides the currency (`nl.` → EUR, `uk.` → GBP, bare → USD), and any
symbol or ISO code in the price overrides it. The number parser handles both conventions:
the last separator with one or two digits behind it is the decimal point, so `€1.234,56`
and `$1,234.56` both read as 1234.56, while a lone `1.234` reads as 1234.

## Development notes

The saved PCPartPicker pages used to develop this live in `pcpp/`, which is gitignored —
their pages, not ours, the same rule the repo applies to the review sources. Note that a
browser-saved product table renders **empty** when reopened, because PCPP's own JavaScript
re-populates it from data a saved copy does not have; part-list pages survive saving
intact. To test against a saved product table, inject its HTML with `innerHTML` (scripts
inserted that way never run, so the markup stays as saved) rather than opening the file.
Otherwise test against the live site, one load at a time.

The scraper has been checked against saved snapshots of every part category — CPU, cooler,
motherboard, memory, storage, case, PSU, video card and a part list — plus the live product
table.
