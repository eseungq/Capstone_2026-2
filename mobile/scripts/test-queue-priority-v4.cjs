/**
 * Contract v4 §6.4 queue sort/filter regression. No live server or write requests.
 * Run: npm run test:queue-priority
 */
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

Module._extensions['.ts'] = (module, filename) => {
  const source = fs.readFileSync(filename, 'utf8');
  module._compile(ts.transpileModule(source, {fileName: filename,
    compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS},
  }).outputText, filename);
};
const apiRoot = path.join(__dirname, '../src/api/backendV4');
const {makeQueueQueryV4, decodeQueuePageV4} = require(path.join(apiRoot, 'inspectionReadCore.ts'));
const {createInspectionReadServiceV4} = require(path.join(apiRoot, 'inspectionReadService.ts'));
const {createReviewQueueBrowserV4, reviewQueueRequestV4, REVIEW_BROWSE_PAGE_SIZE_V4} =
  require(path.join(apiRoot, 'reviewQueueBrowseCoreV4.ts'));

function item(n, {quality='GOOD',reason='ABOVE_THRESHOLD',state='REVIEW_PENDING',part='COWL_COVER',
  calibrated=0.024,threshold=0.01}={}) {
  return {
    inspectionId: `00000000-0000-4000-8000-${String(n).padStart(12,'0')}`,
    inspectionNo: `INS-${String(n).padStart(6,'0')}`,
    partCode:part,displayState:state,predictedQuality:quality,reviewReason:reason,
    errorCode:null,receivedAt:`2026-11-23T10:${String(n%60).padStart(2,'0')}:00+09:00`,
    thumbnailUrl:null,calibratedDefectProbability:calibrated,passThresholdApplied:threshold,
  };
}
function page(items, nextCursor=null, source='SERVER') {
  return {source,value:{items,nextCursor}};
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((ok, fail)=>{resolve=ok;reject=fail;});
  return {promise,resolve,reject};
}
function harness(initialPages=[], options) {
  const calls=[], replies=[...initialPages];
  const reader={async queue(request){calls.push(request);const reply=replies.shift();
    if (reply instanceof Error) throw reply;
    if (reply && typeof reply.then==='function') return reply;
    if (!reply) throw new Error('test fixture depleted');
    return reply;
  }};
  const b=createReviewQueueBrowserV4(reader, options);
  const events=[];
  b.subscribe(s=>events.push(s));
  return {b,calls,replies,events};
}
const filters=(sort='PRIORITY',aiDefectOnly=false,partCode='COWL_COVER')=>({partCode,sort,aiDefectOnly});

