/**
 * 도어 e02 AUTO_PASS 독립 Mock 시연 (2026-11-12 도현님 내부 평가 수치 변경).
 * 이 상수와 판정 함수는 별도 Mock UI 재현 전용입니다.
 * 실제 API 응답, 운영 정책, 검사 DB 판정을 다시 계산하거나 변경하는 데 사용하지 않습니다.
 *
 * 근거: ai/VALIDATION.md, ai/policy_readiness_audit.json, docs/통합_점검표.md
 */
export const DOOR_AUTOPASS_DEMO_V4 = {
  partCode: 'DOOR',
  mockModelVersion: 'mock-door-swin-t-v1',
  basePolicyVersion: 'example-door-demo-0084',
  adjustedPolicyVersion: 'example-door-demo-0084-t1',
  validatedMin: 0.0084,
  validatedMax: 0.0092,
  // 도현님이 제시한 새 시연 정책 기본값. 시연 비교는 0.84%를 먼저 활성화합니다.
  defaultThreshold: 0.0092,
  initialThreshold: 0.0084,
  adjustedThreshold: 0.0092,
  samplePrediction: 'GOOD',
  sampleCalibratedDefectProbability: 0.0088,
} as const;

export type MockDemoDecisionV4 = 'AUTO_PASS' | 'REVIEW';

export function evaluateMockDoorAutopassDemoV4(
  predictedQuality: 'GOOD' | 'DEFECT',
  calibratedDefectProbability: number | null,
  passThreshold: number | null,
  readyAndActive: boolean,
): MockDemoDecisionV4 {
  if (!readyAndActive || predictedQuality !== 'GOOD' ||
      calibratedDefectProbability === null || passThreshold === null ||
      !Number.isFinite(calibratedDefectProbability) || !Number.isFinite(passThreshold) ||
      calibratedDefectProbability < 0 || calibratedDefectProbability > 1 ||
      passThreshold < 0 || passThreshold > 1) {
    return 'REVIEW';
  }
  return calibratedDefectProbability <= passThreshold ? 'AUTO_PASS' : 'REVIEW';
}
