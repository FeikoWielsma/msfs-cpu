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
                        coverage)

HERE = os.path.dirname(os.path.abspath(__file__))
CARD = os.path.join(HERE, 'tierlist_card_build.html')
SPECS_CSV = os.path.join(HERE, 'build_specs.csv')
PRICES_CSV = os.path.join(HERE, 'build_prices.csv')
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
NOT_PICKED = [
    ('RX 9070 GRE', 'an RX 9070 is +20% for €34 more'),
    ('RX 7900 XT', 'a 9070 XT beats it for €67 less'),
    ('RX 9060 XT 8GB', 'the 16GB more than doubles it for €73'),
    ('RTX 5060 Ti 8GB', 'the 16GB twin is +23% for €217'),
    ('Arc B580', 'fine at 1080p, out of its depth above'),
]
TIERS = ['entry', 'mid', 'high']
VENDORS = ['amd', 'nv']
STALE_DAYS = 60
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
    est = sorted(p for p, s in src.items() if s != 'tweakers')
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
        approx = any(price_src.get(p, 'est') != 'tweakers' for p in parts if p in prices)

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
    skipped = []
    for part, reason in NOT_PICKED:
        idx, derived = ref.get(part), False
        if idx is None:
            idx = DERIVED_GPU.get(part, {}).get('1440p')
            derived = idx is not None
        if idx is None:
            warn('NOT_PICKED entry %r has no 1440p index' % part)
            continue
        if part not in prices:
            warn('NOT_PICKED entry %r has no price' % part)
            continue
        skipped.append({'part': part, 'eur': prices[part], 'gi': round(idx),
                        'gd': derived, 'why': reason,
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

    write_json(builds, skipped, prices, price_src, priced_on)

    print('wrote %d builds into %s and %s'
          % (len(builds), os.path.basename(CARD), os.path.basename(JSON_OUT)))
    if warnings:
        print('\n%d warning(s):' % len(warnings), file=sys.stderr)
        for w in warnings:
            print('  ! ' + w, file=sys.stderr)
    else:
        print('no warnings — every part priced, indexed and socket-consistent')


def write_json(builds, skipped, prices, price_src, priced_on):
    """The same picks as the card, for /specs to fetch at runtime.

    The site never inlines data — the SPA fetches data.json, and this page fetches
    this. One generator run feeds both outputs, so the card and the page cannot drift
    apart on a price.
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
    doc = {
        'priced_on': priced_on,
        'currency': 'EUR', 'region': 'Netherlands', 'source': 'Tweakers.net',
        'resolutions': RES, 'tiers': TIERS, 'vendors': VENDORS,
        'builds': rows,
        'not_picked': skipped,
        # every priced part, including the ones no build uses — the page lists them so
        # you can re-total a build you have changed
        'prices': [{'part': p, 'eur': prices[p], 'src': price_src.get(p, 'est')}
                   for p in sorted(prices)],
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