test('legacy queue query leaves sort and prediction absent for existing 5-second polling',()=>{
  assert.equal(makeQueueQueryV4({type:'ALL',size:20}),'/monitoring/queue?type=ALL&size=20');
});
test('PRIORITY and DEFECT filter generate exact server query, no client-side sort',()=>{
  assert.equal(makeQueueQueryV4(reviewQueueRequestV4(filters('PRIORITY',true),'encoded+cursor/=')),
    '/monitoring/queue?type=REVIEW&size=20&partCode=COWL_COVER&sort=PRIORITY&predictedQuality=DEFECT&cursor=encoded%2Bcursor%2F%3D');
  assert.equal(REVIEW_BROWSE_PAGE_SIZE_V4,20);
});
test('RECEIVED plus AI defect filter sends REVIEW with predictedQuality DEFECT, no PRIORITY',()=>{
  assert.deepEqual(reviewQueueRequestV4(filters('RECEIVED',true)),{
    type:'REVIEW',partCode:'COWL_COVER',size:20,sort:'RECEIVED',predictedQuality:'DEFECT',
  });
});
test('unknown sort/quality or invalid size is rejected before network',()=>{
  assert.throws(()=>makeQueueQueryV4({sort:'RANDOM'}),/sort/);
  assert.throws(()=>makeQueueQueryV4({predictedQuality:'UNKNOWN'}),/predictedQuality/);
  assert.throws(()=>makeQueueQueryV4({size:101}),/size/);
});
test('new probability fields preserve decimal fractions and null, invalid values rejected',()=>{
  const values=decodeQueuePageV4({items:[item(1),{...item(2),calibratedDefectProbability:null,passThresholdApplied:null}],nextCursor:null});
  assert.equal(values.items[0].calibratedDefectProbability,0.024);
  assert.equal(values.items[0].passThresholdApplied,0.01);
  assert.equal(values.items[1].calibratedDefectProbability,null);
  assert.throws(()=>decodeQueuePageV4({items:[{...item(3),passThresholdApplied:1.3}],nextCursor:null}),/확률/);
  assert.throws(()=>decodeQueuePageV4({items:[{...item(3),calibratedDefectProbability:-0.5}],nextCursor:null}),/확률/);
});
test('read service issues only GET with the requested query and decodes server page',async()=>{
  const calls=[];
  const transport={async authorizedRequest(url,opts){
    calls.push({url,opts});
    return {items:[item(1)],nextCursor:null};
  }};
  const svc=createInspectionReadServiceV4({mode:'api',transport});
  const answer=await svc.queue(reviewQueueRequestV4(filters('PRIORITY',true)));
  assert.equal(answer.source,'SERVER');
  assert.equal(answer.value.items.length,1);
  assert.deepEqual(calls[0],{
    url:'/monitoring/queue?type=REVIEW&size=20&partCode=COWL_COVER&sort=PRIORITY&predictedQuality=DEFECT',
    opts:{method:'GET'},
  });
});
test('PRIORITY server ordering is preserved as returned, without local re-sort',async()=>{
  const ordered=[item(9),item(5),item(1,{quality:'DEFECT',reason:'DEFECT_PREDICTED'})];
  const h=harness([page(ordered)]);
  h.b.setFilters(filters());
  await h.b.refresh();
  assert.deepEqual(h.b.getSnapshot().items.map(x=>x.inspectionNo),ordered.map(x=>x.inspectionNo));
  assert.equal(h.b.getSnapshot().status,'ready');
});
test('server ignoring PRIORITY sort is rejected when priority group appears after non-priority group',async()=>{
  const h=harness([page([
    item(1,{quality:'DEFECT',reason:'DEFECT_PREDICTED'}),
    item(2,{quality:'GOOD',reason:'ABOVE_THRESHOLD'}),
  ])]);
  h.b.setFilters(filters());
  await h.b.refresh();
  assert.equal(h.b.getSnapshot().status,'error');
  assert.match(h.b.getSnapshot().error,/우선 검토 그룹/);
});
test('cursor paging keeps server-selected group order across pages',async()=>{
  const h=harness([
    page([item(5),item(6)],'pageCursor/2'),
    page([item(7,{quality:'DEFECT',reason:'DEFECT_PREDICTED'})],null),
  ]);
  h.b.setFilters(filters());
  await h.b.refresh();
  assert.equal(h.b.getSnapshot().nextCursor,'pageCursor/2');
  await h.b.loadNext();
  assert.equal(h.calls.length,2);
  assert.deepEqual(h.calls[1],{...h.calls[0],cursor:'pageCursor/2'});
  assert.deepEqual(h.b.getSnapshot().items.map(x=>x.inspectionNo),['INS-000005','INS-000006','INS-000007']);
  assert.equal(h.b.getSnapshot().nextCursor,null);
  await h.b.loadNext();
  assert.equal(h.calls.length,2);
});
test('filter change invalidates late in-flight response, with fresh cursor',async()=>{
  const slow=deferred();
  const h=harness([slow.promise,page([item(8,{quality:'DEFECT',reason:'DEFECT_PREDICTED'})])]);
  h.b.setFilters(filters());
  const old=h.b.refresh();
  h.b.setFilters(filters('RECEIVED',true));
  await h.b.refresh();
  slow.resolve(page([item(1)]));
  await old;
  assert.equal(h.b.getSnapshot().filters.aiDefectOnly,true);
  assert.equal(h.b.getSnapshot().items[0].inspectionNo,'INS-000008');
  assert.deepEqual(h.calls.map(x=>x.sort),['PRIORITY','RECEIVED']);
});
test('server filter mismatch fails closed instead of inventing AI defect results',async()=>{
  const h=harness([page([item(1)])]);
  h.b.setFilters(filters('PRIORITY',true));
  await h.b.refresh();
  assert.equal(h.b.getSnapshot().status,'error');
  assert.deepEqual(h.b.getSnapshot().items,[]);
  assert.match(h.b.getSnapshot().error,/정렬·필터/);
});
test('network error preserves already loaded page and nextCursor, retry succeeds',async()=>{
  const h=harness([
    page([item(1)],'next'),
    new Error('offline'),
    page([item(2)],null),
  ]);
  h.b.setFilters(filters());await h.b.refresh();await h.b.loadNext();
  assert.equal(h.b.getSnapshot().items.length,1);
  assert.equal(h.b.getSnapshot().nextCursor,'next');
  assert.equal(h.b.getSnapshot().status,'error');
  await h.b.loadNext();
  assert.equal(h.b.getSnapshot().items.length,2);
  assert.equal(h.b.getSnapshot().status,'ready');
});
test('repeated cursor is rejected without corrupting previous pages',async()=>{
  const h=harness([page([item(1)],'next'),page([item(2)],'next')]);
  h.b.setFilters(filters());await h.b.refresh();await h.b.loadNext();
  assert.equal(h.b.getSnapshot().status,'error');
  assert.equal(h.b.getSnapshot().items.length,1);
  assert.equal(h.b.getSnapshot().nextCursor,'next');
});
test('duplicate inspection across cursor pages rejected',async()=>{
  const h=harness([page([item(1)],'next'),page([item(1)],null)]);
  h.b.setFilters(filters());await h.b.refresh();await h.b.loadNext();
  assert.equal(h.b.getSnapshot().status,'error');
  assert.equal(h.b.getSnapshot().items.length,1);
});
test('source mismatch cannot be displayed as real SERVER data',async()=>{
  const h=harness([page([item(1)],null,'CONTRACT_EXAMPLE')]);
  h.b.setFilters(filters());await h.b.refresh();
  assert.equal(h.b.getSnapshot().status,'error');
  assert.equal(h.b.getSnapshot().loaded,false);
});
test('clear aborts stale response and restores default mode without network write',async()=>{
  const slow=deferred();
  const h=harness([slow.promise]);
  h.b.setFilters(filters());const old=h.b.refresh();
  h.b.clear();slow.resolve(page([item(1)]));await old;
  assert.equal(h.b.getSnapshot().filters,null);
  assert.equal(h.b.getSnapshot().status,'idle');
  assert.deepEqual(h.b.getSnapshot().items,[]);
});

