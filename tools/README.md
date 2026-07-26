# PCPP price capture

A [Violentmonkey](https://violentmonkey.github.io/) userscript that reads PCPartPicker
prices off pages you are already looking at and hands them back as CSV — so
`build_prices.csv` can be refreshed without transcribing forty numbers by hand, and in
more than one currency.

**Install:** open `pcpp-price-capture.user.js` raw in a browser with Violentmonkey (or
Tampermonkey) installed and confirm. A **€** button appears bottom-right on any
PCPartPicker page.

## The one thing worth knowing

**Let PCPartPicker do the choosing.** Half of a price CSV is not a product but a judgement
— *the cheapest decent AM4 board*, *a decent 650 W unit* — and no filter expresses it: 80+
Gold says nothing about whether a PSU is any good, and capacity says nothing about whether
an SSD is. PCPP's own **parametric selections** answer exactly that question, so the trick
is to let them, and to name each list for what its slots mean:

```
MSFS_LGA1700_DDR4_SINGLETOWER_ALLGPU
MSFS_LGA1700_DDR5_DUALTOWER_ENTRY_PSU
```

One block of config then maps every list at once, present and future:

```
LGA1700_DDR4 : Motherboard  = mb_lga1700_ddr4
LGA1700_DDR5 : Motherboard  = mb_lga1700_ddr5
SINGLETOWER  : CPU Cooler   = cooler_entry
DUALTOWER    : CPU Cooler   = cooler_mid
ENTRY_PSU    : Power Supply = psu_650
```

Add a list, name it to the convention, and **it maps itself** — no per-list setup. Each
list is one page load per region, and a list can carry every GPU besides, so `ALLGPU`
lists pay for themselves.

**CPUs are the exception.** A list holds one CPU, so they come from `/products/cpu/`
instead, where a single load carries a hundred rows and the watchlist names the ones you
track. That is the only category that needs it.

1. Build and save the lists. Add each as a target (**€ → Add this page**).
2. Add `/products/cpu/` with your filters as one more target.
3. Tick the regions on each. Write the list rules and the watchlist once.
4. **Run.** It walks them one at a time, in one tab, and stops on its own.
5. **Copy CSV** for one currency, or **Copy all currencies** for a wide table.

If a category filter spans more than one page of results, add `?page=2` as its own target.

## List rules

`TOKEN : Slot = csv row`. Any list whose name contains the token files that slot under
that name. Matched against both the target's label and the page's own title, so it does
not depend on PCPP's title markup.

The slot names are PCPP's own Component column: `Motherboard`, `CPU Cooler`,
`Power Supply`, `Case`, `Memory`, `Storage`, `Video Card`.

Verified against a real list, with three different names over the same page:

| List name | Rules that fire |
| --- | --- |
| `MSFS_LGA1700_DDR4_SINGLETOWER_ALLGPU` | `mb_lga1700_ddr4`, `cooler_entry`, `case` |
| `MSFS_LGA1700_DDR5_DUALTOWER_ENTRY_PSU` | `mb_lga1700_ddr5`, `cooler_mid`, `psu_650`, `case` |
| `MSFS_AM5_AIO_ALLGPU` | `mb_am5`, `cooler_aio`, `case` |

Tokens are plain substrings, so keep them distinctive — and if two rules end up claiming
one slot, or a slot holds more than one row, the script says so rather than picking one.
Slots that legitimately repeat (Memory, Storage, Video Card) belong in the watchlist,
matched by spec, not here.

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
# Memory. Match the MODULE COUNT, not the total: 1x16, 2x8 and 2x16 are three
# deliberate options (a budget build really does buy a single 16 GB stick), and a
# total-capacity pattern cannot tell 1x16 from 2x8 — they are both "16 GB". The \s?
# is because a list row writes "(2 x 16 GB)" and a category spec column writes
# "2 x 16GB". Two lookaheads because their order differs between those two shapes.
1x16GB DDR5-6000 = /^(?=.*DDR5-6000)(?=.*\b1 x 16\s?GB\b)/
2x8GB DDR5-6000  = /^(?=.*DDR5-6000)(?=.*\b2 x 8\s?GB\b)/
32GB DDR5-6000   = /^(?=.*DDR5-6000)(?=.*\b2 x 16\s?GB\b)/
1x16GB DDR4-3200 = /^(?=.*DDR4-3200)(?=.*\b1 x 16\s?GB\b)/
2x8GB DDR4-3200  = /^(?=.*DDR4-3200)(?=.*\b2 x 8\s?GB\b)/
32GB DDR4-3200   = /^(?=.*DDR4-3200)(?=.*\b2 x 16\s?GB\b)/
# Storage. Here the total IS the thing, so (?<!x ) keeps "2 TB" from matching a
# "2 x 2 TB" pair.
1TB NVMe = /^(?=.*(NVME|M\.2))(?=.*(?<!x )\b1 TB\b)/
2TB NVMe = /^(?=.*(NVME|M\.2))(?=.*(?<!x )\b2 TB\b)/
```

`32GB DDR5-6000` and `32GB DDR4-3200` keep their existing names because `build_specs.csv`
refers to them; the four `1x16` / `2x8` rows are new and would need adding to
`build_prices.csv` before they mean anything to the build table.

The PSU, board, case and cooler rows in `build_prices.csv` are tier bundles
(`psu_650`, `mb_am4`, …) rather than named products. They are not watchable by name —
see the next section, which is about exactly them.
</details>

## Tier bundles: the rows that are a filter, not a product

Half of `build_prices.csv` is not a product at all. `psu_650` means *the cheapest decent
650 W unit*, and `mb_am4` means *the cheapest decent AM4 board* — the answer changes every
month, so no name pattern can track it — and **no filter expresses it either**. 80+ Gold
and a wattage say nothing about whether a PSU is decent; capacity and interface say nothing
about whether an SSD is. Both are minefields where the answer is a curated set, not a spec
query. Three mechanisms, in the order you should reach for them.

### 1. A parametric in a named list

The main one, described at the top. A parametric row resolves to whichever board is
cheapest this week, so its product name is worthless as a key while its Component column
never moves — hence mapping by slot, via the list's name. Verified against a real list:
21 rows in, 20 captured, no clashes, the board by slot and all thirteen GPUs by name from
a single page.

A target can also carry its **own** mapping — a textarea on that target, same
`name = slot:Motherboard` syntax — which beats the list rules. For the one-off that fits
no convention.

### 2. Cheapest of an approved set

Where the set is yours rather than PCPP's, name the models and let the cheapest win.
Repeat the name; the patterns merge into one group:

```
psu_650 = Corsair RM650e
psu_650 = Seasonic Focus GX-650
psu_650 = MSI MAG A650BN
```

That is a parametric whose parameter is your own tier list rather than a spec sheet, and
it is the honest way to price a PSU or an SSD. It works from an ordinary category page —
one load, and the cheapest approved model in stock wins.

If the same model ends up approved for two entries, the script says so, even when neither
entry picked it today.

### 3. Cheapest row on a filtered page

For the cases where filters *are* enough — a case, say. Tick **"cheapest row on this page
is the answer"** on that target and give it a label; the watchlist is skipped there,
because the page is the query.

### Where PSUs bite

A parametric PSU inside a list sizes itself against every GPU in that list, so a list
holding a dozen cards asks for 3600 W and comes back `No Prices`. Keep PSUs in their own
small lists with no GPUs in them — `..._ENTRY_PSU`, `..._MID_PSU` — which is exactly what
the naming convention is for.

### So, the whole set

| `build_prices.csv` rows | Where they come from |
| --- | --- |
| CPUs | one `/products/cpu/` target + the watchlist — all fifteen in one load |
| GPUs | an `ALLGPU` list, or one `/products/video-card/` target |
| Memory, storage | a list slot, or a category page; spec patterns work on both |
| `mb_*` | one named parametric list per platform |
| `cooler_*` | the cooler token in each list's name |
| `psu_*` | a GPU-free `..._PSU` list, or an approved-set watchlist entry |
| `case` | any list carrying one, or "cheapest row" on a filtered page |

CPUs are the only category that cannot come from a list, because a list holds one.

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

## Currencies and regions

Captures are keyed by **region, not currency**. The Netherlands, Germany and France all
quote euros at different prices, so a EUR key would have each overwrite the last and
silently reduce three countries to whichever ran most recently. Export therefore offers one
entry per region (`nl EUR`, `de EUR`, `uk GBP`, …), and the wide CSV gives each its own
column. The big-jump guard compares within a region too — a German price is not a jump from
a Dutch one.

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
