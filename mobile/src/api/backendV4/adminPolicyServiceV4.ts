/**
 * API 계약 v4 §6.9: 실제 부품별 관리자 정책 조회·조정·적용.
 * 요청/응답은 authV4.authorizedRequest의 {data} 해제된 형태.
 * 서버 권한 검사(403)가 최종 권위이며, 라우트 role 파라미터는 신뢰하지 않습니다.
 */
import type { AuthPublicState } from './authCore';
import { validateThresholdEditV4 } from './policyThresholdV4';

export const COWL_PART_CODE_V4 = 'COWL_COVER';
export const POLICY_PART_CODES_V4 = ['DOOR', 'FRAME', 'COWL_COVER'] as const;
export type PolicyPartCodeV4 = typeof POLICY_PART_CODES_V4[number];
export function isPolicyPartCodeV4(code: string): code is PolicyPartCodeV4 {
  return (POLICY_PART_CODES_V4 as readonly string[]).includes(code);
}

export interface AdminPolicyV4 {
  policyId: string;
  policyVersion: string;
  partCode: string;
  modelVersion: string;
  calibratorVersion: string | null;
  passThreshold: number | null;
  /** null when server predates the AUTO_FAIL policy schema; never treat missing as enabled. */
  autoFailEnabled: boolean | null;
  failThreshold: number | null;
  failValidatedMin: number | null;
  failValidatedMax: number | null;
  validatedMin: number | null;
  validatedMax: number | null;
  ready: boolean;
  active: boolean;
  metrics: Record<string, unknown> | null;
  basedOnPolicyId: string | null;
  createdAt: string | null;
  activatedAt: string | null;
}

export interface PolicyAdminTransportV4 {
  authorizedRequest<T>(path: string, options?: {method?: 'GET' | 'POST'; body?: unknown}): Promise<T>;
  restore(): Promise<AuthPublicState>;
}

export function createPolicyVisitV4(auth: PolicyAdminTransportV4 & { sessionEpoch(): number }) {
  const epoch = auth.sessionEpoch();
  let focused = true;
  const isCurrent = () => focused && auth.sessionEpoch() === epoch;
  function assertCurrent() {
    if (!isCurrent()) throw new Error('정책 화면의 로그인 상태가 변경됐습니다.');
  }
  const transport: PolicyAdminTransportV4 = {
    async restore() {
      assertCurrent();
      const session = await auth.restore();
      assertCurrent();
      return session;
    },
    async authorizedRequest<T>(path: string, options?: {method?: 'GET' | 'POST'; body?: unknown}) {
      assertCurrent();
      const result = await auth.authorizedRequest<T>(path, options);
      assertCurrent();
      return result;
    },
  };
  return { transport, isCurrent, assertCurrent, close: () => { focused = false; } };
}

