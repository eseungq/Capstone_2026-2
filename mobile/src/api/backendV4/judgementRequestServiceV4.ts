/** 계약 v4 §6.12 — 서버는 JSON {data}를 해제한 객체를 반환. 이 모듈은 사용자 액션 때만 POST. */
import type { BackendRole } from './authCore';
import {
  makeJudgementRequestBodyV4,makeJudgementResolveBodyV4,
  decodeJudgementRequestV4,decodeJudgementResolveV4,decodeJudgementQueuePageV4,
} from './judgementRequestCoreV4';
import type {
  JudgementRequestV4,JudgementCorrectionV4,JudgementResolveDecisionV4,
  JudgementQueueStatusV4,JudgementQueuePageV4,JudgementResolveResultV4,
} from './judgementRequestCoreV4';
import type { InspectionViewV4, FinalJudgementV4 } from './types';
import {assertWriteUuidV4,WriteV4ValidationError} from './inspectionWriteCore';

export interface JudgementRequestTransportV4 {
  authorizedRequest<T>(path:string,options?:{method?:'GET'|'POST';body?:unknown}):Promise<T>;
}
export function createJudgementRequestServiceV4(transport:JudgementRequestTransportV4) {
  const inFlight=new Set<string>();
  async function postOnce<T>(key:string,path:string,body:unknown,decode:(raw:unknown)=>T):Promise<T>{
    if(inFlight.has(key))throw new WriteV4ValidationError('REQUEST_IN_PROGRESS_LOCAL','같은 요청을 제출 중입니다.');
    inFlight.add(key);
    try{
      const raw=await transport.authorizedRequest<unknown>(path,{method:'POST',body});
      return decode(raw);
    }finally{inFlight.delete(key);}
  }
  async function request(role:BackendRole|null,detail:InspectionViewV4,
    claimed:FinalJudgementV4,area:string,reason:string):Promise<JudgementRequestV4>{
    const body=makeJudgementRequestBodyV4(role,detail,claimed,area,reason);
    const id=detail.inspectionId;
    return postOnce('request:'+id,`/inspections/${encodeURIComponent(id)}/judgement-requests`,body,raw=>{
      const result=decodeJudgementRequestV4(raw);
      if(result.inspectionId!==id || result.claimedJudgement!==claimed)
        throw new WriteV4ValidationError('RESPONSE_MISMATCH','요청한 검사·판정과 서버 응답이 다릅니다.');
      return result;
    });
  }
  async function list(role:BackendRole|null,params:{
    status:JudgementQueueStatusV4;partCode?:string;page:number;size?:number;
  }):Promise<JudgementQueuePageV4>{
    if(role!=='ADMIN') throw new WriteV4ValidationError('ACCESS_DENIED','관리자만 판정 확인 요청을 조회할 수 있습니다.');
    if(!['OPEN','RESOLVED','ALL'].includes(params.status) ||
      !Number.isSafeInteger(params.page)||params.page<0 ||
      !Number.isSafeInteger(params.size??20)||(params.size??20)<1||(params.size??20)>100)
      throw new WriteV4ValidationError('INVALID_PARAMETER','요청 목록 필터 또는 페이지가 잘못됐습니다.');
    const q=[`status=${params.status}`,`page=${params.page}`,`size=${params.size??20}`];
    if(params.partCode?.trim())q.push(`partCode=${encodeURIComponent(params.partCode.trim())}`);
    const raw=await transport.authorizedRequest<unknown>(
      `/admin/judgement-requests?${q.join('&')}`,{method:'GET'});
    const page=decodeJudgementQueuePageV4(raw,params.page);
    if(params.status==='OPEN'&&page.items.some(x=>x.status!=='OPEN')) {
      throw new WriteV4ValidationError('RESPONSE_MISMATCH','대기 요청 목록에 처리된 요청이 포함됐습니다.');
    }
    if(params.status==='RESOLVED'&&page.items.some(x=>x.status==='OPEN')) {
      throw new WriteV4ValidationError('RESPONSE_MISMATCH','처리 완료 목록에 대기 중인 요청이 포함됐습니다.');
    }
    if(params.partCode && page.items.some(x=>x.partCode!==params.partCode)) {
      throw new WriteV4ValidationError('RESPONSE_MISMATCH','부품 필터 결과가 일치하지 않습니다.');
    }
    return page;
  }
  async function resolve(role:BackendRole|null,entry:JudgementRequestV4,
    decision:JudgementResolveDecisionV4,note:string):Promise<JudgementResolveResultV4>{
    const body=makeJudgementResolveBodyV4(role,entry,decision,note);
    assertWriteUuidV4(entry.requestId);
    return postOnce('resolve:'+entry.requestId,
      `/admin/judgement-requests/${encodeURIComponent(entry.requestId)}/resolve`,body,
      raw=>{
        const value=decodeJudgementResolveV4(raw,entry.requestId);
        if((decision==='KEEP'&&value.request.status!=='KEPT') ||
          (decision==='CORRECT'&&value.request.status!=='CORRECTED'))
          throw new WriteV4ValidationError('RESPONSE_MISMATCH','요청한 유지·정정 결정과 응답이 다릅니다.');
        return value;
      });
  }
  return {request,list,resolve};
}
