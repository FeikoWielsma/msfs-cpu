// No dependencies or price-site requests. Run: node tools/test_pcpp_refresh.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const storage = new Map();
const context = vm.createContext({
  document: { readyState: 'loading', addEventListener() {} },
  location: { hostname: 'nl.pcpartpicker.com' }, window: {},
  GM_getValue: (key, fallback) => storage.get(key) ?? fallback,
  GM_setValue: (key, value) => storage.set(key, value),
  GM_registerMenuCommand() {},
});
vm.runInContext(fs.readFileSync(path.join(__dirname, 'pcpp-price-capture.user.js'), 'utf8'), context);
const api = context.window.__pcppCapture;
assert.throws(() => api.exportRefresh(), /Import setup/);
// Use Python's real generated patterns, including every canonical CPU/GPU.
const setup = JSON.parse(execFileSync('python', ['-c',
  "import sys,json;sys.path.insert(0,'tools');import refresh_prices as r;print(json.dumps({'schema':'msfs-pcpp-setup-v1','session':{'id':'test','started':r.utcnow().isoformat()},'required':[],'targets':[],'watch':'\\n'.join(p for row in r.read_csv(r.ROOT/'build_prices.csv') if (p:=r.watch_pattern(row['part'])))}))"
], { cwd: path.join(__dirname, '..'), encoding: 'utf8' }));
api.importSetup(setup);
const watches = api.watchlist();
const matches = (part, name, specs = []) => watches.find(w => w.name === part).test({ name, specs });
assert(matches('Ryzen 5 5600', 'AMD Ryzen 5 5600 3.5 GHz'));
assert(!matches('Ryzen 5 5600', 'AMD Ryzen 5 5600X 3.7 GHz'));
assert(!matches('Ryzen 5 9600X', 'AMD Ryzen 5 9600X3D'));
assert(!matches('Core i5-12600K', 'Intel Core i5-12600KF'));
assert(matches('RX 9070', 'Radeon RX 9070 Asus DUAL'));
assert(!matches('RX 9070', 'Radeon RX 9070 XT Asus DUAL'));
assert(!matches('RX 9070', 'Radeon RX 9070 GRE Asus DUAL'));
assert(!matches('RTX 5070', 'GeForce RTX 5070 Ti MSI'));
assert(matches('RTX 5060 Ti 16GB', 'GeForce RTX 5060 Ti Asus', ['16 GB']));
assert(!matches('RTX 5060 Ti 16GB', 'GeForce RTX 5060 Ti Asus', ['8 GB']));
assert.equal(watches.length, 50);
api.importSetup(setup);
assert.equal(api.watchlist().length, 50, 'setup import must be idempotent');
api.importSetup({ ...setup, rules: 'MSFS : Case = case', targets: [
  { path: '/products/power-supply/', regions: ['nl'], label: 'psu_750a', single: true },
  { path: '/products/power-supply/', regions: ['nl'], label: 'psu_750b', single: true },
  { path: '/products/video-card/#sort=price', regions: ['nl'], label: '5080', query: 'RTX 5080' },
  { path: '/products/video-card/#sort=price', regions: ['nl'], label: '5090', query: 'RTX 5090' },
] });
assert.equal(JSON.parse(storage.get('pcpp_targets')).length, 4, 'single-part targets and distinct queries may share a category');
assert.equal(JSON.parse(storage.get('pcpp_rules')), 'MSFS : Case = case');
const row = { amount: 123.45, cur: 'EUR', at: '2026-01-01', stock: false, suspect: 300,
  url: 'https://nl.pcpartpicker.com/products/cpu/', capturedAt: new Date().toISOString() };
api.prices()['example'] = { nl: row };
const output = JSON.parse(JSON.stringify(api.exportRefresh()));
assert.equal(output.observations[0].stock, false);
assert.equal(output.observations[0].suspect, 300);
assert.equal(output.observations[0].at, '2026-01-01');
assert.equal(output.observations[0].region, 'nl');
assert.equal(output.session.id, 'test');
assert.throws(() => api.importSetup({ ...setup, targets: [{ path: '//evil.example', regions: ['nl'] }] }), /Invalid target/);
console.log('PCPP setup, SKU matching, and lossless refresh export checks passed.');
