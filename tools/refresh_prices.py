"""Local PCPP capture setup, review and import. No network requests or dependencies."""
import argparse
import csv
import datetime as dt
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
REGIONS = dict(nl='EUR', de='EUR', fr='EUR', uk='GBP', ca='CAD', au='AUD', us='USD')
NL_RETAILERS = {'megekko': {'megekko.nl', 'www.megekko.nl'},
                'alternate': {'alternate.nl', 'www.alternate.nl'}}


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def read_csv(path):
    return list(csv.DictReader(line for line in path.read_text(encoding='utf-8-sig').splitlines()
                              if line.strip() and not line.lstrip().startswith('#')))


def watch_pattern(part):
    """Only named CPUs/GPUs: bundles and approved storage/memory need saved lists."""
    if not part.startswith(('Ryzen ', 'Core ', 'RX ', 'RTX ', 'Arc ')):
        return None
    vram = re.search(r' (\d+)GB$', part)
    name = part[:vram.start()] if vram else part
    # Reject SKU suffixes (5600X, 5600XT, 9600X3D) and spaced GPU siblings.
    pattern = r'\b' + re.escape(name).replace(r'\ ', r'\s+') + r'(?![A-Za-z0-9])'
    if part.startswith(('RX ', 'RTX ', 'Arc ')):
        pattern += r'(?!\s+(?:Ti|SUPER|XT|XTX|GRE)\b)'
    if vram:
        pattern += r'.*\b' + vram[1] + r'\s*GB\b'
    return f'{part} = /{pattern}/i'


def prepare(root):
    folder = root / '.price-refresh'
    folder.mkdir(exist_ok=True)
    rows = read_csv(root / 'build_prices.csv')
    parts = [r['part'] for r in rows if r['part'] != 'priced_on']
    setup = {
        'schema': 'msfs-pcpp-setup-v1',
        'session': {'id': str(uuid.uuid4()), 'started': utcnow().isoformat()},
        'watch': '\n'.join(p for part in parts if (p := watch_pattern(part))),
        'required': parts,
        'targets': [
            {'label': 'MSFS CPUs', 'path': '/products/cpu/', 'regions': ['nl']},
            {'label': 'MSFS GPUs', 'path': '/products/video-card/', 'regions': ['nl']},
        ],
    }
    for config_path in (folder / 'collection-config.json', root / 'tools' / 'price-collection.json'):
        if not config_path.exists():
            continue
        config = json.loads(config_path.read_text(encoding='utf-8'))
        # A saved runnable config is distinct from investigation notes/target drafts.
        if config.get('schema') == 'msfs-pcpp-collection-config-v1':
            setup['targets'] = config['targets']
            setup['watch'] = config.get('watch', setup['watch'])
            setup['rules'] = config.get('rules', '')
            print(f'Reusing saved collection config: {config_path}')
            break
    path = folder / 'setup.json'
    path.write_text(json.dumps(setup, indent=2) + '\n', encoding='utf-8')
    print(f'Setup: {path}')
    print(f'Watchlist: {len(setup["watch"].splitlines())} named CPUs/GPUs; {len(parts)} total price keys; {len(setup["targets"])} saved targets.')
    print('1. Install/update tools/pcpp-price-capture.user.js in Violentmonkey/Tampermonkey.')
    print('2. Open https://nl.pcpartpicker.com and click the euro button > Import setup.')
    print('   Choose setup.json above. Existing targets, list rules and custom mappings are kept.')
    print('3. Review the saved targets for memory/storage/boards/PSUs/coolers/case.')
    print('   Add filtered result pages when needed; one category page may not contain every SKU.')
    print('   Capture pages manually, or use Run for your saved targets. Stop on access challenges.')
    print('4. Click Download refresh. Return here with the downloaded JSON file path.')
    return path


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('capture timestamps must include a timezone')
    return parsed.astimezone(dt.timezone.utc)


def csv_updates(path, changes, extra=()):
    """Preserve comments/order while patching known rows and appending new region rows."""
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    out, fields, remaining = [], None, dict(changes)

    def encode(values):
        buff = io.StringIO(newline='')
        csv.writer(buff, lineterminator='').writerow(values)
        return buff.getvalue()

    for line in lines:
        if not line.strip() or line.lstrip().startswith('#'):
            out.append(line)
            continue
        cells = next(csv.reader([line]))
        if fields is None:
            fields = cells
            new_fields = fields + [f for f in extra if f not in fields]
            out.append(encode(new_fields))
            continue
        row = dict(zip(fields, cells))
        row.update(remaining.pop(row['part'], {}))
        out.append(encode([row.get(f, '') for f in new_fields]))
    for part, values in remaining.items():
        row = {'part': part, **values}
        out.append(encode([row.get(f, '') for f in new_fields]))
    return '\n'.join(out) + '\n'


