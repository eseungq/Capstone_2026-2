/**
 * 65단계 — API v4 판정/재검사 계약 검증 (순수 함수, 네트워크/저장 없음).
 * 기준: 이승규 백엔드 API v4(2026-10-15) §6.7/6.8.
 * 이 파일은 기존 Mock, AsyncStorage, 검사/통계 화면을 변경하지 않습니다.
 */
import type { DisplayStateV4, FinalJudgementV4, PredictedQualityV4 } from './types';

export type WriteRoleV4 = 'WORKER' | 'ADMIN' | 'DEVICE';
export type WriteSourceV4 = 'CONTRACT_EXAMPLE' | 'SERVER';
export type WriteActionV4 = 'confirm' | 'retry' | 'manual';
export interface WriteInspectionContextV4 {
  inspectionId: string; // API 경로: UUID (INS-000006 X)
  displayState: DisplayStateV4;
  finalJudgement: FinalJudgementV4 | null;
  /** 서버가 반환한 경우에만 참조. 미제공이면 중복 여부는 서버가 검사 */
  retriedBy?: string | null;
}
export interface ConfirmInputV4 {
  finalJudgement: FinalJudgementV4;
  comment?: string;
}
export interface ConfirmReplyV4 {
  inspectionId: string;
  inspectionNo: string;
  predictedQuality: PredictedQualityV4 | null; // source=MANUAL이면 AI 결과가 없음
  recommendedAction: 'REVIEW';
  finalJudgement: FinalJudgementV4;
  judgedBy: 'WORKER';
  confirmedBy: string;
  confirmedAt: string; // ISO-8601 오프셋 포함
}
export interface RetryReplyV4 {
  inspectionId: string; // 신규 UUID
  inspectionNo: string; // 신규 표시 번호
  status: 'RECEIVED';
  retryOf: string; // 원래 FAILED UUID
}
export interface ManualReplyV4 {
  inspectionId: string; // 새 수동 검사의 UUID
  inspectionNo: string;
  partCode: string;
  source: 'MANUAL';
  status: 'COMPLETED';
  displayState: 'REVIEW_PENDING';
  reviewReason: 'AI_UNAVAILABLE';
  receivedAt: string;
  manualOf: string; // 원본 FAILED UUID
  manualOfInspectionNo: string;
  manualOfErrorCode: string;
}

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const noPattern = /^INS-\d{6,}$/;
function object(x: unknown): x is Record<string, unknown> { return x !== null && typeof x === 'object' && !Array.isArray(x); }
function text(x: unknown): x is string { return typeof x === 'string' && x.trim().length > 0; }
function iso(x: unknown): x is string { return text(x) && /(Z|[+-]\d\d:\d\d)$/.test(x) && Number.isFinite(Date.parse(x)); }
export class WriteV4ValidationError extends Error {
  constructor(public readonly code: string, message: string) { super(message); this.name = 'WriteV4ValidationError'; }
}
function fail(code: string, msg: string): never { throw new WriteV4ValidationError(code, msg); }
export function assertWriteUuidV4(id: unknown): asserts id is string {
  if (typeof id !== 'string' || !uuidPattern.test(id)) fail('INVALID_INSPECTION_ID', '서버 호출에는 INS-표시 번호가 아닌 UUID inspectionId가 필요합니다.');
}
export function makeWritePathV4(id: string, action: WriteActionV4): string {
  assertWriteUuidV4(id);
  return `/inspections/${encodeURIComponent(id)}/${action}`;
}
/** 관리자에게는 판정 버튼을 표시하지 않으며 API 서버에서도 403으로 보호해야 함. */
export function ensureConfirmAllowedV4(role: WriteRoleV4, inspection: WriteInspectionContextV4, choice: FinalJudgementV4): void {
  assertWriteUuidV4(inspection.inspectionId);
  if (role !== 'WORKER') fail('ACCESS_DENIED', '최종 판정은 WORKER만 제출할 수 있습니다.');
  if (choice !== 'PASS' && choice !== 'FAIL') fail('INVALID_JUDGEMENT', '최종 판정은 PASS 또는 FAIL이어야 합니다.');
  if (inspection.displayState === 'REVIEW_PENDING' && inspection.finalJudgement === null) return;
  // 서버의 같은 값 재전송 -> 기존 200 결과 반환: 네트워크 ACK 유실에 대한 명시적 재전송 허용.
  // 화면에는 REVIEW_DONE에서 판정 버튼을 보이지 않아야 합니다.
  if (inspection.displayState === 'REVIEW_DONE' && inspection.finalJudgement === choice) return;
  if (inspection.displayState === 'REVIEW_DONE') fail('ALREADY_CONFIRMED', '기존과 다른 판정으로 재제출할 수 없습니다.');
  fail('NOT_REVIEWABLE', '작업자 확인 대기 상태에서만 판정할 수 있습니다.');
}
export function makeConfirmBodyV4(input: ConfirmInputV4): { finalJudgement: FinalJudgementV4; comment?: string } {
  if (input.finalJudgement !== 'PASS' && input.finalJudgement !== 'FAIL') fail('INVALID_JUDGEMENT', 'PASS 또는 FAIL만 가능합니다.');
  if (input.comment === undefined) return { finalJudgement: input.finalJudgement };
  if (typeof input.comment !== 'string') fail('INVALID_COMMENT', 'comment는 문자열이어야 합니다.');
  const comment = input.comment.trim();
  if ([...comment].length > 200) fail('INVALID_COMMENT', 'comment는 최대 200자입니다(계약 제안사항).');
  return comment ? { finalJudgement: input.finalJudgement, comment } : { finalJudgement: input.finalJudgement };
}
export function ensureRetryAllowedV4(role: WriteRoleV4, inspection: WriteInspectionContextV4): void {
  assertWriteUuidV4(inspection.inspectionId);
  if (role !== 'WORKER' && role !== 'ADMIN') fail('ACCESS_DENIED', '재검사는 WORKER 또는 ADMIN만 요청할 수 있습니다.');
  if (inspection.displayState !== 'FAILED') fail('NOT_RETRYABLE', 'FAILED 검사만 재검사할 수 있습니다.');
  if (inspection.retriedBy) fail('ALREADY_RETRIED', '이미 재검사 또는 수동 판정으로 전환된 검사입니다.');
}
/** 수동 판정은 AI 서버 가용성과 관계없이 WORKER에게만 허용됩니다. */
export function ensureManualAllowedV4(role: WriteRoleV4, inspection: WriteInspectionContextV4): void {
  assertWriteUuidV4(inspection.inspectionId);
  if (role !== 'WORKER') fail('ACCESS_DENIED', '수동 판정 전환은 WORKER만 요청할 수 있습니다.');
  if (inspection.displayState !== 'FAILED') fail('NOT_MANUAL_CONVERTIBLE', 'FAILED 검사만 수동 판정으로 전환할 수 있습니다.');
  if (inspection.retriedBy) fail('ALREADY_RETRIED', '이미 재검사 또는 수동 판정으로 전환된 검사입니다.');
}

