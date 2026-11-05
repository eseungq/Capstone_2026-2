/**
 * 67단계 · AI 결과/Grad-CAM 표시 규칙 (오프라인, 순수 함수)
 * 근거: 백엔드 API v4 초안(10/15) + 도현님 10/28 AI 현황 공유.
 * 승규님과 합의한 NO_ACTIVATION 추가 상태값을 표시 계층에 반영합니다.
 * 현재 실측 보정값/보정기 버전/운영 AUTO_PASS 정책은 검증되지 않았습니다.
 */
import type { InspectionDetailV4 } from './types';

export type CamPresentationState =
  | 'PENDING' | 'AI_FAILED' | 'NOT_REQUIRED' | 'AVAILABLE'
  | 'GENERATED_URL_MISSING' | 'GENERATION_FAILED'
  | 'NO_SPATIAL_RESPONSE' | 'UNKNOWN' | 'CONTRACT_MISMATCH';


export interface AiDisplayPresentationV4 {
  partSupportText: string;
  aiPrediction: 'GOOD' | 'DEFECT' | null;
  aiPredictionLabel: string;
  modelVersionText: string;
  rawDefectScoreText: string;
  calibratedProbabilityText: string;
  calibratorVersionText: string;
  policyActionText: string;
  finalJudgementText: string;
  displayStateText: string;
  cam: {
    state: CamPresentationState;
    title: string;
    description: string;
    imageUrl: string | null;
    /** 오버레이는 결함 좌표, 마스크, 정확한 면적이 아닙니다. */
    showInterpretationDisclaimer: boolean;
  };
  /** 서버에서 받은 상태를 재판정하지 않습니다. */
  policyBlockPresent: boolean;
}

const PERCENT_DIGITS = 1;
export function formatCalibratedProbabilityV4(value: number | null | undefined): string {
  // 0.0%와 미제공(null)을 반드시 구분합니다.
  if (value == null) return '미제공 (보정 전 점수와 별개)';
  if (!Number.isFinite(value) || value < 0 || value > 1) return '유효하지 않은 값';
  return `${(value * 100).toFixed(PERCENT_DIGITS)}% (보정 불량 확률)`;
}
export function formatRawDefectScoreV4(value: number | null | undefined): string {
  if (value == null) return '미제공';
  if (!Number.isFinite(value) || value < 0 || value > 1) return '유효하지 않은 값';
  return `${(value * 100).toFixed(PERCENT_DIGITS)}% (보정 전 · 자동 통과 판단에 사용하지 않음)`;
}

const spatialNoResponse = 'AI 예측은 완료됐지만, 위치별 강조 반응이 없어 판단 근거 이미지를 제공하기 어렵습니다.';
const camCaveat = 'Grad-CAM은 AI 판단 참고자료이며 정확한 결함 위치·면적·마스크를 뜻하지 않습니다.';

