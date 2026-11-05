/**
 * 63단계: 이승규 API v4 (10/15) 검사 조회/모니터링 응답 파서.
 * 이 파일은 네트워크 요청/영구 저장을 하지 않습니다.
 * 목록의 정확한 페이지 JSON 형태는 서버 확인 전이므로 두 후보 형태만 엄격히 지원합니다.
 */
import { ContractV4Error } from './adapter';
import type { DisplayStateV4, FinalJudgementV4, PredictedQualityV4, ReviewReasonV4 } from './types';

export const INSPECTION_UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const displayStates: readonly DisplayStateV4[] = ['ANALYZING', 'AUTO_PASS', 'REVIEW_PENDING', 'REVIEW_DONE', 'FAILED'];
const reviewReasons: readonly ReviewReasonV4[] = ['DEFECT_PREDICTED', 'NO_ACTIVE_POLICY', 'CALIBRATION_UNAVAILABLE', 'ABOVE_THRESHOLD'];

type Dict = Record<string, unknown>;
function record(x: unknown): x is Dict { return typeof x === 'object' && x !== null && !Array.isArray(x); }
function nonblank(x: unknown): x is string { return typeof x === 'string' && x.trim().length > 0; }
function optionalString(x: unknown): x is string | null | undefined { return x == null || typeof x === 'string'; }
function nonnegativeInt(x: unknown): x is number { return typeof x === 'number' && Number.isSafeInteger(x) && x >= 0; }
function validIso(x: unknown): x is string {
  return nonblank(x) && /(Z|[+-]\d\d:\d\d)$/.test(x) && Number.isFinite(Date.parse(x));
}
function state(x: unknown): x is DisplayStateV4 { return displayStates.includes(x as DisplayStateV4); }
function optionalPrediction(x: unknown): x is PredictedQualityV4 | null | undefined {
  return x == null || x === 'GOOD' || x === 'DEFECT';
}
function optionalJudgement(x: unknown): x is FinalJudgementV4 | null | undefined {
  return x == null || x === 'PASS' || x === 'FAIL';
}
function optionalReason(x: unknown): x is ReviewReasonV4 | null | undefined {
  return x == null || reviewReasons.includes(x as ReviewReasonV4);
}
function optionalUrl(x: unknown): x is string | null | undefined {
  // thumbnailUrl은 계약상 상대 경로 또는 서명된 절대 URL 가능. JS 이미지 로더 연결은 추후.
  return x == null || (typeof x === 'string' && x.length > 0);
}
function nullableField<T>(x: T | undefined): T | null { return x === undefined ? null : x; }

export interface HistoryRowV4 {
  inspectionId: string; // API 호출용 UUID, inspectionNo 아님
  inspectionNo: string | null; // 목록에 없는 경우 "미제공"으로 표시, 상세 GET 후 표시
  partCode: string;
  displayState: DisplayStateV4;
  receivedAt: string;
  predictedQuality: PredictedQualityV4 | null;
  reviewReason: ReviewReasonV4 | null;
  errorCode: string | null;
  thumbnailUrl: string | null;
  finalJudgement: FinalJudgementV4 | null;
  judgedBy: 'SYSTEM' | 'WORKER' | null;
  confirmedAt: string | null;
}
export interface HistoryPageV4 {
  items: HistoryRowV4[];
  page: number;
  size: number;
  hasNext: boolean | null; // 서버 메타가 없으면 추측하지 않음
  totalElements: number | null;
  pageFormat: 'items' | 'spring-content'; // 실서버 형식 확정 전 임시 지원
}
export type QueueTypeV4 = 'ALL' | 'REVIEW' | 'FAILED';
export interface QueueItemV4 {
  inspectionId: string;
  inspectionNo: string | null;
  partCode: string;
  displayState: 'REVIEW_PENDING' | 'FAILED';
  predictedQuality: PredictedQualityV4 | null;
  reviewReason: ReviewReasonV4 | null;
  errorCode: string | null;
  receivedAt: string;
  thumbnailUrl: string | null;
}
export interface QueuePageV4 { items: QueueItemV4[]; nextCursor: string | null; }
export interface MonitoringRecentV4 {
  inspectionId: string;
  inspectionNo: string | null;
  displayState: DisplayStateV4;
  receivedAt: string;
  thumbnailUrl: string | null;
}
export interface MonitoringPartV4 {
  partCode: string;
  partName: string;
  modelAvailable: boolean;
  policyActive: boolean;
  lastReceivedAt: string | null;
  pendingReviewCount: number;
  failedCount: number;
  recent: MonitoringRecentV4[];
}

export function assertInspectionUuidV4(id: string): void {
  if (!INSPECTION_UUID_V4.test(id)) throw new ContractV4Error('API 조회에는 inspectionNo가 아닌 UUID inspectionId가 필요합니다.');
}

