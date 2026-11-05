import type {
  ApiV4DataEnvelope, DisplayStateV4, GradcamStatusV4,
  InspectionDetailV4, InspectionViewV4, ProcessingStatusV4, ReviewReasonV4,
} from './types';

export class ContractV4Error extends Error {
  constructor(message: string) {
    super(`백엔드 v4 응답 형식 오류: ${message}`);
    this.name = 'ContractV4Error';
  }
}

type ObjectLike = Record<string, unknown>;
const obj = (v: unknown): v is ObjectLike => v !== null && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const oneOf = <T extends string | null>(v: unknown, values: readonly T[]): v is T =>
  values.some(x => x === v);
const nullableText = (v: unknown): v is string | null | undefined => v == null || typeof v === 'string';
const probability = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1;

const processingStatuses = ['RECEIVED', 'ANALYZING', 'COMPLETED', 'FAILED'] as const;
const displayStates = ['ANALYZING', 'AUTO_PASS', 'REVIEW_PENDING', 'REVIEW_DONE', 'FAILED'] as const;
const reviewReasons = ['DEFECT_PREDICTED', 'NO_ACTIVE_POLICY', 'CALIBRATION_UNAVAILABLE', 'ABOVE_THRESHOLD'] as const;
const gradcamStatuses = ['GENERATED', 'NOT_REQUIRED', 'FAILED', 'NO_ACTIVATION'] as const;

export const reviewReasonLabels: Record<ReviewReasonV4, string> = {
  DEFECT_PREDICTED: 'AI가 불량으로 예측하여 작업자 확인이 필요합니다.',
  NO_ACTIVE_POLICY: '현재 부품·모델에 적용 가능한 활성 정책이 없습니다.',
  CALIBRATION_UNAVAILABLE: '보정 불량 확률이 없어 작업자 확인이 필요합니다.',
  ABOVE_THRESHOLD: '보정 불량 확률이 자동 통과 기준을 초과했습니다.',
};

export const stateLabels: Record<DisplayStateV4, string> = {
  ANALYZING: '분석 중',
  AUTO_PASS: '자동 통과',
  REVIEW_PENDING: '작업자 확인 대기',
  REVIEW_DONE: '작업자 판정 완료',
  FAILED: 'AI 분석 실패',
};

function readImage(v: unknown, where: string): { url: string; width?: number | null; height?: number | null } | null {
  if (v == null) return null;
  if (!obj(v) || !text(v.url)) throw new ContractV4Error(`${where}.url이 없습니다.`);
  if ((v.width != null && (typeof v.width !== 'number' || v.width <= 0)) ||
      (v.height != null && (typeof v.height !== 'number' || v.height <= 0))) {
    throw new ContractV4Error(`${where}의 이미지 크기가 올바르지 않습니다.`);
  }
  return { url: v.url, width: (v.width as number | null | undefined), height: (v.height as number | null | undefined) };
}

/**
 * 서버의 {data:{...}} 전체 응답을 검사합니다. 예기치 않은 상태는 정상 검사로 대체하지 않습니다.
 * 정교한 서버 계약 스키마 검증은 Swagger/OpenAPI 문서 수신 후 확장합니다.
 */
