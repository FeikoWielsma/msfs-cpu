"""Generate the build-table card data from build_specs.csv + build_prices.csv.

    python make_build_table.py

Rewrites the block between the BUILDS markers in tierlist_card_build.html, so the
card's data is never hand-maintained. Edit the two CSVs, not the HTML.

Deliberately noisy: a missing price, an unknown part name or a socket/memory mismatch
prints a warning and (for prices) renders a dash rather than a plausible-looking wrong
number. A build table that is quietly wrong about money is worse than one that admits
it does not know.
"""
import csv, datetime, os, sys

from msfs_index import (cpu_index, gpu_index, CPU_SPECS, CPU_VENDOR, GPU_SPECS,
                        coverage)

HERE = os.path.dirname(os.path.abspath(__file__))
CARD = os.path.join(HERE, 'tierlist_card_build.html')
SPECS_CSV = os.path.join(HERE, 'build_specs.csv')
PRICES_CSV = os.path.join(HERE, 'build_prices.csv')
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

# Priced, plausible, but beaten on value by something already in the matrix. Listed
# under it because "why isn't X in here?" is the question that always follows.
# (part, reason) — index shown is at 1440p.
NOT_PICKED = [
    ('RX 9070 GRE', 'a 9070 XT is +35% for €114 more'),
    ('RTX 5070', 'a 9060 XT 16GB matches it for €215 less'),
    ('RX 7900 XT', 'a 9070 XT beats it and costs €67 less'),
    ('RTX 5060 Ti 8GB', 'the 16GB twin is +23% for €217'),
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
        ci = cpu_idx.get(cpu)
        gi, gd = prices_by_res[res].get(gpu), False
        if gi is None:                       # fall back to a TPU-derived figure
            gi = DERIVED_GPU.get(gpu, {}).get(res)
            gd = gi is not None
        if ci is None:
            warn('CPU %r is not in the index data (typo?)' % cpu)
        if gi is None:
            warn('GPU %r has no index for %s — measured or derived (typo?)' % (gpu, res))

        # socket vs memory generation
        socket = CPU_SPECS.get(cpu, {}).get('socket')
        want = SOCKET_MEM.get(socket, None) if socket else None
        if want and want not in ram:
            warn('%s is %s so it needs %s, but the build lists %r'
                 % (cpu, socket, want, ram))

        # total — any missing part kills the total rather than under-reporting it
        bundle = 'bundle_%s_%s' % (tier, ven)
        parts = [cpu, gpu, ram, sto, bundle]
        missing = [p for p in parts if p not in prices]
        for p in missing:
            warn('no price for %r (needed by %s/%s/%s)' % (p, res, tier, ven))
        total = None if missing else sum(prices[p] for p in parts)
        # approximate if any component price is still a placeholder
        approx = any(price_src.get(p, 'est') != 'tweakers' for p in parts if p in prices)

        builds[(res, tier, ven)] = {
            'cpu': cpu, 'ci': ci, 'cn': cpu_cov.get(cpu, 0),
            'gpu': gpu, 'gi': gi, 'gd': gd, 'gn': gpu_cov.get(gpu, 0),
            'ram': ram, 'sto': sto, 'total': total, 'approx': approx,
            'vram': GPU_SPECS.get(gpu, {}).get('vram'),
        }

    for res in RES:
        for tier in TIERS:
            for ven in VENDORS:
                if (res, tier, ven) not in builds:
                    warn('build_specs.csv has no row for %s/%s/%s' % (res, tier, ven))

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
                    '    { v:"%s", cpu:%s, ci:%s, gpu:%s, gi:%s, gd:%s, vram:%s,'
                    ' ram:%s, sto:%s, eur:%s, approx:%s }'
                    % (ven, js_str(b['cpu']), fmt(b['ci']), js_str(b['gpu']),
                       fmt(b['gi']), 'true' if b['gd'] else 'false',
                       fmt(b['vram']), js_str(b['ram']), js_str(b['sto']),
                       'null' if b['total'] is None else b['total'],
                       'true' if b['approx'] else 'false'))
            js.append('  "%s": [\n%s\n  ],' % (tier, ',\n'.join(cells)))
        js.append('},')
    js.append('};')

    # the "priced but not picked" strip, indexed at 1440p
    ref = prices_by_res['1440p']
    js.append('const NOT_PICKED = [')
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
        js.append('  { p:%s, eur:%d, gi:%d, gd:%s, vram:%s, why:%s },'
                  % (js_str(part), prices[part], round(idx),
                     'true' if derived else 'false',
                     fmt(GPU_SPECS.get(part, {}).get('vram')), js_str(reason)))
    js.append('];')
    block = '\n'.join(js)

    html = open(CARD, encoding='utf-8').read()
    pre, rest = html.split(BEGIN, 1)
    _, post = rest.split(END, 1)
    open(CARD, 'w', encoding='utf-8').write(pre + BEGIN + '\n' + block + '\n' + END + post)

    print('wrote %d builds into %s' % (len(builds), os.path.basename(CARD)))
    if warnings:
        print('\n%d warning(s):' % len(warnings), file=sys.stderr)
        for w in warnings:
            print('  ! ' + w, file=sys.stderr)
    else:
        print('no warnings — every part priced, indexed and socket-consistent')


def fmt(v):
    return 'null' if v is None else str(int(round(v)))


def js_str(s):
    return 'null' if s is None else '"%s"' % str(s).replace('"', r'\"')


if __name__ == '__main__':
    main()
