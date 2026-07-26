"""Generate the build-table card data from build_specs.csv + build_prices.csv.

    python make_build_table.py

Writes two things from the same pass, so the PNG card and the site page can never
disagree about a price:

  - the block between the BUILDS markers in tierlist_card_build.html (the card is
    rendered from file:// by headless Chrome, so it cannot fetch anything)
  - public/builds.json, which /specs fetches at runtime like the rest of the site

Edit the two CSVs, not either output.

Deliberately noisy: a missing price, an unknown part name or a socket/memory mismatch
prints a warning and (for prices) renders a dash rather than a plausible-looking wrong
number. A build table that is quietly wrong about money is worse than one that admits
it does not know.
"""
import csv, datetime, json, os, re, sys

from msfs_index import (cpu_index, gpu_index, CPU_SPECS, CPU_VENDOR, GPU_SPECS,
                        GPU_VENDOR, coverage)

HERE = os.path.dirname(os.path.abspath(__file__))
CARD = os.path.join(HERE, 'tierlist_card_build.html')
SPECS_CSV = os.path.join(HERE, 'build_specs.csv')
PRICES_CSV = os.path.join(HERE, 'build_prices.csv')
REGIONS_CSV = os.path.join(HERE, 'build_prices_regions.csv')
# public/ is copied verbatim into dist/, so writing here publishes it at /builds.json
JSON_OUT = os.path.join(HERE, 'public', 'builds.json')
BEGIN, END = '// <<< BUILDS', '// >>> BUILDS'

RES = ['1080p', '1440p', '4K']

# Cards with no MSFS benchmark coverage, placed on our index by interpolating
# TechPowerUp's relative-performance aggregate between two cards we DO measure. Derived,
# not measured — the card marks these chips with a ° and says so in the footer.
#
#   RX 9070 GRE: TPU has it at 100 with the RX 7800 XT at 92 and the RX 9070 at 117
#   (1080p) / 118 (1440p). Interpolating that 0.32 / 0.31 fraction onto our own figures
#   for those two anchors -- 67 to 90 at 1080p, 54 to 72 at 1440p -- lands it here.
#   No 4K figure: TPU's chart does not cover it, and a 12 GB card at 4K in this game
#   would break the aggregate anyway.
DERIVED_GPU = {
    'RX 9070 GRE': {'1080p': 74, '1440p': 60},
}

# Parts that are the same silicon under another name, so index and socket resolve
# through the alias. Not an estimate and not an interpolation — an equivalence — so
# these carry no ° marker. The KF is a 12600K with the iGPU fused off; the arch prior
# in msfs_index.py already treats the K and KF bins as equal.
CPU_ALIAS = {
    'Core i5-12600KF': 'Core i5-12600K',
    # Same silicon with the iGPU fused off, and the cheapest chip on the whole card that
    # still carries a measured index — the reason the generator can reach a low budget.
    'Core i3-14100F': 'Core i3-14100',
}

# LGA1700 chips are indexed on DDR5, so pairing one with DDR4 has to be discounted or
# the card overstates it. These factors are measured, not guessed: Tom's 5800X3D
# re-review ran the same three chips on DDR5 and on DDR4-3200, and the raw cross-source
# fit puts DDR5 ahead by 6.8% (12700K), 12.7% (13700K) and 11.3% (14700K). Inverted,
# DDR4 lands at these fractions of the DDR5 figure. Applied per Intel generation, and
# the resulting chip is marked derived.
# AM4 needs no factor: those parts were only ever tested on DDR4, so their index is
# already the DDR4 number.
DDR4_FACTOR = {12: 0.936, 13: 0.887, 14: 0.898}

# VRAM for cards that are not in gpu_data.json, so they still get a memory tag.
VRAM_EXTRA = {'RX 9070 GRE': 12}

