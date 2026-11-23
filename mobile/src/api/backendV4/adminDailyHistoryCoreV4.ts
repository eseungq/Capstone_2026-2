/** Contract v4 §6.13 KST daily automation history and threshold-neighbor details.
 * Pure validation: no network, local aggregation, or persistent writes.
 */
export const DAILY_HISTORY_MAX_DAYS_V4=92;
export type AutomationDailyPartV4='DOOR'|'FRAME'|'COWL_COVER';
export interface DailyCountV4 {done:number;total:number}
export interface DailyOppositeV4 {
 autoPassThenFail:number;autoFailThenPass:number;resolvedRequests:number;
}
export interface DailyHistoryRowV4 {
 date:string;policyId:string|null;policyVersion:string|null;
 modelVersion:string|null;calibratorVersion:string|null;
 passThreshold:number|null;failThreshold:number|null;autoFailEnabled:boolean;
 total:number;autoPass:number;autoFail:number;
 review:DailyCountV4;manual:DailyCountV4;failed:number;
 confirmedOpposite:DailyOppositeV4;openRequests:number;
}
export interface DailyBandItemV4 {
 inspectionId:string;inspectionNo:string;calibratedDefectProbability:number|null;
 finalJudgement:'PASS'|'FAIL'|null;correctedJudgement:'PASS'|'FAIL'|null;
}
export interface DailyBandV4 {
 from:number;to:number;total:number;pass:number;fail:number;pending:number;items:DailyBandItemV4[];
}
export interface DailyDetailV4 {
 date:string;partCode:AutomationDailyPartV4;policyId:string;
 policyVersion:string;modelVersion:string|null;calibratorVersion:string|null;
 passThreshold:number|null;failThreshold:number|null;autoFailEnabled:boolean;
 band:number;passBand:DailyBandV4|null;failBand:DailyBandV4|null;reference:null;
}
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const NO=/^INS-\d{6,}$/;
const parts:readonly string[]=['DOOR','FRAME','COWL_COVER'];
const bad=(message:string):never=>{throw new Error('관리자 날짜별 이력 계약 오류: '+message);};
const obj=(v:unknown):v is Record<string,unknown>=>typeof v==='object'&&v!==null&&!Array.isArray(v);
const txt=(v:unknown):v is string=>typeof v==='string'&&v.trim().length>0;
const optionalTxt=(v:unknown):v is string|null|undefined=>v==null||typeof v==='string';
const count=(v:unknown):v is number=>Number.isSafeInteger(v)&&typeof v==='number'&&v>=0;
const frac=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1;
const fracOrNull=(v:unknown):v is number|null|undefined=>v==null||frac(v);
function dateMs(value:string):number{
 if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return NaN;
 const t=Date.parse(value+'T00:00:00.000Z');
 return Number.isFinite(t)&&new Date(t).toISOString().slice(0,10)===value?t:NaN;
}
export function validateDailyRangeV4(partCode:string,from:string,to:string){
 if(!parts.includes(partCode))throw new Error('부품은 DOOR / FRAME / COWL_COVER 중 하나여야 합니다.');
 const a=dateMs(from),b=dateMs(to);
 if(!Number.isFinite(a)||!Number.isFinite(b)||b<=a)
   throw new Error('날짜는 YYYY-MM-DD 형식이며 시작일은 종료일보다 이전이어야 합니다.');
 const days=(b-a)/86400000;
 if(days>DAILY_HISTORY_MAX_DAYS_V4)throw new Error('날짜 범위는 최대 92일입니다.');
 return {partCode:partCode as AutomationDailyPartV4,from,to,days};
}
export function kstCalendarTodayV4(atMs:number=Date.now()):string{
 const v=new Date(atMs+9*3600000).toISOString().slice(0,10);
 return v;
}
export function plusDaysV4(date:string,n:number):string{
 const ms=dateMs(date);
 if(!Number.isFinite(ms)||!Number.isInteger(n))throw new Error('KST 날짜 계산 오류');
 return new Date(ms+n*86400000).toISOString().slice(0,10);
}
function decodeCount(raw:unknown,name:string):DailyCountV4{
 if(!obj(raw)||!count(raw.done)||!count(raw.total)||raw.done>raw.total)
   return bad(name+'의 판정 완료·전체 건수가 올바르지 않습니다.');
 return {done:raw.done,total:raw.total};
}
function decodeOpposite(raw:unknown):DailyOppositeV4{
 if(!obj(raw)||!count(raw.autoPassThenFail)||!count(raw.autoFailThenPass)||!count(raw.resolvedRequests)||
 raw.autoPassThenFail+raw.autoFailThenPass>raw.resolvedRequests)
   return bad('확인 요청 정정·처리 건수가 올바르지 않습니다.');
 return {autoPassThenFail:raw.autoPassThenFail,autoFailThenPass:raw.autoFailThenPass,
   resolvedRequests:raw.resolvedRequests};
}
export function decodeDailyHistoryRowsV4(raw:unknown):DailyHistoryRowV4[]{
 if(!Array.isArray(raw))return bad('날짜별 이력은 배열이어야 합니다.');
 const keys=new Set<string>();
 let previousDate:string|null=null;
 return raw.map((value):DailyHistoryRowV4=>{
   if(!obj(value)||!txt(value.date)||!Number.isFinite(dateMs(value.date))||
      !optionalTxt(value.policyId)||!optionalTxt(value.policyVersion)||
      !optionalTxt(value.modelVersion)||!optionalTxt(value.calibratorVersion)||
      !fracOrNull(value.passThreshold)||!fracOrNull(value.failThreshold)||
      typeof value.autoFailEnabled!=='boolean'||!count(value.total)||
      !count(value.autoPass)||!count(value.autoFail)||!count(value.failed)||
      !count(value.openRequests))return bad('날짜 행 기본 필드가 올바르지 않습니다.');
   const review=decodeCount(value.review,'REVIEW'),manual=decodeCount(value.manual,'수동 전환');
   const confirmedOpposite=decodeOpposite(value.confirmedOpposite);
   if(value.total!==value.autoPass+value.autoFail+review.total ||
      manual.total>review.total||manual.done>review.done)
     return bad('total = autoPass + autoFail + review.total, manual은 REVIEW 부분집합이어야 합니다.');
   if(confirmedOpposite.autoPassThenFail>value.autoPass||
      confirmedOpposite.autoFailThenPass>value.autoFail)
     return bad('정정 건수가 시스템 자동 판정 건수보다 큽니다.');
   if(value.policyId==null && (value.policyVersion!=null||value.autoFailEnabled))
     return bad('정책 없는 행에 정책 버전이나 자동 불량 활성값이 있습니다.');
   if(value.policyId!=null&&!txt(value.policyId))return bad('policyId가 올바르지 않습니다.');
   if(previousDate!==null&&value.date>previousDate)
     return bad('날짜별 이력이 최신 날짜순이 아닙니다.');
   previousDate=value.date;
   const key=[value.date,value.policyId??'',value.modelVersion??'',value.calibratorVersion??''].join('|');
   if(keys.has(key))return bad('동일 날짜·정책·모델·보정기 행이 중복됩니다.');
   keys.add(key);
   return {
     date:value.date,policyId:(value.policyId??null) as string|null,
     policyVersion:(value.policyVersion??null) as string|null,
     modelVersion:(value.modelVersion??null) as string|null,
     calibratorVersion:(value.calibratorVersion??null) as string|null,
     passThreshold:(value.passThreshold??null) as number|null,
     failThreshold:(value.failThreshold??null) as number|null,
     autoFailEnabled:value.autoFailEnabled,total:value.total,
     autoPass:value.autoPass,autoFail:value.autoFail,review,manual,failed:value.failed,
     confirmedOpposite,openRequests:value.openRequests,
   };
 });
}
function band(raw:unknown,name:string):DailyBandV4|null{
 if(raw==null)return null;
 if(!obj(raw)||!frac(raw.from)||!frac(raw.to)||raw.from>raw.to||
    !count(raw.total)||!count(raw.pass)||!count(raw.fail)||!count(raw.pending)||
    raw.total!==raw.pass+raw.fail+raw.pending||!Array.isArray(raw.items)||
    raw.items.length!==raw.total)return bad(name+' 구간 합계·경계가 올바르지 않습니다.');
 const ids=new Set<string>();
 let prior=-1;
 const items=raw.items.map((row):DailyBandItemV4=>{
   if(!obj(row)||!txt(row.inspectionId)||!UUID.test(row.inspectionId)||
     !txt(row.inspectionNo)||!NO.test(row.inspectionNo)||
     !fracOrNull(row.calibratedDefectProbability)||
     (row.finalJudgement!=null&&row.finalJudgement!=='PASS'&&row.finalJudgement!=='FAIL')||
     (row.correctedJudgement!=null&&row.correctedJudgement!=='PASS'&&row.correctedJudgement!=='FAIL'))
     return bad(name+' 검사 식별·판정 정보가 유효하지 않습니다.');
   if(ids.has(row.inspectionId))return bad(name+'에 동일 검사 ID가 중복됩니다.');
   ids.add(row.inspectionId);
   const prob=row.calibratedDefectProbability;
   if(prob==null||prob<raw.from||prob>raw.to||prob<prior)
     return bad(name+' 검사의 보정 확률이 범위를 벗어나거나 순서가 올바르지 않습니다.');
   prior=prob;
   return {inspectionId:row.inspectionId,inspectionNo:row.inspectionNo,
     calibratedDefectProbability:prob,
     finalJudgement:(row.finalJudgement??null) as 'PASS'|'FAIL'|null,
     correctedJudgement:(row.correctedJudgement??null) as 'PASS'|'FAIL'|null};
 });
 return {from:raw.from,to:raw.to,total:raw.total,pass:raw.pass,fail:raw.fail,
   pending:raw.pending,items};
}
export function decodeDailyDetailV4(raw:unknown,expected:{
  partCode:AutomationDailyPartV4;date:string;policyId:string;band:number;
}):DailyDetailV4{
 if(!obj(raw)||raw.date!==expected.date||raw.partCode!==expected.partCode||
    raw.policyId!==expected.policyId||!txt(raw.policyId)||
    !txt(raw.policyVersion)||!optionalTxt(raw.modelVersion)||
    !optionalTxt(raw.calibratorVersion)||!fracOrNull(raw.passThreshold)||
    !fracOrNull(raw.failThreshold)||typeof raw.autoFailEnabled!=='boolean'||
    typeof raw.band!=='number'||!Number.isFinite(raw.band)||
    Math.abs(raw.band-expected.band)>1e-9||raw.reference!=null)
   return bad('날짜·정책·band·참고 자료가 요청 계약과 다릅니다.');
 const passBand=band(raw.passBand,'통과 기준'),failBand=band(raw.failBand,'불량 기준');
 if(raw.failThreshold==null&&failBand!==null)
   return bad('불량 기준이 없는 정책인데 불량 기준 주변 구간이 반환됐습니다.');
 if(raw.passThreshold==null&&passBand!==null)
   return bad('통과 기준이 없는 정책인데 통과 기준 주변 구간이 반환됐습니다.');
 return {
   date:raw.date,partCode:raw.partCode,policyId:raw.policyId,
   policyVersion:raw.policyVersion,
   modelVersion:(raw.modelVersion??null) as string|null,
   calibratorVersion:(raw.calibratorVersion??null) as string|null,
   passThreshold:(raw.passThreshold??null) as number|null,
   failThreshold:(raw.failThreshold??null) as number|null,
   autoFailEnabled:raw.autoFailEnabled,band:raw.band,
   passBand,failBand,reference:null,
 };
}
export function dailyAiReviewRateV4(row:DailyHistoryRowV4):number|null{
 const denominator=row.total-row.manual.total;
 if(denominator<=0)return null;
 return (row.review.total-row.manual.total)/denominator;
}
export function oppositeEvidenceTextV4(row:DailyHistoryRowV4):string{
 const n=row.confirmedOpposite.resolvedRequests;
 return n===0?'확인 자료 없음':`확인 ${n}건 중 정정 ${row.confirmedOpposite.autoPassThenFail+row.confirmedOpposite.autoFailThenPass}건`;
}
export function validateDailyBandV4(value:string):number{
 const raw=value.trim();
 if(!/^(?:0(?:\.\d+)?|1(?:\.0+)?)$/.test(raw))
   throw new Error('band는 0.001~0.5 사이의 확률 차로 입력하세요.');
 const number=Number(raw);
 if(!Number.isFinite(number)||number<0.001||number>0.5)
   throw new Error('band는 0.001~0.5 사이여야 합니다.');
 return number;
}