export class PolicyAdminContractErrorV4 extends Error {
  constructor(message: string) {
    super('정책 API 응답 오류: ' + message);
    this.name = 'PolicyAdminContractErrorV4';
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function nonblank(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}
function nullableText(value: unknown): value is string | null | undefined {
  return value == null || typeof value === 'string';
}
function nullableUnit(value: unknown): value is number | null | undefined {
  return value == null || (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1);
}

export function decodeAdminPolicyV4(raw: unknown): AdminPolicyV4 {
  if (!record(raw) || !nonblank(raw.policyId) || !nonblank(raw.policyVersion) ||
      !nonblank(raw.partCode) || !nonblank(raw.modelVersion) ||
      !nullableText(raw.calibratorVersion) || !nullableText(raw.basedOnPolicyId) ||
      !nullableText(raw.createdAt) || !nullableText(raw.activatedAt) ||
      (raw.autoFailEnabled != null && typeof raw.autoFailEnabled !== 'boolean') ||
      !nullableUnit(raw.failThreshold) || !nullableUnit(raw.failValidatedMin) ||
      !nullableUnit(raw.failValidatedMax) ||
      !nullableUnit(raw.passThreshold) || !nullableUnit(raw.validatedMin) ||
      !nullableUnit(raw.validatedMax) || typeof raw.ready !== 'boolean' ||
      typeof raw.active !== 'boolean' || (raw.metrics != null && !record(raw.metrics))) {
    throw new PolicyAdminContractErrorV4('필수 필드·정책 기준값·상태가 계약과 일치하지 않습니다.');
  }
  if ((raw.validatedMin != null && raw.validatedMax != null) && raw.validatedMin > raw.validatedMax) {
    throw new PolicyAdminContractErrorV4('validatedMin이 validatedMax보다 큽니다.');
  }
  if (raw.active && !raw.ready) throw new PolicyAdminContractErrorV4('미준비 정책이 활성 상태입니다.');
  const failValues=[raw.failThreshold,raw.failValidatedMin,raw.failValidatedMax];
  const present=failValues.filter(x=>x!=null).length;
  if(present!==0&&present!==3)
    throw new PolicyAdminContractErrorV4('자동 불량 기준과 검증 범위 3개 필드는 함께 제공되어야 합니다.');
  if(present===3) {
    const threshold=raw.failThreshold as number;
    const min=raw.failValidatedMin as number;
    const max=raw.failValidatedMax as number;
    if(min>max||threshold<min||threshold>max||
      raw.passThreshold==null||threshold<=raw.passThreshold)
      throw new PolicyAdminContractErrorV4('자동 불량 기준·검증 범위·통과 기준 간의 관계가 잘못됐습니다.');
  }
  if(raw.autoFailEnabled===true&&present!==3)
    throw new PolicyAdminContractErrorV4('자동 불량 활성화에 필요한 불량 기준이 없습니다.');
  return {
    policyId: raw.policyId,
    policyVersion: raw.policyVersion,
    partCode: raw.partCode,
    modelVersion: raw.modelVersion,
    calibratorVersion: raw.calibratorVersion ?? null,
    passThreshold: raw.passThreshold ?? null,
    autoFailEnabled: raw.autoFailEnabled ?? null,
    failThreshold: raw.failThreshold ?? null,
    failValidatedMin: raw.failValidatedMin ?? null,
    failValidatedMax: raw.failValidatedMax ?? null,
    validatedMin: raw.validatedMin ?? null,
    validatedMax: raw.validatedMax ?? null,
    ready: raw.ready,
    active: raw.active,
    metrics: raw.metrics == null ? null : raw.metrics,
    basedOnPolicyId: raw.basedOnPolicyId ?? null,
    createdAt: raw.createdAt ?? null,
    activatedAt: raw.activatedAt ?? null,
  };
}

export function decodePolicyListV4(raw: unknown, partCode: string): AdminPolicyV4[] {
  if (!isPolicyPartCodeV4(partCode)) throw new Error('지원하지 않는 정책 부품입니다.');
  if (!Array.isArray(raw)) throw new PolicyAdminContractErrorV4('GET /admin/policies 결과는 배열이어야 합니다.');
  const policies = raw.map(decodeAdminPolicyV4);
  if (policies.some((p) => p.partCode !== partCode)) {
    throw new PolicyAdminContractErrorV4('요청한 부품이 아닌 정책이 포함됐습니다.');
  }
  const activeModels = new Set<string>();
  for (const policy of policies) {
    if (!policy.active) continue;
    if (activeModels.has(policy.modelVersion)) {
      throw new PolicyAdminContractErrorV4('동일 모델에 활성 정책이 여러 개입니다.');
    }
    activeModels.add(policy.modelVersion);
  }
  return policies;
}

/** Compatibility for existing callers that explicitly request cowl policies. */
export function decodeCowlPolicyListV4(raw: unknown): AdminPolicyV4[] {
  return decodePolicyListV4(raw, COWL_PART_CODE_V4);
}

// 정책의 평가 근거는 JSON입니다. 객체 키의 순서는 근거의 의미를 바꾸지 않습니다.
function policyEvidenceKey(metrics: AdminPolicyV4['metrics']): string {
  return JSON.stringify(metrics ?? null, (_key, value) => {
    if (!record(value)) return value;
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, value[key]]));
  });
}

/** 서버가 통과 기준을 변경할 때 원본에서 승계하는 설정을 모두 비교합니다. */
function matchesThresholdEdit(candidate: AdminPolicyV4, base: AdminPolicyV4, threshold: number): boolean {
  return candidate.partCode === base.partCode &&
    candidate.modelVersion === base.modelVersion &&
    candidate.calibratorVersion === base.calibratorVersion &&
    candidate.ready === base.ready &&
    candidate.validatedMin === base.validatedMin &&
    candidate.validatedMax === base.validatedMax &&
    (candidate.autoFailEnabled ?? null) === (base.autoFailEnabled ?? null) &&
    (candidate.failThreshold ?? null) === (base.failThreshold ?? null) &&
    (candidate.failValidatedMin ?? null) === (base.failValidatedMin ?? null) &&
    (candidate.failValidatedMax ?? null) === (base.failValidatedMax ?? null) &&
    candidate.passThreshold != null &&
    Math.abs(candidate.passThreshold - threshold) < 0.0000005 &&
    policyEvidenceKey(candidate.metrics) === policyEvidenceKey(base.metrics);
}

export function findEquivalentPolicyVersionV4(
  policies: readonly AdminPolicyV4[],
  activePolicy: AdminPolicyV4,
  threshold: number,
): AdminPolicyV4 | null {
  if (!Number.isFinite(threshold) || !activePolicy.ready || !isPolicyPartCodeV4(activePolicy.partCode)) return null;
  let firstMatch: AdminPolicyV4 | null = null;
  for (const policy of policies) {
    if (!matchesThresholdEdit(policy, activePolicy, threshold)) continue;
    if (policy.active) return policy;
    firstMatch ??= policy;
  }
  return firstMatch;
}

export function percentageTextV4(fraction: number | null, digits = 2): string {
  return fraction == null ? '미제공' : `${(fraction * 100).toFixed(digits)}%`;
}

