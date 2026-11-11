/**
 * 백엔드 API 계약 v4(2026-10-15) + 이승규 10/28 필드 대조표 기준.
 * 이 타입은 실제 API 계약을 나타내며, src/data/mockInspections.ts의 시연 모델과 분리합니다.
 * 아직 서버 Swagger의 실제 JSON으로 검증하지 않았습니다.
 */
export type ProcessingStatusV4 = 'RECEIVED' | 'ANALYZING' | 'COMPLETED' | 'FAILED';
export type DisplayStateV4 = 'ANALYZING' | 'AUTO_PASS' | 'REVIEW_PENDING' | 'REVIEW_DONE' | 'FAILED';
export type PredictedQualityV4 = 'GOOD' | 'DEFECT';
export type FinalJudgementV4 = 'PASS' | 'FAIL';
export type InspectionSourceV4 = 'DEVICE' | 'ADMIN' | 'RETRY' | 'MANUAL';
export interface ManualOriginV4 {
  inspectionId: string;
  inspectionNo: string;
  errorCode: string;
  errorMessage: string;
}
export interface InspectionFollowUpV4 {
  inspectionId: string;
  inspectionNo: string;
  source: 'RETRY' | 'MANUAL';
}
export type RecommendedActionV4 = 'AUTO_PASS' | 'REVIEW';
export type JudgedByV4 = 'SYSTEM' | 'WORKER';
export type ReviewReasonV4 =
  | 'DEFECT_PREDICTED' | 'NO_ACTIVE_POLICY'
  | 'CALIBRATION_UNAVAILABLE' | 'ABOVE_THRESHOLD' | 'AI_UNAVAILABLE';
export type GradcamStatusV4 = 'GENERATED' | 'NOT_REQUIRED' | 'FAILED' | 'NO_ACTIVATION';

export interface ImageReferenceV4 {
  url: string;
  width?: number | null;
  height?: number | null;
}

export interface InspectionDetailV4 {
  inspectionId: string;         // 서버 API 경로에 쓰는 UUID
  inspectionNo: string;         // UI 표시용: INS-000006
  partCode: string;
  lineCode?: string | null;
  status: ProcessingStatusV4;
  displayState: DisplayStateV4;
  receivedAt: string;           // ISO8601 + 오프셋 (capturedAt과 혼동 금지)
  completedAt?: string | null;
  retryOf?: string | null;      // 원본 검사 inspectionId (UUID)
  source?: InspectionSourceV4 | null;
  manualOf?: ManualOriginV4 | null;
  followUp?: InspectionFollowUpV4 | null;
  ai: {
    modelVersion: string;
    calibratorVersion: string | null;
    predictedQuality: PredictedQualityV4;
    rawDefectProbability: number;
    calibratedDefectProbability: number | null;
    inferenceTimeMs: number;
  } | null;
  policy: {
    automationPolicyReady: boolean;
    policyVersion: string | null;
    passThreshold: number | null;
    recommendedAction: RecommendedActionV4 | null;
    reviewReason: ReviewReasonV4 | null;
  } | null;
  judgement: {
    finalJudgement: FinalJudgementV4 | null;
    judgedBy: JudgedByV4 | null;
    confirmedBy: string | null;
    confirmedAt: string | null;
  } | null;
  images: {
    original: ImageReferenceV4 | null;
    gradcam: ImageReferenceV4 | null;
    gradcamStatus: GradcamStatusV4 | null;
    urlExpiresAt: string | null;
  } | null;
  error: { code: string; message: string; retryable: boolean } | null;
}

export interface ApiV4DataEnvelope<T> { data: T }
export interface ApiV4ErrorEnvelope {
  error: { code: string; message: string; traceId?: string; inspectionId?: string; status?: string }
}

/** 앱 UI에 필요한 데이터만 옮겨 둔 중간 모델. UI는 이 타입만 소비하도록 단계적으로 전환합니다. */
export interface InspectionViewV4 {
  inspectionId: string;       // API 호출에는 이것만 사용
  inspectionNo: string;       // 화면 표시에만 사용
  partCode: string;
  receivedAt: string;         // ISO8601 오프셋 보존
  displayState: DisplayStateV4;
  displayStateLabel: string;
  processingStatus: ProcessingStatusV4;
  prediction: PredictedQualityV4 | null;
  calibratedDefectProbability: number | null;
  modelVersion: string | null;
  policyVersion: string | null;
  reviewReasonCode: ReviewReasonV4 | null;
  reviewReasonText: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  finalJudgement: FinalJudgementV4 | null;
  judgedBy: JudgedByV4 | null;
  confirmedBy: string | null;
  confirmedAt: string | null;
  originalImageUrl: string | null;
  gradcamImageUrl: string | null;
  gradcamStatus: GradcamStatusV4 | null;
  imageUrlExpiresAt: string | null;
  retryOf: string | null; // 기존 검사 표시 번호가 아닌 서버 UUID
  source: InspectionSourceV4 | null;
  manualOf: ManualOriginV4 | null;
  followUp: InspectionFollowUpV4 | null;
  canOfferManual: boolean; // WORKER 권한·서버 충돌 검증이 별도로 필요
  canOfferConfirm: boolean; // 화면 표시 힌트. 서버 권한 검사를 대신하지 않음.
  canOfferRetry: boolean;   // 화면 표시 힌트. 서버 409 검사 필수.
  isServerAutoPass: boolean; // Mock AUTO_PASS_EXAMPLE과 혼동 금지
}
