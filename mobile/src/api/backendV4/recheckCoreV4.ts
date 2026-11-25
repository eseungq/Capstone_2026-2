/** 계약 6.11: AUTO_PASS 재확인과 관리자의 '확인함'은 원래 PASS·SYSTEM 판정과 별도. */
import type { FinalJudgementV4, RecheckBlockV4 } from './types';
import type { InspectionDwellV4 } from './inspectionDwellV4';

export type RecheckStatusV4 = 'PENDING' | 'DONE';
export type RecheckStratumV4 = 'NEAR' | 'MID' | 'LOW';
export interface RecheckListItemV4 {
  inspectionId: string;
  inspectionNo: string;
  partCode: string;
  receivedAt: string;
  stratum: RecheckStratumV4;
  sampledAt: string;
  result: FinalJudgementV4 | null;
  recheckedAt: string | null;
  acknowledgedBy: string | null;
  acknowledgedAt: string | null;
}
export interface RecheckPageV4 {
  items: RecheckListItemV4[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
}
export interface RecheckFiltersV4 {
  status: RecheckStatusV4;
  result?: FinalJudgementV4;
  acknowledged?: boolean;
  partCode?: string;
  page: number;
  size?: number;
}
export interface RecheckReplyV4 {
  inspectionId: string;
  inspectionNo: string;
  finalJudgement: 'PASS';
  judgedBy: 'SYSTEM';
  recheck: RecheckBlockV4;
}

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const isRecord = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === 'object' && !Array.isArray(x);
const isText = (x: unknown): x is string => typeof x === 'string' && x.trim().length > 0;
const isNullableText = (x: unknown): boolean => x == null || typeof x === 'string';
const isIso = (x: unknown): x is string => isText(x) && /(Z|[+-]\d\d:\d\d)$/.test(x) && Number.isFinite(Date.parse(x));
const isNullableIso = (x: unknown): boolean => x == null || isIso(x);
const isJudgement = (x: unknown): x is FinalJudgementV4 => x === 'PASS' || x === 'FAIL';
const isStratum = (x: unknown): x is RecheckStratumV4 => x === 'NEAR' || x === 'MID' || x === 'LOW';

export function assertRecheckIdV4(inspectionId: string): void {
  if (!uuidPattern.test(inspectionId)) throw new Error('재확인 API에는 검사 표시번호가 아닌 UUID가 필요합니다.');
}
export function makeRecheckListPathV4(f: RecheckFiltersV4): string {
  if (f.status !== 'PENDING' && f.status !== 'DONE') throw new Error('재확인 상태 오류');
  if (!Number.isSafeInteger(f.page) || f.page < 0) throw new Error('재확인 페이지 번호 오류');
  const size = f.size ?? 20;
  if (!Number.isSafeInteger(size) || size < 1 || size > 100) throw new Error('재확인 목록 size는 1~100입니다.');
  if (f.status === 'PENDING' && (f.result !== undefined || f.acknowledged !== undefined)) {
    throw new Error('대기 중인 재확인은 결과·관리자 확인함 필터를 사용할 수 없습니다.');
  }
  if (f.result !== undefined && !isJudgement(f.result)) throw new Error('재확인 결과 필터 오류');
  if (f.acknowledged !== undefined && typeof f.acknowledged !== 'boolean') throw new Error('확인함 필터 오류');
  const q = new URLSearchParams({ status: f.status, page: String(f.page), size: String(size) });
  if (f.result !== undefined) q.append('result', f.result);
  if (f.acknowledged !== undefined) q.append('acknowledged', String(f.acknowledged));
  if (f.partCode) q.append('partCode', f.partCode);
  return '/rechecks?' + q.toString();
}
export function makeRecheckPostPathV4(id: string, action: 'recheck' | 'acknowledge'): string {
  assertRecheckIdV4(id);
  return action === 'recheck'
    ? '/inspections/' + encodeURIComponent(id) + '/recheck'
    : '/admin/rechecks/' + encodeURIComponent(id) + '/acknowledge';
}
export function validateDwellFieldsV4(timing: InspectionDwellV4 | null | undefined): InspectionDwellV4 | undefined {
  if (!timing) return undefined;
  if (!Number.isSafeInteger(timing.screenDwellMs) || timing.screenDwellMs < 0 || timing.screenDwellMs > 86_400_000 ||
      !Number.isSafeInteger(timing.openCount) || timing.openCount < 1 || timing.openCount > 1000 ||
      !isIso(timing.firstOpenedAt)) {
    throw new Error('체류 시간 세 필드가 올바르지 않습니다. 일부만 전송하지 않습니다.');
  }
  return {
    screenDwellMs: timing.screenDwellMs,
    firstOpenedAt: timing.firstOpenedAt,
    openCount: timing.openCount,
  };
}
export function makeRecheckSubmitBodyV4(
  result: FinalJudgementV4, comment?: string, timing?: InspectionDwellV4 | null,
): { result: FinalJudgementV4; comment?: string; screenDwellMs?: number; firstOpenedAt?: string; openCount?: number } {
  if (!isJudgement(result)) throw new Error('재확인 결과는 PASS 또는 FAIL이어야 합니다.');
  if (comment !== undefined && (typeof comment !== 'string' || [...comment.trim()].length > 200)) {
    throw new Error('재확인 메모는 최대 200자입니다.');
  }
  const trimmed = comment?.trim();
  const dwell = validateDwellFieldsV4(timing);
  return { result, ...(trimmed ? { comment: trimmed } : {}), ...(dwell ?? {}) };
}
export function makeAcknowledgeBodyV4(note?: string): { note?: string } {
  if (note !== undefined && (typeof note !== 'string' || [...note.trim()].length > 200)) {
    throw new Error('관리자 확인 메모는 최대 200자입니다.');
  }
  const trimmed = note?.trim();
  return trimmed ? { note: trimmed } : {};
}
export function decodeRecheckBlockV4(raw: unknown): RecheckBlockV4 | null {
  if (raw == null) return null; // 표본 재확인이 아닌 일반 검사에는 recheck=null
  if (!isRecord(raw) || !isStratum(raw.stratum) ||
      typeof raw.samplingRate !== 'number' || !Number.isFinite(raw.samplingRate) ||
      raw.samplingRate < 0 || raw.samplingRate > 1 ||
      !isIso(raw.sampledAt) || !isNullableText(raw.ruleVersion) || !isNullableText(raw.trialName) ||
      (raw.result != null && !isJudgement(raw.result)) ||
      !isNullableText(raw.comment) || !isNullableText(raw.recheckedBy) ||
      !isNullableIso(raw.recheckedAt) ||
      !isNullableText(raw.acknowledgedBy) || !isNullableIso(raw.acknowledgedAt) ||
      !isNullableText(raw.acknowledgeNote)) {
    throw new Error('재확인 상세 recheck 필드 형식 오류');
  }
  if (raw.result == null && (raw.recheckedAt != null || raw.recheckedBy != null || raw.acknowledgedAt != null)) {
    throw new Error('재확인 전인데 완료·관리자 확인 기록이 있습니다.');
  }
  if ((raw.acknowledgedAt == null) !== (raw.acknowledgedBy == null) ||
      (raw.acknowledgedAt != null && raw.result !== 'FAIL')) {
    throw new Error('관리자 확인함 상태와 재확인 결과가 불일치합니다.');
  }
  return {
    stratum: raw.stratum,
    samplingRate: raw.samplingRate,
    ruleVersion: (raw.ruleVersion ?? null) as string | null,
    trialName: (raw.trialName ?? null) as string | null,
    sampledAt: raw.sampledAt,
    result: (raw.result ?? null) as FinalJudgementV4 | null,
    comment: (raw.comment ?? null) as string | null,
    recheckedBy: (raw.recheckedBy ?? null) as string | null,
    recheckedAt: (raw.recheckedAt ?? null) as string | null,
    acknowledgedBy: (raw.acknowledgedBy ?? null) as string | null,
    acknowledgedAt: (raw.acknowledgedAt ?? null) as string | null,
    acknowledgeNote: (raw.acknowledgeNote ?? null) as string | null,
  };
}
export function decodeRecheckPageV4(raw: unknown, requestedStatus: RecheckStatusV4): RecheckPageV4 {
  if (!isRecord(raw) || !Array.isArray(raw.items) ||
      !Number.isSafeInteger(raw.page) || (raw.page as number) < 0 ||
      !Number.isSafeInteger(raw.size) || (raw.size as number) < 1 ||
      !Number.isSafeInteger(raw.totalElements) || (raw.totalElements as number) < 0 ||
      !Number.isSafeInteger(raw.totalPages) || (raw.totalPages as number) < 0) {
    throw new Error('재확인 목록 페이지 형식 오류');
  }
  const items: RecheckListItemV4[] = raw.items.map((x: unknown) => {
    if (!isRecord(x) || !isText(x.inspectionId) || !isText(x.inspectionNo) || !isText(x.partCode) ||
        !isIso(x.receivedAt) || !isStratum(x.stratum) || !isIso(x.sampledAt) ||
        (x.result != null && !isJudgement(x.result)) || !isNullableIso(x.recheckedAt) ||
        !isNullableText(x.acknowledgedBy) || !isNullableIso(x.acknowledgedAt)) {
      throw new Error('재확인 목록 항목 형식 오류');
    }
    assertRecheckIdV4(x.inspectionId);
    if ((requestedStatus === 'PENDING' && x.result != null) ||
        (requestedStatus === 'DONE' && x.result == null) ||
        (x.acknowledgedAt == null) !== (x.acknowledgedBy == null) ||
        (x.acknowledgedAt != null && x.result !== 'FAIL')) {
      throw new Error('재확인 목록의 결과·관리자 확인함 상태 오류');
    }
    return {
      inspectionId: x.inspectionId, inspectionNo: x.inspectionNo, partCode: x.partCode,
      receivedAt: x.receivedAt, stratum: x.stratum, sampledAt: x.sampledAt,
      result: (x.result ?? null) as FinalJudgementV4 | null,
      recheckedAt: (x.recheckedAt ?? null) as string | null,
      acknowledgedBy: (x.acknowledgedBy ?? null) as string | null,
      acknowledgedAt: (x.acknowledgedAt ?? null) as string | null,
    };
  });
  return { items, page: raw.page as number, size: raw.size as number,
    totalElements: raw.totalElements as number, totalPages: raw.totalPages as number };
}
export function decodeRecheckReplyV4(raw: unknown, id: string, expected?: FinalJudgementV4): RecheckReplyV4 {
  assertRecheckIdV4(id);
  if (!isRecord(raw) || raw.inspectionId !== id || !isText(raw.inspectionNo) ||
      raw.finalJudgement !== 'PASS' || raw.judgedBy !== 'SYSTEM') {
    throw new Error('재확인 서버 응답에서 원래 PASS·SYSTEM 판정이 확인되지 않았습니다.');
  }
  const block = decodeRecheckBlockV4(raw.recheck);
  if (!block || (expected !== undefined && block.result !== expected)) {
    throw new Error('재확인 서버 결과가 요청과 다릅니다.');
  }
  return { inspectionId: id, inspectionNo: raw.inspectionNo, finalJudgement: 'PASS',
    judgedBy: 'SYSTEM', recheck: block };
}
