const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const ts=require('typescript');
Module._extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{fileName:filename,compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,filename);
const {reviewReasonCopyV4,reviewListReasonV4,hasReviewReasonDetailV4}=require('../src/components/reviewReasonCopyV4.ts');
test('all five server review reasons map to four distinct worker titles without policy jargon',()=>{
  const expected={DEFECT_PREDICTED:'불량 의심',ABOVE_THRESHOLD:'정상 예측, 확신 부족',NO_ACTIVE_POLICY:'자동 판정 불가',CALIBRATION_UNAVAILABLE:'자동 판정 불가',AI_UNAVAILABLE:'AI 분석 없음'};
  for(const [reason,title] of Object.entries(expected)){
    const copy=reviewReasonCopyV4(reason);
    assert.equal(copy.title,title);
    assert.equal(reviewListReasonV4('REVIEW_PENDING',reason),title);
    assert.doesNotMatch(copy.title+' '+copy.description,/기준|정책|[A-Z_]{2,}/);
  }
  assert.equal(new Set(Object.values(expected).map(title=>title.split(' ')[0])).size,4);
});
test('policy and calibration failure have identical worker copy but distinct administrator causes',()=>{
  const a=reviewReasonCopyV4('NO_ACTIVE_POLICY'),b=reviewReasonCopyV4('CALIBRATION_UNAVAILABLE');
  assert.equal(a.title,b.title);assert.equal(a.description,b.description);
  assert.notEqual(a.adminCause,b.adminCause);
  assert.equal(a.adminCause,'활성 정책 없음');assert.equal(b.adminCause,'보정 확률 사용 불가');
});
test('unknown reasons stay generic and completed or failed records are not labeled as pending',()=>{
  assert.equal(reviewReasonCopyV4(null).title,'판정 필요');
  for(const state of ['AUTO_PASS','AUTO_FAIL','FAILED','ANALYZING','REVIEW_DONE']){
    assert.equal(reviewListReasonV4(state,'ABOVE_THRESHOLD'),null);
  }
  assert.equal(hasReviewReasonDetailV4('REVIEW_DONE','ABOVE_THRESHOLD'),true);
  assert.equal(hasReviewReasonDetailV4('AUTO_PASS','ABOVE_THRESHOLD'),false);
});
test('operational lists show title only and detail gates policy-specific cause and threshold on ADMIN',()=>{
  const read=file=>fs.readFileSync(path.join(__dirname,'../src',file),'utf8');
  const m=read('components/MonitoringLiveDashboardV4.tsx'),h=read('components/HistoryLiveScreenV4.tsx'),b=read('app/batch-fail-live.tsx'),i=read('app/inspection-live.tsx');
  for(const file of [m,h,b])assert.match(file,/reviewListReasonV4\(item.displayState,item.reviewReason\)/);
  assert.doesNotMatch(m,/item\.(?:calibratedDefectProbability|passThresholdApplied)/);
  assert.doesNotMatch(b,/item\.(?:calibratedDefectProbability|passThresholdApplied)/);
  assert.match(i,/const adminDetail=!roleLoading&&role==='ADMIN'/);
  assert.match(i,/adminDetail && <Field label="구체적인 원인"/);
  assert.match(i,/\{adminDetail&&<>\s*<Field label="정책 버전"/);
  assert.match(i,/visibleDetail.passThresholdApplied/);
  assert.match(read('api/backendV4/adapter.ts'),/passThresholdApplied: detail.policy\?\.passThreshold \?\? null/);
});