# ---- the rest of the build, composed rather than carried as one bundle figure -------
# PSU sized by the card it has to feed. Anything not listed takes the 650W unit.
PSU = {
    'RTX 5090': 'psu_1000',
    'RTX 5080': 'psu_850', 'RTX 5070 Ti': 'psu_850',
    'RX 9070 XT': 'psu_850', 'RX 7900 XT': 'psu_850',
    'RTX 5070': 'psu_750a', 'RX 9070': 'psu_750a',
    'RTX 5060 Ti 16GB': 'psu_750b', 'RTX 5060 Ti 8GB': 'psu_750b',
    'RX 9070 GRE': 'psu_750b',
}
PSU_DEFAULT = 'psu_650'

# Chips that want a better board than the cheapest B-series: flagships, and K-series
# parts whose VRM demands are more than a bargain board is happy with.
MB_GREAT = {'Ryzen 7 9800X3D', 'Core i5-14600K'}

# 360mm AIO territory (the hot Intel parts) and dual-tower territory. Everything else
# takes the 120mm single tower.
COOLER_AIO = {'Core Ultra 9 285K', 'Core Ultra 7 270K Plus', 'Core i7-14700K'}
COOLER_MID = {'Ryzen 7 9800X3D', 'Ryzen 7 7800X3D', 'Ryzen 7 5800X3D',
              'Core i5-12600KF', 'Core i5-14600K', 'Ryzen 5 9600X'}


# Human names for the composed parts. The card only ever shows their combined cost, but
# /specs itemises a build, and "psu_750a" is not a thing anyone recognises. A composed
# part with no entry here is warned about rather than shown by its key.
PART_LABEL = {
    'psu_650': '650 W power supply',
    'psu_750a': '750 W power supply',
    'psu_750b': '750 W power supply',
    'psu_850': '850 W power supply',
    'psu_1000': '1000 W power supply',
    'mb_am4': 'AM4 motherboard',
    'mb_am5': 'AM5 motherboard',
    'mb_am5_great': 'AM5 motherboard, upper tier',
    'mb_lga1700_ddr4': 'LGA1700 motherboard, DDR4',
    'mb_lga1700_ddr4_great': 'LGA1700 motherboard, DDR4, upper tier',
    'mb_lga1700_ddr5': 'LGA1700 motherboard, DDR5',
    'mb_lga1700_ddr5_great': 'LGA1700 motherboard, DDR5, upper tier',
    'mb_lga1851': 'LGA1851 motherboard',
    'cooler_entry': '120 mm tower cooler',
    'cooler_mid': 'Dual-tower air cooler',
    'cooler_aio': '360 mm AIO',
    'case': 'Case',
}


def psu_for(gpu):
    return PSU.get(gpu, PSU_DEFAULT)


def mb_for(cpu, socket, ram):
    great = '_great' if cpu in MB_GREAT else ''
    if socket == 'AM4':
        return 'mb_am4'                     # no great tier: B550 is the sensible ceiling
    if socket == 'AM5':
        return 'mb_am5' + great
    if socket == 'LGA1851':
        return 'mb_lga1851'
    if socket == 'LGA1700':
        return 'mb_lga1700_ddr4' + great if 'DDR4' in ram else 'mb_lga1700_ddr5' + great
    return None


def cooler_for(cpu):
    return ('cooler_aio' if cpu in COOLER_AIO else
            'cooler_mid' if cpu in COOLER_MID else 'cooler_entry')

# Priced, plausible, but beaten on value by something already in the matrix. Listed
# under it because "why isn't X in here?" is the question that always follows.
# (part, reason) — index shown is at 1440p.
# (part, what it loses to, reason). {d} is the price gap in EUR and {p} the index gap as
# a percentage, both COMPUTED — this strip exists to justify a price comparison, so a
# hand-typed "€73" in it goes wrong the moment either price moves, which is precisely
# when someone is reading the card to decide what to buy.
NOT_PICKED = [
    ('RX 9070 GRE', 'RX 9070', 'an RX 9070 is +{p}% for €{d} more'),
    ('RX 7900 XT', 'RX 9070 XT', 'a 9070 XT beats it for €{d} less'),
    ('RX 9060 XT 8GB', 'RX 9060 XT 16GB', 'the 16GB is +{p}% for €{d}'),
    ('RTX 5060 Ti 8GB', 'RTX 5060 Ti 16GB', 'the 16GB twin is +{p}% for €{d}'),
    ('Arc B580', None, 'fine at 1080p, out of its depth above'),
]
TIERS = ['entry', 'mid', 'high']
VENDORS = ['amd', 'nv']
STALE_DAYS = 60

