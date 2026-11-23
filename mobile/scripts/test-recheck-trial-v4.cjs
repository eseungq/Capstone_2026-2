const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

Module._extensions['.ts'] = (module, filename) => {
  const source = fs.readFileSync(filename, 'utf8');
  const js = ts.transpileModule(source, {
    fileName: filename,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  module._compile(js, filename);
};

const api = require(path.join(__dirname, '../src/api/backendV4/recheckCoreV4.ts'));
const { createInspectionDwellTrackerV4 } = require(
  path.join(__dirname, '../src/api/backendV4/inspectionDwellV4.ts'));
const { makeConfirmBodyV4 } = require(
  path.join(__dirname, '../src/api/backendV4/inspectionWriteCore.ts'));
const { createRecheckServiceV4 } = require(
  path.join(__dirname, '../src/api/backendV4/recheckServiceV4.ts'));

const id = '12345678-1234-4123-8123-123456789abc';
const sampled = '2026-11-18T21:00:00+09:00';
const recheck = {
  stratum:'NEAR',samplingRate:1,ruleVersion:'v1-b40-80-p100-30-10',
  trialName:'공동시험 1차',sampledAt:sampled,result:'FAIL',
  comment:'불량 확인',recheckedBy:'worker',recheckedAt:sampled,
  acknowledgedBy:null,acknowledgedAt:null,acknowledgeNote:null,
};

test('recheck pending/complete filters remain independent of REVIEW queue', () => {
  assert.equal(api.makeRecheckListPathV4({status:'PENDING',page:0}),
    '/rechecks?status=PENDING&page=0&size=20');
  assert.match(api.makeRecheckListPathV4({status:'DONE',page:1,result:'FAIL',acknowledged:false}),
    /result=FAIL&acknowledged=false/);
  assert.throws(()=>api.makeRecheckListPathV4({status:'PENDING',page:0,result:'FAIL'}));
});
test('recheck and acknowledge routes require UUID, not inspection number', () => {
  assert.equal(api.makeRecheckPostPathV4(id,'recheck'),'/inspections/'+id+'/recheck');
  assert.equal(api.makeRecheckPostPathV4(id,'acknowledge'),'/admin/rechecks/'+id+'/acknowledge');
  assert.throws(()=>api.makeRecheckPostPathV4('INS-000123','recheck'));
});
test('recheck body sends three timing fields together', () => {
  const timing = {screenDwellMs:24300,firstOpenedAt:sampled,openCount:2};
  assert.deepEqual(api.makeRecheckSubmitBodyV4('FAIL','핀 들뜸',timing),
    {result:'FAIL',comment:'핀 들뜸',...timing});
  assert.deepEqual(api.makeRecheckSubmitBodyV4('PASS',''),{result:'PASS'});
  assert.throws(()=>api.makeRecheckSubmitBodyV4('FAIL','', {screenDwellMs:1,firstOpenedAt:'bad',openCount:1}));
});
test('REVIEW confirm follows the same timing contract', () => {
  const timing={screenDwellMs:22000,firstOpenedAt:sampled,openCount:1};
  assert.deepEqual(makeConfirmBodyV4({finalJudgement:'PASS',comment:'정상',...timing}),
    {finalJudgement:'PASS',comment:'정상',...timing});
  assert.throws(()=>makeConfirmBodyV4({finalJudgement:'FAIL',openCount:1}), /체류 시간/);
});
test('first focus and reentry count, background resume does not', () => {
  const t=createInspectionDwellTrackerV4();
  t.focus(id,true,1000);
  t.setForeground(id,false,5000);
  t.setForeground(id,true,10000);
  t.blur(id,13000);
  t.focus(id,true,20000);
  assert.equal(t.snapshot(id,25000).screenDwellMs,4000+3000+5000);
  assert.equal(t.snapshot(id,25000).openCount,2);
});
test('failed submit preserves timing and successful submit clears it', () => {
  const t=createInspectionDwellTrackerV4();
  t.focus(id,true,1000);
  t.blur(id,3000);
  assert.equal(t.snapshot(id,9000).screenDwellMs,2000);
  t.clear(id);
  assert.equal(t.snapshot(id,10000),null);
});
test('long dwell or abnormal open count never generates partial invalid body', () => {
  const t=createInspectionDwellTrackerV4();
  t.focus(id,true,1000);
  assert.equal(t.snapshot(id,86_401_001),null);
});
test('detailed FAIL retains system PASS and administrator state separately', () => {
  assert.equal(api.decodeRecheckBlockV4(recheck).result,'FAIL');
  assert.deepEqual(api.decodeRecheckReplyV4({inspectionId:id,inspectionNo:'INS-000123',
    finalJudgement:'PASS',judgedBy:'SYSTEM',recheck},id,'FAIL').recheck.result,'FAIL');
  assert.throws(()=>api.decodeRecheckReplyV4({inspectionId:id,inspectionNo:'INS-000123',
    finalJudgement:'FAIL',judgedBy:'SYSTEM',recheck},id));
});
test('acknowledged FAIL requires acknowledgement record and is not solved', () => {
  const acked={...recheck,acknowledgedBy:'admin',acknowledgedAt:sampled,acknowledgeNote:'확인함'};
  assert.equal(api.decodeRecheckBlockV4(acked).acknowledgedBy,'admin');
  assert.throws(()=>api.decodeRecheckBlockV4({...acked,result:'PASS'}));
  assert.throws(()=>api.decodeRecheckBlockV4({...acked,acknowledgedBy:null}));
});
test('list parser requires DONE results and valid UUID', () => {
  const raw={items:[{inspectionId:id,inspectionNo:'INS-000123',partCode:'DOOR',
    receivedAt:sampled,stratum:'MID',sampledAt:sampled,result:'FAIL',
    recheckedAt:sampled,acknowledgedBy:null,acknowledgedAt:null}],
    page:0,size:20,totalElements:1,totalPages:1};
  assert.equal(api.decodeRecheckPageV4(raw,'DONE').items[0].result,'FAIL');
  assert.throws(()=>api.decodeRecheckPageV4(raw,'PENDING'));
});
test('service sends actual POST once; does not alter original system judgement', async () => {
  const calls=[];
  const svc=createRecheckServiceV4({ authorizedRequest: async (path,options)=>{
    calls.push({path,options});
    return {inspectionId:id,inspectionNo:'INS-000123',
      finalJudgement:'PASS',judgedBy:'SYSTEM',recheck};
  }});
  const value=await svc.recheck(id,'FAIL','불량');
  assert.equal(value.finalJudgement,'PASS');
  assert.equal(value.recheck.result,'FAIL');
  assert.equal(calls[0].path,'/inspections/'+id+'/recheck');
  assert.equal(calls.length,1);
});
test('acknowledge API returns only after FAIL and administrator acknowledgement fields', async () => {
  const svc=createRecheckServiceV4({ authorizedRequest:async()=>({
    inspectionId:id,inspectionNo:'INS-000123',finalJudgement:'PASS',judgedBy:'SYSTEM',
    recheck:{...recheck,acknowledgedBy:'admin',acknowledgedAt:sampled},
  })});
  assert.equal((await svc.acknowledge(id,'확인')).recheck.acknowledgedBy,'admin');
});
