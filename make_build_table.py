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

from msfs_index import cpu_index, gpu_index, CPU_SPECS, CPU_VENDOR, coverage

HERE = os.path.dirname(os.path.abspath(__file__))
CARD = os.path.join(HERE, 'tierlist_card_build.html')
SPECS_CSV = os.path.join(HERE, 'build_specs.csv')
PRICES_CSV = os.path.join(HERE, 'build_prices.csv')
BEGIN, END = '// <<< BUILDS', '// >>> BUILDS'

RES = ['1080p', '1440p', '4K']
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
    prices, priced_on = {}, None
    for row in read_csv(PRICES_CSV):
        part, val = row['part'].strip(), row['eur'].strip()
        if part == 'priced_on':
            priced_on = val
            continue
        try:
            prices[part] = int(round(float(val)))
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
    return prices, priced_on


def main():
    cpu_idx, prices_by_res = cpu_index(), {r: gpu_index(r) for r in RES}
    cpu_cov, gpu_cov = coverage('cpu'), coverage('gpu')
    prices, priced_on = load_prices()

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
        gi = prices_by_res[res].get(gpu)
        if ci is None:
            warn('CPU %r is not in the index data (typo?)' % cpu)
        if gi is None:
            warn('GPU %r is not in the %s index data (typo?)' % (gpu, res))

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

        builds[(res, tier, ven)] = {
            'cpu': cpu, 'ci': ci, 'cn': cpu_cov.get(cpu, 0),
            'gpu': gpu, 'gi': gi, 'gn': gpu_cov.get(gpu, 0),
            'ram': ram, 'sto': sto, 'total': total,
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
                    '    { v:"%s", cpu:%s, ci:%s, gpu:%s, gi:%s, ram:%s, sto:%s, eur:%s }'
                    % (ven, js_str(b['cpu']), fmt(b['ci']), js_str(b['gpu']),
                       fmt(b['gi']), js_str(b['ram']), js_str(b['sto']),
                       'null' if b['total'] is None else b['total']))
            js.append('  "%s": [\n%s\n  ],' % (tier, ',\n'.join(cells)))
        js.append('},')
    js.append('};')
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
