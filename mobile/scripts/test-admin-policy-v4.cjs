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
  createPolicyVisitV4,
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

test('a pass-only change cannot reuse a version with different automatic FAIL settings, bounds or evidence', () => {
  const active = decodeAdminPolicyV4({
    ...ORIGINAL, autoFailEnabled: true, failThreshold: 0.9966, failValidatedMin: 0.99, failValidatedMax: 1,
    metrics: { autoFail: { count: 50, tested: true }, strata: [1, 2] },
  });
  const candidate = { ...active, policyId: 'new-id', active: false, passThreshold: 0.01 };
  for (const change of [
    { autoFailEnabled: false }, { autoFailEnabled: null }, { failThreshold: 0.997 },
    { failValidatedMin: 0.98 }, { failValidatedMax: 0.999 }, { validatedMin: 0.009 },
    { validatedMax: 0.02 }, { metrics: null }, { metrics: { ...active.metrics, strata: [2, 1] } },
  ]) {
    assert.equal(findEquivalentPolicyVersionV4([{ ...candidate, ...change }], active, 0.01), null);
  }
  const same = { ...candidate, metrics: { strata: [1, 2], autoFail: { tested: true, count: 50 } } };
  assert.equal(findEquivalentPolicyVersionV4([same], active, 0.01), same);
  const alsoSame = { ...same, passThreshold: active.passThreshold };
  assert.equal(findEquivalentPolicyVersionV4([alsoSame, active], active, active.passThreshold), active);
  const legacy = decodeAdminPolicyV4(ORIGINAL);
  const disabled = { ...legacy, autoFailEnabled: false, passThreshold: 0.01 };
  assert.equal(findEquivalentPolicyVersionV4([disabled], legacy, 0.01), null);
});

test('pass threshold save requires the server to preserve automatic FAIL settings', async () => {
  const base = decodeAdminPolicyV4({
    ...ORIGINAL, autoFailEnabled: true, failThreshold: 0.9966, failValidatedMin: 0.9966, failValidatedMax: 0.9966,
  });
  const reply = { ...base, passThreshold: 0.012, basedOnPolicyId: base.policyId, active: false, policyId: 'saved' };
  const { transport, calls } = fakeTransport({ thresholdReply: { ...reply, autoFailEnabled: false } });
  await assert.rejects(createAdminPolicyServiceV4(transport).saveNewVersion(base, '1.20'), /승계한 설정/);
  assert.equal(calls.length, 1);
  const valid = fakeTransport({ thresholdReply: reply });
  assert.equal((await createAdminPolicyServiceV4(valid.transport).saveNewVersion(base, '1.20')).autoFailEnabled, true);
});

test('a pass threshold at or above the automatic FAIL threshold is rejected before saving', async () => {
  const base = { ...ORIGINAL, failThreshold: 0.015, autoFailEnabled: false };
  const { transport, calls } = fakeTransport();
  for (const percent of ['1.50', '1.60']) {
    await assert.rejects(createAdminPolicyServiceV4(transport).saveNewVersion(base, percent), /자동 불량 기준보다 낮아야/);
  }
  assert.equal(calls.length, 0);
});

test('four-decimal percent matches exact server bounds and rejects equality with automatic FAIL', async () => {
  const boundary = 0.009005;
  const base = { ...ORIGINAL, passThreshold: 0.009006, validatedMin: boundary, validatedMax: 0.009007,
    failThreshold: 0.009007, failValidatedMin: 0.009007, failValidatedMax: 0.009007 };
  const reply = { ...base, policyId: 'new-boundary', basedOnPolicyId: base.policyId,
    active: false, passThreshold: boundary };
  const { transport, calls } = fakeTransport({ thresholdReply: reply });
  const service = createAdminPolicyServiceV4(transport);

  const saved = await service.saveNewVersion(base, '0.9005');
  assert.equal(calls[0].options.body.passThreshold, boundary);
  assert.equal(percentageTextV4(saved.passThreshold, 4), '0.9005%');
  assert.throws(() => parsePolicyPercentInputV4('0.9004', base), /0\.9005%~0\.9007%/);
  assert.equal(parsePolicyPercentInputV4('0.9007', { ...base, failThreshold: null }), base.validatedMax);
  const touchingFail = { ...base, passThreshold: 0.009004, validatedMin: 0.009003,
    failThreshold: boundary, failValidatedMin: boundary };
  await assert.rejects(service.saveNewVersion(touchingFail, '0.9005'), /자동 불량 기준보다 낮아야/);
  assert.equal(calls.length, 1);
});

test('a confirmation from a closed policy screen cannot submit after refocus or re-login', async () => {
  const { transport, calls } = fakeTransport({ activateReply: { ...EXISTING_T1, active: true } });
  let epoch = 1;
  const auth = { ...transport, sessionEpoch: () => epoch };
  const oldVisit = createPolicyVisitV4(auth);
  const oldService = createAdminPolicyServiceV4(oldVisit.transport);
  oldVisit.close();
  const currentVisit = createPolicyVisitV4(auth);
  await assert.rejects(oldService.activate(EXISTING_T1), /정책 화면/);
  assert.equal(calls.length, 0);
  const nextService = createAdminPolicyServiceV4(currentVisit.transport);
  await nextService.activate(EXISTING_T1);
  epoch++;
  await assert.rejects(nextService.activate(EXISTING_T1), /정책 화면/);
  assert.equal(calls.length, 1);
});

