/**
 * §6.7.1 batch FAIL contract tests. Mock transport only: no real DB or POST.
 * Run: npm run test:batch-fail
 */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
Module._extensions['.ts'] = (module,filename) => {
  const source=fs.readFileSync(filename,'utf8');
  module._compile(ts.transpileModule(source,{
    fileName:filename,compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS},
  }).outputText,filename);
};
const root=path.join(__dirname,'../src/api/backendV4');
const {MAX_BATCH_FAIL_V4,selectableReviewForBatchV4,prepareBatchFailBodyV4,
  decodeBatchFailReplyV4,batchFailResultLabelV4,canReviewBatchImagesV4,batchQueueFiltersFromRouteV4,createBatchConfirmationGuardV4} = require(path.join(root,'batchFailCoreV4.ts'));
const {createBatchFailServiceV4}=require(path.join(root,'batchFailServiceV4.ts'));
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const item=n=>({inspectionId:id(n),inspectionNo:`INS-${String(n).padStart(6,'0')}`,partCode:'COWL_COVER'});
const detail=(n,state='REVIEW_PENDING',judge=null)=>({...item(n),displayState:state,finalJudgement:judge});
const confirmed=n=>({inspectionId:id(n),inspectionNo:item(n).inspectionNo,result:'CONFIRMED',
  finalJudgement:'FAIL',judgedBy:'WORKER',confirmedBy:'worker01',
  confirmedAt:'2026-11-23T14:55:00+09:00',errorCode:null});
