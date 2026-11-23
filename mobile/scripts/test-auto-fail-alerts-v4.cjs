/**
 * AUTO_FAIL in-app polling regression (no server, no writes, no Expo/APNs).
 * Run: npm run test:auto-fail-alerts
 */
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

Module._extensions['.ts'] = (module, filename) => {
  const source = fs.readFileSync(filename, 'utf8');
  module._compile(ts.transpileModule(source, {
    fileName: filename,
    compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS},
  }).outputText, filename);
};
const {
  createAutoFailInAppControllerV4, AUTO_FAIL_POLL_MS_V4,
  AUTO_FAIL_PAGE_SIZE_V4,
} = require(path.join(__dirname, '../src/api/backendV4/autoFailInAppCoreV4.ts'));
const {decodeHistoryPageV4} = require(path.join(__dirname, '../src/api/backendV4/inspectionReadCore.ts'));
const {decodeInspectionDetailV4, mapInspectionDetailV4} =
  require(path.join(__dirname, '../src/api/backendV4/adapter.ts'));

function item(n, displayState = 'AUTO_FAIL') {
  return {
    inspectionId: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`,
    inspectionNo: `INS-${String(n).padStart(6, '0')}`,
    partCode: 'COWL_COVER', displayState, receivedAt: '2026-11-23T11:00:00Z',
  };
}
function harness(initial = []) {
  let items = initial;
  let broken = false;
  let source = 'SERVER';
  let now = 0, nextId = 1;
  const timers = new Map(), alerts = [], requests = [];
  const scheduler = {
    setTimeout(cb, ms) { const id=nextId++; timers.set(id, { cb, when: now + ms }); return id; },
    clearTimeout(id) { timers.delete(id); },
  };
  const reader = {
    async history(req) {
      requests.push(req);
      if (broken) throw new Error('network failed');
      return {source, value:{items, page:0, size:100, totalElements:items.length, hasNext:false, pageFormat:'items'}};
    },
  };
  const controller = createAutoFailInAppControllerV4({
    reader, scheduler, onAlert: (events) => alerts.push(...events),
  });
  return {
    controller, alerts, requests,
    update(value) { items=value; },
    fail(value) { broken=value; },
    setSource(value) {source=value;},
    pending() {return timers.size;},
    interval() { const t=[...timers.values()][0]; return t ? t.when-now : null; },
    async tick() {
      const due=[...timers.entries()].sort((a,b)=>a[1].when-b[1].when)[0];
      assert.ok(due,'scheduled poll expected');
      const [id,t]=due; timers.delete(id); now=t.when; t.cb();
      await new Promise(resolve=>setImmediate(resolve));
    },
  };
}
test('initial successful AUTO_FAIL poll baselines historic records and requests only GET history filter',async()=>{
  const h=harness([item(1),item(2)]); h.controller.start(); await h.tick();
  assert.equal(h.alerts.length,0);
  assert.deepEqual(h.requests[0],{page:0,size:AUTO_FAIL_PAGE_SIZE_V4,displayState:'AUTO_FAIL'});
  assert.equal(h.interval(),AUTO_FAIL_POLL_MS_V4);h.controller.stop();
});
test('new AUTO_FAIL yields AUTO_FAILED, original REVIEW queue is untouched',async()=>{
  const h=harness([item(1)]);h.controller.start();await h.tick();
  h.update([item(2),item(1)]);await h.tick();
  assert.equal(h.alerts.length,1);assert.equal(h.alerts[0].kind,'AUTO_FAILED');
  assert.equal(h.alerts[0].inspectionId,item(2).inspectionId);
  h.controller.stop();
});
test('same inspection ID never alerts twice, even if it disappears then reappears',async()=>{
  const h=harness();h.controller.start();await h.tick();
  h.update([item(3)]);await h.tick();await h.tick();
  h.update([]);await h.tick();h.update([item(3)]);await h.tick();
  assert.equal(h.alerts.length,1);h.controller.stop();
});
test('failed first request does not alert existing records when service recovers',async()=>{
  const h=harness([item(1)]);h.fail(true);h.controller.start();await h.tick();
  h.fail(false);await h.tick();assert.equal(h.alerts.length,0);
  h.update([item(2),item(1)]);await h.tick();assert.equal(h.alerts.length,1);
  h.controller.stop();
});
test('non-SERVER source cannot establish baseline or emit events',async()=>{
  const h=harness([item(1)]);h.setSource('CONTRACT_EXAMPLE');
  h.controller.start();await h.tick();
  h.setSource('SERVER');await h.tick();assert.equal(h.alerts.length,0);
  h.update([item(2),item(1)]);await h.tick();assert.equal(h.alerts.length,1);
  h.controller.stop();
});
test('background pause stops polling, resume sees new items once',async()=>{
  const h=harness([item(1)]);h.controller.start();await h.tick();
  h.controller.setForeground(false);assert.equal(h.pending(),0);
  h.update([item(2),item(1)]);assert.equal(h.alerts.length,0);
  h.controller.setForeground(true);assert.equal(h.interval(),0);
  await h.tick();assert.equal(h.alerts.length,1);
  await h.tick();assert.equal(h.alerts.length,1);h.controller.stop();
});
test('stopped controller has no new requests or alerts',async()=>{
  const h=harness();h.controller.start();await h.tick();h.controller.stop();
  assert.equal(h.pending(),0);h.update([item(1)]);assert.equal(h.alerts.length,0);
});
test('wrong displayState response is rejected before baseline',async()=>{
  const h=harness([item(1,'REVIEW_PENDING')]);h.controller.start();await h.tick();
  h.update([item(1)]);await h.tick();assert.equal(h.alerts.length,0);
  h.update([item(2),item(1)]);await h.tick();assert.equal(h.alerts.length,1);
  h.controller.stop();
});
test('inspection history parser accepts AUTO_FAIL and strict query guards continue',()=>{
  const page=decodeHistoryPageV4({
    items:[item(1)],page:0,size:20,totalElements:1,hasNext:false,
  },0,20);
  assert.equal(page.items[0].displayState,'AUTO_FAIL');
});
test('AUTO_FAIL detail retains FAIL · SYSTEM and does not offer manual confirm',()=>{
  const d={
    inspectionId:item(1).inspectionId,inspectionNo:item(1).inspectionNo,
    partCode:'COWL_COVER',status:'COMPLETED',displayState:'AUTO_FAIL',
    receivedAt:'2026-11-23T11:00:00Z',source:'DEVICE',
    ai:{modelVersion:'model',calibratorVersion:'cal-v1',predictedQuality:'DEFECT',
      rawDefectProbability:0.99,calibratedDefectProbability:0.9966,inferenceTimeMs:100},
    policy:{automationPolicyReady:true,policyVersion:'v13',passThreshold:0.01,
      recommendedAction:'AUTO_FAIL',reviewReason:null,failThreshold:0.9966},
    judgement:{finalJudgement:'FAIL',judgedBy:'SYSTEM',confirmedBy:null,confirmedAt:null},
    images:{original:null,gradcam:null,gradcamStatus:'NO_ACTIVATION',urlExpiresAt:null},
    error:null,
  };
  const detail=mapInspectionDetailV4(decodeInspectionDetailV4({data:d}));
  assert.equal(detail.displayStateLabel,'자동 불량');
  assert.equal(detail.finalJudgement,'FAIL');assert.equal(detail.judgedBy,'SYSTEM');
  assert.equal(detail.canOfferConfirm,false);assert.equal(detail.canOfferRetry,false);
  assert.equal(detail.canOfferManual,false);
});
test('incorrect AUTO_FAIL original judgement must fail contract validation',()=>{
  const d={
    inspectionId:item(1).inspectionId,inspectionNo:item(1).inspectionNo,
    partCode:'COWL_COVER',status:'COMPLETED',displayState:'AUTO_FAIL',
    receivedAt:'2026-11-23T11:00:00Z',source:'DEVICE',
    ai:{modelVersion:'model',calibratorVersion:'cal-v1',predictedQuality:'DEFECT',
      rawDefectProbability:0.99,calibratedDefectProbability:0.99,inferenceTimeMs:100},
    policy:{automationPolicyReady:true,policyVersion:'v13',passThreshold:0.01,
      recommendedAction:'AUTO_FAIL',reviewReason:null},
    judgement:{finalJudgement:'PASS',judgedBy:'SYSTEM',confirmedBy:null,confirmedAt:null},
    images:null,error:null,
  };
  assert.throws(()=>decodeInspectionDetailV4({data:d}),/AUTO_FAIL/);
});
