/** API v4 §6.9, TBD-18. Automatic FAIL threshold values are 0..1 fractions, UI accepts percent. */
import type {AdminPolicyV4} from './adminPolicyServiceV4';

export interface AutoFailThresholdEditV4 {
  failThreshold:number; failValidatedMin:number; failValidatedMax:number;
}
/** Equal bounds fix the trial value; they do not establish a validated tuning range. */
export function autoFailRangeLabelV4(min:number|null,max:number|null):string {
  if(min==null||max==null)return '미제공';
  if(min===max)return '검증 범위 없음(고정값)';
  return `${(min*100).toFixed(4)}% ~ ${(max*100).toFixed(4)}%`;
}
export function parseAutoFailPercentV4(input:string):number {
  const t=input.trim();
  // Four decimal places of percent correspond to six fractional decimal places.
  if(!/^(?:\d{1,3})(?:\.\d{1,4})?$/.test(t))
    throw new Error('백분율은 0~100, 소수점 넷째 자리까지 입력해 주세요.');
  const number=Number(t);
  if(!Number.isFinite(number)||number<0||number>100)
    throw new Error('백분율은 0~100 사이여야 합니다.');
  return Math.round(number*10000)/1000000;
}
export function makeAutoFailThresholdEditV4(
  base:AdminPolicyV4, thresholdPercent:string,minPercent:string,maxPercent:string,
):AutoFailThresholdEditV4 {
  if(base.partCode!=='COWL_COVER'||!base.ready||!base.active)
    throw new Error('준비된 활성 COWL_COVER 정책에서만 불량 기준을 조정할 수 있습니다.');
  if(base.autoFailEnabled===null)
    throw new Error('현재 서버가 자동 불량 정책 기능을 제공하지 않습니다.');
  if(base.passThreshold==null)
    throw new Error('서버의 자동 통과 기준이 없어 자동 불량 기준을 조정할 수 없습니다.');
  const threshold=parseAutoFailPercentV4(thresholdPercent);
  const min=parseAutoFailPercentV4(minPercent);
  const max=parseAutoFailPercentV4(maxPercent);
  if(min>max)throw new Error('불량 기준 검증 최솟값은 최댓값 이하여야 합니다.');
  if(min>threshold||threshold>max)
    throw new Error('불량 기준은 입력한 min·max 범위 안에 있어야 합니다.');
  if(threshold<=base.passThreshold)
    throw new Error('자동 불량 기준은 자동 통과 기준보다 높아야 합니다.');
  return {failThreshold:threshold,failValidatedMin:min,failValidatedMax:max};
}
export function ensureAutoFailToggleV4(base:AdminPolicyV4,enabled:boolean):void {
  if(base.partCode!=='COWL_COVER'||!base.ready)
    throw new Error('준비된 COWL_COVER 정책에서만 자동 불량 설정을 변경할 수 있습니다.');
  if(base.autoFailEnabled===null)
    throw new Error('현재 서버가 자동 불량 설정을 지원하지 않습니다.');
  if(enabled===base.autoFailEnabled)
    throw new Error('이미 해당 설정 상태입니다. 불필요한 새 정책 생성을 방지합니다.');
  if(enabled && (base.failThreshold==null||base.failValidatedMin==null||
      base.failValidatedMax==null))
    throw new Error('자동 불량을 켜기 전에 불량 기준과 min·max 설정값을 등록해야 합니다.');
  if(enabled && (base.passThreshold==null || base.failThreshold! <= base.passThreshold))
    throw new Error('자동 불량 기준은 자동 통과 기준보다 높아야 합니다.');
}
export function sameAutoFailPolicyLineageV4(base:AdminPolicyV4,next:AdminPolicyV4):boolean {
  return next.policyId!==base.policyId&&next.basedOnPolicyId===base.policyId&&
    next.partCode===base.partCode&&next.modelVersion===base.modelVersion&&
    next.calibratorVersion===base.calibratorVersion&&next.ready===base.ready&&
    next.active===false&&next.passThreshold===base.passThreshold;
}