test('unscoped batch entry reads pending REVIEW across parts and omits part and prediction parameters', async()=>{
  const h=harness([page([item(1, {part:'DOOR'}), item(2, {part:'FRAME'})])], {reviewOnly:true});
  h.b.setFilters(filters('RECEIVED', false, null));
  await h.b.refresh();
  assert.deepEqual(h.calls, [{type:'REVIEW', size:20, sort:'RECEIVED'}]);
  assert.deepEqual(h.b.getSnapshot().items.map(row=>row.partCode), ['DOOR', 'FRAME']);
});

test('batch browse fails closed for a wrong part, non-review state, or an ignored defect filter', async()=>{
  for (const [row, aiDefectOnly] of [
    [item(1, {part:'FRAME'}), false], [item(2, {state:'FAILED'}), false], [item(3), true],
  ]) {
    const h=harness([page([row])], {reviewOnly:true});
    h.b.setFilters(filters('PRIORITY', aiDefectOnly));
    await h.b.refresh();
    assert.equal(h.calls[0].type, 'REVIEW');
    assert.equal(h.b.getSnapshot().status, 'error');
    assert.deepEqual(h.b.getSnapshot().items, []);
  }
});

test('changing batch filters discards the previous cursor and pending page until the new server query resolves', async()=>{
  const oldPage=deferred();
  const h=harness([page([item(1)], 'old-cursor'), oldPage.promise, page([item(3, {part:'DOOR', quality:'DEFECT'})])], {reviewOnly:true});
  h.b.setFilters(filters('RECEIVED'));
  await h.b.refresh();
  const pending=h.b.loadNext();
  h.b.setFilters(filters('PRIORITY', true, 'DOOR'));
  assert.equal(h.b.getSnapshot().nextCursor, null);
  await h.b.refresh();
  oldPage.resolve(page([item(2)], 'ignored'));
  await pending;
  assert.deepEqual(h.calls[2], {type:'REVIEW', size:20, sort:'PRIORITY', partCode:'DOOR', predictedQuality:'DEFECT'});
  assert.deepEqual(h.b.getSnapshot().items.map(row=>row.inspectionId), [item(3).inspectionId]);
  assert.equal(h.b.getSnapshot().nextCursor, null);
});

test('refresh after a batch clears old pages and can retry the same first page on read failure', async()=>{
  const h=harness([page([item(1)], 'before-judgement'), new Error('offline'), page([])], {reviewOnly:true});
  h.b.setFilters(filters('PRIORITY'));
  await h.b.refresh();
  await h.b.refresh();
  assert.equal(h.b.getSnapshot().status, 'error');
  assert.deepEqual(h.b.getSnapshot().items, []);
  assert.equal(h.b.getSnapshot().nextCursor, null);
  await h.b.loadNext();
  assert.equal(h.calls.length, 2);
  await h.b.refresh();
  assert.deepEqual(h.calls, Array(3).fill({type:'REVIEW', partCode:'COWL_COVER', size:20, sort:'PRIORITY'}));
  assert.equal(h.b.getSnapshot().status, 'ready');
});