def review(root, capture, allow_large=False):
    if not isinstance(capture, dict):
        raise ValueError('Capture must be a JSON object.')
    if capture.get('schema') not in {'msfs-pcpp-refresh-v1', 'msfs-price-refresh-v1'}:
        raise ValueError('Expected Download refresh JSON from userscript v1.1 or newer (not CSV/setup).')
    session = capture.get('session') or {}
    if not isinstance(session, dict) or not session.get('id'):
        raise ValueError('No refresh session. Import a newly generated setup.json first.')
    started = timestamp(session['started'])
    if not utcnow() - dt.timedelta(days=7) <= started <= utcnow():
        raise ValueError('Refresh session is over seven days old or in the future. Prepare a new setup.')
    canonical = read_csv(root / 'build_prices.csv')
    priced_on = next(r['eur'] for r in canonical if r['part'] == 'priced_on')
    base = {r['part']: r for r in canonical if r['part'] != 'priced_on'}
    regional = read_csv(root / 'build_prices_regions.csv')
    regional_by_part = {r['part']: r for r in regional}
    region_cols = set(regional[0]) - {'part'}
    ledger_path = root / 'build_price_observations.json'
    ledger = json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.exists() else {}
    ledger = json.loads(json.dumps(ledger))
    changes, region_changes, accepted, rejected, seen = {}, {}, [], [], set()
    records = capture.get('observations')
    if not isinstance(records, list):
        raise ValueError('observations must be an array')
    for row in records:
        if not isinstance(row, dict):
            raise ValueError('Each observation must be an object')
        part, region = row.get('part'), row.get('region')
        source_key = row.get('source', 'pcpp' if capture['schema'] == 'msfs-pcpp-refresh-v1' else '')
        if not isinstance(part, str) or not isinstance(region, str):
            raise ValueError('Each observation needs a string part and region.')
        key = (part, region)
        if key in seen:
            raise ValueError(f'Duplicate observation: {part}/{region}')
        seen.add(key)
        why = None
        if part not in base:
            why = 'unknown price key'
        elif region not in REGIONS or row.get('cur') != REGIONS[region]:
            why = 'unsupported region or currency mismatch'
        elif f'{region}_{REGIONS[region].lower()}' not in region_cols:
            why = 'region is not configured in build_prices_regions.csv'
        try:
            observed = timestamp(row.get('capturedAt', ''))
            amount = row.get('amount')
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not 0 < amount < 1_000_000:
                why = why or 'invalid price'
            if not started <= observed <= utcnow():
                why = why or 'not captured during this refresh'
            if row.get('stock') is not True or row.get('suspect'):
                why = why or 'out of stock / unconfirmed stock / flagged price'
            if row.get('ambiguous'):
                why = why or 'ambiguous product mapping'
            source = row.get('url', '')
            from urllib.parse import urlparse
            url = urlparse(source)
            expected_host = 'pcpartpicker.com' if region == 'us' else f'{region}.pcpartpicker.com'
            allowed_hosts = {expected_host} if source_key == 'pcpp' else NL_RETAILERS.get(source_key, set()) if region == 'nl' else set()
            if url.scheme != 'https' or url.netloc not in allowed_hosts:
                why = why or 'source URL does not match region'
            previous = ledger.get(part, {}).get(region)
            if previous and observed <= timestamp(previous['capturedAt']):
                why = why or 'already imported or older than current observation'
        except (ValueError, TypeError, AttributeError):
            why = why or 'invalid/missing capture timestamp or URL'
        if why:
            rejected.append(f'{part}/{region}: {why}')
            continue
        col = f'{region}_{REGIONS[region].lower()}'
        old = base[part]['eur'] if region == 'nl' else regional_by_part.get(part, {}).get(col, '')
        if old and not allow_large and not 0.5 <= amount / float(old) <= 1.5:
            rejected.append(f'{part}/{region}: large change ({old} -> {amount}); inspect, then --allow-large-changes')
            continue
        # Existing hand-entered dates are also a baseline; an older capture cannot replace them.
        date = observed.date().isoformat()
        if region == 'nl' and date < (base[part].get('observed_on') or priced_on):
            rejected.append(f'{part}/{region}: older than current canonical price')
            continue
        region_changes.setdefault(part, {})[col] = f'{amount:g}'
        if region == 'nl':
            changes[part] = {'eur': f'{amount:g}', 'src': source_key, 'observed_on': date}
        ledger.setdefault(part, {})[region] = dict(row)
        accepted.append({'part': part, 'region': region, 'old': old, 'new': amount, 'date': date})
    # Conservatively retain the oldest actual NL observation as the global date.
    if changes:
        for part, row in base.items():
            changes.setdefault(part, {})['observed_on'] = changes.get(part, {}).get('observed_on') or row.get('observed_on') or priced_on
        dates = [c['observed_on'] for c in changes.values()]
        changes['priced_on'] = {'eur': min(dates)}
    refreshed_nl = {r['part'] for r in accepted if r['region'] == 'nl'}
    report = {'session': session, 'accepted': accepted, 'skipped': rejected,
              'not_refreshed_nl': sorted(set(base) - refreshed_nl)}
    files = {}
    if accepted:
        if changes:
            files['build_prices.csv'] = csv_updates(root / 'build_prices.csv', changes, ('observed_on',))
        files['build_prices_regions.csv'] = csv_updates(root / 'build_prices_regions.csv', region_changes)
        files['build_price_observations.json'] = json.dumps(ledger, indent=2, ensure_ascii=False) + '\n'
    return report, files


