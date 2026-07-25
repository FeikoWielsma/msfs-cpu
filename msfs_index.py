"""Shared Performance Index math for the card generators.

This is the Python counterpart of the fit in src/main.ts. Keep the two in step: if
the site's normalisation changes, the cards must change with it or they will quietly
disagree with msfs.razortek.nl.

    from msfs_index import cpu_index, gpu_index, CPU_SPECS, CPU_VENDOR

    cpu = cpu_index()            # {name: 0-100}, leader = 100
    gpu = gpu_index('1440p')     # {name: 0-100}, leader = 100, per resolution

Both scales are relative and normalised to their own leader. GPU figures are
normalised PER RESOLUTION and are never comparable across resolutions. Neither is a
frame rate — absolute FPS are not comparable across sites, which is the whole reason
the index exists.
"""
import json, math, os, re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    with open(os.path.join(HERE, 'public', name), encoding='utf-8') as f:
        return json.load(f)


_CPU = _load('data.json')
_GPU = _load('gpu_data.json')

CPU_SPECS = _CPU.get('specs', {})
GPU_SPECS = _GPU.get('specs', {})
CPU_VENDOR, GPU_VENDOR = {}, {}
for _r in _CPU['rows']:
    CPU_VENDOR.setdefault(_r['cpu'], _r['vendor'])
for _r in _GPU['rows']:
    GPU_VENDOR.setdefault(_r['cpu'], _r['vendor'])


# ---------------------------------------------------------------- shared fit

def _dedup_newest(rows):
    """One row per part per dataset — the newest, matching dedupNewest() in main.ts."""
    best = {}
    for r in rows:
        cur = best.get(r['cpu'])
        if not cur or r['date'] > cur['date']:
            best[r['cpu']] = r
    return list(best.values())


def _series_data(rows, spec, field):
    groups = spec.get('groups') or ([spec['group']] if spec.get('group') else None)
    sel = [r for r in rows
           if r['site'] == spec['site'] and (groups is None or r['group'] in groups)]
    return {r['cpu']: r[field] for r in _dedup_newest(sel) if r.get(field) is not None}


def _twoway(series, parts, ref, iters=200):
    """Two-way additive fit in log space: log(value) = datasetOffset + partEffect.

    Alternating least squares, same as twowayFit() in main.ts. This is what lets a
    part tested by one reviewer be compared with one tested by another.
    """
    a = [0.0] * len(series)
    b = {p: 0.0 for p in parts}
    for _ in range(iters):
        for i, s in enumerate(series):
            items = list(s.items())
            a[i] = sum(math.log(v) - b[p] for p, v in items) / len(items)
        for p in parts:
            obs = [(s, i) for i, s in enumerate(series) if p in s]
            b[p] = sum(math.log(s[p]) - a[i] for s, i in obs) / len(obs)
    base = b[ref]
    return {p: math.exp(b[p] - base) * 100 for p in parts}


def _to_leader(raw):
    top = max(raw.values())
    return {p: v / top * 100 for p, v in raw.items()}


# ------------------------------------------------- CPU-only sanity priors
# Within one Intel microarchitecture a higher-tier part cannot be slower than a lesser
# sibling, so thinly-tested SKUs get snapped back into order. Deliberately NOT applied
# to AMD, where the spec ladder does not track gaming order (a 7800X3D beats a
# 7950X3D). Ported from applyArchPrior() / applyClockPairs() in src/main.ts.

_BIN = {'KS': 5, 'K': 4, 'KF': 4, 'F': 3, 'T': 1}


def _arch_key(cpu):
    m = re.match(r'^Core i(\d)-(1[1234])(\d)\d{2}([A-Z]*)$', cpu)
    if m:
        gen = int(m.group(2))
        fam = ('intel-rocket' if gen <= 11 else
               'intel-alder' if gen == 12 else 'intel-raptor')
        return fam, [int(m.group(1)), int(m.group(3)), gen, _BIN.get(m.group(4), 2)]
    m = re.match(r'^Core Ultra (\d) (\d{3})([A-Z]*)', cpu)
    if m:
        return 'intel-arrow', [int(m.group(1)), int(m.group(2)), _BIN.get(m.group(3), 2)]
    return None


