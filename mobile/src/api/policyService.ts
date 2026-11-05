import {
  type EvaluationSampleSummary,
  type PolicyCandidateRequest,
  type PolicyCandidateResponse,
  type PolicyEvaluationService,
} from './policyContracts';
import { simulatePolicyForTarget } from '../data/demoPolicyEvaluation';

function assertTarget(target: number): void {
  if (!Number.isFinite(target) || target < 0 || target > 100) {
    throw new Error('목표 미검출률은 0~100% 범위여야 합니다.');
  }
}

function validateRequest(request: PolicyCandidateRequest): void {
  assertTarget(request.targetMissRatePercent);
  if (!request.partCode.trim()) throw new Error('검사 대상 부품 코드가 필요합니다.');
}

/** 기존 40건 튜닝 / 40건 평가 가상 표본을 계약 형태로 변환합니다. */
export const mockPolicyService: PolicyEvaluationService = {
  async evaluateCandidate(request) {
    validateRequest(request);
    const s = simulatePolicyForTarget(request.targetMissRatePercent);
    return {
      origin: 'SYNTHETIC_DEMO',
      partCode: request.partCode,
      modelVersion: 'mock-swin-t-v0',
      targetMissRatePercent: s.targetPercent,
      scoreBasis: 'DEMO_MODEL_SCORE',
      candidateThreshold: s.candidateThreshold,
      tuning: {
        total: s.tuningTotal,
        actualDefects: s.tuningDefects,
        autoPassed: s.tuningAutoPassed,
        missedDefects: s.tuningMissedDefects,
        missRatePercent: s.tuningMissRatePercent,
        autoPassRatePercent: 100 * s.tuningAutoPassed / s.tuningTotal,
      },
      evaluation: {
        total: s.evaluationTotal,
        actualDefects: s.evaluationDefects,
        autoPassed: s.evaluationAutoPassed,
        missedDefects: s.evaluationMissedDefects,
        missRatePercent: s.evaluationMissRatePercent,
        autoPassRatePercent: s.evaluationAutoPassRatePercent,
      },
      meetsTargetOnEvaluation: s.evaluationMeetsTargetEmpirically,
      missRateUpperConfidenceBoundPercent: null,
      validationReportId: null,
      validatedAllowedRange: null,
      // Mock에서는 타 화면의 '준비됨/적용 중 · 예시' 선택과 상관없이 실제 정책은 항상 미준비.
      readiness: 'UNREADY',
      policyVersion: null,
      notes: ['가상 표본 시연 결과이며 실제 보정 확률이나 검증된 운영 정책이 아닙니다.'],
    } satisfies PolicyCandidateResponse;
  },
};

// 아래는 서버 계약이 합의된 후 사용하기 위한 HTTP 어댑터입니다.
// 제안 엔드포인트는 예시일 뿐 현재 팀의 서버 API가 존재한다는 뜻이 아닙니다.
const PROPOSED_ENDPOINT = '/api/v1/policy-evaluations/candidate';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function finiteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}
function isNullableNumber(value: unknown): value is number | null {
  return value === null || finiteNumber(value);
}
function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}
function isNonnegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && typeof value === 'number' && value >= 0;
}
function isPercentage(value: unknown): value is number {
  return finiteNumber(value) && value >= 0 && value <= 100;
}
function isNullablePercentage(value: unknown): value is number | null {
  return value === null || isPercentage(value);
}
function isSample(value: unknown): value is EvaluationSampleSummary {
  if (!isRecord(value)) return false;
  const { total, actualDefects, autoPassed, missedDefects } = value;
  if (!isNonnegativeInteger(total) || !isNonnegativeInteger(actualDefects) ||
      !isNonnegativeInteger(autoPassed) || !isNonnegativeInteger(missedDefects)) return false;
  if (actualDefects > total || autoPassed > total || missedDefects > actualDefects || missedDefects > autoPassed) return false;
  if (!isNullablePercentage(value.missRatePercent) || !isNullablePercentage(value.autoPassRatePercent)) return false;
  // 서버에서 돌려준 분모/비율이 일치하지 않는 응답을 차단합니다.
  if (actualDefects === 0) {
    if (value.missRatePercent !== null) return false;
  } else if (value.missRatePercent === null || Math.abs(value.missRatePercent - 100 * missedDefects / actualDefects) > 0.11) return false;
  if (total === 0) {
    if (value.autoPassRatePercent !== null) return false;
  } else if (value.autoPassRatePercent === null || Math.abs(value.autoPassRatePercent - 100 * autoPassed / total) > 0.11) return false;
  return true;
}