test('a delayed policy preflight and the last role check before POST stay bound to the initiating visit', async () => {
  let epoch = 1;
  let finishList;
  let posts = 0;
  const auth = {
    sessionEpoch: () => epoch,
    async restore() { return { signedIn: true, role: 'ADMIN', loginId: 'admin' }; },
    authorizedRequest(path, options) {
      if (options.method === 'GET') return new Promise(resolve => { finishList = resolve; });
      posts++;
      return Promise.resolve({ ...EXISTING_T1, active: true });
    },
  };
  const oldVisit = createPolicyVisitV4(auth);
  const oldService = createAdminPolicyServiceV4(oldVisit.transport);
  const oldFlow = oldService.list().then(() => oldService.activate(EXISTING_T1));
  await new Promise(resolve => setImmediate(resolve));
  oldVisit.close();
  finishList([ORIGINAL, EXISTING_T1]);
  await assert.rejects(oldFlow, /정책 화면/);

  const newVisit = createPolicyVisitV4(auth);
  const newService = createAdminPolicyServiceV4(newVisit.transport);
  let finishRestore;
  auth.restore = () => new Promise(resolve => { finishRestore = resolve; });
  const pendingPost = newService.activate(EXISTING_T1);
  epoch++;
  finishRestore({ signedIn: true, role: 'ADMIN', loginId: 'next-admin' });
  await assert.rejects(pendingPost, /정책 화면/);
  assert.equal(posts, 0);
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
  await assert.rejects(() => service.saveNewVersion({ ...ORIGINAL, partCode: 'DOOR' }, '1.20'), /선택한 부품/);
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
  await assert.rejects(() => createAdminPolicyServiceV4(foreign.transport).activate({ ...EXISTING_T1, partCode: 'DOOR' }), /선택한 부품/);
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

for (const partCode of ['DOOR', 'FRAME', 'COWL_COVER']) {
  test(partCode + ' policy service scopes reads and writes and rejects other-part responses', async () => {
    const base = {...ORIGINAL, partCode};
    const saved = {...EXISTING_T1, partCode};
    const h = fakeTransport({list:[base,saved], thresholdReply:saved, activateReply:{...saved,active:true}});
    const service = createAdminPolicyServiceV4(h.transport,partCode);
    assert.equal((await service.list())[0].partCode,partCode);
    assert.equal(h.calls[0].path,'/admin/policies?partCode='+partCode);
    assert.equal(findEquivalentPolicyVersionV4([saved],base,0.01),saved);
    assert.equal((await service.saveNewVersion(base,'1.00')).partCode,partCode);
    assert.equal((await service.activate(saved)).partCode,partCode);
    const otherPart = partCode==='DOOR'?'FRAME':'DOOR';
    const count=h.calls.length;
    await assert.rejects(service.saveNewVersion({...base,partCode:otherPart},'1.00'),/선택한 부품/);
    await assert.rejects(service.activate({...saved,partCode:otherPart}),/선택한 부품/);
    assert.equal(h.calls.length,count);
    const wrong=fakeTransport({list:[{...base,partCode:otherPart}],thresholdReply:{...saved,partCode:otherPart},activateReply:{...saved,partCode:otherPart,active:true}});
    const wrongService=createAdminPolicyServiceV4(wrong.transport,partCode);
    await assert.rejects(wrongService.list(),/부품/);
    await assert.rejects(wrongService.saveNewVersion(base,'1.00'),/승계한 설정/);
    await assert.rejects(wrongService.activate(saved),/활성 상태/);
  });
}
test('unsupported policy parts are rejected before transport access', () => {
  assert.throws(()=>createAdminPolicyServiceV4(fakeTransport().transport,'UNKNOWN'),/지원하지 않는/);
});
test('changing policy part invalidates old preflight and old confirmation without POST', async () => {
  const h=fakeTransport({list:[ORIGINAL]});
  const auth={...h.transport,sessionEpoch:()=>1};
  const oldVisit=createPolicyVisitV4(auth);
  const oldService=createAdminPolicyServiceV4(oldVisit.transport,'COWL_COVER');
  const pending=oldService.list();
  oldVisit.close();
  await assert.rejects(pending,/정책 화면/);
  await assert.rejects(oldService.saveNewVersion(ORIGINAL,'1.20'),/정책 화면/);
  assert.equal(h.calls.filter(c=>c.options.method==='POST').length,0);
});
test('policy part selector uses Korean labels and resets the full visit on switch', () => {
  const source=fs.readFileSync(path.join(__dirname,'../src/app/policy-live.tsx'),'utf8');
  assert.match(source, /<PolicyPartScreen key={partCode}/);
  assert.match(source, /focusedVisit.current\?\.close\(\)/);
  assert.match(source, /partLabelV4\(code\)/);
  assert.match(source, /createAdminPolicyServiceV4\(visit.transport, partCode\)/);
  assert.match(source, /writing!==null \|\| writeLock.current/);
});