/** 승인된 계약: 응답은 authorizedRequest가 {data}를 해제한 객체. */
export function decodeConfirmReplyV4(raw: unknown, originId: string, sent: FinalJudgementV4): ConfirmReplyV4 {
  assertWriteUuidV4(originId);
  if (!object(raw) || !text(raw.inspectionId) || !text(raw.inspectionNo) ||
      !text(raw.confirmedBy) || !iso(raw.confirmedAt) || !noPattern.test(String(raw.inspectionNo)) ||
      (raw.predictedQuality != null && raw.predictedQuality !== 'GOOD' && raw.predictedQuality !== 'DEFECT') ||
      raw.recommendedAction !== 'REVIEW' || (raw.finalJudgement !== 'PASS' && raw.finalJudgement !== 'FAIL') ||
      raw.judgedBy !== 'WORKER') {
    return fail('INVALID_CONFIRM_RESPONSE', '판정 응답의 필수 필드/상태가 계약과 다릅니다.');
  }
  assertWriteUuidV4(raw.inspectionId);
  if (raw.inspectionId !== originId || raw.finalJudgement !== sent) {
    return fail('CONFIRM_RESPONSE_MISMATCH', '서버 판정 ID 또는 결과가 요청과 일치하지 않습니다.');
  }
  return raw as unknown as ConfirmReplyV4;
}
export function decodeRetryReplyV4(raw: unknown, originId: string): RetryReplyV4 {
  assertWriteUuidV4(originId);
  if (!object(raw) || !text(raw.inspectionId) || !text(raw.inspectionNo) ||
      !noPattern.test(String(raw.inspectionNo)) || raw.status !== 'RECEIVED' || !text(raw.retryOf)) {
    return fail('INVALID_RETRY_RESPONSE', '재검사 응답의 필수 필드/상태가 계약과 다릅니다.');
  }
  assertWriteUuidV4(raw.inspectionId);
  assertWriteUuidV4(raw.retryOf);
  if (raw.inspectionId === originId || raw.retryOf !== originId) {
    return fail('RETRY_RESPONSE_MISMATCH', '신규 검사 UUID와 원본 retryOf 연결이 올바르지 않습니다.');
  }
  return raw as unknown as RetryReplyV4;
}

