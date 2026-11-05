import type { ApiV4DataEnvelope, InspectionDetailV4 } from './types';

// 실제 서버 결과가 아닙니다. v4 계약에 따른 변환기 점검 전용 가상 레코드 5개입니다.
const ids = [
  '8f3c1e2a-1234-4123-8123-111111111111',
  '8f3c1e2a-1234-4123-8123-222222222222',
  '8f3c1e2a-1234-4123-8123-333333333333',
  '8f3c1e2a-1234-4123-8123-444444444444',
  '8f3c1e2a-1234-4123-8123-555555555555',
];

const base: InspectionDetailV4 = {
  inspectionId: ids[0], inspectionNo: 'INS-000006', partCode: 'DOOR',
  lineCode: null, status: 'COMPLETED', displayState: 'REVIEW_PENDING',
  receivedAt: '2026-10-28T10:03:21+09:00', completedAt: '2026-10-28T10:03:25+09:00', retryOf: null,
  ai: {
    modelVersion: 'mock-door-swin-t-v1', calibratorVersion: null, predictedQuality: 'DEFECT',
    rawDefectProbability: 0.823, calibratedDefectProbability: null, inferenceTimeMs: 412,
  },
  policy: {
    automationPolicyReady: false, policyVersion: null, passThreshold: null,
    recommendedAction: 'REVIEW', reviewReason: 'DEFECT_PREDICTED',
  },
  judgement: { finalJudgement: null, judgedBy: null, confirmedBy: null, confirmedAt: null },
  images: {
    original: { url: 'https://example.invalid/original-1.jpg', width: 3024, height: 4032 },
    gradcam: null, gradcamStatus: 'FAILED', urlExpiresAt: '2030-12-31T23:59:59+09:00',
  },
  error: null,
};

const confirmed: InspectionDetailV4 = {
  ...base, inspectionId: ids[1], inspectionNo: 'INS-000005',
  displayState: 'REVIEW_DONE',
  judgement: { finalJudgement: 'FAIL', judgedBy: 'WORKER', confirmedBy: 'worker01', confirmedAt: '2026-10-28T10:05:00+09:00' },
};

const autoPass: InspectionDetailV4 = {
  ...base, inspectionId: ids[2], inspectionNo: 'INS-000002', displayState: 'AUTO_PASS',
  ai: { ...base.ai!, predictedQuality: 'GOOD', rawDefectProbability: 0.012, calibratedDefectProbability: 0.020, calibratorVersion: 'mock-cal-v1' },
  policy: { automationPolicyReady: true, policyVersion: 'example-door-p1', passThreshold: 0.05,
            recommendedAction: 'AUTO_PASS', reviewReason: null },
  judgement: { finalJudgement: 'PASS', judgedBy: 'SYSTEM', confirmedBy: null, confirmedAt: null },
  images: { ...base.images!, gradcamStatus: 'NOT_REQUIRED' },
};

const failed: InspectionDetailV4 = {
  ...base, inspectionId: ids[3], inspectionNo: 'INS-000007',
  status: 'FAILED', displayState: 'FAILED', ai: null, policy: null,
  judgement: { finalJudgement: null, judgedBy: null, confirmedBy: null, confirmedAt: null },
  error: { code: 'AI_SERVER_TIMEOUT', message: 'AI 분석 요청 시간이 초과됐습니다.', retryable: true },
  images: { ...base.images!, gradcamStatus: 'NOT_REQUIRED' },
};

const analyzing: InspectionDetailV4 = {
  ...base, inspectionId: ids[4], inspectionNo: 'INS-000008',
  status: 'ANALYZING', displayState: 'ANALYZING', completedAt: null, ai: null, policy: null,
  judgement: { finalJudgement: null, judgedBy: null, confirmedBy: null, confirmedAt: null },
  images: { ...base.images!, gradcamStatus: 'NOT_REQUIRED' },
};

export const sampleV4Responses: Array<{ title: string; response: ApiV4DataEnvelope<InspectionDetailV4> }> = [
  { title: '확인 대기', response: { data: base } },
  { title: '작업자 판정 완료', response: { data: confirmed } },
  { title: '서버 자동 통과 (가상 계약 예시)', response: { data: autoPass } },
  { title: '분석 실패', response: { data: failed } },
  { title: '분석 중', response: { data: analyzing } },
];