const batchId=id(900);
const reply=results=>({batchId,results});
function deferred(){let resolve;const promise=new Promise(ok=>{resolve=ok;});return {promise,resolve};}
test('detail REVIEW_PENDING and no final judgement is selectable',()=>{
  assert.deepEqual(selectableReviewForBatchV4(detail(1)),item(1));
});
test('AUTO_PASS, REVIEW_DONE and FAILED cannot be manually batch selected',()=>{
  for(const [state,judgement] of [['AUTO_PASS','PASS'],['REVIEW_DONE','FAIL'],['FAILED',null]]){
    assert.throws(()=>selectableReviewForBatchV4(detail(1,state,judgement)),/REVIEW_PENDING/);
  }
});
test('WORKER-only; ADMIN and DEVICE blocked before transport',()=>{
  for(const role of [null,'ADMIN','DEVICE']) assert.throws(()=>prepareBatchFailBodyV4(role,[item(1)],''),/WORKER/);
});
test('FAIL-only body has UUID items and trimmed common comment',()=>{
  assert.deepEqual(prepareBatchFailBodyV4('WORKER',[item(2),item(1)],'  고정핀 들뜸  '),{
    finalJudgement:'FAIL',comment:'고정핀 들뜸',
    items:[{inspectionId:id(2)},{inspectionId:id(1)}],
  });
});
test('empty optional comment omitted; no fictitious screen dwell fields',()=>{
  assert.deepEqual(prepareBatchFailBodyV4('WORKER',[item(1)],'   '),{
    finalJudgement:'FAIL',items:[{inspectionId:id(1)}],
  });
});
test('one to fifty items accepted and 0/51 refused',()=>{
  assert.equal(MAX_BATCH_FAIL_V4,50);
  assert.equal(prepareBatchFailBodyV4('WORKER',Array.from({length:50},(_,i)=>item(i+1)),'').items.length,50);
  assert.throws(()=>prepareBatchFailBodyV4('WORKER',[],''),/1~50/);
  assert.throws(()=>prepareBatchFailBodyV4('WORKER',Array.from({length:51},(_,i)=>item(i+1)),''),/1~50/);
});
test('duplicate or invalid id and missing inspection number rejected',()=>{
  assert.throws(()=>prepareBatchFailBodyV4('WORKER',[item(1),item(1)],''),/두 번/);
  assert.throws(()=>prepareBatchFailBodyV4('WORKER',[{...item(1),inspectionId:'INS-000001'}],''),/UUID/);
  assert.throws(()=>prepareBatchFailBodyV4('WORKER',[{...item(1),inspectionNo:'INS-1'}],''),/검사번호/);
});
test('comment maximum length enforced on unicode characters',()=>{
  assert.equal(prepareBatchFailBodyV4('WORKER',[item(1)],'한'.repeat(200)).comment.length,200);
  assert.throws(()=>prepareBatchFailBodyV4('WORKER',[item(1)],'한'.repeat(201)),/200자/);
});
test('successful CONFIRMED response parsed in request order and FAIL WORKER',()=>{
  const req=prepareBatchFailBodyV4('WORKER',[item(1),item(2)],'');
  const v=decodeBatchFailReplyV4(reply([confirmed(1),confirmed(2)]),req);
  assert.equal(v.batchId,batchId);assert.equal(v.results[1].inspectionId,id(2));
});
test('mixed per-item outcomes accepted without inventing all-success',()=>{
  const req=prepareBatchFailBodyV4('WORKER',[item(1),item(2),item(3),item(4),item(5),item(6)],'');
  const res=decodeBatchFailReplyV4(reply([
    confirmed(1),
    {...confirmed(2),result:'ALREADY_CONFIRMED'},
    {...confirmed(3),result:'CONFLICT',finalJudgement:'PASS',judgedBy:'WORKER',errorCode:'ALREADY_CONFIRMED'},
    {...confirmed(4),result:'NOT_REVIEWABLE',finalJudgement:'PASS',judgedBy:'SYSTEM',errorCode:'NOT_REVIEWABLE'},
    {inspectionId:id(5),inspectionNo:null,result:'NOT_FOUND',finalJudgement:null,judgedBy:null,
     confirmedBy:null,confirmedAt:null,errorCode:'INSPECTION_NOT_FOUND'},
    {inspectionId:id(6),inspectionNo:null,result:'ERROR',finalJudgement:null,judgedBy:null,
     confirmedBy:null,confirmedAt:null,errorCode:'INTERNAL_SERVER_ERROR'},
  ]),req);
  assert.deepEqual(res.results.map(x=>x.result),
    ['CONFIRMED','ALREADY_CONFIRMED','CONFLICT','NOT_REVIEWABLE','NOT_FOUND','ERROR']);
  assert.match(batchFailResultLabelV4('ERROR'),/저장되지/);
});
test('wrong success judgement or judgedBy cannot be accepted',()=>{
  const req=prepareBatchFailBodyV4('WORKER',[item(1)],'');
  assert.throws(()=>decodeBatchFailReplyV4(reply([{...confirmed(1),finalJudgement:'PASS'}]),req),/FAIL/);
  assert.throws(()=>decodeBatchFailReplyV4(reply([{...confirmed(1),judgedBy:'SYSTEM'}]),req),/FAIL/);
});
test('missing errorCode for failed item or present errorCode for success is rejected',()=>{
  const req=prepareBatchFailBodyV4('WORKER',[item(1)],'');
  assert.throws(()=>decodeBatchFailReplyV4(reply([{...confirmed(1),result:'CONFLICT'}]),req),/errorCode/);
  assert.throws(()=>decodeBatchFailReplyV4(reply([{...confirmed(1),errorCode:'ERROR'}]),req),/FAIL/);
});
test('incorrect batchId, result length, result id/order are rejected',()=>{
  const req=prepareBatchFailBodyV4('WORKER',[item(1),item(2)],'');
  assert.throws(()=>decodeBatchFailReplyV4({batchId:'bad',results:[confirmed(1),confirmed(2)]},req),/batchId/);
  assert.throws(()=>decodeBatchFailReplyV4(reply([confirmed(1)]),req),/건수/);
  assert.throws(()=>decodeBatchFailReplyV4(reply([confirmed(2),confirmed(1)]),req),/순서/);
});
test('service sends exactly one POST with contract body after WORKER validation',async()=>{
  const calls=[];
  const transport={async authorizedRequest(path,opts){
    calls.push({path,opts});return reply([confirmed(1)]);
  }};
  const svc=createBatchFailServiceV4(transport);
  const value=await svc.submit('WORKER',[item(1)],'불량 확인');
  assert.equal(value.value.results[0].result,'CONFIRMED');
  assert.deepEqual(calls,[{path:'/inspections/confirm-batch',
    opts:{method:'POST',body:{finalJudgement:'FAIL',comment:'불량 확인',
      items:[{inspectionId:id(1)}]}}}]);
});
test('invalid selection or ADMIN triggers zero transport calls',async()=>{
  let count=0;const svc=createBatchFailServiceV4({async authorizedRequest(){count++;return reply([]);}});
  await assert.rejects(svc.submit('ADMIN',[item(1)],''),/WORKER/);
  await assert.rejects(svc.submit('WORKER',[],''),/1~50/);
  assert.equal(count,0);
});
test('concurrent tap is rejected locally; one transport POST only',async()=>{
  const wait=deferred();let count=0;
  const svc=createBatchFailServiceV4({async authorizedRequest(){count++;return wait.promise;}});
  const first=svc.submit('WORKER',[item(1)],'');
  await assert.rejects(svc.submit('WORKER',[item(1)],''),/이미 진행/);
  wait.resolve(reply([confirmed(1)]));
  await first;assert.equal(count,1);
});
test('network failure releases lock for later deliberate retry',async()=>{
  let count=0;const svc=createBatchFailServiceV4({async authorizedRequest(){
    count++;if(count===1)throw new Error('offline');
    return reply([confirmed(1)]);
  }});
  await assert.rejects(svc.submit('WORKER',[item(1)],''),/offline/);
  assert.equal((await svc.submit('WORKER',[item(1)],'')).value.results[0].result,'CONFIRMED');
  assert.equal(count,2);
});