def apply_changes(root, files):
    """Back up exact inputs/outputs and roll back if regeneration fails."""
    names = set(files) | {'public/builds.json', 'tierlist_card_build.html'}
    backup = root / '.price-refresh' / 'backups' / (utcnow().strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8])
    originals = {name: (root / name).read_bytes() if (root / name).exists() else None for name in names}
    backup.mkdir(parents=True)
    for name, data in originals.items():
        if data is not None:
            dest = backup / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    try:
        for name, content in files.items():
            (root / name).write_text(content, encoding='utf-8', newline='')
        subprocess.run([sys.executable, str(root / 'make_build_table.py')], cwd=root, check=True)
    except BaseException:
        for name, data in originals.items():
            if data is None:
                (root / name).unlink(missing_ok=True)
            else:
                (root / name).write_bytes(data)
        raise
    print(f'Applied and regenerated builds. Backup: {backup}')
    print('Curated part choices and PNGs still need a review; no commit or publish was performed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', nargs='?', type=Path, help='Downloaded refresh JSON; omit for guided setup')
    parser.add_argument('--prepare', action='store_true', help='Write setup and exit without waiting')
    parser.add_argument('--apply', action='store_true', help='Apply accepted observations after printing the review')
    parser.add_argument('--allow-large-changes', action='store_true', help='Accept reviewed changes outside -50%%/+50%%')
    args = parser.parse_args()
    guided = args.capture is None
    if guided:
        prepare(ROOT)
        if args.prepare or not sys.stdin.isatty():
            return
        value = input('\nDownloaded refresh JSON path (Enter to exit): ').strip().strip('"')
        if not value:
            return
        args.capture = Path(value)
    capture = json.loads(args.capture.read_text(encoding='utf-8-sig'))
    report, files = review(ROOT, capture, args.allow_large_changes)
    folder = ROOT / '.price-refresh'
    folder.mkdir(exist_ok=True)
    (folder / 'review.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'\n{len(report["accepted"])} accepted observations:')
    for row in report['accepted']:
        print(f'  {row["region"]}: {row["part"]}: {row["old"] or "missing"} -> {row["new"]:g} ({row["date"]})')
    print(f'{len(report["skipped"])} skipped:')
    for reason in report['skipped']:
        print(f'  {reason}')
    print(f'NL parts not refreshed: {len(report["not_refreshed_nl"])}')
    print('  ' + ', '.join(report['not_refreshed_nl']))
    print(f'Full review: {folder / "review.json"}')
    if not files:
        print('Nothing to apply.')
        return
    apply = args.apply
    if guided and not apply:
        apply = input('Apply accepted prices and regenerate builds? [y/N] ').strip().lower() == 'y'
    if apply:
        apply_changes(ROOT, files)
    else:
        print('Review only. Re-run with the capture path and --apply to update.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Price refresh failed: {exc}', file=sys.stderr)
        sys.exit(1)