def _apply_arch_prior(raw, series):
    """Weighted isotonic regression (pool-adjacent-violators) per Intel family."""
    weight = lambda p: max(sum(1 for s in series if p in s), 1)
    fams = defaultdict(list)
    for cpu in raw:
        k = _arch_key(cpu)
        if k:
            fams[k[0]].append((cpu, k[1]))
    for members in fams.values():
        members.sort(key=lambda x: x[1])          # weakest first
        blocks = []
        for cpu, _ in members:
            blocks.append([math.log(raw[cpu]), weight(cpu), [cpu]])
            while len(blocks) >= 2 and blocks[-2][0] > blocks[-1][0]:
                b2, b1 = blocks.pop(), blocks.pop()
                blocks.append([(b1[0] * b1[1] + b2[0] * b2[1]) / (b1[1] + b2[1]),
                               b1[1] + b2[1], b1[2] + b2[2]])
        for v, _, cpus in blocks:
            for cpu in cpus:
                raw[cpu] = math.exp(v)


# Same silicon, clock-only siblings [faster, slower]. Physically guaranteed ordering,
# so the faster part is floored just above the slower one.
_CLOCK_PAIRS = [('Ryzen 7 5800X3D', 'Ryzen 7 5700X3D'),
                ('Ryzen 5 7600X', 'Ryzen 5 7500F')]


def _apply_clock_pairs(raw, series):
    for fast, slow in _CLOCK_PAIRS:
        if fast not in raw or slow not in raw:
            continue
        ratios = [s[fast] / s[slow] for s in series if fast in s and slow in s]
        r = math.exp(sum(map(math.log, ratios)) / len(ratios)) if ratios else 1.0
        raw[fast] = max(raw[fast], raw[slow] * max(r, 1.002))


# ---------------------------------------------------------------- public API

def cpu_index(field='avg'):
    """CPU Performance Index across every dataset, leader = 100.

    Single-resolution by nature: CPU reviews are run at low resolution to isolate the
    CPU, so there is one ladder. Do not read resolution-specific advice out of it.
    """
    rows = _CPU['rows']
    series = [sd for sd in (_series_data(rows, s, field) for s in _CPU['norm']) if sd]
    parts = list(dict.fromkeys(p for s in series for p in s))
    raw = _twoway(series, parts, parts[0])
    _apply_arch_prior(raw, series)
    _apply_clock_pairs(raw, series)
    return _to_leader(raw)


def gpu_index(resolution, field='avg'):
    """GPU Performance Index for one resolution, leader = 100.

    Normalised per resolution — figures never compare across 1080p / 1440p / 4K.
    No priors: the Intel-CPU families and Ryzen clock pairs above do not apply here.
    """
    rows = _GPU['rows']
    series = [sd for sd in (_series_data(rows, s, field) for s in _GPU['norm']
                            if s.get('resolution') == resolution) if sd]
    if not series:
        raise ValueError('no GPU data for resolution %r' % resolution)
    parts = list(dict.fromkeys(p for s in series for p in s))
    return _to_leader(_twoway(series, parts, parts[0]))


def coverage(which='cpu'):
    """How many datasets cover each part — thin coverage means treat gaps as ties."""
    data = _CPU if which == 'cpu' else _GPU
    rows = data['rows']
    series = [sd for sd in (_series_data(rows, s, 'avg') for s in data['norm']) if sd]
    return {p: sum(1 for s in series if p in s)
            for p in dict.fromkeys(p for s in series for p in s)}


if __name__ == '__main__':
    cpu = cpu_index()
    print('CPU index — top 5:')
    for p, v in sorted(cpu.items(), key=lambda kv: -kv[1])[:5]:
        print('  %-22s %5.1f' % (p, v))
    for res in ('1080p', '1440p', '4K'):
        g = gpu_index(res)
        xt = g.get('RX 9070 XT')
        print('%-6s %d cards, 9070 XT = %.0f' % (res, len(g), xt))
