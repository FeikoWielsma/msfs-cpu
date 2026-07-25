"""Generate the GPU tier-list card data from public/gpu_data.json.

Rewrites the block between the CLUSTERS markers in tierlist_card_gpu.html, so the
card's data is never hand-maintained. Run after the data step changes gpu_data.json:

    python make_tierlist_clusters.py

Cards within GAP index points of each other merge into one row (max CAP per row),
because 35 individual rows are illegible at Discord thumbnail size and, with most
cards covered by a single test pass, small gaps are not real differences anyway.

Tier bands are a fixed fraction of the leader and identical across resolutions, so a
letter means the same thing on all three cards. That is what makes them comparable:
1080p puts 4 cards in S and 2 in E, 4K puts 1 in S and 11 in E.
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
CARD = os.path.join(HERE, 'tierlist_card_gpu.html')
BEGIN, END = '// <<< CLUSTERS', '// >>> CLUSTERS'

GAP, CAP = 5.0, 5
BANDS = [('S', 90), ('A', 68), ('B', 48), ('C', 36), ('D', 20), ('E', 0)]

d = json.load(open(os.path.join(HERE, 'public', 'gpu_data.json'), encoding='utf-8'))
ROWS, NORM, SPECS = d['rows'], d['norm'], d['specs']
VENDOR = {}
for r in ROWS:
    VENDOR.setdefault(r['cpu'], r['vendor'])

# full name shown on the detail card, short name on the compact one. VRAM suffixes are
# dropped where the coloured tag already states it, and kept on 16GB parts that need to
# be told apart from an 8GB twin.
NAMES = {
    'RTX 5090': ('RTX 5090', '5090'),          'RTX 4090': ('RTX 4090', '4090'),
    'RTX 5080': ('RTX 5080', '5080'),          'RTX 4080 Super': ('RTX 4080 Super', '4080S'),
    'RTX 5070 Ti': ('RTX 5070 Ti', '5070Ti'),  'RTX 4070 Ti Super': ('RTX 4070 Ti Super', '4070TiS'),
    'RTX 4070 Ti': ('RTX 4070 Ti', '4070Ti'),  'RTX 4070 Super': ('RTX 4070 Super', '4070S'),
    'RTX 5070': ('RTX 5070', '5070'),          'RTX 4070': ('RTX 4070', '4070'),
    'RTX 5060 Ti 16GB': ('RTX 5060 Ti 16GB', '5060Ti16'),
    'RTX 5060 Ti 8GB': ('RTX 5060 Ti', '5060Ti'),
    'RTX 4060 Ti 16GB': ('RTX 4060 Ti 16GB', '4060Ti16'),
    'RTX 4060 Ti 8GB': ('RTX 4060 Ti', '4060Ti'),
    'RTX 5060': ('RTX 5060', '5060'),          'RTX 4060': ('RTX 4060', '4060'),
    'RTX 5050': ('RTX 5050', '5050'),          'RTX 3060 12GB': ('RTX 3060', '3060'),
    'RTX 3060 Ti': ('RTX 3060 Ti', '3060Ti'),  'RTX 3050': ('RTX 3050', '3050'),
    'RX 9070 XT': ('RX 9070 XT', '9070XT'),    'RX 9070': ('RX 9070', '9070'),
    'RX 7900 XTX': ('RX 7900 XTX', '7900XTX'), 'RX 7900 XT': ('RX 7900 XT', '7900XT'),
    'RX 7800 XT': ('RX 7800 XT', '7800XT'),    'RX 7700 XT': ('RX 7700 XT', '7700XT'),
    'RX 9060 XT 16GB': ('RX 9060 XT 16GB', '9060XT16'),
    'RX 9060 XT 8GB': ('RX 9060 XT', '9060XT'),
    'RX 7600 XT': ('RX 7600 XT', '7600XT'),    'RX 7600': ('RX 7600', '7600'),
    'RX 6600': ('RX 6600', '6600'),
    'Arc B580': ('Arc B580', 'B580'),          'Arc B570': ('Arc B570', 'B570'),
    'Arc A770 16GB': ('Arc A770 16GB', 'A770'), 'Arc A750': ('Arc A750', 'A750'),
}
VMAP = {'Nvidia': 'nv', 'AMD': 'amd', 'Intel': 'intel'}
VORDER = {'Nvidia': 0, 'AMD': 1, 'Intel': 2}   # listing order within a row

# Value picks, rendered as a purple star plus a glow on the card's name. Editorial,
# not computed — there is no price data in the dataset, so this is a judgement call
# about what the index is worth per pound, and it is labelled as such on the card.
# A mark attaches to one card, never a whole row: clusters are mixed (the 9070 XT
# shares a row with the 4090 at 1440p), so marking the row would mis-attribute it.
# No 'fastest' mark — the 5090 already sits alone at the top of S on 100.
MARKS = {
    'RX 9070 XT': 'value',
    'RX 9070': 'value',
    'RX 9060 XT 16GB': 'value',
}


def dedup_newest(rows):
    best = {}
    for r in rows:
        c = best.get(r['cpu'])
        if not c or r['date'] > c['date']:
            best[r['cpu']] = r
    return list(best.values())


def series_data(spec, field='avg'):
    groups = spec.get('groups') or [spec['group']]
    rows = dedup_newest([r for r in ROWS if r['site'] == spec['site'] and r['group'] in groups])
    return {r['cpu']: r[field] for r in rows if r.get(field) is not None}


def twoway(series, cards, ref):
    """The same two-way additive fit in log space the site uses: log(v) = run + card."""
    a = [0.0] * len(series)
    b = {c: 0.0 for c in cards}
    for _ in range(200):
        for i, s in enumerate(series):
            e = list(s.items())
            a[i] = sum(math.log(v) - b[c] for c, v in e) / len(e)
        for c in cards:
            obs = [(s, i) for i, s in enumerate(series) if c in s]
            b[c] = sum(math.log(s[c]) - a[i] for s, i in obs) / len(obs)
    return {c: math.exp(b[c] - b[ref]) * 100 for c in cards}


def index_for(res):
    """Index for one resolution, leader = 100. Normalised per resolution, so the
    numbers are never comparable across them."""
    valid = [sd for sd in (series_data(s) for s in NORM if s['resolution'] == res) if sd]
    cards = list(dict.fromkeys(c for s in valid for c in s))
    raw = twoway(valid, cards, cards[0])
    top = max(raw.values())
    return {c: raw[c] / top * 100 for c in cards}


def tier_of(v):
    return next(t for t, lo in BANDS if v >= lo)


def clusters(idx):
    out, cur = [], []
    for name, v in sorted(idx.items(), key=lambda kv: -kv[1]):
        t = tier_of(v)
        if cur and (t != cur[0][2] or cur[-1][1] - v > GAP or len(cur) >= CAP):
            out.append(cur)
            cur = []
        cur.append((name, v, t))
    if cur:
        out.append(cur)
    return out


def js_for(res):
    idx = index_for(res)
    unknown = [c for c in idx if c not in NAMES]
    assert not unknown, f'no display name for {unknown} - add it to NAMES'
    lines, prev_t = [], None
    for cl in clusters(idx):
        t = cl[0][2]
        if t != prev_t:
            if prev_t is not None:
                lines.append('  ]},')
            lines.append('  { t:"%s", rows:[' % t)
            prev_t = t
        cards = []
        # within a row, order by vendor (Nvidia > AMD > Intel), then by index desc.
        # Row order itself is still purely by index — only the listing is grouped.
        cl = sorted(cl, key=lambda c: (VORDER[VENDOR[c[0]]], -c[1]))
        for name, _, _ in cl:
            full, short = NAMES[name]
            g = SPECS.get(name, {}).get('vram')
            g = g if g and g <= 12 else 0              # only <=12GB earns a tag
            mark = MARKS.get(name)
            if mark:                                   # 0 keeps the mark in slot 4
                arg = ',%d,"%s"' % (g, mark)
            else:
                arg = ',%d' % g if g else ''
            cards.append('%s("%s","%s"%s)' % (VMAP[VENDOR[name]], full, short, arg))
        vals = [v for _, v, _ in cl]
        lines.append('    { cards:[%s],' % ', '.join(cards))
        lines.append('      lo:%d, hi:%d, mean:%d },'
                     % (round(min(vals)), round(max(vals)), round(sum(vals) / len(vals))))
    lines.append('  ]},')
    return '\n'.join(lines)


def main():
    block = '\n'.join('"%s": [\n%s\n],' % (res, js_for(res))
                      for res in ['1080p', '1440p', '4K'])
    html = open(CARD, encoding='utf-8').read()
    pre, rest = html.split(BEGIN, 1)
    _, post = rest.split(END, 1)
    open(CARD, 'w', encoding='utf-8').write(pre + BEGIN + '\n' + block + '\n' + END + post)
    print('wrote %d cluster rows across 3 resolutions into %s'
          % (block.count('cards:['), os.path.basename(CARD)))


if __name__ == '__main__':
    main()
