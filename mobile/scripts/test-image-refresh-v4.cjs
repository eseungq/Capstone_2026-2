const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const ts = require('typescript');
Module._extensions['.ts'] = (module, filename) => {
  module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename, compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS},
  }).outputText, filename);
};
const {createImageErrorRefreshBudgetV4, imageExpiryRefreshDelayV4} = require('../src/api/backendV4/imageRefreshBudgetV4.ts');

test('changing signed URLs cannot cause more than two automatic failure refreshes per visit', () => {
  const budget = createImageErrorRefreshBudgetV4();
  assert.equal(budget.exhausted(), false);
  assert.deepEqual(Array.from({length:10},()=>budget.take()), [true,true,false,false,false,false,false,false,false,false]);
  assert.equal(budget.exhausted(), true);
  budget.reset();
  assert.equal(budget.take(), true);
  assert.equal(createImageErrorRefreshBudgetV4().take(), true);
});
test('expiry updates can happen normally but near-expired replies cannot create a tight loop', () => {
  const now = 100_000;
  assert.equal(imageExpiryRefreshDelayV4(now + 600_000, null, now), 570_000);
  assert.equal(imageExpiryRefreshDelayV4(now - 1, null, now), 0);
  assert.equal(imageExpiryRefreshDelayV4(now - 1, now - 500, now), 29_500);
  assert.equal(imageExpiryRefreshDelayV4(now - 1, now - 31_000, now), 0);
});