# ---- the /specs generator ----------------------------------------------------------
# The page also ships a catalogue of every part the budget generator may choose from,
# with the platform rules above already resolved per part. The search itself runs in
# the browser; these are its ingredients.

# How much of a build's score each side carries, per resolution — the CPU's share, the
# GPU takes the rest.
#
# JUDGEMENT, NOT MEASUREMENT, and the generator says so on the page. The two indices are
# separate fits normalised to their own leaders, so a CPU 100 is not "the same amount of
# performance" as a GPU 100 and no arithmetic across them is a frame rate. What these
# weights encode is only which side decides the outcome at that resolution, which is the
# one thing the data does say clearly: at 1080p the GPU field compresses to a 5.5x spread
# and the CPU becomes the limit, while at 4K it opens to 17x and the GPU decides nearly
# everything.
BLEND_CPU = {'1080p': 0.55, '1440p': 0.35, '4K': 0.20}

# Priced for reference but never offered by the generator: the group build_prices.csv
# marks as no longer reasonably available or priced far above their index. They are all
# beaten on value by something current anyway — the exclusion only stops a big budget
# surfacing one on raw score alone. The 9070 GRE is NOT here: it is current and buyable,
# it simply has no MSFS coverage, so it carries a derived index and a ° like anywhere
# else on the page.
GEN_EXCLUDE = {
    'RX 7600 XT': 'superseded, and beaten by a 9060 XT 16GB for less',
    'RX 7700 XT': 'superseded, and beaten by a 9060 XT 16GB for less',
    'RX 7800 XT': 'superseded, and priced far above its index',
    'RX 7900 XT': 'superseded, and beaten by an RX 9070 for less',
    'RX 7900 XTX': 'superseded, and beaten by a 9070 XT for half the money',
    'RTX 4090': 'last generation, no longer reasonably available at this price',
    'RTX 4080': 'last generation, no longer reasonably available at this price',
}

# The only memory and storage the generator considers. Explicit rather than pattern-
# matched, so a new kit in the CSV cannot silently become an option: 32 GB is what every
# build on this page runs, and 64 GB currently costs more than a 9800X3D.
# (part, memory kind, minimum-spec only). 32 GB is what every build on this page runs and
# what the generator picks by default. The 16 GB kits are marked `min` because capacity is
# not scored — nothing in the index knows how much memory a build has — so if they were
# ordinary options the generator would put 16 GB in a €5,000 machine purely because it is
# cheaper. They are offered only when you ask for a minimum-spec build.
GEN_MEMORY = [('32GB DDR4-3200', 'DDR4', False), ('32GB DDR5-6000', 'DDR5', False),
              ('2x8GB DDR4-3200', 'DDR4', True), ('2x8GB DDR5-6000', 'DDR5', True)]
GEN_STORAGE = ['1TB NVMe', '2TB NVMe']

# Which src values in build_prices.csv are a real price someone looked up, as opposed to
# a guess. A total built entirely from these is exact; anything else marks the total with
# a ~ so the card never passes an estimate off as a figure.
#   tweakers  Tweakers.net, by hand
#   pcpp      nl.pcpartpicker.com, via tools/pcpp-price-capture.user.js
# 'aliexpress' is deliberately NOT here: it is a real price with no NL retail channel, so
# a build containing one should still read as approximate.
LOOKED_UP = {'tweakers': 'Tweakers.net', 'pcpp': 'PCPartPicker NL'}
# memory a socket can actually take
SOCKET_MEM = {'AM4': 'DDR4', 'AM5': 'DDR5', 'LGA1851': 'DDR5',
              'LGA1700': None}   # None = either
warnings = []


def warn(msg):
    warnings.append(msg)