export function decodeHistoryRowV4(value: unknown): HistoryRowV4 {
  if (!record(value) || !nonblank(value.inspectionId) || !nonblank(value.partCode) ||
      !state(value.displayState) || !validIso(value.receivedAt)) {
    throw new ContractV4Error('검사 이력 항목에 필수 id/partCode/displayState/receivedAt이 없습니다.');
  }
  assertInspectionUuidV4(value.inspectionId);
  if (!optionalString(value.inspectionNo) || !optionalPrediction(value.predictedQuality) ||
      !optionalReason(value.reviewReason) || !optionalString(value.errorCode) ||
      !optionalUrl(value.thumbnailUrl) || !optionalJudgement(value.finalJudgement) ||
      (value.judgedBy != null && value.judgedBy !== 'WORKER' && value.judgedBy !== 'SYSTEM') ||
      (value.confirmedAt != null && !validIso(value.confirmedAt))) {
    throw new ContractV4Error('검사 이력 항목의 선택 필드 형식이 올바르지 않습니다.');
  }
  return {
    inspectionId: value.inspectionId, inspectionNo: nullableField(value.inspectionNo as string | null | undefined),
    partCode: value.partCode, displayState: value.displayState, receivedAt: value.receivedAt,
    predictedQuality: nullableField(value.predictedQuality as PredictedQualityV4 | null | undefined),
    reviewReason: nullableField(value.reviewReason as ReviewReasonV4 | null | undefined),
    errorCode: nullableField(value.errorCode as string | null | undefined),
    thumbnailUrl: nullableField(value.thumbnailUrl as string | null | undefined),
    finalJudgement: nullableField(value.finalJudgement as FinalJudgementV4 | null | undefined),
    judgedBy: nullableField(value.judgedBy as 'WORKER' | 'SYSTEM' | null | undefined),
    confirmedAt: nullableField(value.confirmedAt as string | null | undefined),
  };
}

/**
 * v4 §6.6의 목록 page JSON이 문서에서 미확정이라 명시적인 두 형태만 허용:
 * A: {items, page?, size?, hasNext?, totalElements?}
 * B: Spring Page {content, number?, size?, last?, totalElements?}.
 * 어느 것도 아니면 오해를 막기 위해 오류. 응답 페이지 수/다음 페이지는 임의 계산하지 않습니다.
 */
export function decodeHistoryPageV4(data: unknown, requestedPage: number, requestedSize: number): HistoryPageV4 {
  if (!record(data)) throw new ContractV4Error('검사 이력의 페이지 응답은 객체여야 합니다.');
  const format = Array.isArray(data.items) ? 'items' : Array.isArray(data.content) ? 'spring-content' : null;
  if (!format) throw new ContractV4Error('검사 이력 페이지의 items/content 필드를 확인할 수 없습니다. 백엔드 실제 형식 확인 필요.');
  const raw = format === 'items' ? data.items : data.content;
  const serverPage = format === 'spring-content' ? data.number : data.page;
  const page = serverPage === undefined ? requestedPage : serverPage;
  const size = data.size === undefined ? requestedSize : data.size;
  if (!nonnegativeInt(page) || !nonnegativeInt(size) || size < 1 || size > 100) {
    throw new ContractV4Error('검사 이력 페이지 번호 또는 크기 오류');
  }
  if (data.totalElements != null && !nonnegativeInt(data.totalElements)) {
    throw new ContractV4Error('totalElements 형식 오류');
  }
  if (data.hasNext != null && typeof data.hasNext !== 'boolean') throw new ContractV4Error('hasNext 형식 오류');
  if (data.last != null && typeof data.last !== 'boolean') throw new ContractV4Error('last 형식 오류');
  const hasNext = typeof data.hasNext === 'boolean' ? data.hasNext :
    typeof data.last === 'boolean' ? !data.last :
    typeof data.totalElements === 'number' ? (page + 1) * size < data.totalElements : null;
  return {
    items: (raw as unknown[]).map(decodeHistoryRowV4), page, size, hasNext,
    totalElements: typeof data.totalElements === 'number' ? data.totalElements : null, pageFormat: format,
  };
}

export function decodeQueuePageV4(data: unknown): QueuePageV4 {
  if (!record(data) || !Array.isArray(data.items) || !optionalString(data.nextCursor)) {
    throw new ContractV4Error('확인 필요 목록 items/nextCursor 형식 오류');
  }
  const items = data.items.map((v: unknown): QueueItemV4 => {
    if (!record(v)) throw new ContractV4Error('확인 필요 항목 형식 오류');
    const r = decodeHistoryRowV4(v);
    if (r.displayState !== 'REVIEW_PENDING' && r.displayState !== 'FAILED') {
      throw new ContractV4Error('확인 필요 목록에는 REVIEW_PENDING/FAILED만 허용합니다.');
    }
    return {
      inspectionId: r.inspectionId, inspectionNo: r.inspectionNo, partCode: r.partCode,
      displayState: r.displayState, predictedQuality: r.predictedQuality, reviewReason: r.reviewReason,
      errorCode: r.errorCode, receivedAt: r.receivedAt, thumbnailUrl: r.thumbnailUrl,
    };
  });
  return { items, nextCursor: nullableField(data.nextCursor as string | null | undefined) };
}