/** API는 비율 0~1을 받지만, 관리자 입력창에는 1.00 등의 백분율을 받습니다. */
export function parsePolicyPercentInputV4(input: string, policy: AdminPolicyV4): number {
  const trimmed = input.trim();
  if (!/^(?:\d{1,3})(?:\.\d{1,4})?$/.test(trimmed)) {
    throw new Error('백분율을 숫자로 입력해 주세요. 예: 1.00');
  }
  const number = Number(trimmed);
  if (!Number.isFinite(number) || number < 0 || number > 100) {
    throw new Error('백분율은 0~100 사이여야 합니다.');
  }
  // 백분율의 소수점 네 자리는 서버 비율의 여섯 자리와 정확히 대응합니다.
  const fractionText = (number / 100).toFixed(6);
  const result = validateThresholdEditV4(fractionText, {
    validatedMin: policy.validatedMin,
    validatedMax: policy.validatedMax,
    evidenceVerified: policy.ready,
  });
  if (!result.ok) {
    const messages = {
      UNVERIFIED: '준비 완료된 정책과 서버 검증 범위가 있어야 조정할 수 있습니다.',
      BAD_RANGE: '서버가 제공한 허용 범위가 올바르지 않습니다.',
      INVALID_VALUE: '기준치 숫자를 확인해 주세요.',
      OUT_OF_RANGE: `허용 범위(${percentageTextV4(policy.validatedMin, 4)}~${percentageTextV4(policy.validatedMax, 4)}) 밖입니다.`,
    };
    throw new Error(messages[result.reason]);
  }
  if (policy.failThreshold != null && result.value >= policy.failThreshold) {
    throw new Error('자동 통과 기준은 자동 불량 기준보다 낮아야 합니다.');
  }
  return result.value;
}

export function rootPolicyForV4(active: AdminPolicyV4, all: AdminPolicyV4[]): AdminPolicyV4 | null {
  let cursor: AdminPolicyV4 | undefined = active;
  const visited = new Set<string>();
  while (cursor?.basedOnPolicyId) {
    if (visited.has(cursor.policyId)) return null;
    visited.add(cursor.policyId);
    cursor = all.find((p) => p.policyId === cursor?.basedOnPolicyId);
  }
  return cursor ?? null;
}

export function createAdminPolicyServiceV4(transport: PolicyAdminTransportV4, partCode: string = COWL_PART_CODE_V4) {
  if (!isPolicyPartCodeV4(partCode)) throw new Error('지원하지 않는 정책 부품입니다.');
  let writing = false;
  const assertAdmin = async () => {
    const session = await transport.restore();
    if (!session.signedIn || session.role !== 'ADMIN') {
      throw new Error('실제 서버 ADMIN 계정으로 로그인해야 정책을 조회·수정할 수 있습니다.');
    }
  };
  async function list(): Promise<AdminPolicyV4[]> {
    await assertAdmin();
    const raw = await transport.authorizedRequest<unknown>(
      `/admin/policies?partCode=${encodeURIComponent(partCode)}`,
      { method: 'GET' },
    );
    return decodePolicyListV4(raw, partCode);
  }
  async function serialize<T>(action: () => Promise<T>): Promise<T> {
    if (writing) throw new Error('정책 쓰기 요청이 진행 중입니다. 중복 제출하지 마세요.');
    writing = true;
    try { return await action(); }
    finally { writing = false; }
  }
  async function saveNewVersion(base: AdminPolicyV4, inputPercent: string): Promise<AdminPolicyV4> {
    return serialize(async () => {
      await assertAdmin();
      if (base.partCode !== partCode || !base.active || !base.ready) {
        throw new Error('현재 활성·준비된 선택한 부품 정책에서만 새 버전을 저장할 수 있습니다.');
      }
      const passThreshold = parsePolicyPercentInputV4(inputPercent, base);
      const raw = await transport.authorizedRequest<unknown>(
        `/admin/policies/${encodeURIComponent(base.policyId)}/threshold`,
        { method: 'POST', body: { passThreshold } },
      );
      const result = decodeAdminPolicyV4(raw);
      if (result.policyId === base.policyId || result.basedOnPolicyId !== base.policyId ||
          result.active || !matchesThresholdEdit(result, base, passThreshold)) {
        throw new PolicyAdminContractErrorV4('새 버전이 비활성 상태로 생성되지 않았거나 원본에서 승계한 설정이 다릅니다.');
      }
      return result;
    });
  }
  async function activate(policy: AdminPolicyV4): Promise<AdminPolicyV4> {
    return serialize(async () => {
      await assertAdmin();
      if (policy.partCode !== partCode || !policy.ready) {
        throw new Error('준비된 선택한 부품 정책만 적용할 수 있습니다.');
      }
      const raw = await transport.authorizedRequest<unknown>(
        `/admin/policies/${encodeURIComponent(policy.policyId)}/activate`, { method: 'POST' },
      );
      const result = decodeAdminPolicyV4(raw);
      if (result.policyId !== policy.policyId || !result.active || result.partCode !== partCode) {
        throw new PolicyAdminContractErrorV4('적용 응답의 정책 ID 또는 활성 상태가 다릅니다.');
      }
      return result;
    });
  }
  return { list, saveNewVersion, activate };
}
