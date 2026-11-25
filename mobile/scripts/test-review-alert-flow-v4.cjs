const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const ts=require('typescript');
Module._extensions['.ts']=(module,filename)=>{
  module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{fileName:filename,compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,filename);
};
const {createReviewAlertQueueV4,findNextReviewAlertV4}=require('../src/components/reviewAlertQueueV4.ts');
const alert=(id,kind='REVIEW_REQUIRED')=>({inspectionId:id,inspectionNo:'INS-'+id,partCode:'DOOR',kind,receivedAt:'2026-11-25T00:00:00Z'});
test('notification sequence contains only pending review alerts and consumes each on entry',()=>{
  const q=createReviewAlertQueueV4(),a=alert('a'),b=alert('b'),failed=alert('f','ANALYSIS_FAILED');
  q.add(1,[a,b,failed]);q.add(1,[b]);const token=q.begin(1,a);
  assert.ok(token);assert.deepEqual(q.candidates(1,token,'a'),[b]);
  assert.equal(q.advance(1,token,'a',failed),false);
  assert.equal(q.advance(1,token,'a',b),true);
  assert.deepEqual(q.snapshot(1),[failed]);assert.equal(q.matches(1,token,'a'),false);
  assert.deepEqual(q.candidates(1,token,'b'),[]);
});
test('declining continuation keeps all other alerts and invalidates old confirmation',()=>{
  const q=createReviewAlertQueueV4(),a=alert('a'),b=alert('b');q.add(1,[a,b]);
  const token=q.begin(1,a);q.stop(1,token,'a');
  assert.deepEqual(q.snapshot(1),[b]);assert.equal(q.advance(1,token,'a',b),false);
});
test('failed alert cannot begin a review sequence',()=>{
  const q=createReviewAlertQueueV4(),f=alert('f','ANALYSIS_FAILED');q.add(1,[f]);
  assert.equal(q.begin(1,f),null);
});
test('old account responses never expose or consume new session alerts',()=>{
  const q=createReviewAlertQueueV4(),a=alert('a'),b=alert('b'),c=alert('c');q.add(1,[a,b]);const token=q.begin(1,a);
  q.add(2,[c]);q.add(1,[b]);assert.deepEqual(q.snapshot(2),[c]);
  assert.deepEqual(q.snapshot(1),[]);assert.equal(q.advance(1,token,'a',b),false);
});
test('next read skips completed items, keeps failed notifications and does not consume next until chosen',async()=>{
  const q=createReviewAlertQueueV4(),a=alert('a'),b=alert('b'),c=alert('c'),f=alert('f','ANALYSIS_FAILED');
  q.add(1,[a,b,c,f]);const token=q.begin(1,a);
  const seen=[];const result=await findNextReviewAlertV4(q,1,token,'a',()=>true,async item=>{seen.push(item.inspectionId);return item===c||item.inspectionId==='c';});
  assert.deepEqual(seen,['b','c']);assert.equal(result.inspectionId,'c');
  assert.deepEqual(q.snapshot(1),[c,f]);
});
test('network failure and loss of visit do not drop unresolved next alerts',async()=>{
  const q=createReviewAlertQueueV4(),a=alert('a'),b=alert('b');q.add(1,[a,b]);const token=q.begin(1,a);
  await assert.rejects(()=>findNextReviewAlertV4(q,1,token,'a',()=>true,async()=>{throw Error('offline');}),/offline/);
  assert.deepEqual(q.snapshot(1),[b]);let current=true;
  const next=await findNextReviewAlertV4(q,1,token,'a',()=>current,async()=>{current=false;return false;});
  assert.equal(next,null);assert.deepEqual(q.snapshot(1),[b]);
});
test('notification UI is shared and limited to worker; only saved confirmation offers continuation',()=>{
  const read=file=>fs.readFileSync(path.join(__dirname,'../src',file),'utf8');
  const root=read('app/_layout.tsx'),monitor=read('app/monitoring.tsx'),host=read('components/AutoFailInAppAlertV4.tsx'),detail=read('app/inspection-live.tsx');
  assert.match(root,/session\?\.role === 'WORKER' && <AutoFailInAppAlertHostV4/);
  assert.match(monitor,/isLive && verifiedRole==='WORKER' && activeTab==='monitoring'/);
  assert.match(monitor,/<InspectionAlertBannerV4/);assert.match(host,/<InspectionAlertBannerV4/);
  assert.match(host,/session.signedIn && session.role === 'WORKER'/);
  assert.match(detail,/await writer.confirm\(/);
  assert.match(detail,/if\(action==='confirm'&&isCurrentVisit\(displayedVisit\)\)await offerNextAlert\(displayedVisit\)/);
  assert.match(detail,/response.value.displayState==='REVIEW_PENDING'&&response.value.finalJudgement===null&&response.value.canOfferConfirm/);
  assert.match(detail,/router.replace\(\{pathname:'\/inspection-live',params:\{inspectionId:latest.inspectionId,alertFlow:flowToken\}\}\)/);
});
