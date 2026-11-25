import type {ReviewReasonV4, DisplayStateV4} from '../api/backendV4/types';

type ReviewCopy = {title:string; description:string; adminDescription:string; adminCause:string};

/** Display-only vocabulary. Never infer the server's decision or change review priority. */
const copies:Record<ReviewReasonV4,ReviewCopy>={
  DEFECT_PREDICTED:{
    title:'불량 의심',
    description:'AI가 불량으로 예측했습니다.',
    adminDescription:'AI가 불량으로 예측했습니다.',
    adminCause:'AI 불량 예측',
  },
  ABOVE_THRESHOLD:{
    title:'정상 예측, 확신 부족',
    description:'AI는 정상으로 봤지만 자동 통과하기에는 확신이 부족했습니다.',
    adminDescription:'AI는 정상으로 봤지만 자동 통과에 필요한 확신 수준을 충족하지 못했습니다. 보정 불량 확률이 자동 통과 기준치를 초과했습니다.',
    adminCause:'자동 통과 기준치 초과',
  },
  NO_ACTIVE_POLICY:{
    title:'자동 판정 불가',
    description:'자동 판정을 할 수 없었습니다. 사진을 직접 확인해 주세요.',
    adminDescription:'판정 기준을 적용하지 못했습니다. 사진을 직접 확인해 주세요.',
    adminCause:'활성 정책 없음',
  },
  CALIBRATION_UNAVAILABLE:{
    title:'자동 판정 불가',
    description:'자동 판정을 할 수 없었습니다. 사진을 직접 확인해 주세요.',
    adminDescription:'판정 기준을 적용하지 못했습니다. 사진을 직접 확인해 주세요.',
    adminCause:'보정 확률 사용 불가',
  },
  AI_UNAVAILABLE:{
    title:'AI 분석 없음',
    description:'작업자가 직접 판정합니다.',
    adminDescription:'작업자가 직접 판정합니다.',
    adminCause:'AI 분석 미제공',
  },
};
const unknown:ReviewCopy={
  title:'판정 필요',
  description:'자동 판정되지 않은 검사입니다. 사진을 직접 확인해 주세요.',
  adminDescription:'서버에서 구체적인 판정 대기 사유를 제공하지 않았습니다.',
  adminCause:'사유 미제공',
};
export function reviewReasonCopyV4(reason:ReviewReasonV4|null|undefined):ReviewCopy{
  return reason?copies[reason]??unknown:unknown;
}
export function reviewListReasonV4(state:DisplayStateV4,reason:ReviewReasonV4|null|undefined):string|null{
  return state==='REVIEW_PENDING'?reviewReasonCopyV4(reason).title:null;
}
export function hasReviewReasonDetailV4(state:DisplayStateV4,reason:ReviewReasonV4|null|undefined):boolean{
  return state==='REVIEW_PENDING'||(state==='REVIEW_DONE'&&reason!=null);
}
