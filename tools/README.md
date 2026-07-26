# PCPP price capture

A [Violentmonkey](https://violentmonkey.github.io/) userscript that reads PCPartPicker
prices off pages you are already looking at and hands them back as CSV — so
`build_prices.csv` can be refreshed without transcribing forty numbers by hand, and in
more than one currency.

**Install:** open `pcpp-price-capture.user.js` raw in a browser with Violentmonkey (or
Tampermonkey) installed and confirm. A **€** button appears bottom-right on any
PCPartPicker page.

## The one thing worth knowing

**Use one filtered category page per part type, not part lists.** A PCPartPicker list holds
only one CPU, one motherboard, one case and one PSU, so it cannot hold fifteen chips — but
`/products/cpu/` with your filters returns a hundred rows in a single load. Eight category
pages (CPU, cooler, motherboard, memory, storage, video card, PSU, case) therefore cover
every part you track, and the same paths serve every regional subdomain:

> **8 pages × the regions you want** — about 24 loads for three currencies — rather than one
> page per part per region, which would be hundreds.

1. Open `/products/cpu/`, set your filters, and get the URL you want to keep.
2. Hit **€ → Add this page**, give it a label.
3. Tick the regions for that target. Repeat for the other categories.
4. Fill in the **watchlist** (below) so a hundred rows come back as your forty parts.
5. **Run.** It walks them one at a time, in one tab, and stops on its own.
6. **Copy CSV** for one currency, or **Copy all currencies** for a wide table.

If a filter spans more than one page of results, add `?page=2` as its own target. A saved
part list works as a target too, and is the better shape when you want the exact parts of
one specific build rather than a category.

## The watchlist

A category page gives you a hundred rows; your CSV wants forty, under its own names. The
watchlist is that mapping, and without it the export is unusable noise.

```
Ryzen 7 9800X3D                          name is also the pattern
RX 9070 XT = Radeon RX 9070 XT           different pattern
RTX 5070 = /RTX 5070(?! Ti)/             a regex, where a substring would be ambiguous
32GB DDR5-6000 = /\b32 GB\b.*DDR5-6000/  matches the spec columns too
```

Patterns match against the name **and the spec columns**, which is what makes half of a real
watchlist possible at all: PCPP's name for a card is "GeForce RTX 5060 Ti Asus DUAL OC" with
`16 GB` in a column of its own, and a memory kit is "G.Skill Flare X5" with `32 GB` and
`DDR5-6000` beside it.

**Mind the loose pattern.** `RX 9070` matches an RX 9070 XT; `RTX 5060` matches a 5060 Ti;
`Ryzen 5 5600` matches a 5600X. Recording the faster card's price under the slower card's
name is the exact failure this tool exists to prevent, so use a lookahead.

The script checks for it rather than trusting you. A loose entry usually *looks* fine —
`RX 9070` picks the cheapest of its matches, and the plain card is normally cheaper than the
XT, so the right price lands by luck; on a page where the XT is discounted it would not, and
nothing would appear wrong. So any entry whose pattern reaches **another entry's product** is
flagged even when today's pick was correct, with a suggested tightening:

```
"RX 9070" also matches RX 9070 XT's product ("Radeon RX 9070 XT ASRock Challenger")
  — tighten it, e.g. /RX 9070(?! XT)/
```

The panel shows which watched parts have **no price yet in the current region**, which is
how you know a run actually finished.

<details>
<summary>Ready-to-paste watchlist for this repo's <code>build_prices.csv</code></summary>

Checked against saved snapshots of every category: 37 of 44 resolve to the right product,
with no clashes. The seven that do not are absent from PCPP or from those filters — the
AliExpress-only 5500X3D, and last-generation cards the snapshots filtered out.

```
# CPUs
Ryzen 7 9800X3D
Ryzen 7 7800X3D
Ryzen 7 5800X3D
Ryzen 5 9600X = /Ryzen 5 9600X(?!3D)/
Ryzen 5 7600X = /Ryzen 5 7600X(?!3D)/
Ryzen 5 7500X3D
Ryzen 5 7500F
Ryzen 5 5600 = /Ryzen 5 5600(?!X|G)/
Ryzen 5 5600X = /Ryzen 5 5600X(?!3D|T)/
Ryzen 5 5500X3D
Core Ultra 9 285K = /Core Ultra 9 285K(?!F)/
Core Ultra 7 270K Plus
Core Ultra 5 250K Plus
Core i7-14700K = /Core i7-14700K(?!F|S)/
Core i5-14600K = /Core i5-14600K(?!F)/
Core i5-12400F
Core i5-12600KF
# GPUs — a base model needs a lookahead or it matches its own faster sibling
RX 9070 XT = /RX 9070 XT/
RX 9070 = /RX 9070(?! XT| GRE)/
RX 9070 GRE
RX 9060 XT 16GB = /RX 9060 XT.*\b16 GB/
RX 9060 XT 8GB = /RX 9060 XT.*\b8 GB/
RX 7600 = /RX 7600(?! XT)/
RX 7600 XT
RX 7700 XT
RX 7800 XT
RX 7900 XT = /RX 7900 XT(?!X)/
RX 7900 XTX
RTX 5090
RTX 5080 = /RTX 5080(?! Ti| Super)/
RTX 5070 Ti = /RTX 5070 Ti/
RTX 5070 = /RTX 5070(?! Ti)/
RTX 5060 Ti 16GB = /RTX 5060 Ti.*\b16 GB/
RTX 5060 Ti 8GB = /RTX 5060 Ti.*\b8 GB/
RTX 5060 = /RTX 5060(?! Ti)/
RTX 5050
RTX 4090
RTX 4080 = /RTX 4080(?! Super)/
Arc B580
Arc B570
# Memory and storage. Two lookaheads rather than one pattern, because the order
# differs by page shape: a list row reads "32 GB (2 x 16 GB) DDR4-3200", a category
# row puts capacity and speed in separate spec columns. The (?<!x ) is load-bearing —
# without it "32 GB" also matches the "2 x 32 GB" of a 64 GB kit.
32GB DDR5-6000 = /^(?=.*DDR5-6000)(?=.*(?<!x )\b32 GB\b)/
32GB DDR4-3200 = /^(?=.*DDR4-3200)(?=.*(?<!x )\b32 GB\b)/
1TB NVMe = /^(?=.*(NVME|M\.2))(?=.*(?<!x )\b1 TB\b)/
2TB NVMe = /^(?=.*(NVME|M\.2))(?=.*(?<!x )\b2 TB\b)/
```

The PSU, board, case and cooler rows in `build_prices.csv` are tier bundles
(`psu_650`, `mb_am4`, …) rather than named products. They are not watchable by name —
see the next section, which is about exactly them.
</details>

## Tier bundles: the rows that are a filter, not a product

Half of `build_prices.csv` is not a product at all. `psu_650` means *the cheapest decent
650 W unit*, and `mb_am4` means *the cheapest decent AM4 board* — the answer changes every
month, so no name pattern can track it. Two mechanisms cover this, and which you want
depends on whether PCPP can express "decent" as a filter.

### Cheapest row on a filtered page

Set the filters until the page contains only units you would actually buy, then tick
**"cheapest row on this page is the answer"** on that target and give it a label. The
watchlist is skipped for that target — the page *is* the query.

This is the answer for **PSUs**, and it sidesteps the parametric problem entirely: a
parametric PSU inside a list sizes itself against every GPU in that list, so a list holding
a dozen cards asks for 3600 W and comes back `No Prices`. A filtered category page has no
such coupling. Five targets — 650 / 750 basic / 750 / 850 / 1000, each with its efficiency
and form-factor filters set — give five tier prices per region.

The same shape works for `case` and the cooler tiers.

### Parametric part lists, mapped by slot

Where "decent" is easier to say as a PCPP parametric than as a filter, put it in a list and
map the row by the **slot** it occupies rather than by what it resolved to:

```
mb_lga1700_ddr4 = slot:Motherboard
case            = slot:Case
cooler_entry    = slot:CPU Cooler
```

A parametric row resolves to whichever board is cheapest this week, so its product name is
worthless as a key while its Component column never moves. Target mappings apply **only on
that target's pages** and take precedence over the global watchlist, so one list can yield
both its own board (by slot) and every GPU on it (by name) in a single load — verified
against a real "biglist": 21 rows in, 20 captured, no clashes.

`slot:` needs the slot to hold exactly one row, which is true for Motherboard, Case, CPU
Cooler and PSU. Memory, Storage and Video Card can repeat, so match those by spec pattern
instead; if a `slot:` mapping is ambiguous the script says so rather than picking one.

### So, the whole set

| `build_prices.csv` rows | Where they come from |
| --- | --- |
| CPUs | one `/products/cpu/` target + the watchlist — all fifteen in one load |
| GPUs | one `/products/video-card/` target, or a list holding them all |
| Memory, storage | either; spec patterns work on both page shapes |
| `mb_*` | one parametric list per platform, mapped `slot:Motherboard` |
| `psu_*` | one filtered PSU page per tier, "cheapest row" |
| `case`, `cooler_*` | either |

CPUs need no list at all — a list holds one, and the category page holds a hundred.

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
