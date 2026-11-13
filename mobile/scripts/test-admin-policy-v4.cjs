/**
 * API v4 §6.9 policy service regression checks without a live backend.
 * Run: npm run test:admin-policy
 * Uses only Node test/assert and the existing TypeScript dev dependency.
 */
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

// Load the actual source TS modules, not a reimplementation.
Module._extensions['.ts'] = (module, filename) => {
  const source = fs.readFileSync(filename, 'utf8');
  const js = ts.transpileModule(source, {
    fileName: filename,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  module._compile(js, filename);
};

const {
  COWL_PART_CODE_V4,
  createAdminPolicyServiceV4,
  findEquivalentPolicyVersionV4,
  decodeAdminPolicyV4,
  decodeCowlPolicyListV4,
  parsePolicyPercentInputV4,
  percentageTextV4,
  rootPolicyForV4,
} = require(path.join(__dirname, '../src/api/backendV4/adminPolicyServiceV4.ts'));

const ORIGINAL = Object.freeze({
  policyId: 'policy-base-uuid', policyVersion: 'cowl-e08-demo-0163',
  partCode: 'COWL_COVER', modelVersion: 'cowl-e08-model',
  calibratorVersion: 'cowl-e08-calibrator',
  passThreshold: 0.0163, validatedMin: 0.01, validatedMax: 0.0163,
  ready: true, active: true,
  metrics: { sampleCount: 2531 },
  basedOnPolicyId: null,
  createdAt: '2026-11-11T09:00:00+09:00',
  activatedAt: '2026-11-11T09:01:00+09:00',
});
const EXISTING_T1 = Object.freeze({
  ...ORIGINAL, policyId: 'policy-t1-uuid', policyVersion: 'cowl-e08-demo-0163-t1',
  passThreshold: 0.01, ready: true, active: false,
  basedOnPolicyId: ORIGINAL.policyId, activatedAt: null,
});

function fakeTransport({
  role = 'ADMIN', signedIn = true, list = [ORIGINAL, EXISTING_T1],
  thresholdReply = null, activateReply = null, activateGate = null,
} = {}) {
  const calls = [];
  const transport = {
    async restore() { return { signedIn, role, loginId: signedIn ? 'test-admin' : null }; },
    async authorizedRequest(requestPath, options) {
      calls.push({ path: requestPath, options });
      if (requestPath.startsWith('/admin/policies?')) return list;
      if (requestPath.endsWith('/threshold')) {
        if (!thresholdReply) throw new Error('unexpected threshold POST');
        return thresholdReply;
      }
      if (requestPath.endsWith('/activate')) {
        if (activateGate) await activateGate;
        if (!activateReply) throw new Error('unexpected activate POST');
        return activateReply;
      }
      throw new Error('unexpected API path: ' + requestPath);
    },
  };
  return { transport, calls };
}

test('existing 1.00% t1 is reused; no duplicate policy needs to be saved', () => {
  assert.equal(
    findEquivalentPolicyVersionV4([ORIGINAL, EXISTING_T1], ORIGINAL, 0.01)?.policyId,
    EXISTING_T1.policyId,
  );
  assert.equal(findEquivalentPolicyVersionV4([ORIGINAL, EXISTING_T1], ORIGINAL, 0.012), null);
});

test('equivalent policy check requires same model, calibrator, part and ready state', () => {
  const t1 = EXISTING_T1;
  const variants = [
    { ...t1, partCode: 'DOOR' },
    { ...t1, modelVersion: 'some-other-model' },
    { ...t1, calibratorVersion: 'some-other-calibrator' },
    { ...t1, ready: false },
    { ...t1, passThreshold: null },
  ];
  for (const variant of variants) {
    assert.equal(findEquivalentPolicyVersionV4([variant], ORIGINAL, 0.01), null);
  }
  assert.equal(findEquivalentPolicyVersionV4([t1], ORIGINAL, Number.NaN), null);
});

test('refresh before POST detects a policy version created since the initial screen load', () => {
  const firstList = [ORIGINAL];
  const refreshedList = [ORIGINAL, EXISTING_T1];
  assert.equal(findEquivalentPolicyVersionV4(firstList, ORIGINAL, 0.01), null);
  assert.equal(
    findEquivalentPolicyVersionV4(refreshedList, ORIGINAL, 0.01)?.policyId,
    EXISTING_T1.policyId,
  );
});

test('ADMIN GET loads exactly COWL_COVER policies with original 1.63% and existing t1 1.00%', async () => {
  const { transport, calls } = fakeTransport();
  const policies = await createAdminPolicyServiceV4(transport).list();
  assert.equal(policies.length, 2);
  assert.equal(policies[0].passThreshold, 0.0163);
  assert.equal(policies[1].passThreshold, 0.01);
  assert.equal(policies[1].active, false);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, '/admin/policies?partCode=' + encodeURIComponent(COWL_PART_CODE_V4));
  assert.deepEqual(calls[0].options, { method: 'GET' });
});

test('WORKER and logged-out sessions are rejected locally before any API request', async () => {
  for (const config of [{ role: 'WORKER' }, { role: 'ADMIN', signedIn: false }]) {
    const { transport, calls } = fakeTransport(config);
    const service = createAdminPolicyServiceV4(transport);
    await assert.rejects(() => service.list(), /ADMIN/);
    await assert.rejects(() => service.saveNewVersion(ORIGINAL, '1.20'), /ADMIN/);
    await assert.rejects(() => service.activate(EXISTING_T1), /ADMIN/);
    assert.equal(calls.length, 0);
  }
});

test('contract rejects malformed policy, wrong part, duplicate active policy on same model', () => {
  assert.throws(() => decodeAdminPolicyV4({ ...ORIGINAL, ready: false, active: true }), /응답 오류/);
  assert.throws(() => decodeAdminPolicyV4({ ...ORIGINAL, validatedMin: 0.02 }), /validatedMin/);
  assert.throws(() => decodeAdminPolicyV4({ ...ORIGINAL, passThreshold: '1.63%' }), /응답 오류/);
  assert.throws(() => decodeCowlPolicyListV4({ data: [ORIGINAL] }), /배열/);
  assert.throws(() => decodeCowlPolicyListV4([{ ...ORIGINAL, partCode: 'DOOR' }]), /부품/);
  assert.throws(() => decodeCowlPolicyListV4([ORIGINAL, { ...EXISTING_T1, active: true }]), /활성 정책/);
});

test('percentage input converts 1.00 to API 0.01, accepts inclusive bounds, rejects unvalidated values', () => {
  assert.equal(percentageTextV4(0.0163), '1.63%');
  assert.equal(parsePolicyPercentInputV4('1.00', ORIGINAL), 0.01);
  assert.equal(parsePolicyPercentInputV4('1.63', ORIGINAL), 0.0163);
  for (const input of ['0.99', '1.64', 'hello', '1e0', '-1', '1.00001']) {
    assert.throws(() => parsePolicyPercentInputV4(input, ORIGINAL), Error, input);
  }
  assert.throws(() => parsePolicyPercentInputV4('1.20', { ...ORIGINAL, ready: false }), /준비/);
  assert.throws(() => parsePolicyPercentInputV4('1.20', { ...ORIGINAL, validatedMin: null }), /준비/);
});

test('threshold POST sends decimal 0.012, expects a new inactive linked policy; never activates implicitly', async () => {
  const fresh = { ...EXISTING_T1, policyId: 'policy-t2-uuid', policyVersion: 'cowl-e08-demo-0163-t2',
    passThreshold: 0.012, basedOnPolicyId: ORIGINAL.policyId };
  const { transport, calls } = fakeTransport({ thresholdReply: fresh });
  const newPolicy = await createAdminPolicyServiceV4(transport).saveNewVersion(ORIGINAL, '1.20');
  assert.equal(newPolicy.policyId, fresh.policyId);
  assert.equal(newPolicy.active, false);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], {
    path: '/admin/policies/' + encodeURIComponent(ORIGINAL.policyId) + '/threshold',
    options: { method: 'POST', body: { passThreshold: 0.012 } },
  });
});