function makeCamViewV4(
  detail: InspectionDetailV4
): AiDisplayPresentationV4['cam'] {
  const ai = detail.ai;
  const status = detail.images?.gradcamStatus ?? null;
  const url = detail.images?.gradcam?.url ?? null;
  const common = (state: CamPresentationState, title: string, description: string, imageUrl: string | null = null) => ({
    state, title, description, imageUrl,
    showInterpretationDisclaimer: imageUrl !== null,
  });

  if (!ai) {
    return detail.status === 'FAILED'
      ? common('AI_FAILED', 'AI 분석 실패', 'AI 분류 결과가 없어 Grad-CAM 상태도 판단할 수 없습니다.')
      : common('PENDING', 'AI 분석 대기·진행 중', 'AI 예측과 Grad-CAM이 아직 준비되지 않았습니다.');
  }

  if (ai.predictedQuality === 'GOOD') {
    // GOOD는 AI 규칙상 CAM 대상이 아닙니다. 백엔드가 상충한 코드를 보낸다면 조용히 정상으로 취급하지 않습니다.
    if (status === 'FAILED' || status === 'GENERATED' || status === 'NO_ACTIVATION' || url !== null) {
      return common('CONTRACT_MISMATCH', 'CAM 응답 확인 필요', 'GOOD 예측의 CAM 정보가 합의된 규칙과 일치하지 않습니다. 백엔드 응답을 확인해 주세요.');
    }
    return common('NOT_REQUIRED', 'Grad-CAM 생성 대상 아님', 'GOOD 예측은 CAM을 생성하지 않습니다. REVIEW 상태여도 CAM이 없는 것은 정상입니다.');
  }

  // DEFECT: 분류는 성공했고 CAM이 실패해도 DEFECT는 유지합니다.
  if (status === 'NOT_REQUIRED') {
    return common('CONTRACT_MISMATCH', 'CAM 응답 확인 필요', 'DEFECT 예측의 CAM 상태가 NOT_REQUIRED로 도착했습니다. 백엔드 응답을 확인해 주세요.');
  }
  if (status === 'FAILED') {
    return common('GENERATION_FAILED', 'Grad-CAM 생성 실패', 'AI의 DEFECT 예측은 유지됩니다. 판단 근거 이미지가 제공되지 않았습니다.');
  }
  if (status === 'NO_ACTIVATION') {
    // 백엔드 명시 상태만 사용합니다. 0/상수맵을 이미지 픽셀이나 null만으로 추측하지 않습니다.
    if (url !== null) return common('CONTRACT_MISMATCH', 'CAM 응답 확인 필요', 'NO_ACTIVATION에서는 이미지가 null이어야 합니다.');
    return common('NO_SPATIAL_RESPONSE', '위치별 강조 반응 없음', spatialNoResponse);
  }
  if (status === 'GENERATED') {
    return url
      ? common('AVAILABLE', 'Grad-CAM 참고 이미지', camCaveat, url)
      : common('GENERATED_URL_MISSING', 'Grad-CAM 조회 정보 미제공', '생성 상태는 성공으로 표시됐지만 이미지 URL이 없습니다. 상세 응답 재조회·백엔드 확인이 필요합니다.');
  }
  return common('UNKNOWN', 'Grad-CAM 상태 미제공', 'DEFECT 예측이지만 CAM 생성 여부를 확인할 수 없습니다. 상태 코드를 임의로 추정하지 않습니다.');
}

export function makeAiDisplayPresentationV4(
  detail: InspectionDetailV4
): AiDisplayPresentationV4 {
  const ai = detail.ai;
  const policy = detail.policy;
  const judgement = detail.judgement;
  const final = judgement?.finalJudgement ?? null;
  const judgedBy = judgement?.judgedBy ?? null;
  let finalText = '미확정';
  if (final) {
    finalText = judgedBy === 'WORKER'
      ? `작업자 최종 ${final}`
      : judgedBy === 'SYSTEM'
        ? `시스템 ${final} (서버 결과)`
        : `${final} (판정 주체 미제공)`;
  }
  let policyText = '정책 결과 미제공';
  if (policy?.recommendedAction === 'REVIEW') policyText = 'REVIEW · 작업자 확인 필요';
  if (policy?.recommendedAction === 'AUTO_PASS') policyText = 'AUTO_PASS · 서버 정책 결과';

  return {
    partSupportText: detail.partCode === 'DOOR'
      ? 'DOOR · AI API 지원 확인'
      : `${detail.partCode} · AI API 지원 여부 미확인 (확인된 부품: DOOR)`,
    aiPrediction: ai?.predictedQuality ?? null,
    aiPredictionLabel: ai?.predictedQuality === 'GOOD'
      ? 'GOOD · 정상 쪽 AI 예측 (최종 PASS 아님)'
      : ai?.predictedQuality === 'DEFECT'
        ? 'DEFECT · 불량 쪽 AI 예측 (최종 FAIL 아님)'
        : detail.status === 'FAILED'
          ? 'AI 분석 실패 · 예측 없음'
          : '예측 미제공 · 분석 대기/진행 중',
    modelVersionText: ai?.modelVersion ?? '미제공',
    rawDefectScoreText: formatRawDefectScoreV4(ai?.rawDefectProbability),
    calibratedProbabilityText: formatCalibratedProbabilityV4(ai?.calibratedDefectProbability),
    calibratorVersionText: ai?.calibratorVersion ?? '미제공',
    policyActionText: policyText,
    finalJudgementText: finalText,
    displayStateText: detail.displayState,
    cam: makeCamViewV4(detail),
    policyBlockPresent: policy !== null,
  };
}