def read_csv(path):
    """Rows from a CSV, skipping # comments and blanks."""
    with open(path, encoding='utf-8') as f:
        lines = [ln for ln in f if ln.strip() and not ln.lstrip().startswith('#')]
    return list(csv.DictReader(lines))


def load_prices():
    """-> ({part: eur}, {part: src}, priced_on). src distinguishes a real looked-up
    figure from a placeholder, so a total built on guesses can be marked as one."""
    prices, src, priced_on = {}, {}, None
    for row in read_csv(PRICES_CSV):
        part, val = row['part'].strip(), row['eur'].strip()
        if part == 'priced_on':
            priced_on = val
            continue
        try:
            prices[part] = int(round(float(val)))
            src[part] = (row.get('src') or '').strip() or 'est'
        except ValueError:
            warn('price for %r is not a number: %r' % (part, val))
    if not priced_on:
        warn('build_prices.csv has no priced_on row')
    else:
        try:
            age = (datetime.date.today() - datetime.date.fromisoformat(priced_on)).days
            if age > STALE_DAYS:
                warn('prices are %d days old (priced_on %s) — refresh them' % (age, priced_on))
        except ValueError:
            warn('priced_on is not an ISO date: %r' % priced_on)
    est = sorted(p for p, s in src.items() if s not in LOOKED_UP)
    if est:
        warn('%d part(s) still on estimated prices, so their totals show a ~ prefix: %s'
             % (len(est), ', '.join(est)))
    return prices, src, priced_on