test('out-of-range and unready threshold writes are blocked before POST', async () => {
  const { transport, calls } = fakeTransport();
  const service = createAdminPolicyServiceV4(transport);
  await assert.rejects(() => service.saveNewVersion(ORIGINAL, '0.80'), /허용 범위/);
  await assert.rejects(() => service.saveNewVersion({ ...ORIGINAL, ready: false }, '1.20'), /활성·준비/);
  await assert.rejects(() => service.saveNewVersion({ ...ORIGINAL, active: false }, '1.20'), /활성·준비/);
  await assert.rejects(() => service.saveNewVersion({ ...ORIGINAL, partCode: 'DOOR' }, '1.20'), /COWL_COVER/);
  assert.equal(calls.length, 0);
});

test('incorrect threshold API response is rejected rather than reporting saved policy', async () => {
  const { transport, calls } = fakeTransport({ thresholdReply: { ...EXISTING_T1, basedOnPolicyId: 'wrong-parent' } });
  await assert.rejects(
    () => createAdminPolicyServiceV4(transport).saveNewVersion(ORIGINAL, '1.00'),
    /새 버전이 비활성/,
  );
  assert.equal(calls.length, 1);
});

test('existing t1 policy activation uses only activate POST and checks active response', async () => {
  const { transport, calls } = fakeTransport({ activateReply: { ...EXISTING_T1, active: true } });
  const applied = await createAdminPolicyServiceV4(transport).activate(EXISTING_T1);
  assert.equal(applied.active, true);
  assert.equal(applied.policyId, EXISTING_T1.policyId);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], {
    path: '/admin/policies/' + encodeURIComponent(EXISTING_T1.policyId) + '/activate',
    options: { method: 'POST' },
  });
});

