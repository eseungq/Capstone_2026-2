/** ADMIN read-only GET service for v4 §6.13. No local aggregation / writes. */
import type {AuthPublicState} from './authCore';
import {
 decodeDailyHistoryRowsV4,decodeDailyDetailV4,validateDailyBandV4,validateDailyRangeV4,
 type DailyHistoryRowV4,type DailyDetailV4,type AutomationDailyPartV4,
} from './adminDailyHistoryCoreV4';
export interface DailyReadTransportV4{
 restore():Promise<AuthPublicState>;
 authorizedRequest<T>(path:string,options?:{method?:'GET'|'POST';body?:unknown}):Promise<T>;
}
export function createDailyHistoryServiceV4(transport:DailyReadTransportV4){
 async function guard(){
   const session=await transport.restore();
   if(!session.signedIn||session.role!=='ADMIN')
     throw new Error('실제 서버 ADMIN 계정으로 로그인해야 날짜별 이력을 조회할 수 있습니다.');
 }
 return {
  async daily(partCode:string,from:string,to:string):Promise<DailyHistoryRowV4[]>{
   const validated=validateDailyRangeV4(partCode,from,to);
   await guard();
   const path=`/admin/automation/daily?partCode=${encodeURIComponent(validated.partCode)}&from=${validated.from}&to=${validated.to}`;
   const raw=await transport.authorizedRequest<unknown>(path,{method:'GET'});
   const rows=decodeDailyHistoryRowsV4(raw);
   if(rows.some(x=>x.date<validated.from||x.date>=validated.to))
     throw new Error('서버 조회 날짜 범위 밖의 검사 통계 행이 반환됐습니다.');
   return rows;
  },
  async detail(partCode:string,date:string,policyId:string,band:string):Promise<DailyDetailV4>{
   validateDailyRangeV4(partCode,date,
     new Date(Date.parse(date+'T00:00:00Z')+86400000).toISOString().slice(0,10));
   if(!policyId.trim())throw new Error('정책 없는 이력 행은 기준 상세가 제공되지 않습니다.');
   const fraction=validateDailyBandV4(band);
   await guard();
   const part=partCode as AutomationDailyPartV4;
   const path=`/admin/automation/daily/detail?partCode=${encodeURIComponent(part)}&date=${date}&policyId=${encodeURIComponent(policyId)}&band=${fraction}`;
   const raw=await transport.authorizedRequest<unknown>(path,{method:'GET'});
   return decodeDailyDetailV4(raw,{partCode:part,date,policyId,band:fraction});
  },
 };
}