def main():
    cpu_idx, prices_by_res = cpu_index(), {r: gpu_index(r) for r in RES}
    cpu_cov, gpu_cov = coverage('cpu'), coverage('gpu')
    prices, price_src, priced_on = load_prices()

    builds = {}
    for row in read_csv(SPECS_CSV):
        res, tier, ven = row['res'].strip(), row['tier'].strip(), row['vendor'].strip()
        if res not in RES or tier not in TIERS or ven not in VENDORS:
            warn('skipping unrecognised row: %s/%s/%s' % (res, tier, ven))
            continue
        cpu, gpu = row['cpu'].strip(), row['gpu'].strip()
        ram, sto = row['ram'].strip(), row['storage'].strip()

        # index lookups — a miss means a typo, so say so rather than showing no chip
        cpu_key = CPU_ALIAS.get(cpu, cpu)      # same silicon, other name
        ci, cd = cpu_idx.get(cpu_key), False
        gi, gd = prices_by_res[res].get(gpu), False
        if gi is None:                       # fall back to a TPU-derived figure
            gi = DERIVED_GPU.get(gpu, {}).get(res)
            gd = gi is not None
        if ci is None:
            warn('CPU %r is not in the index data (typo?)' % cpu)
        if gi is None:
            warn('GPU %r has no index for %s — measured or derived (typo?)' % (gpu, res))

        # socket vs memory generation
        socket = CPU_SPECS.get(cpu_key, {}).get('socket')
        want = SOCKET_MEM.get(socket, None) if socket else None
        if want and want not in ram:
            warn('%s is %s so it needs %s, but the build lists %r'
                 % (cpu, socket, want, ram))

        # LGA1700 on DDR4: discount the index by the measured factor for that generation
        if ci is not None and socket == 'LGA1700' and 'DDR4' in ram:
            m = re.match(r'^Core i\d-(\d\d)', cpu_key)
            gen = int(m.group(1)) if m else None
            if gen in DDR4_FACTOR:
                ci, cd = ci * DDR4_FACTOR[gen], True
            else:
                warn('%s is on DDR4 but has no measured DDR4 factor' % cpu)

        # total — any missing part kills the total rather than under-reporting it
        mb = mb_for(cpu, socket, ram)
        if mb is None:
            warn('no motherboard rule for %s on %r' % (cpu, socket))
        # (slot, part key) in the order a build is read. The card shows only the sum;
        # /specs itemises it, which is the one thing a PNG cannot do.
        bom = [('CPU', cpu), ('GPU', gpu), ('Memory', ram), ('Storage', sto)]
        if mb:
            bom.append(('Motherboard', mb))
        bom += [('Power supply', psu_for(gpu)), ('CPU cooler', cooler_for(cpu)),
                ('Case', 'case')]
        parts = [p for _, p in bom]
        missing = [p for p in parts if p not in prices]
        for p in missing:
            warn('no price for %r (needed by %s/%s/%s)' % (p, res, tier, ven))
        total = None if missing else sum(prices[p] for p in parts)
        # approximate if any component price is still a placeholder
        approx = any(price_src.get(p, 'est') not in LOOKED_UP for p in parts if p in prices)

        items = []
        for slot, part in bom:
            if part in PART_LABEL:
                name = PART_LABEL[part]
            elif re.match(r'^(psu|mb|cooler)_', part) or part == 'case':
                warn('composed part %r has no entry in PART_LABEL' % part)
                name = part
            else:
                name = part                      # a real product name, as written
            items.append({'slot': slot, 'part': name,
                          'eur': prices.get(part),
                          'src': price_src.get(part)})

        builds[(res, tier, ven)] = {
            'cpu': cpu, 'ci': ci, 'cd': cd, 'cn': cpu_cov.get(cpu_key, 0),
            'gpu': gpu, 'gi': gi, 'gd': gd, 'gn': gpu_cov.get(gpu, 0),
            'ram': ram, 'sto': sto, 'total': total, 'approx': approx,
            'vram': GPU_SPECS.get(gpu, {}).get('vram') or VRAM_EXTRA.get(gpu),
            'cbest': False, 'gbest': False, 'socket': socket, 'items': items,
        }

    for res in RES:
        for tier in TIERS:
            for ven in VENDORS:
                if (res, tier, ven) not in builds:
                    warn('build_specs.csv has no row for %s/%s/%s' % (res, tier, ven))

    # Better value per row, judged independently for CPU and GPU. The two vendor columns
    # are alternatives, not packages — nothing stops an Intel chip driving a Radeon card,
    # and at these prices that mix is usually the cheaper build. The CPU is judged on
    # chip + memory because the socket drags the RAM cost with it: a 7800X3D obliges
    # DDR5 at 400 EUR where a 12600KF takes DDR4 at 240.
    for res in RES:
        for tier in TIERS:
            pair = [builds.get((res, tier, v)) for v in VENDORS]
            if not all(pair):
                continue
            for kind, idx_key, cost in (('cbest', 'ci', lambda b: pf(prices, b['cpu']) + pf(prices, b['ram'])),
                                        ('gbest', 'gi', lambda b: pf(prices, b['gpu']))):
                scores = []
                for b in pair:
                    c, i = cost(b), b[idx_key]
                    scores.append(i / c if c and i else None)
                if None in scores:
                    continue
                hi, lo = max(scores), min(scores)
                if lo <= 0 or hi / lo < 1.02:      # too close to call, so call neither
                    continue
                pair[scores.index(hi)][kind] = True

    js = ['const PRICED_ON = %s;' % js_str(priced_on),
          'const BUILDS = {']
    for res in RES:
        js.append('"%s": {' % res)
        for tier in TIERS:
            cells = []
            for ven in VENDORS:
                b = builds.get((res, tier, ven))
                if not b:
                    continue
                cells.append(
                    '    { v:"%s", cpu:%s, ci:%s, cd:%s, cbest:%s, gpu:%s, gi:%s,'
                    ' gd:%s, gbest:%s, vram:%s, ram:%s, sto:%s, eur:%s, approx:%s }'
                    % (ven, js_str(b['cpu']), fmt(b['ci']),
                       'true' if b['cd'] else 'false',
                       'true' if b['cbest'] else 'false', js_str(b['gpu']),
                       fmt(b['gi']), 'true' if b['gd'] else 'false',
                       'true' if b['gbest'] else 'false',
                       fmt(b['vram']), js_str(b['ram']), js_str(b['sto']),
                       'null' if b['total'] is None else b['total'],
                       'true' if b['approx'] else 'false'))
            js.append('  "%s": [\n%s\n  ],' % (tier, ',\n'.join(cells)))
        js.append('},')
    js.append('};')

    # the "priced but not picked" strip, indexed at 1440p
    ref = prices_by_res['1440p']
    def idx_of(part):
        """1440p index, measured or derived. -> (value, derived) or (None, False)."""
        v = ref.get(part)
        if v is not None:
            return v, False
        v = DERIVED_GPU.get(part, {}).get('1440p')
        return (v, True) if v is not None else (None, False)

    skipped = []
    for part, versus, reason in NOT_PICKED:
        idx, derived = idx_of(part)
        if idx is None:
            warn('NOT_PICKED entry %r has no 1440p index' % part)
            continue
        if part not in prices:
            warn('NOT_PICKED entry %r has no price' % part)
            continue
        why = reason
        if versus:
            alt_idx, _ = idx_of(versus)
            if versus not in prices or alt_idx is None or not idx:
                warn('NOT_PICKED %r compares with %r, which has no price or index'
                     % (part, versus))
                continue
            why = reason.format(d=abs(prices[versus] - prices[part]),
                                p=int(round((alt_idx / idx - 1) * 100)))
        skipped.append({'part': part, 'eur': prices[part], 'gi': round(idx),
                        'gd': derived, 'why': why,
                        'vram': GPU_SPECS.get(part, {}).get('vram')
                        or VRAM_EXTRA.get(part)})

    js.append('const NOT_PICKED = [')
    for n in skipped:
        js.append('  { p:%s, eur:%d, gi:%d, gd:%s, vram:%s, why:%s },'
                  % (js_str(n['part']), n['eur'], n['gi'],
                     'true' if n['gd'] else 'false', fmt(n['vram']),
                     js_str(n['why'])))
    js.append('];')
    block = '\n'.join(js)

    html = open(CARD, encoding='utf-8').read()
    pre, rest = html.split(BEGIN, 1)
    _, post = rest.split(END, 1)
    open(CARD, 'w', encoding='utf-8').write(pre + BEGIN + '\n' + block + '\n' + END + post)

    region_list, regs = load_regions()
    # build_prices.csv IS the Netherlands price list, so anything it prices is priced in
    # nl by definition. Seeding that here keeps the canonical region complete and means
    # only the other six ever need a fallback.
    if any(r['key'] == 'nl' for r in region_list):
        for part, eur in prices.items():
            regs.setdefault(part, {}).setdefault('nl', eur)
    catalogue = build_catalogue(prices, cpu_idx, prices_by_res, cpu_cov, gpu_cov,
                                regs, region_list)
    write_json(builds, skipped, prices, price_src, priced_on, catalogue)

    print('wrote %d builds (+ %d CPUs / %d GPUs for the generator) into %s and %s'
          % (len(builds), len(catalogue['cpus']), len(catalogue['gpus']),
             os.path.basename(CARD), os.path.basename(JSON_OUT)))
    if warnings:
        print('\n%d warning(s):' % len(warnings), file=sys.stderr)
        for w in warnings:
            print('  ! ' + w, file=sys.stderr)
    else:
        print('no warnings — every part priced, indexed and socket-consistent')