test('batch review requires successful image loading rather than URL presence',()=>{
 const url='https://example.test/original.png',cam='https://example.test/cam.png';
 for(const state of ['loading','failed']){
   assert.equal(canReviewBatchImagesV4(url,state,cam,'loaded'),false);
   assert.equal(canReviewBatchImagesV4(url,'loaded',cam,state),false);
 }
 assert.equal(canReviewBatchImagesV4(null,'loaded',null,'loaded'),false);
 assert.equal(canReviewBatchImagesV4(url,'loaded',cam,'loaded'),true);
 assert.equal(canReviewBatchImagesV4(url,'loaded',null,'loading'),true);
});

test('monitoring route passes the selected part, server sort and prediction filter; direct entry keeps all REVIEW', ()=>{
  assert.deepEqual(batchQueueFiltersFromRouteV4({}), {partCode:null, sort:'RECEIVED', aiDefectOnly:false});
  for (const partCode of ['DOOR','FRAME','COWL_COVER']) {
    assert.deepEqual(batchQueueFiltersFromRouteV4({partCode, sort:'PRIORITY', aiDefectOnly:'true'}),
      {partCode, sort:'PRIORITY', aiDefectOnly:true});
  }
  assert.deepEqual(batchQueueFiltersFromRouteV4({partCode:'FRAME', aiDefectOnly:'false'}),
    {partCode:'FRAME', sort:'RECEIVED', aiDefectOnly:false});
});

test('invalid or repeated route filters cannot silently open a broader set of batch candidates', ()=>{
  for (const params of [
    {partCode:''}, {partCode:'OTHER'}, {partCode:['DOOR','FRAME']},
    {sort:'LATEST'}, {sort:['PRIORITY']}, {aiDefectOnly:'1'}, {aiDefectOnly:['true','false']},
  ]) assert.equal(batchQueueFiltersFromRouteV4(params), null);
});

test('late batch confirmation is invalid after a different draft, navigation, or account change during restore', async()=>{
  let epoch=4;
  const guard=createBatchConfirmationGuardV4(()=>epoch);
  const oldPrompt=guard.capture();
  const newerPrompt=guard.capture();
  assert.equal(oldPrompt(), false);
  assert.equal(newerPrompt(), true);
  guard.invalidate();
  assert.equal(newerPrompt(), false);
  const beforeRestore=guard.capture();
  const restoring=deferred();
  const checkedAfterRestore=restoring.promise.then(()=>beforeRestore());
  epoch++;
  restoring.resolve();
  assert.equal(await checkedAfterRestore, false);
  assert.equal(guard.capture()(), false);
  assert.equal(createBatchConfirmationGuardV4(()=>epoch).capture()(), true);
});
