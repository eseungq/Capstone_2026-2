/**
 * AUTO_FAIL admin policy operations (contract v4 6.9 / backend PR #52).
 * POST only on explicit ADMIN action; returns a NEW INACTIVE policy, never implicitly activates.
 */
import type {AdminPolicyV4,PolicyAdminTransportV4} from './adminPolicyServiceV4';
import {decodeAdminPolicyV4,PolicyAdminContractErrorV4} from './adminPolicyServiceV4';
import {
  ensureAutoFailToggleV4,makeAutoFailThresholdEditV4,sameAutoFailPolicyLineageV4,
} from './autoFailPolicyCoreV4';
export function createAutoFailPolicyServiceV4(transport:PolicyAdminTransportV4){
  let writing=false;
  async function guardAdmin(){
    const session=await transport.restore();
    if(!session.signedIn||session.role!=='ADMIN')
      throw new Error('실제 서버 ADMIN 계정으로 로그인해야 자동 불량 정책을 저장할 수 있습니다.');
  }
  async function serialize<T>(f:()=>Promise<T>):Promise<T>{
    if(writing)throw new Error('다른 정책 저장 요청을 처리 중입니다.');
    writing=true;
    try{return await f();}finally{writing=false;}
  }
  async function saveThreshold(
    base:AdminPolicyV4,threshold:string,min:string,max:string,
  ):Promise<AdminPolicyV4>{
    return serialize(async()=>{
      await guardAdmin();
      const body=makeAutoFailThresholdEditV4(base,threshold,min,max);
      const raw=await transport.authorizedRequest<unknown>(
        `/admin/policies/${encodeURIComponent(base.policyId)}/fail-threshold`,
        {method:'POST',body});
      const next=decodeAdminPolicyV4(raw);
      if(!sameAutoFailPolicyLineageV4(base,next) ||
        next.autoFailEnabled!==base.autoFailEnabled||
        next.failThreshold!==body.failThreshold||
        next.failValidatedMin!==body.failValidatedMin||
        next.failValidatedMax!==body.failValidatedMax){
        throw new PolicyAdminContractErrorV4('새 불량 기준 정책이 비활성 버전으로 저장되지 않았거나 응답 값이 다릅니다.');
      }
      return next;
    });
  }
  async function saveToggle(base:AdminPolicyV4,enabled:boolean):Promise<AdminPolicyV4>{
    return serialize(async()=>{
      await guardAdmin();
      ensureAutoFailToggleV4(base,enabled);
      const raw=await transport.authorizedRequest<unknown>(
        `/admin/policies/${encodeURIComponent(base.policyId)}/auto-fail`,
        {method:'POST',body:{enabled}});
      const next=decodeAdminPolicyV4(raw);
      if(!sameAutoFailPolicyLineageV4(base,next)||next.autoFailEnabled!==enabled||
        next.failThreshold!==base.failThreshold||
        next.failValidatedMin!==base.failValidatedMin||
        next.failValidatedMax!==base.failValidatedMax){
        throw new PolicyAdminContractErrorV4('자동 불량 켜기/끄기 응답이 새로운 비활성 버전과 일치하지 않습니다.');
      }
      return next;
    });
  }
  return {saveThreshold,saveToggle};
}
