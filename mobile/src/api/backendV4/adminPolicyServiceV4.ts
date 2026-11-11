/**
 * API 계약 v4 §6.9: 실제 COWL_COVER 관리자 정책 조회·조정·적용.
 * 요청/응답은 authV4.authorizedRequest의 {data} 해제된 형태.
 * 서버 권한 검사(403)가 최종 권위이며, 라우트 role 파라미터는 신뢰하지 않습니다.
 */
import type { AuthPublicState } from './authCore';
import { validateThresholdEditV4 } from './policyThresholdV4';

export const COWL_PART_CODE_V4 = 'COWL_COVER';

export interface AdminPolicyV4 {
  policyId: string;
  policyVersion: string;
  partCode: string;
  modelVersion: string;
  calibratorVersion: string | null;
  passThreshold: number | null;
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
      !nullableUnit(raw.passThreshold) || !nullableUnit(raw.validatedMin) ||
      !nullableUnit(raw.validatedMax) || typeof raw.ready !== 'boolean' ||
      typeof raw.active !== 'boolean' || (raw.metrics != null && !record(raw.metrics))) {
    throw new PolicyAdminContractErrorV4('필수 필드·정책 기준값·상태가 계약과 일치하지 않습니다.');
  }
  if ((raw.validatedMin != null && raw.validatedMax != null) && raw.validatedMin > raw.validatedMax) {
    throw new PolicyAdminContractErrorV4('validatedMin이 validatedMax보다 큽니다.');
  }
  if (raw.active && !raw.ready) throw new PolicyAdminContractErrorV4('미준비 정책이 활성 상태입니다.');
  return {
    policyId: raw.policyId,
    policyVersion: raw.policyVersion,
    partCode: raw.partCode,
    modelVersion: raw.modelVersion,
    calibratorVersion: raw.calibratorVersion ?? null,
    passThreshold: raw.passThreshold ?? null,
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

export function decodeCowlPolicyListV4(raw: unknown): AdminPolicyV4[] {
  if (!Array.isArray(raw)) throw new PolicyAdminContractErrorV4('GET /admin/policies 결과는 배열이어야 합니다.');
  const policies = raw.map(decodeAdminPolicyV4);
  if (policies.some((p) => p.partCode !== COWL_PART_CODE_V4)) {
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
  const result = validateThresholdEditV4(String(number / 100), {
    validatedMin: policy.validatedMin,
    validatedMax: policy.validatedMax,
    evidenceVerified: policy.ready,
  });
  if (!result.ok) {
    const messages = {
      UNVERIFIED: '준비 완료된 정책과 서버 검증 범위가 있어야 조정할 수 있습니다.',
      BAD_RANGE: '서버가 제공한 허용 범위가 올바르지 않습니다.',
      INVALID_VALUE: '기준치 숫자를 확인해 주세요.',
      OUT_OF_RANGE: `허용 범위(${percentageTextV4(policy.validatedMin)}~${percentageTextV4(policy.validatedMax)}) 밖입니다.`,
    };
    throw new Error(messages[result.reason]);
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

export function createAdminPolicyServiceV4(transport: PolicyAdminTransportV4) {
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
      `/admin/policies?partCode=${encodeURIComponent(COWL_PART_CODE_V4)}`,
      { method: 'GET' },
    );
    return decodeCowlPolicyListV4(raw);
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
      if (base.partCode !== COWL_PART_CODE_V4 || !base.active || !base.ready) {
        throw new Error('현재 활성·준비된 COWL_COVER 정책에서만 새 버전을 저장할 수 있습니다.');
      }
      const passThreshold = parsePolicyPercentInputV4(inputPercent, base);
      const raw = await transport.authorizedRequest<unknown>(
        `/admin/policies/${encodeURIComponent(base.policyId)}/threshold`,
        { method: 'POST', body: { passThreshold } },
      );
      const result = decodeAdminPolicyV4(raw);
      if (result.policyId === base.policyId || result.basedOnPolicyId !== base.policyId ||
          result.partCode !== base.partCode || result.modelVersion !== base.modelVersion ||
          result.active || Math.abs((result.passThreshold ?? -1) - passThreshold) > 0.000001) {
        throw new PolicyAdminContractErrorV4('새 버전이 비활성 상태로 생성되지 않았거나 원본 연결이 다릅니다.');
      }
      return result;
    });
  }
  async function activate(policy: AdminPolicyV4): Promise<AdminPolicyV4> {
    return serialize(async () => {
      await assertAdmin();
      if (policy.partCode !== COWL_PART_CODE_V4 || !policy.ready) {
        throw new Error('준비된 COWL_COVER 정책만 적용할 수 있습니다.');
      }
      const raw = await transport.authorizedRequest<unknown>(
        `/admin/policies/${encodeURIComponent(policy.policyId)}/activate`, { method: 'POST' },
      );
      const result = decodeAdminPolicyV4(raw);
      if (result.policyId !== policy.policyId || !result.active || result.partCode !== COWL_PART_CODE_V4) {
        throw new PolicyAdminContractErrorV4('적용 응답의 정책 ID 또는 활성 상태가 다릅니다.');
      }
      return result;
    });
  }
  return { list, saveNewVersion, activate };
}
