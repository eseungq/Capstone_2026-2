/** §6.12 server-free WORKER request / ADMIN correction contract tests. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
Module._extensions['.ts']=(module,filename)=>{
  module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{fileName:filename,
    compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,filename);
};
const root=path.join(__dirname,'../src/api/backendV4');
const core=require(path.join(root,'judgementRequestCoreV4.ts'));
const {createJudgementRequestServiceV4}=require(path.join(root,'judgementRequestServiceV4.ts'));
const {decodeInspectionDetailV4,mapInspectionDetailV4}=require(path.join(root,'adapter.ts'));
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const entry=(status='OPEN',claimed='FAIL')=>({
  requestId:id(111),inspectionId:id(1),inspectionNo:'INS-000001',partCode:'FRAME',
  originalJudgement:'PASS',originalJudgedBy:'SYSTEM',currentJudgement:'PASS',
  claimedJudgement:claimed,area:'헤밍부',reason:'실물 확인 결과 틈이 보임',
  requestedBy:'worker01',requestedAt:'2026-11-23T17:00:00+09:00',status,
  resolvedBy:status==='OPEN'?null:'admin01',
  resolvedAt:status==='OPEN'?null:'2026-11-23T17:10:00+09:00',
  resolveNote:status==='OPEN'?null:'근거를 확인함',
});
const correction={requestId:id(111),correctedJudgement:'FAIL',
  correctedBy:'admin01',correctedAt:'2026-11-23T17:10:00+09:00',note:'실물 검사 결과 결함 확인'};
const inspection=(correctionValue=null,requests=[])=>({
  inspectionId:id(1),inspectionNo:'INS-000001',partCode:'FRAME',judgedBy:'SYSTEM',
  finalJudgement:'PASS',correction:correctionValue,judgementRequests:requests,
});
const page=(items,status='OPEN')=>({items,page:0,size:20,totalElements:items.length,totalPages:items.length?1:0});
test('WORKER can claim opposite of initial SYSTEM PASS with trimmed area and reason',()=>{
  assert.deepEqual(core.makeJudgementRequestBodyV4('WORKER',inspection(),'FAIL',' 헤밍부 ',' 근거 '),{
    claimedJudgement:'FAIL',area:'헤밍부',reason:'근거',
  });
});
test('WORKER request fails for ADMIN, WORKER verdict, same current verdict',()=>{
  assert.throws(()=>core.makeJudgementRequestBodyV4('ADMIN',inspection(),'FAIL','','근거'),/WORKER/);
  assert.throws(()=>core.makeJudgementRequestBodyV4('WORKER',
    {...inspection(),judgedBy:'WORKER'},'FAIL','','근거'),/시스템/);
  assert.throws(()=>core.makeJudgementRequestBodyV4('WORKER',inspection(),'PASS','','근거'),/다른/);
});
test('last correction is current verdict but original SYSTEM PASS unchanged',()=>{
  assert.equal(core.currentJudgementV4('PASS',correction),'FAIL');
  assert.equal(core.makeJudgementRequestBodyV4('WORKER',inspection(correction),'PASS','','근거').claimedJudgement,'PASS');
  assert.throws(()=>core.makeJudgementRequestBodyV4('WORKER',inspection(correction),'FAIL','','근거'),/다른/);
});
test('one existing OPEN request blocks a second selection',()=>{
  assert.throws(()=>core.makeJudgementRequestBodyV4('WORKER',
    inspection(null,[entry()]),'FAIL','','근거'),/대기/);
});
test('required reason 1-500 chars and optional area max 100',()=>{
  assert.throws(()=>core.makeJudgementRequestBodyV4('WORKER',inspection(),'FAIL','',' '),/1~500/);
  assert.equal(core.makeJudgementRequestBodyV4('WORKER',inspection(),'FAIL','','한'.repeat(500)).reason.length,500);
  assert.throws(()=>core.makeJudgementRequestBodyV4('WORKER',inspection(),'FAIL','','한'.repeat(501)),/1~500/);
  assert.throws(()=>core.makeJudgementRequestBodyV4('WORKER',inspection(),'FAIL','한'.repeat(101),'근거'),/100/);
});
test('decode OPEN request and resolved KEEP/CORRECTED with original verdict retained',()=>{
  for(const status of ['OPEN','KEPT','CORRECTED']){
    const found=core.decodeJudgementRequestV4(entry(status));
    assert.equal(found.status,status);
    assert.equal(found.originalJudgement,'PASS');
    assert.equal(found.originalJudgedBy,'SYSTEM');
  }
});
test('OPEN with resolver, resolved missing reason, or equal claim fail closed',()=>{
  assert.throws(()=>core.decodeJudgementRequestV4({...entry(),resolvedBy:'admin01'}),/처리 상태/);
  assert.throws(()=>core.decodeJudgementRequestV4({...entry('KEPT'),resolveNote:null}),/처리 상태/);
  assert.throws(()=>core.decodeJudgementRequestV4({...entry(),claimedJudgement:'PASS'}),/응답 값/);
});
test('correction model only accepted with valid UUID, verdict, time, note',()=>{
  assert.deepEqual(core.decodeJudgementCorrectionV4(correction),correction);
  assert.equal(core.decodeJudgementCorrectionV4(null),null);
  assert.throws(()=>core.decodeJudgementCorrectionV4({...correction,requestId:'INS-000001'}),/correction/);
});
test('resolve parsing requires matching ID, CORRECTED correction and correct verdict',()=>{
  assert.equal(core.decodeJudgementResolveV4({request:entry('KEPT'),correction:null},id(111)).correction,null);
  assert.deepEqual(core.decodeJudgementResolveV4({request:entry('CORRECTED'),correction},id(111)).correction,correction);
  assert.throws(()=>core.decodeJudgementResolveV4({request:entry('OPEN'),correction:null},id(111)),/대상/);
  assert.throws(()=>core.decodeJudgementResolveV4({request:entry('CORRECTED'),correction:null},id(111)),/정정/);
});
test('ADMIN resolution validates OPEN status and mandatory evidence',()=>{
  assert.deepEqual(core.makeJudgementResolveBodyV4('ADMIN',entry(),'CORRECT',' 증거 확인 '),
    {decision:'CORRECT',note:'증거 확인'});
  assert.throws(()=>core.makeJudgementResolveBodyV4('WORKER',entry(),'CORRECT','근거'),/ADMIN/);
  assert.throws(()=>core.makeJudgementResolveBodyV4('ADMIN',entry('KEPT'),'KEEP','근거'),/처리/);
  assert.throws(()=>core.makeJudgementResolveBodyV4('ADMIN',entry(),'KEEP',' '),/1~500/);
});
test('queue page strict parsing and duplicate request IDs rejected',()=>{
  assert.equal(core.decodeJudgementQueuePageV4(page([entry()]),0).items.length,1);
  assert.throws(()=>core.decodeJudgementQueuePageV4({...page([entry()]),page:2},0),/페이지/);
  assert.throws(()=>core.decodeJudgementQueuePageV4(page([entry(),entry()]),0),/중복/);
});
test('WORKER service sends one POST only with exact input',async()=>{
  const calls=[];const service=createJudgementRequestServiceV4({async authorizedRequest(route,opts){
    calls.push({route,opts});return entry();
  }});
  const result=await service.request('WORKER',inspection(),'FAIL','헤밍부','틈 보임');
  assert.equal(result.status,'OPEN');
  assert.deepEqual(calls,[{route:`/inspections/${id(1)}/judgement-requests`,
    opts:{method:'POST',body:{claimedJudgement:'FAIL',area:'헤밍부',reason:'틈 보임'}}}]);
});
test('ADMIN service lists only GET and rejects WORKER without network',async()=>{
  const calls=[];const service=createJudgementRequestServiceV4({async authorizedRequest(route,opts){
    calls.push({route,opts});return page([entry()]);
  }});
  await assert.rejects(service.list('WORKER',{status:'OPEN',page:0}),/관리자/);
  assert.equal(calls.length,0);
  const result=await service.list('ADMIN',{status:'OPEN',partCode:'FRAME',page:0,size:20});
  assert.equal(result.items[0].status,'OPEN');
  assert.deepEqual(calls[0],{route:'/admin/judgement-requests?status=OPEN&page=0&size=20&partCode=FRAME',
    opts:{method:'GET'}});
});
test('admin list response cannot claim OPEN when resolved or wrong part',async()=>{
  const service=createJudgementRequestServiceV4({async authorizedRequest(){return page([entry('KEPT')]);}});
  await assert.rejects(service.list('ADMIN',{status:'OPEN',page:0}),/대기/);
  const service2=createJudgementRequestServiceV4({async authorizedRequest(){return page([entry()]);}});
  await assert.rejects(service2.list('ADMIN',{status:'OPEN',partCode:'DOOR',page:0}),/부품/);
});
test('ADMIN service resolve POST returns separate correction without changing initial judgement',async()=>{
  const calls=[];const service=createJudgementRequestServiceV4({async authorizedRequest(route,opts){
    calls.push({route,opts});return {request:entry('CORRECTED'),correction};
  }});
  const result=await service.resolve('ADMIN',entry(),'CORRECT','실물 결함 확인');
  assert.equal(result.request.originalJudgement,'PASS');
  assert.equal(result.correction.correctedJudgement,'FAIL');
  assert.deepEqual(calls[0],{route:`/admin/judgement-requests/${id(111)}/resolve`,
    opts:{method:'POST',body:{decision:'CORRECT',note:'실물 결함 확인'}}});
});
test('service resolve rejects wrong result for decision instead of pretending success',async()=>{
  const service=createJudgementRequestServiceV4({async authorizedRequest(){
    return {request:entry('KEPT'),correction:null};
  }});
  await assert.rejects(service.resolve('ADMIN',entry(),'CORRECT','근거'),/유지·정정/);
});
test('detail parser accepts absent request fields as empty, correction as null',()=>{
  const data={inspectionId:id(1),inspectionNo:'INS-000001',partCode:'FRAME',
    receivedAt:'2026-11-23T14:00:00+09:00',status:'COMPLETED',displayState:'AUTO_PASS',
    source:'DEVICE',
    ai:{modelVersion:'model',calibratorVersion:'cal-1',predictedQuality:'GOOD',
      rawDefectProbability:0.01,calibratedDefectProbability:0.01,inferenceTimeMs:120},
    policy:{automationPolicyReady:true,policyVersion:'p1',passThreshold:0.02,
      recommendedAction:'AUTO_PASS',reviewReason:null},
    judgement:{finalJudgement:'PASS',judgedBy:'SYSTEM',confirmedBy:null,confirmedAt:null},
    images:null,error:null,
  };
  const detail=mapInspectionDetailV4(decodeInspectionDetailV4({data}));
  assert.deepEqual(detail.judgementRequests,[]);
  assert.equal(detail.correction,null);
  const changed=mapInspectionDetailV4(decodeInspectionDetailV4({data:{...data,
    judgementRequests:[entry('CORRECTED')],correction}}));
  assert.equal(changed.finalJudgement,'PASS');
  assert.equal(changed.correctedJudgement,'FAIL');
  assert.equal(changed.judgementRequests.length,1);
});