def load_regions():
    """build_prices_regions.csv -> ([{key,cur,label}], {part: {region: eur}}).

    Feeds the generator's region selector and nothing else — build_prices.csv remains
    the canonical EUR/NL file the site and cards are built from. A blank cell means that
    region has no price for that part, which is carried through as a genuine absence: the
    generator will not offer the part there rather than borrowing a Dutch figure.
    """
    if not os.path.exists(REGIONS_CSV):
        warn('no build_prices_regions.csv — the generator will be single-region')
        return [], {}
    rows = read_csv(REGIONS_CSV)
    if not rows:
        return [], {}
    cols = [c for c in rows[0].keys() if c and c != 'part' and c != 'flags']
    regions = []
    for c in cols:                       # "nl_eur" -> key nl, currency EUR
        key, _, cur = c.partition('_')
        regions.append({'key': key, 'cur': cur.upper(), 'col': c})
    by_part = {}
    for r in rows:
        part = (r.get('part') or '').strip()
        if not part:
            continue
        vals = {}
        for reg in regions:
            raw = (r.get(reg['col']) or '').strip()
            if not raw:
                continue
            try:
                vals[reg['key']] = int(round(float(raw)))
            except ValueError:
                warn('regions: %r has a non-numeric price for %s' % (part, reg['key']))
        by_part[part] = vals
    return [{'key': r['key'], 'cur': r['cur']} for r in regions], by_part