export function decodeMonitoringPartsV4(data: unknown): MonitoringPartV4[] {
  if (!Array.isArray(data)) throw new ContractV4Error('monitoring/parts 응답은 배열이어야 합니다.');
  return data.map((v: unknown): MonitoringPartV4 => {
    if (!record(v) || !nonblank(v.partCode) || !nonblank(v.partName) ||
        typeof v.modelAvailable !== 'boolean' || typeof v.policyActive !== 'boolean' ||
        !nonnegativeInt(v.pendingReviewCount) || !nonnegativeInt(v.failedCount) ||
        (v.lastReceivedAt != null && !validIso(v.lastReceivedAt)) || !Array.isArray(v.recent)) {
      throw new ContractV4Error('부품별 모니터링 필드 형식 오류');
    }
    const recent = v.recent.map((entry: unknown): MonitoringRecentV4 => {
      if (!record(entry) || !nonblank(entry.inspectionId) || !state(entry.displayState) || !validIso(entry.receivedAt) ||
          !optionalUrl(entry.thumbnailUrl) || !optionalString(entry.inspectionNo)) {
        throw new ContractV4Error('최근 접수 썸네일의 필드 형식 오류');
      }
      assertInspectionUuidV4(entry.inspectionId);
      return {
        inspectionId: entry.inspectionId,
        inspectionNo: nullableField(entry.inspectionNo as string | null | undefined),
        displayState: entry.displayState, receivedAt: entry.receivedAt,
        thumbnailUrl: nullableField(entry.thumbnailUrl as string | null | undefined),
      };
    });
    return {
      partCode: v.partCode, partName: v.partName, modelAvailable: v.modelAvailable,
      policyActive: v.policyActive,
      lastReceivedAt: nullableField(v.lastReceivedAt as string | null | undefined),
      pendingReviewCount: v.pendingReviewCount, failedCount: v.failedCount, recent,
    };
  });
}

/** 서버의 만료 서명 이미지 URL을 로컬 저장/영구 캐시에 사용하지 마세요. */
export function imageNeedsDetailRefetchV4(
  expiresAt: string | null, imageLoadFailed: boolean, nowMs: number = Date.now(),
): boolean {
  if (imageLoadFailed) return true; // 만료 시각이 없는 URL도 onError라면 1회 상세 재조회
  if (!expiresAt) return false; // 알 수 없는 만료: 화면 이미지 onError에서 갱신
  const ms = Date.parse(expiresAt);
  return !Number.isFinite(ms) || ms - nowMs <= 30_000;
}

export function makeHistoryQueryV4(params: {
  page: number; size?: number; partCode?: string;
  displayState?: DisplayStateV4; from?: string; to?: string;
}): string {
  const size = params.size ?? 20;
  if (!nonnegativeInt(params.page) || !nonnegativeInt(size) || size < 1 || size > 100) {
    throw new Error('page >= 0, size 1~100이어야 합니다.');
  }
  if (params.displayState != null && !state(params.displayState)) throw new Error('지원하지 않는 displayState');
  if (params.from != null && !validIso(params.from)) throw new Error('from은 오프셋 포함 ISO 시각이어야 합니다.');
  if (params.to != null && !validIso(params.to)) throw new Error('to는 오프셋 포함 ISO 시각이어야 합니다.');
  const query = [`page=${params.page}`, `size=${size}`];
  if (params.partCode) query.push(`partCode=${encodeURIComponent(params.partCode)}`);
  if (params.displayState) query.push(`displayState=${encodeURIComponent(params.displayState)}`);
  if (params.from) query.push(`from=${encodeURIComponent(params.from)}`);
  if (params.to) query.push(`to=${encodeURIComponent(params.to)}`);
  return `/inspections?${query.join('&')}`;
}
export function makeQueueQueryV4(params: { type?: QueueTypeV4; partCode?: string; cursor?: string | null; size?: number } = {}): string {
  const type = params.type ?? 'ALL'; const size = params.size ?? 20;
  if (type !== 'ALL' && type !== 'REVIEW' && type !== 'FAILED') throw new Error('queue.type 오류');
  if (!nonnegativeInt(size) || size < 1 || size > 100) throw new Error('queue.size는 1~100이어야 합니다.');
  const query = [`type=${type}`, `size=${size}`];
  if (params.partCode) query.push(`partCode=${encodeURIComponent(params.partCode)}`);
  if (params.cursor) query.push(`cursor=${encodeURIComponent(params.cursor)}`);
  return `/monitoring/queue?${query.join('&')}`;
}

/** 현재 화면에서 data.source 라벨로 server/가상 응답을 구분하세요. */
export type InspectionReadSourceV4 = 'CONTRACT_EXAMPLE' | 'SERVER';
export const listItemTitleV4 = (inspectionNo: string | null): string => inspectionNo ?? '검사번호 미제공 (상세 조회)';
