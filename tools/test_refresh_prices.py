"""Offline price-import integration checks; all mutations happen in temp directories."""
import copy
from contextlib import redirect_stdout
import io
import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import refresh_prices as refresh


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('build_prices.csv', 'build_prices_regions.csv'):
            shutil.copy2(refresh.ROOT / name, self.root / name)
        now = refresh.utcnow()
        self.capture = {
            'schema': 'msfs-pcpp-refresh-v1',
            'session': {'id': 'test', 'started': (now - dt.timedelta(minutes=1)).isoformat()},
            'observations': [{
                'part': 'Ryzen 7 9800X3D', 'region': 'nl', 'cur': 'EUR', 'amount': 379.95,
                'stock': True, 'suspect': None, 'capturedAt': now.isoformat(),
                'url': 'https://nl.pcpartpicker.com/products/cpu/',
                'seen': 'AMD Ryzen 7 9800X3D',
            }],
        }

    def test_partial_import_syncs_nl_preserves_comments_dates_and_other_regions(self):
        before = {r['part']: r for r in refresh.read_csv(self.root / 'build_prices_regions.csv')}
        original_prices = {r['part']: r for r in refresh.read_csv(self.root / 'build_prices.csv')}
        original_date = original_prices['Ryzen 7 7800X3D'].get('observed_on') or original_prices['priced_on']['eur']
        report, files = refresh.review(self.root, self.capture)
        self.assertEqual(len(report['accepted']), 1)
        self.assertEqual(len(report['not_refreshed_nl']), 73)
        self.assertIn('# --- CPUs', files['build_prices.csv'])
        for name, data in files.items():
            (self.root / name).write_text(data, encoding='utf-8')
        prices = {r['part']: r for r in refresh.read_csv(self.root / 'build_prices.csv')}
        regions = {r['part']: r for r in refresh.read_csv(self.root / 'build_prices_regions.csv')}
        self.assertEqual(prices['Ryzen 7 9800X3D']['eur'], '379.95')
        self.assertEqual(regions['Ryzen 7 9800X3D']['nl_eur'], '379.95')
        self.assertEqual(regions['Ryzen 7 9800X3D']['de_eur'], before['Ryzen 7 9800X3D']['de_eur'])
        self.assertEqual(prices['priced_on']['eur'], '2026-07-26')
        self.assertEqual(prices['Ryzen 7 7800X3D']['observed_on'], original_date)
        second, _ = refresh.review(self.root, self.capture)
        self.assertFalse(second['accepted'])
        self.assertIn('already imported', second['skipped'][0])

    def test_prepare_reuses_runnable_collection_config(self):
        folder = self.root / '.price-refresh'
        folder.mkdir()
        config = {'schema': 'msfs-pcpp-collection-config-v1',
                  'targets': [{'path': '/products/memory/', 'regions': ['nl']}],
                  'watch': '32GB DDR5-6000 = approved kit', 'rules': 'AM5 : Motherboard = mb_am5'}
        (folder / 'collection-config.json').write_text(json.dumps(config), encoding='utf-8')
        with redirect_stdout(io.StringIO()):
            setup_path = refresh.prepare(self.root)
        setup = json.loads(setup_path.read_text(encoding='utf-8'))
        self.assertEqual(setup['targets'], config['targets'])
        self.assertEqual(setup['watch'], config['watch'])
        self.assertEqual(setup['rules'], config['rules'])
        self.assertIn('started', setup['session'])

    def test_rejects_bad_observations_without_changes(self):
        cases = [
            {'cur': 'USD'}, {'stock': False}, {'suspect': 399}, {'amount': 0},
            {'amount': float('nan')}, {'amount': 1000}, {'ambiguous': True},
            {'url': 'https://de.pcpartpicker.com/products/cpu/'},
            {'capturedAt': '2026-01-01T00:00:00Z'}, {'capturedAt': ''},
            {'part': 'unmapped SKU'}, {'region': 'zz'},
        ]
        for values in cases:
            with self.subTest(values=values):
                capture = copy.deepcopy(self.capture)
                capture['observations'][0].update(values)
                report, files = refresh.review(self.root, capture)
                self.assertFalse(report['accepted'])
                self.assertFalse(files)

    def test_large_changes_are_explicit_and_duplicate_records_are_invalid(self):
        self.capture['observations'][0]['amount'] = 1000
        report, _ = refresh.review(self.root, self.capture, allow_large=True)
        self.assertEqual(len(report['accepted']), 1)
        self.capture['observations'] *= 2
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            refresh.review(self.root, self.capture)

    def test_non_nl_import_does_not_change_canonical_prices(self):
        self.capture['observations'][0].update(region='de', url='https://de.pcpartpicker.com/products/cpu/')
        report, files = refresh.review(self.root, self.capture)
        self.assertEqual(len(report['accepted']), 1)
        self.assertNotIn('build_prices.csv', files)

    def test_direct_retailer_quotes_keep_source_and_reject_wrong_hosts(self):
        self.capture['schema'] = 'msfs-price-refresh-v1'
        row = self.capture['observations'][0]
        row.update(source='megekko', url='https://www.megekko.nl/product/known-product')
        report, files = refresh.review(self.root, self.capture)
        self.assertEqual(len(report['accepted']), 1)
        self.assertIn('megekko', files['build_prices.csv'])
        self.assertIn('https://www.megekko.nl/product/known-product', files['build_price_observations.json'])
        row['url'] = 'https://unverified.example/product'
        report, files = refresh.review(self.root, self.capture)
        self.assertFalse(report['accepted'])
        self.assertFalse(files)

    def test_regeneration_failure_rolls_back_all_files(self):
        originals = {name: (self.root / name).read_bytes() for name in ('build_prices.csv', 'build_prices_regions.csv')}
        _, files = refresh.review(self.root, self.capture)
        with patch.object(refresh.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'test')):
            with self.assertRaises(subprocess.CalledProcessError):
                refresh.apply_changes(self.root, files)
        for name, data in originals.items():
            self.assertEqual((self.root / name).read_bytes(), data)
        self.assertFalse((self.root / 'build_price_observations.json').exists())

    def test_real_build_regeneration_on_isolated_copy(self):
        # Exercise the actual generator with all benchmark inputs, never the working tree.
        for pattern in ('*.py', '*.csv', 'tierlist_card_build.html'):
            for path in refresh.ROOT.glob(pattern):
                shutil.copy2(path, self.root / path.name)
        (self.root / 'public').mkdir()
        for name in ('data.json', 'gpu_data.json'):
            shutil.copy2(refresh.ROOT / 'public' / name, self.root / 'public' / name)
        _, files = refresh.review(self.root, self.capture)
        refresh.apply_changes(self.root, files)
        doc = json.loads((self.root / 'public/builds.json').read_text(encoding='utf-8'))
        price = next(p for p in doc['prices'] if p['part'] == 'Ryzen 7 9800X3D')
        self.assertEqual(price['eur'], 380)
        self.assertEqual(doc['priced_on'], '2026-07-26')
        self.assertEqual(price['observed_on'], refresh.utcnow().date().isoformat())
        self.assertEqual(doc['latest_priced_on'], refresh.utcnow().date().isoformat())
        stale_cpu = next(c for c in doc['catalogue']['cpus'] if c['part'] == 'Core Ultra 5 250K Plus')
        self.assertNotIn('nl', stale_cpu['by'])
        self.assertIn('de', stale_cpu['by'], 'regional observations must remain independent')
        self.assertEqual(len(doc['builds']), 24)


if __name__ == '__main__':
    unittest.main()