export function decodeInspectionDetailV4(payload: unknown): InspectionDetailV4 {
  if (!obj(payload) || !obj(payload.data)) throw new ContractV4Error('최상위 {data} 객체가 없습니다.');
  const d = payload.data;
  if (!text(d.inspectionId) || !text(d.inspectionNo) || !text(d.partCode) || !text(d.receivedAt)) {
    throw new ContractV4Error('inspectionId, inspectionNo, partCode, receivedAt이 필요합니다.');
  }
  // Mock의 INS-006을 UUID 자리에 넣어 API 호출하지 않도록 검사합니다.
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(d.inspectionId)) {
    throw new ContractV4Error('inspectionId가 UUID 형식이 아닙니다.');
  }
  if (!oneOf(d.status, processingStatuses) || !oneOf(d.displayState, displayStates)) {
    throw new ContractV4Error('알 수 없는 status/displayState입니다.');
  }
  if (!/(Z|[+-]\d{2}:\d{2})$/.test(d.receivedAt) || !Number.isFinite(Date.parse(d.receivedAt))) {
    throw new ContractV4Error('receivedAt은 타임존 오프셋이 포함된 ISO 시각이어야 합니다.');
  }
  if (!nullableText(d.retryOf)) throw new ContractV4Error('retryOf는 UUID 또는 null이어야 합니다.');

  const a = d.ai;
  if (a != null && (!obj(a) || !text(a.modelVersion) ||
      !oneOf(a.predictedQuality, ['GOOD', 'DEFECT'] as const) ||
      !probability(a.rawDefectProbability) ||
      (a.calibratedDefectProbability != null && !probability(a.calibratedDefectProbability)) ||
      !nullableText(a.calibratorVersion) ||
      typeof a.inferenceTimeMs !== 'number' || !Number.isFinite(a.inferenceTimeMs) || a.inferenceTimeMs < 0)) {
    throw new ContractV4Error('ai 블록 값이 유효하지 않습니다.');
  }

  const p = d.policy;
  if (p != null && (!obj(p) || typeof p.automationPolicyReady !== 'boolean' ||
      !nullableText(p.policyVersion) ||
      (p.passThreshold != null && !probability(p.passThreshold)) ||
      !oneOf(p.recommendedAction, ['AUTO_PASS', 'REVIEW', null] as const) ||
      !oneOf(p.reviewReason, [...reviewReasons, null] as const))) {
    throw new ContractV4Error('policy 블록 값이 유효하지 않습니다.');
  }

  const j = d.judgement;
  if (j != null && (!obj(j) ||
    !oneOf(j.finalJudgement, ['PASS', 'FAIL', null] as const) ||
    !oneOf(j.judgedBy, ['WORKER', 'SYSTEM', null] as const) ||
    !nullableText(j.confirmedBy) || !nullableText(j.confirmedAt))) {
    throw new ContractV4Error('judgement 블록 값이 유효하지 않습니다.');
  }

  const i = d.images;
  let images: InspectionDetailV4['images'] = null;
  if (i != null) {
    if (!obj(i) || !oneOf(i.gradcamStatus, [...gradcamStatuses, null] as const) || !nullableText(i.urlExpiresAt)) {
      throw new ContractV4Error('images 블록 값이 유효하지 않습니다.');
    }
    images = {
      original: readImage(i.original, 'images.original'),
      gradcam: readImage(i.gradcam, 'images.gradcam'),
      gradcamStatus: (i.gradcamStatus ?? null) as GradcamStatusV4 | null,
      urlExpiresAt: (i.urlExpiresAt ?? null) as string | null,
    };
    if (images.gradcamStatus === 'GENERATED' && !images.gradcam) {
      throw new ContractV4Error('Grad-CAM GENERATED인데 이미지가 없습니다.');
    }
    if (images.gradcamStatus === 'NO_ACTIVATION' && images.gradcam !== null) {
      throw new ContractV4Error('Grad-CAM NO_ACTIVATION 상태의 이미지 값은 null이어야 합니다.');
    }
  }

  const e = d.error;
  if (e != null && (!obj(e) || !text(e.code) || !text(e.message) || typeof e.retryable !== 'boolean')) {
    throw new ContractV4Error('error 블록 값이 유효하지 않습니다.');
  }

  // 합의된 상태 조합 검증. 잘못된 응답을 자동 통과/확정 판정으로 오해하지 않도록 합니다.
  const status = d.status as ProcessingStatusV4;
  const displayState = d.displayState as DisplayStateV4;
  const action = obj(p) ? p.recommendedAction : null;
  const final = obj(j) ? j.finalJudgement : null;
  const by = obj(j) ? j.judgedBy : null;
  if (displayState === 'ANALYZING' && !['RECEIVED', 'ANALYZING'].includes(status)) {
    throw new ContractV4Error('ANALYZING은 RECEIVED/ANALYZING에서만 가능합니다.');
  }
  if (displayState === 'FAILED' && (status !== 'FAILED' || final != null || action != null)) {
    throw new ContractV4Error('FAILED의 상태/판정 조합이 잘못됐습니다.');
  }
  if (displayState === 'AUTO_PASS' && (status !== 'COMPLETED' || action !== 'AUTO_PASS' || final !== 'PASS' || by !== 'SYSTEM')) {
    throw new ContractV4Error('AUTO_PASS의 시스템 PASS 판정 조합이 잘못됐습니다.');
  }
  if (displayState === 'REVIEW_PENDING' && (status !== 'COMPLETED' || action !== 'REVIEW' || final != null)) {
    throw new ContractV4Error('REVIEW_PENDING 판정 조합이 잘못됐습니다.');
  }
  if (displayState === 'REVIEW_DONE' && (status !== 'COMPLETED' || action !== 'REVIEW' || !['PASS', 'FAIL'].includes(String(final)) || by !== 'WORKER')) {
    throw new ContractV4Error('REVIEW_DONE 판정 조합이 잘못됐습니다.');
  }
  if (status === 'FAILED' && displayState !== 'FAILED') throw new ContractV4Error('FAILED 상태와 displayState 불일치');
  if (status === 'FAILED' && e == null) throw new ContractV4Error('FAILED에는 error 블록이 필요합니다.');
  if (status === 'COMPLETED' && (a == null || p == null)) {
    throw new ContractV4Error('COMPLETED에는 ai와 policy 블록이 필요합니다.');
  }
  if (status === 'COMPLETED' && !['AUTO_PASS', 'REVIEW_PENDING', 'REVIEW_DONE'].includes(displayState)) {
    throw new ContractV4Error('COMPLETED 상태에 유효한 displayState가 없습니다.');
  }

  const detail: InspectionDetailV4 = {
    inspectionId: d.inspectionId,
    inspectionNo: d.inspectionNo,
    partCode: d.partCode,
    lineCode: nullableText(d.lineCode) ? d.lineCode ?? null : null,
    status,
    displayState,
    receivedAt: d.receivedAt,
    completedAt: nullableText(d.completedAt) ? d.completedAt ?? null : null,
    retryOf: (d.retryOf ?? null) as string | null,
    ai: a == null ? null : a as unknown as InspectionDetailV4['ai'],
    policy: p == null ? null : p as unknown as InspectionDetailV4['policy'],
    judgement: j == null ? null : j as unknown as InspectionDetailV4['judgement'],
    images,
    error: e == null ? null : e as unknown as InspectionDetailV4['error'],
  };
  return detail;
}