/** 외부 JSON을 그대로 신뢰하지 않고, 화면이 사용하는 필드를 검사합니다. */
export function parsePolicyCandidateResponse(payload: unknown): PolicyCandidateResponse {
  if (!isRecord(payload)) throw new Error('정책 평가 API 응답 형식이 올바르지 않습니다.');
  if (payload.origin !== 'BACKEND') throw new Error('서버 응답의 출처가 BACKEND가 아닙니다.');
  if (typeof payload.partCode !== 'string' || !payload.partCode.trim()) throw new Error('부품 코드가 없습니다.');
  if (!isNullableString(payload.modelVersion) || !isPercentage(payload.targetMissRatePercent)) throw new Error('모델/목표 미검출률 값이 잘못되었습니다.');
  if (payload.scoreBasis !== 'MODEL_SCORE' && payload.scoreBasis !== 'CALIBRATED_DEFECT_PROBABILITY') throw new Error('점수 기준이 잘못되었습니다.');
  if (!isNullableNumber(payload.candidateThreshold)) throw new Error('산출된 후보 기준값이 잘못되었습니다.');
  if (!isSample(payload.tuning) || !isSample(payload.evaluation)) throw new Error('평가 표본의 수치가 잘못되었습니다.');
  if (payload.meetsTargetOnEvaluation !== null && typeof payload.meetsTargetOnEvaluation !== 'boolean') throw new Error('목표 충족 상태가 잘못되었습니다.');
  if (!isNullablePercentage(payload.missRateUpperConfidenceBoundPercent)) throw new Error('신뢰 상한 값이 잘못되었습니다.');
  if (!isNullableString(payload.validationReportId) || !isNullableString(payload.policyVersion)) throw new Error('정책 버전/검증 보고서 값이 잘못되었습니다.');
  if (payload.readiness !== 'UNREADY' && payload.readiness !== 'READY' && payload.readiness !== 'ACTIVE') throw new Error('정책 준비 상태가 잘못되었습니다.');
  if (!Array.isArray(payload.notes) || !payload.notes.every((n) => typeof n === 'string')) throw new Error('설명 정보가 잘못되었습니다.');
  const range = payload.validatedAllowedRange;
  if (range !== null && (!isRecord(range) || !finiteNumber(range.min) || !finiteNumber(range.max) || range.min > range.max)) {
    throw new Error('검증된 허용 범위가 잘못되었습니다.');
  }
  // 백엔드에서 READY/ACTIVE로 내려줘도 검증 보고서와 범위 등이 없으면 앱이 수용하지 않음.
  if (payload.readiness !== 'UNREADY' && (
    payload.candidateThreshold === null ||
    !payload.validationReportId ||
    payload.validatedAllowedRange === null ||
    payload.missRateUpperConfidenceBoundPercent === null ||
    payload.missRateUpperConfidenceBoundPercent > payload.targetMissRatePercent ||
    payload.meetsTargetOnEvaluation !== true ||
    payload.evaluation.actualDefects === 0
  )) {
    throw new Error('검증 근거가 부족한 정책을 준비/적용 상태로 표시할 수 없습니다.');
  }
  return payload as unknown as PolicyCandidateResponse;
}

/**
 * 실제 서비스가 구축되면 팀이 합의한 경로로 교체하세요.
 * 인증 토큰/역할 검증은 백엔드 담당이며, 앱의 시연용 role 파라미터는 인증 수단이 아닙니다.
 */
export function createHttpPolicyService(baseUrl: string, endpoint = PROPOSED_ENDPOINT): PolicyEvaluationService {
  if (!/^https?:\/\//.test(baseUrl)) throw new Error('API 주소가 필요합니다.');
  return {
    async evaluateCandidate(request) {
      validateRequest(request);
      const response = await fetch(`${baseUrl.replace(/\/$/, '')}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });
      if (!response.ok) throw new Error(`정책 평가 요청 실패 (HTTP ${response.status})`);
      const payload: unknown = await response.json();
      const parsed = parsePolicyCandidateResponse(payload);
      if (parsed.partCode !== request.partCode || Math.abs(parsed.targetMissRatePercent - request.targetMissRatePercent) > 1e-9) {
        throw new Error('요청 조건과 서버 응답이 일치하지 않습니다.');
      }
      return parsed;
    },
  };
}

// ★ 현재 기본 모드는 항상 Mock입니다. 실제 서버 준비 전에는 변경하지 마세요.
// 서버 준비 후 예시: export const policyService = createHttpPolicyService('https://실제-서버-주소');
export const policyService: PolicyEvaluationService = mockPolicyService;
