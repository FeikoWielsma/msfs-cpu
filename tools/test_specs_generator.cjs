// Exercise the actual generator against the published catalogue, without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const path = require('node:path');
const root = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'src/specs.ts'), 'utf8')
  .replace('import "./specs.css";', '').replace(/boot\(\);\s*$/, '')
  + '\nglobalThis.api = { generate, candidates, gen, readGenUrl, setDoc: d => DOC = d };';
const context = { localStorage: { getItem: () => null }, location: { search: '' }, URLSearchParams };
vm.createContext(context);
vm.runInContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context);
const { api } = context;
const doc = JSON.parse(fs.readFileSync(path.join(root, 'public/builds.json'), 'utf8'));
api.setDoc(doc);
assert.equal(api.gen.allow8, true);
assert.equal(api.gen.budget, 1000);
const state = { ...api.gen, cpu: new Set(['AMD', 'Intel']), gpu: new Set(['AMD', 'Nvidia', 'Intel']) };
const all = api.candidates(doc, '1080p', state);
assert.ok(all.length);
const floor = Math.min(...all.map(c => c.eur));
const fullFloor = Math.min(...all.filter(c => !c.mem.min).map(c => c.eur));
assert.ok(floor < fullFloor);
assert.equal(api.generate(doc, '1080p', { ...state, budget: floor - 1 }).ok, false);
for (const budget of [floor, fullFloor, 1500, 5000]) {
  const result = api.generate(doc, '1080p', { ...state, budget });
  assert.equal(result.ok, true);
  assert.ok(result.total <= budget + 1e-6);
  assert.ok(Math.abs(result.items.reduce((n, i) => n + i.eur, 0) - result.total) < 1e-6);
  assert.equal(result.mem.part.startsWith('2x8GB'), budget < fullFloor);
}
assert.equal(api.generate(doc, '1080p', { ...state, budget: floor, allow8: false }).ok, false);
for (const resolution of ['1440p', '4K']) {
  assert.ok(api.candidates(doc, resolution, state).every(c => c.gpu.vram >= 16));
}
for (const [search, expected] of [['', true], ['?vram8=0', false], ['?vram8=1', true]]) {
  context.location.search = search;
  api.readGenUrl();
  assert.equal(api.gen.allow8, expected);
}
assert.equal(doc.builds.filter(b => b.tier === 'budget').length, 6);
for (const build of doc.builds) {
  assert.ok(Math.abs(build.items.reduce((n, i) => n + i.eur, 0) - build.eur) < 1e-6);
}
console.log('Budget generator: floor, RAM fallback, totals, VRAM policy and shared links passed.');