def named(prices, key, regs=None):
    """A composed part as the page shows it: {part, eur, by}, or None if unpriced.

    `by` is the price per region for the generator's region selector. A board or cooler
    that a region never priced simply has no entry there — see fill_region() for the one
    documented exception.
    """
    if key is None or key not in prices:
        return None
    out = {'part': PART_LABEL.get(key, key), 'eur': prices[key], 'key': key}
    if regs is not None:
        out['by'] = dict(regs.get(key, {}))
    return out


def fill_region(entry, regs, fallback_key):
    """Where a region never priced the upper-tier board, fall back to the standard one
    for that socket rather than dropping every build that wants it.

    Only two chips ask for a "_great" board and only NL ever priced one, so without this
    a 9800X3D could not be built in any other country -- a hole big enough to be worse
    than the approximation, which is why the entry records that it happened."""
    if not entry or not fallback_key:
        return entry
    base = regs.get(fallback_key, {})
    for reg, val in base.items():
        if reg not in entry.get('by', {}):
            entry.setdefault('by', {})[reg] = val
            entry.setdefault('approx_in', []).append(reg)
    return entry


def build_catalogue(prices, cpu_idx, idx_by_res, cpu_cov, gpu_cov, regs, region_list):
    """Every part the budget generator may pick, with its platform costs resolved.

    The rules are applied here rather than in the browser so there is exactly one
    implementation of "what else does this chip drag along" — the generator's totals
    and the hand-picked matrix above it are composed by the same code, and a build the
    generator proposes can be compared with one from the table without an asterisk.
    """
    cpus = []
    for part in sorted(prices):
        key = CPU_ALIAS.get(part, part)
        base = cpu_idx.get(key)
        if base is None:
            continue                        # not a CPU, or a CPU we cannot place
        if part in GEN_EXCLUDE:
            continue
        socket = CPU_SPECS.get(key, {}).get('socket')
        cooler = named(prices, cooler_for(part), regs)
        if socket is None or cooler is None:
            warn('generator skips %r: no socket or no cooler price' % part)
            continue

        idx, derived, mobo = {}, {}, {}
        for mem, kind, _min in GEN_MEMORY:
            want = SOCKET_MEM.get(socket, None)
            if want and want != kind:
                continue                    # the socket cannot take this memory at all
            board = named(prices, mb_for(part, socket, mem), regs)
            if board and board['key'].endswith('_great'):
                board = fill_region(board, regs, board['key'][:-len('_great')])
            if board is None:
                continue
            if socket == 'LGA1700' and kind == 'DDR4':
                # indexed on DDR5, so DDR4 has to be discounted by the measured factor
                m = re.match(r'^Core i\d-(\d\d)', key)
                gen = int(m.group(1)) if m else None
                if gen not in DDR4_FACTOR:
                    warn('generator skips %s on DDR4: no measured factor' % part)
                    continue
                idx[kind], derived[kind] = base * DDR4_FACTOR[gen], True
            else:
                idx[kind], derived[kind] = base, False
            mobo[kind] = board
        if not idx:
            warn('generator skips %r: no usable memory/board combination' % part)
            continue

        cpus.append({'part': part, 'vendor': CPU_VENDOR.get(key), 'socket': socket,
                     'eur': prices[part], 'by': regs.get(part, {}),
                     'cov': cpu_cov.get(key, 0),
                     'idx': {k: rnd(v) for k, v in idx.items()}, 'derived': derived,
                     'cooler': cooler, 'mobo': mobo})

    gpus = []
    for part in sorted(prices):
        if part in GEN_EXCLUDE or part in cpu_idx or CPU_ALIAS.get(part) in cpu_idx:
            continue
        idx, derived = {}, False
        for res in RES:
            v = idx_by_res[res].get(part)
            if v is None:
                v = DERIVED_GPU.get(part, {}).get(res)
                if v is not None:
                    derived = True
            if v is not None:
                idx[res] = rnd(v)
        if not idx:
            continue                        # not a GPU, or one we cannot place
        psu = named(prices, psu_for(part), regs)
        if psu is None:
            warn('generator skips %r: no PSU price for its class' % part)
            continue
        gpus.append({'part': part, 'vendor': GPU_VENDOR.get(part), 'eur': prices[part],
                     'by': regs.get(part, {}), 'cov': gpu_cov.get(part, 0), 'idx': idx, 'derived': derived,
                     'vram': GPU_SPECS.get(part, {}).get('vram') or VRAM_EXTRA.get(part),
                     'psu': psu})

    memory = [{'part': m, 'kind': k, 'eur': prices[m], 'min': mn,
                'by': regs.get(m, {})}
              for m, k, mn in GEN_MEMORY if m in prices]
    storage = [{'part': s, 'eur': prices[s], 'by': regs.get(s, {})}
               for s in GEN_STORAGE if s in prices]
    for want, got in (('memory', memory), ('storage', storage)):
        if not got:
            warn('generator has no %s priced — it cannot compose a build' % want)

    return {
        'cpus': cpus, 'gpus': gpus, 'memory': memory, 'storage': storage,
        'case': named(prices, 'case', regs),
        'regions': region_list,
        'blend_cpu': BLEND_CPU,
        'excluded': [{'part': p, 'why': w} for p, w in sorted(GEN_EXCLUDE.items())],
    }


