/**
 * 2026-11-12 DOOR AUTO_PASS Mock scenario regression tests.
 * Run: npm run test:door-demo
 * No backend, device requests, policy writes, or push notifications.
 */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

Module._extensions['.ts'] = (module, filename) => {
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  module._compile(compiled, filename);
};

const root = path.join(__dirname, '..');
const { DOOR_AUTOPASS_DEMO_V4: S, evaluateMockDoorAutopassDemoV4: evaluate } =
  require(path.join(root, 'src/api/backendV4/demoPolicyScenarioV4.ts'));
const { validateThresholdEditV4 } =
  require(path.join(root, 'src/api/backendV4/policyThresholdV4.ts'));

test('11/12 agreed DOOR percentages use fractions and preserve 0.92% default', () => {
  assert.equal(S.partCode, 'DOOR');
  assert.equal(S.validatedMin, 0.0084);
  assert.equal(S.validatedMax, 0.0092);
  assert.equal(S.defaultThreshold, 0.0092);
  assert.equal(S.initialThreshold, 0.0084);
  assert.equal(S.adjustedThreshold, 0.0092);
  assert.equal(S.sampleCalibratedDefectProbability, 0.0088);
  assert.equal(S.samplePrediction, 'GOOD');
  assert.equal((S.initialThreshold * 100).toFixed(2), '0.84');
  assert.equal((S.adjustedThreshold * 100).toFixed(2), '0.92');
  assert.equal((S.sampleCalibratedDefectProbability * 100).toFixed(2), '0.88');
});

test('GOOD at 0.88% is REVIEW with 0.84%, AUTO_PASS with 0.92%', () => {
  assert.equal(evaluate('GOOD', S.sampleCalibratedDefectProbability, S.initialThreshold, true), 'REVIEW');
  assert.equal(evaluate('GOOD', S.sampleCalibratedDefectProbability, S.adjustedThreshold, true), 'AUTO_PASS');
  assert.equal(evaluate('GOOD', S.sampleCalibratedDefectProbability, S.defaultThreshold, true), 'AUTO_PASS');
});

test('saved but inactive version must still evaluate under initial 0.84%', () => {
  // UI uses initialThreshold until phase === ACTIVE. Saving alone cannot apply policy.
  const savedButInactiveThreshold = S.initialThreshold;
  assert.equal(evaluate('GOOD', S.sampleCalibratedDefectProbability, savedButInactiveThreshold, true), 'REVIEW');
  assert.notEqual(S.basePolicyVersion, S.adjustedPolicyVersion);
});

test('DEFECT, absent calibration, and inactive/unready policy never AUTO_PASS', () => {
  assert.equal(evaluate('DEFECT', 0, S.adjustedThreshold, true), 'REVIEW');
  assert.equal(evaluate('GOOD', null, S.adjustedThreshold, true), 'REVIEW');
  assert.equal(evaluate('GOOD', 0.0088, S.adjustedThreshold, false), 'REVIEW');
  assert.equal(evaluate('GOOD', Number.NaN, S.adjustedThreshold, true), 'REVIEW');
});

test('threshold validator accepts both bounds; rejects outside and malformed fractions', () => {
  const bounds = { validatedMin: S.validatedMin, validatedMax: S.validatedMax, evidenceVerified: true };
  assert.deepEqual(validateThresholdEditV4('0.0084', bounds), { ok: true, value: 0.0084 });
  assert.deepEqual(validateThresholdEditV4('0.0092', bounds), { ok: true, value: 0.0092 });
  assert.equal(validateThresholdEditV4('0.0083', bounds).reason, 'OUT_OF_RANGE');
  assert.equal(validateThresholdEditV4('0.0093', bounds).reason, 'OUT_OF_RANGE');
  assert.equal(validateThresholdEditV4('0.92', bounds).reason, 'OUT_OF_RANGE');
  assert.equal(validateThresholdEditV4('0.0092', { ...bounds, evidenceVerified: false }).reason, 'UNVERIFIED');
});

test('Mock app screens and README contain updated labels, not previous 30/35/32%', () => {
  for (const p of ['src/app/policy.tsx', 'src/app/policy-adjust.tsx', 'src/app/policy-assumed.tsx', 'README.md']) {
    const text = fs.readFileSync(path.join(root, p), 'utf8');
    assert.doesNotMatch(text, /(?:30%|35%|32%|0\.2801|0\.3752)/, p);
    assert.match(text, /0\.84%/, p);
    assert.match(text, /0\.92%/, p);
  }
  const screen = fs.readFileSync(path.join(root, 'src/app/policy-assumed.tsx'), 'utf8');
  assert.match(screen, /0\.88%/);
  assert.match(screen, /REVIEW \(ABOVE_THRESHOLD\)/);
  assert.match(screen, /SYSTEM 최종 PASS/);
  assert.match(screen, /실제 e02/);
});


test('Mock WORKER entry is distinct from ADMIN; policy screens guard WORKER role', () => {
  const login = fs.readFileSync(path.join(root, 'src/app/index.tsx'), 'utf8');
  const settings = fs.readFileSync(path.join(root, 'src/app/settings.tsx'), 'utf8');
  const policy = fs.readFileSync(path.join(root, 'src/app/policy.tsx'), 'utf8');
  const mockPolicy = fs.readFileSync(path.join(root, 'src/app/policy-assumed.tsx'), 'utf8');

  assert.match(login, /현장 작업자 시연으로 이동 · Mock/);
  assert.match(login, /handleWorkerPreview/);
  assert.match(login, /role: 'WORKER', mode: 'mock'/);
  assert.match(login, /role: 'ADMIN'/);
  assert.match(settings, /isAdmin\s*&&\s*mode\s*===\s*'mock'/);
  assert.match(policy, /role\s*!==\s*'ADMIN'/);
  assert.match(mockPolicy, /role\s*!==\s*'ADMIN'/);
});
