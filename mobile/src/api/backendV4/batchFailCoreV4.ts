/**
 * 계약 v4 §6.7.1 작업자 REVIEW 일괄 FAIL — 순수 검증/응답 파서.
 * 실서버 요청과 화면 표시를 분리하고, 실제 판정 저장은 사용자의 명시적 제출만 허용.
 */
import type { InspectionViewV4 } from './types';
import { MONITORED_PARTS, type ReviewQueueFiltersV4 } from './reviewQueueBrowseCoreV4';
import type { BackendRole } from './authCore';
import { assertWriteUuidV4, WriteV4ValidationError } from './inspectionWriteCore';

/** A link without any scope keeps the original all-parts REVIEW queue. */
export function batchQueueFiltersFromRouteV4(params: {
  partCode?: string | string[]; sort?: string | string[]; aiDefectOnly?: string | string[];
}): ReviewQueueFiltersV4 | null {
  const {partCode, sort, aiDefectOnly} = params;
  if (partCode !== undefined && !MONITORED_PARTS.some(part => part === partCode)) return null;
  if (sort !== undefined && sort !== 'RECEIVED' && sort !== 'PRIORITY') return null;
  if (aiDefectOnly !== undefined && aiDefectOnly !== 'true' && aiDefectOnly !== 'false') return null;
  return {
    partCode: typeof partCode === 'string' ? partCode : null,
    sort: sort ?? 'RECEIVED',
    aiDefectOnly: aiDefectOnly === 'true',
  };
}

/** Native confirmations can outlive a draft, its screen, or the account that reviewed it. */
export function createBatchConfirmationGuardV4(currentEpoch: () => number) {
  const entryEpoch = currentEpoch();
  let revision = 0;
  return {
    invalidate() { revision++; },
    capture() {
      const atConfirmation = ++revision;
      return () => revision === atConfirmation && currentEpoch() === entryEpoch;
    },
  };
}

export const MAX_BATCH_FAIL_V4 = 50;
export type BatchReviewImageStateV4 = 'loading' | 'loaded' | 'failed';
/** A returned image URL is not proof that the worker can actually see the image. */
export function canReviewBatchImagesV4(
  originalUrl: string | null, original: BatchReviewImageStateV4,
  gradcamUrl: string | null, gradcam: BatchReviewImageStateV4,
): boolean {
  return !!originalUrl && original === 'loaded' &&
    (!gradcamUrl || gradcam === 'loaded');
}
export interface BatchFailSelectionV4 {
  inspectionId: string;
  inspectionNo: string;
  partCode: string;
}
export interface BatchFailRequestV4 {
  finalJudgement: 'FAIL';
  comment?: string;
  items: { inspectionId: string }[];
}
export type BatchFailOutcomeV4 =
  | 'CONFIRMED' | 'ALREADY_CONFIRMED' | 'CONFLICT'
  | 'NOT_REVIEWABLE' | 'NOT_FOUND' | 'ERROR';