def write_json(builds, skipped, prices, price_src, priced_on, catalogue):
    """The same picks as the card, for /specs to fetch at runtime.

    The site never inlines data — the SPA fetches data.json, and this page fetches
    this. One generator run feeds both outputs, so the card and the page cannot drift
    apart on a price.

    `catalogue` is the extra the card has no use for: the parts bin the page's budget
    generator searches.
    """
    rows = []
    for res in RES:
        for tier in TIERS:
            for ven in VENDORS:
                b = builds.get((res, tier, ven))
                if not b:
                    continue
                rows.append({
                    'res': res, 'tier': tier, 'vendor': ven,
                    'cpu': b['cpu'], 'ci': rnd(b['ci']), 'cd': b['cd'],
                    'cbest': b['cbest'], 'cn': b['cn'], 'socket': b['socket'],
                    'gpu': b['gpu'], 'gi': rnd(b['gi']), 'gd': b['gd'],
                    'gbest': b['gbest'], 'gn': b['gn'], 'vram': b['vram'],
                    'ram': b['ram'], 'sto': b['sto'],
                    'eur': b['total'], 'approx': b['approx'], 'items': b['items'],
                })
    # Name the sources actually present rather than a fixed string: the file is a mix
    # now, and claiming one shop for prices that came from two would be exactly the kind
    # of quiet wrongness the rest of this generator goes out of its way to avoid.
    used = sorted({price_src.get(p, 'est') for p in prices} & set(LOOKED_UP))
    source = ' and '.join(LOOKED_UP[s] for s in used) or 'estimates'

    doc = {
        'priced_on': priced_on,
        'currency': 'EUR', 'region': 'Netherlands', 'source': source,
        'resolutions': RES, 'tiers': TIERS, 'vendors': VENDORS,
        'builds': rows,
        'not_picked': skipped,
        # every priced part, including the ones no build uses — the page lists them so
        # you can re-total a build you have changed
        'prices': [{'part': p, 'eur': prices[p], 'src': price_src.get(p, 'est')}
                   for p in sorted(prices)],
        'catalogue': catalogue,
    }
    os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
    with open(JSON_OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write('\n')


def rnd(v):
    return None if v is None else int(round(v))


def pf(prices, part):
    """Price of a part, or None if it is not priced."""
    return prices.get(part)


def fmt(v):
    return 'null' if v is None else str(int(round(v)))


def js_str(s):
    return 'null' if s is None else '"%s"' % str(s).replace('"', r'\"')


if __name__ == '__main__':
    main()