test('inactive or mismatched activate response is rejected, never considered success', async () => {
  const { transport } = fakeTransport({ activateReply: EXISTING_T1 });
  await assert.rejects(() => createAdminPolicyServiceV4(transport).activate(EXISTING_T1), /활성 상태/);
  const next = fakeTransport({ activateReply: { ...EXISTING_T1, active: true, policyId: 'another-id' } });
  await assert.rejects(() => createAdminPolicyServiceV4(next.transport).activate(EXISTING_T1), /정책 ID/);
  const foreign = fakeTransport();
  await assert.rejects(() => createAdminPolicyServiceV4(foreign.transport).activate({ ...EXISTING_T1, partCode: 'DOOR' }), /COWL_COVER/);
  assert.equal(foreign.calls.length, 0);
});

test('duplicate concurrent POST is prevented; second submit cannot call transport', async () => {
  let release;
  const activationBlocked = new Promise((resolve) => { release = resolve; });
  const { transport, calls } = fakeTransport({
    activateGate: activationBlocked,
    activateReply: { ...EXISTING_T1, active: true },
  });
  const service = createAdminPolicyServiceV4(transport);
  const first = service.activate(EXISTING_T1);
  await assert.rejects(() => service.activate(EXISTING_T1), /진행 중/);
  release();
  await first;
  assert.equal(calls.length, 1);
});

test('original policy is recovered from t1/t2 ancestry; missing links/cycles return null', () => {
  const appliedT1 = { ...EXISTING_T1, active: true };
  const t2 = { ...EXISTING_T1, policyId: 'policy-t2-uuid', basedOnPolicyId: EXISTING_T1.policyId };
  assert.equal(rootPolicyForV4(appliedT1, [appliedT1, ORIGINAL]).policyId, ORIGINAL.policyId);
  assert.equal(rootPolicyForV4(t2, [t2, EXISTING_T1, ORIGINAL]).policyId, ORIGINAL.policyId);
  assert.equal(rootPolicyForV4(t2, [t2]), null);
  const selfReferential = { ...ORIGINAL, basedOnPolicyId: ORIGINAL.policyId };
  assert.equal(rootPolicyForV4(selfReferential, [selfReferential]), null);
});

test('server-side 403 propagates; UI must not treat it as a successful activation', async () => {
  const calls = [];
  const transport = {
    async restore() { return { signedIn: true, role: 'ADMIN', loginId: 'admin' }; },
    async authorizedRequest(requestPath, options) {
      calls.push({ requestPath, options });
      const err = new Error('403 FORBIDDEN');
      err.httpStatus = 403;
      err.code = 'FORBIDDEN';
      throw err;
    },
  };
  await assert.rejects(() => createAdminPolicyServiceV4(transport).activate(EXISTING_T1), /403 FORBIDDEN/);
  assert.equal(calls.length, 1);
});
