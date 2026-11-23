/** API v4 §6.13 read-only daily stats, date boundaries, ratio and bands. Zero live requests. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
Module._extensions['.ts']=(module,filename)=>{
 module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{fileName:filename,
   compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,filename);
};
const root=path.join(__dirname,'../src/api/backendV4');
const core=require(path.join(root,'adminDailyHistoryCoreV4.ts'));
const {createDailyHistoryServiceV4}=require(path.join(root,'adminDailyHistoryServiceV4.ts'));
const pid='91f17717-d9c0-4e77-8f1b-7d9a66cc11a0';
const uuid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const row=(changes={})=>({
 date:'2026-11-23',policyId:pid,policyVersion:'cowl-f1-a1',
 modelVersion:'cowl-e08',calibratorVersion:'cal-v1',
 passThreshold:0.0163,failThreshold:0.9966,autoFailEnabled:true,
 total:8,autoPass:2,autoFail:2,
 review:{done:2,total:4},manual:{done:1,total:1},failed:1,
 confirmedOpposite:{autoPassThenFail:1,autoFailThenPass:0,resolvedRequests:2},
 openRequests:1,...changes,
});
const band=(items=[])=>({
 from:0.0163,to:0.0663,total:items.length,
 pass:items.filter(x=>x.finalJudgement==='PASS').length,
 fail:items.filter(x=>x.finalJudgement==='FAIL').length,
 pending:items.filter(x=>x.finalJudgement==null).length,items,
});
const item=(n,prob=0.025,judgement=null,corrected=null)=>({
 inspectionId:uuid(n),inspectionNo:`INS-${String(n).padStart(6,'0')}`,
 calibratedDefectProbability:prob,finalJudgement:judgement,correctedJudgement:corrected,
});
const detail=(changes={})=>({
 date:'2026-11-23',partCode:'COWL_COVER',policyId:pid,
 policyVersion:'cowl-f1-a1',modelVersion:'cowl-e08',calibratorVersion:'cal-v1',
 passThreshold:0.0163,failThreshold:0.9966,autoFailEnabled:true,band:0.05,
 passBand:band([item(1,0.025,'PASS'),item(2,0.05)]),
 failBand:{from:0.9466,to:0.9966,total:0,pass:0,fail:0,pending:0,items:[]},
 reference:null,...changes,
});
function mock({role='ADMIN',signedIn=true,dailyRows=[row()],detailResponse=detail()}={}){
 const calls=[];const service=createDailyHistoryServiceV4({
   async restore(){return {signedIn,role,loginId:signedIn?'admin':null};},
   async authorizedRequest(url,opts){
     calls.push({url,opts});
     if(url.includes('/daily/detail?'))return detailResponse;
     return dailyRows;
   },
 });
 return {service,calls};
}
test('KST calendar day is independent of local/UTC machine timezone',()=>{
 // 2026-11-23 15:30 UTC = 2026-11-24 00:30 Seoul
 assert.equal(core.kstCalendarTodayV4(Date.parse('2026-11-23T15:30:00Z')),'2026-11-24');
 assert.equal(core.kstCalendarTodayV4(Date.parse('2026-11-23T14:59:59Z')),'2026-11-23');
});
test('last-seven-day default range arithmetic and exclusive tomorrow boundary',()=>{
 assert.equal(core.plusDaysV4('2026-11-24',-6),'2026-11-18');
 assert.equal(core.plusDaysV4('2026-11-24',1),'2026-11-25');
 assert.equal(core.validateDailyRangeV4('COWL_COVER','2026-11-18','2026-11-25').days,7);
});
test('date validation rejects nonexistent dates, reversed and 93 days',()=>{
 for(const [a,b] of [['2026-02-30','2026-03-01'],['2026-11-24','2026-11-24'],['2026-12-01','2026-11-24']])
   assert.throws(()=>core.validateDailyRangeV4('COWL_COVER',a,b),/날짜/);
 assert.throws(()=>core.validateDailyRangeV4('COWL_COVER','2026-01-01','2026-04-04'),/92일/);
 assert.equal(core.validateDailyRangeV4('DOOR','2026-01-01','2026-04-03').days,92);
});
test('unknown part fails before transport; all three known parts accepted',()=>{
 assert.throws(()=>core.validateDailyRangeV4('UNKNOWN','2026-11-23','2026-11-24'),/부품/);
 for(const p of ['DOOR','FRAME','COWL_COVER'])
   assert.equal(core.validateDailyRangeV4(p,'2026-11-23','2026-11-24').partCode,p);
});
test('row parser preserves counts and manual subset rather than double counting',()=>{
 const data=core.decodeDailyHistoryRowsV4([row()])[0];
 assert.equal(data.total,8);assert.equal(data.review.total,4);
 assert.equal(data.manual.total,1);assert.equal(data.failed,1);
 assert.equal(data.confirmedOpposite.resolvedRequests,2);
});
test('AI REVIEW ratio excludes manual conversion and FAILED',()=>{
 assert.equal(core.dailyAiReviewRateV4(row()),3/7);
 assert.equal(core.dailyAiReviewRateV4(row({
   total:3,autoPass:0,autoFail:0,review:{done:2,total:3},
   manual:{done:2,total:3},confirmedOpposite:{autoPassThenFail:0,autoFailThenPass:0,resolvedRequests:0},
 })),null);
});
test('resolvedRequests=0 explicitly shows no evidence, not zero percent accuracy',()=>{
 const r=row({confirmedOpposite:{autoPassThenFail:0,autoFailThenPass:0,resolvedRequests:0}});
 assert.equal(core.oppositeEvidenceTextV4(r),'확인 자료 없음');
 assert.equal(core.oppositeEvidenceTextV4(row()),'확인 2건 중 정정 1건');
});
test('bad total, manual exceeding REVIEW, or done exceeding total fails closed',()=>{
 assert.throws(()=>core.decodeDailyHistoryRowsV4([row({total:9})]),/total/);
 assert.throws(()=>core.decodeDailyHistoryRowsV4([row({manual:{done:1,total:5}})]),/부분집합/);
 assert.throws(()=>core.decodeDailyHistoryRowsV4([row({review:{done:5,total:4}})]),/REVIEW/);
});
test('policy absent allows separate null row while AUTO_FAIL disabled',()=>{
 const none=row({policyId:null,policyVersion:null,passThreshold:null,
 failThreshold:null,autoFailEnabled:false,autoPass:0,autoFail:0,
 total:2,review:{done:1,total:2},manual:{done:1,total:1},
 confirmedOpposite:{autoPassThenFail:0,autoFailThenPass:0,resolvedRequests:0}});
 const all=core.decodeDailyHistoryRowsV4([row(),none]);
 assert.equal(all[1].policyId,null);
 assert.throws(()=>core.decodeDailyHistoryRowsV4([{...none,autoFailEnabled:true}]),/정책 없는/);
});
test('row sorting and duplicate policy/date/model grouped rows enforced',()=>{
 assert.throws(()=>core.decodeDailyHistoryRowsV4([row(),row()]),/중복/);
 assert.throws(()=>core.decodeDailyHistoryRowsV4([
   row({date:'2026-11-22'}),row({date:'2026-11-23'}),
 ]),/최신/);
 assert.equal(core.decodeDailyHistoryRowsV4([
   row({date:'2026-11-24'}),row(),
 ]).length,2);
});
test('band 0.001..0.5 allowed; out-of-range and wrong syntax rejected',()=>{
 for(const input of ['0.001','0.05','0.5'])assert.equal(core.validateDailyBandV4(input),Number(input));
 for(const input of ['0','0.0009','0.5001','-0.1','5','garbage','0,05'])
   assert.throws(()=>core.validateDailyBandV4(input),/band/);
});
test('detail supports threshold bands and corrected verdict separately',()=>{
 const d=core.decodeDailyDetailV4(detail(),{
   partCode:'COWL_COVER',date:'2026-11-23',policyId:pid,band:0.05,
 });
 assert.equal(d.passBand.total,2);
 assert.equal(d.passBand.pending,1);
 assert.equal(d.reference,null);
 const corrected=detail({passBand:band([item(1,0.025,'PASS','FAIL')])});
 assert.equal(core.decodeDailyDetailV4(corrected,{
   partCode:'COWL_COVER',date:'2026-11-23',policyId:pid,band:0.05,
 }).passBand.items[0].correctedJudgement,'FAIL');
});
test('null failThreshold must have null failBand; reference remains null',()=>{
 const d=detail({failThreshold:null,autoFailEnabled:false,failBand:null});
 assert.equal(core.decodeDailyDetailV4(d,{
   partCode:'COWL_COVER',date:'2026-11-23',policyId:pid,band:0.05,
 }).failBand,null);
 assert.throws(()=>core.decodeDailyDetailV4({...d,failBand:band([])},{
   partCode:'COWL_COVER',date:'2026-11-23',policyId:pid,band:0.05,
 }),/불량 기준/);
 assert.throws(()=>core.decodeDailyDetailV4(detail({reference:{value:1}}),{
   partCode:'COWL_COVER',date:'2026-11-23',policyId:pid,band:0.05,
 }),/참고/);
});
test('detail rejects incorrect policy id, date, band, item order and totals',()=>{
 const expect={partCode:'COWL_COVER',date:'2026-11-23',policyId:pid,band:0.05};
 assert.throws(()=>core.decodeDailyDetailV4(detail(),{...expect,policyId:'another'}),/계약/);
 assert.throws(()=>core.decodeDailyDetailV4(detail({band:0.04}),expect),/계약/);
 assert.throws(()=>core.decodeDailyDetailV4(detail({passBand:{
   ...band([item(2,0.05),item(1,0.025)]),
 }}),expect),/순서/);
 assert.throws(()=>core.decodeDailyDetailV4(detail({passBand:{...band([item(1)]),pending:2}}),expect),/합계/);
});
test('ADMIN daily service sends a single GET with KST dates, no POST',async()=>{
 const h=mock();
 const result=await h.service.daily('COWL_COVER','2026-11-23','2026-11-24');
 assert.equal(result[0].total,8);
 assert.deepEqual(h.calls,[{
   url:'/admin/automation/daily?partCode=COWL_COVER&from=2026-11-23&to=2026-11-24',
   opts:{method:'GET'},
 }]);
});
test('WORKER and logged-out roles cannot access either GET endpoint',async()=>{
 for(const cfg of [{role:'WORKER'},{signedIn:false}]){
   const h=mock(cfg);
   await assert.rejects(h.service.daily('COWL_COVER','2026-11-23','2026-11-24'),/ADMIN/);
   await assert.rejects(h.service.detail('COWL_COVER','2026-11-23',pid,'0.05'),/ADMIN/);
   assert.equal(h.calls.length,0);
 }
});
test('ADMIN detail URL matches policy, KST date, requested band',async()=>{
 const h=mock();const d=await h.service.detail('COWL_COVER','2026-11-23',pid,'0.05');
 assert.equal(d.policyId,pid);
 assert.deepEqual(h.calls,[{
   url:`/admin/automation/daily/detail?partCode=COWL_COVER&date=2026-11-23&policyId=${pid}&band=0.05`,
   opts:{method:'GET'},
 }]);
});
test('no policy row must not trigger detail request; unknown band rejected first',async()=>{
 const h=mock();
 await assert.rejects(h.service.detail('COWL_COVER','2026-11-23','', '0.05'),/정책 없는/);
 await assert.rejects(h.service.detail('COWL_COVER','2026-11-23',pid,'0.7'),/band/);
 assert.equal(h.calls.length,0);
});
test('server may not return rows outside requested date range',async()=>{
 const h=mock({dailyRows:[row({date:'2026-11-22'})]});
 await assert.rejects(h.service.daily('COWL_COVER','2026-11-23','2026-11-24'),/범위 밖/);
});