/** 원본 FAILED는 변경하지 않고 새 수동 검사를 201로 돌려받습니다. */
export function decodeManualReplyV4(raw: unknown, originId: string): ManualReplyV4 {
  assertWriteUuidV4(originId);
  if (!object(raw) || !text(raw.inspectionId) || !text(raw.inspectionNo) ||
      !noPattern.test(raw.inspectionNo) || !text(raw.partCode) ||
      raw.source !== 'MANUAL' || raw.status !== 'COMPLETED' ||
      raw.displayState !== 'REVIEW_PENDING' || raw.reviewReason !== 'AI_UNAVAILABLE' ||
      !iso(raw.receivedAt) || !text(raw.manualOf) ||
      !text(raw.manualOfInspectionNo) || !noPattern.test(raw.manualOfInspectionNo) ||
      !text(raw.manualOfErrorCode)) {
    return fail('INVALID_MANUAL_RESPONSE', '수동 전환 응답의 필수 필드/상태가 계약과 다릅니다.');
  }
  assertWriteUuidV4(raw.inspectionId);
  assertWriteUuidV4(raw.manualOf);
  if (raw.inspectionId === originId || raw.manualOf !== originId) {
    return fail('MANUAL_RESPONSE_MISMATCH', '신규 검사 UUID와 원본 연결이 올바르지 않습니다.');
  }
  return raw as unknown as ManualReplyV4;
}

/** 문자열만 사용자 표시. 토큰이나 민감한 요청 본문을 포함하지 않음. 서버 traceId는 별도 전달 가능. */
export function writeErrorLabelV4(code: string): string {
  const labels: Record<string, string> = {
    ACCESS_DENIED: '접근 권한이 없습니다.', NOT_REVIEWABLE: '확인 대상 검사가 아닙니다. 최신 상태를 다시 조회해 주세요.',
    ALREADY_CONFIRMED: '이미 다른 판정으로 확정됐습니다. 최신 결과를 조회해 주세요.',
    NOT_RETRYABLE: '재검사 가능한 FAILED 상태가 아닙니다.',
    ALREADY_RETRIED: '이미 재검사 또는 수동 판정으로 전환된 검사입니다. 새 검사로 이동해 주세요.',
    NOT_MANUAL_CONVERTIBLE: 'FAILED 상태가 아니므로 수동 판정으로 전환할 수 없습니다.',
    ORIGINAL_IMAGE_MISSING: '원본 사진이 없어 수동 판정으로 전환할 수 없습니다. 재촬영 후 새 검사로 접수해 주세요.',
    REQUEST_IN_PROGRESS_LOCAL: '처리 중입니다. 중복 제출하지 마세요.',
    NETWORK_ERROR: '서버 연결을 확인한 뒤 검사 상세에서 처리 여부를 먼저 확인해 주세요.',
    NOT_LOGGED_IN: '로그인이 필요합니다.',
  };
  return labels[code] ?? '검사 처리에 실패했습니다. 최신 상태를 조회해 주세요.';
}