export interface BatchFailResultRowV4 {
  inspectionId: string;
  inspectionNo: string | null;
  result: BatchFailOutcomeV4;
  finalJudgement: 'PASS' | 'FAIL' | null;
  judgedBy: 'WORKER' | 'SYSTEM' | null;
  confirmedBy: string | null;
  confirmedAt: string | null;
  errorCode: string | null;
}
export interface BatchFailReplyV4 {
  batchId: string;
  results: BatchFailResultRowV4[];
}
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const INS = /^INS-\d{6,}$/;
const OUTCOMES: readonly BatchFailOutcomeV4[] = [
  'CONFIRMED','ALREADY_CONFIRMED','CONFLICT','NOT_REVIEWABLE','NOT_FOUND','ERROR',
];
function obj(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}
function iso(v: unknown): v is string {
  return typeof v === 'string' && /(Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
}
function invalid(reason: string): never {
  throw new WriteV4ValidationError('INVALID_BATCH_FAIL', reason);
}
export function selectableReviewForBatchV4(detail: InspectionViewV4): BatchFailSelectionV4 {
  assertWriteUuidV4(detail.inspectionId);
  if (detail.displayState !== 'REVIEW_PENDING' || detail.finalJudgement !== null) {
    return invalid('아직 판정하지 않은 REVIEW_PENDING 검사만 선택할 수 있습니다.');
  }
  if (!INS.test(detail.inspectionNo) || !detail.partCode.trim()) {
    return invalid('상세에서 검사번호와 부품을 확인할 수 없습니다.');
  }
  return { inspectionId: detail.inspectionId, inspectionNo: detail.inspectionNo, partCode: detail.partCode };
}
/** 상세 GET으로 직접 검토한 후보만 선택 배열에 들어와야 합니다. */
export function prepareBatchFailBodyV4(
  role: BackendRole | null,
  selected: readonly BatchFailSelectionV4[],
  comment: string,
): BatchFailRequestV4 {
  if (role !== 'WORKER') invalid('일괄 FAIL 판정은 작업자(WORKER)만 제출할 수 있습니다.');
  if (selected.length < 1 || selected.length > MAX_BATCH_FAIL_V4) {
    invalid('일괄 FAIL은 1~50건까지만 선택할 수 있습니다.');
  }
  const ids = new Set<string>();
  for (const item of selected) {
    assertWriteUuidV4(item.inspectionId);
    if (!INS.test(item.inspectionNo) || !item.partCode.trim()) invalid('검사번호·부품 정보가 필요합니다.');
    if (ids.has(item.inspectionId)) invalid('동일한 검사 ID를 두 번 선택할 수 없습니다.');
    ids.add(item.inspectionId);
  }
  const trimmed = comment.trim();
  if ([...trimmed].length > 200) invalid('공통 판정 사유는 200자 이하여야 합니다.');
  return { finalJudgement: 'FAIL', ...(trimmed ? {comment:trimmed} : {}),
    items: selected.map(({inspectionId}) => ({inspectionId})) };
}
export function decodeBatchFailReplyV4(raw: unknown, request: BatchFailRequestV4): BatchFailReplyV4 {
  if (!obj(raw) || typeof raw.batchId !== 'string' || !UUID.test(raw.batchId) || !Array.isArray(raw.results) ||
    raw.results.length !== request.items.length) {
    return invalid('일괄 FAIL 응답의 batchId 또는 결과 건수가 올바르지 않습니다.');
  }
  const results = raw.results.map((entry, index): BatchFailResultRowV4 => {
    if (!obj(entry) || entry.inspectionId !== request.items[index].inspectionId ||
      !OUTCOMES.includes(entry.result as BatchFailOutcomeV4) ||
      (entry.inspectionNo != null && (typeof entry.inspectionNo !== 'string' || !INS.test(entry.inspectionNo))) ||
      (entry.finalJudgement != null && entry.finalJudgement !== 'PASS' && entry.finalJudgement !== 'FAIL') ||
      (entry.judgedBy != null && entry.judgedBy !== 'WORKER' && entry.judgedBy !== 'SYSTEM') ||
      (entry.confirmedBy != null && typeof entry.confirmedBy !== 'string') ||
      (entry.confirmedAt != null && !iso(entry.confirmedAt)) ||
      (entry.errorCode != null && (typeof entry.errorCode !== 'string' || !entry.errorCode.trim()))) {
      return invalid('일괄 FAIL 응답의 결과 순서·값이 요청과 다릅니다.');
    }
    const success = entry.result === 'CONFIRMED' || entry.result === 'ALREADY_CONFIRMED';
    if (success && (entry.finalJudgement !== 'FAIL' || entry.judgedBy !== 'WORKER' ||
      typeof entry.confirmedBy !== 'string' || !entry.confirmedBy.trim() ||
      !iso(entry.confirmedAt) || entry.errorCode != null)) {
      return invalid('성공 결과에 FAIL · WORKER 판정 기록이 없습니다.');
    }
    if (!success && (typeof entry.errorCode !== 'string' || !entry.errorCode.trim())) {
      return invalid('실패 결과에 errorCode가 없습니다.');
    }
    return {
      inspectionId: entry.inspectionId as string,
      inspectionNo: (entry.inspectionNo ?? null) as string | null,
      result: entry.result as BatchFailOutcomeV4,
      finalJudgement: (entry.finalJudgement ?? null) as 'PASS' | 'FAIL' | null,
      judgedBy: (entry.judgedBy ?? null) as 'WORKER' | 'SYSTEM' | null,
      confirmedBy: (entry.confirmedBy ?? null) as string | null,
      confirmedAt: (entry.confirmedAt ?? null) as string | null,
      errorCode: (entry.errorCode ?? null) as string | null,
    };
  });
  return {batchId: raw.batchId, results};
}
export function batchFailResultLabelV4(code: BatchFailOutcomeV4): string {
  switch(code) {
    case 'CONFIRMED': return '이번 요청으로 FAIL 저장';
    case 'ALREADY_CONFIRMED': return '이미 FAIL 확정됨 (중복 저장 없음)';
    case 'CONFLICT': return '이미 PASS 판정되어 덮어쓰지 않음';
    case 'NOT_REVIEWABLE': return '현재 REVIEW 대기 검사가 아님';
    case 'NOT_FOUND': return '검사 없음';
    case 'ERROR': return '건별 서버 오류 (저장되지 않음)';
  }
}
