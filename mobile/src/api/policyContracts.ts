/**
 * 캡스톤 모바일 앱 ↔ 정책 평가 백엔드 간 협의용 초안 DTO.
 * 실제 서버의 확정된 API 스펙이 아닙니다. 백엔드 팀과 필드명/엔드포인트를 합의한 뒤 적용하세요.
 */
export type EvaluationOrigin = 'SYNTHETIC_DEMO' | 'BACKEND';
export type ScoreBasis = 'DEMO_MODEL_SCORE' | 'MODEL_SCORE' | 'CALIBRATED_DEFECT_PROBABILITY';
export type PolicyReadiness = 'UNREADY' | 'READY' | 'ACTIVE';

/** 관리자는 목표 미검출률만 요청하며, passThreshold를 제출하지 않습니다. */
export interface PolicyCandidateRequest {
  partCode: string;
  targetMissRatePercent: number; // 0~100
  modelVersion?: string;
}

/** 미검출률 분모는 실제 불량 수. 자동 통과 비율 분모는 전체 수. */
export interface EvaluationSampleSummary {
  total: number;
  actualDefects: number;
  autoPassed: number;
  missedDefects: number;
  missRatePercent: number | null; // 실제 불량이 0이면 null
  autoPassRatePercent: number | null; // 전체 0이면 null
}

export interface PolicyCandidateResponse {
  origin: EvaluationOrigin;
  partCode: string;
  modelVersion: string | null;
  targetMissRatePercent: number;
  scoreBasis: ScoreBasis;
  /** 시스템이 계산한 후보. 관리자 임의 입력 값이 아님. 실제 검증 전에는 운영 정책으로 쓰지 않습니다. */
  candidateThreshold: number | null;
  tuning: EvaluationSampleSummary;
  evaluation: EvaluationSampleSummary;
  meetsTargetOnEvaluation: boolean | null;
  /** 통계적 신뢰 상한은 별도 검증 단계에서 산출. 현재 Mock은 null. */
  missRateUpperConfidenceBoundPercent: number | null;
  validationReportId: string | null;
  validatedAllowedRange: { min: number; max: number } | null;
  readiness: PolicyReadiness;
  policyVersion: string | null;
  notes: string[];
}

export interface PolicyEvaluationService {
  evaluateCandidate(request: PolicyCandidateRequest): Promise<PolicyCandidateResponse>;
}