export function mapInspectionDetailV4(detail: InspectionDetailV4): InspectionViewV4 {
  return {
    inspectionId: detail.inspectionId,
    inspectionNo: detail.inspectionNo,
    partCode: detail.partCode,
    receivedAt: detail.receivedAt,
    processingStatus: detail.status,
    displayState: detail.displayState,
    displayStateLabel: stateLabels[detail.displayState],
    prediction: detail.ai?.predictedQuality ?? null,
    calibratedDefectProbability: detail.ai?.calibratedDefectProbability ?? null,
    modelVersion: detail.ai?.modelVersion ?? null,
    policyVersion: detail.policy?.policyVersion ?? null,
    reviewReasonCode: detail.policy?.reviewReason ?? null,
    reviewReasonText: detail.policy?.reviewReason ? reviewReasonLabels[detail.policy.reviewReason] : null,
    errorCode: detail.error?.code ?? null,
    errorMessage: detail.error?.message ?? null,
    finalJudgement: detail.judgement?.finalJudgement ?? null,
    judgedBy: detail.judgement?.judgedBy ?? null,
    confirmedBy: detail.judgement?.confirmedBy ?? null,
    confirmedAt: detail.judgement?.confirmedAt ?? null,
    originalImageUrl: detail.images?.original?.url ?? null,
    gradcamImageUrl: detail.images?.gradcamStatus === 'GENERATED' ? detail.images.gradcam?.url ?? null : null,
    gradcamStatus: detail.images?.gradcamStatus ?? null,
    imageUrlExpiresAt: detail.images?.urlExpiresAt ?? null,
    retryOf: detail.retryOf ?? null,
    canOfferConfirm: detail.displayState === 'REVIEW_PENDING',
    canOfferRetry: detail.displayState === 'FAILED',
    isServerAutoPass: detail.displayState === 'AUTO_PASS',
  };
}

export function adaptInspectionDetailResponseV4(payload: unknown): InspectionViewV4 {
  return mapInspectionDetailV4(decodeInspectionDetailV4(payload));
}

/** 이미지 접근 URL 만료 직전/만료 시 GET 상세를 재조회해야 함. 30초 여유를 둡니다. */
export function isImageUrlExpiring(expiresAt: string | null, atMs: number = Date.now()): boolean {
  if (expiresAt === null) return false; // 만료 정보 미제공: 이미지 onError로 상세 재조회 처리 필요
  const timestamp = Date.parse(expiresAt);
  return !Number.isFinite(timestamp) || timestamp - atMs <= 30_000;
}
