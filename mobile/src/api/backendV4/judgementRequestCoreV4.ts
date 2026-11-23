/**
 * 계약 v4 §6.12 판정 확인 요청·정정.
 * 최초 시스템 판정은 변경하지 않고 요청과 별도 정정 이력만 표시합니다.
 */
import type { FinalJudgementV4, JudgedByV4 } from './types';
import type { BackendRole } from './authCore';
import { assertWriteUuidV4, WriteV4ValidationError } from './inspectionWriteCore';

export type JudgementRequestStatusV4 = 'OPEN' | 'KEPT' | 'CORRECTED';
export type JudgementResolveDecisionV4 = 'KEEP' | 'CORRECT';
export type JudgementQueueStatusV4 = 'OPEN' | 'RESOLVED' | 'ALL';
export interface JudgementCorrectionV4 {
  requestId: string;
  correctedJudgement: FinalJudgementV4;
  correctedBy: string;
  correctedAt: string;
  note: string;
}
export interface JudgementRequestV4 {
  requestId: string;
  inspectionId: string;
  inspectionNo: string;
  partCode: string;
  originalJudgement: FinalJudgementV4;
  originalJudgedBy: 'SYSTEM';
  currentJudgement: FinalJudgementV4;
  claimedJudgement: FinalJudgementV4;
  area: string | null;
  reason: string;
  requestedBy: string;
  requestedAt: string;
  status: JudgementRequestStatusV4;
  resolvedBy: string | null;
  resolvedAt: string | null;
  resolveNote: string | null;
}
export interface JudgementResolveResultV4 {
  request: JudgementRequestV4;
  correction: JudgementCorrectionV4 | null;
}
export interface JudgementQueuePageV4 {
  items: JudgementRequestV4[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
}
export interface JudgementRequestBodyV4 {
  claimedJudgement: FinalJudgementV4;
  area?: string;
  reason: string;
}
export interface JudgementResolveBodyV4 { decision: JudgementResolveDecisionV4; note: string; }
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const NO = /^INS-\d{6,}$/;
function obj(x: unknown): x is Record<string, unknown> {
  return typeof x === 'object' && x !== null && !Array.isArray(x);
}
function nonempty(x: unknown): x is string { return typeof x === 'string' && x.trim().length > 0; }
function iso(x: unknown): x is string {
  return nonempty(x) && /(Z|[+-]\d{2}:\d{2})$/.test(x) && Number.isFinite(Date.parse(x));
}
function judgement(x: unknown): x is FinalJudgementV4 { return x === 'PASS' || x === 'FAIL'; }
function error(msg: string): never { throw new WriteV4ValidationError('INVALID_JUDGEMENT_REQUEST', msg); }
function longEnough(x: string, min: number, max: number): boolean {
  const n=[...x.trim()].length;return n>=min && n<=max;
}
export function currentJudgementV4(
  original: FinalJudgementV4 | null,
  correction: JudgementCorrectionV4 | null,
): FinalJudgementV4 | null { return correction?.correctedJudgement ?? original; }

export function makeJudgementRequestBodyV4(
  role: BackendRole | null,
  inspection: {inspectionId: string; judgedBy: JudgedByV4 | null;
    finalJudgement: FinalJudgementV4 | null; correction?: JudgementCorrectionV4 | null;
    judgementRequests?: readonly JudgementRequestV4[]},
  claimed: FinalJudgementV4,
  area: string,
  reason: string,
): JudgementRequestBodyV4 {
  assertWriteUuidV4(inspection.inspectionId);
  if (role !== 'WORKER') return error('판정 확인 요청은 WORKER만 작성할 수 있습니다.');
  if (inspection.judgedBy !== 'SYSTEM' || !judgement(inspection.finalJudgement)) {
    return error('최초 시스템 판정이 있는 검사만 확인 요청할 수 있습니다.');
  }
  const current=currentJudgementV4(inspection.finalJudgement,inspection.correction ?? null);
  if (!judgement(claimed) || claimed === current) return error('현재 판정과 다른 PASS/FAIL을 선택해야 합니다.');
  if (inspection.judgementRequests?.some(x=>x.status==='OPEN')) {
    return error('이 검사는 이미 처리 대기 중인 확인 요청이 있습니다. 상세를 새로 조회해 주세요.');
  }
  const trimmedReason=reason.trim(),trimmedArea=area.trim();
  if (!longEnough(trimmedReason,1,500)) return error('요청 근거는 1~500자여야 합니다.');
  if (trimmedArea && !longEnough(trimmedArea,1,100)) return error('부위는 최대 100자여야 합니다.');
  return {claimedJudgement:claimed,...(trimmedArea?{area:trimmedArea}:{}),reason:trimmedReason};
}
export function makeJudgementResolveBodyV4(
  role: BackendRole | null, request: JudgementRequestV4,
  decision: JudgementResolveDecisionV4, note: string,
): JudgementResolveBodyV4 {
  assertWriteUuidV4(request.requestId);
  if (role !== 'ADMIN') return error('판정 요청 처리는 ADMIN만 가능합니다.');
  if (request.status !== 'OPEN') return error('이미 처리된 요청입니다. 최신 결과를 확인하세요.');
  if (decision !== 'KEEP' && decision !== 'CORRECT') return error('처리 선택은 유지 또는 정정이어야 합니다.');
  const trimmed=note.trim();
  if (!longEnough(trimmed,1,500)) return error('처리 근거는 1~500자여야 합니다.');
  return {decision,note:trimmed};
}
export function decodeJudgementCorrectionV4(raw: unknown): JudgementCorrectionV4 | null {
  if (raw == null) return null;
  if (!obj(raw) || !nonempty(raw.requestId) || !UUID.test(raw.requestId) ||
    !judgement(raw.correctedJudgement) || !nonempty(raw.correctedBy) ||
    !iso(raw.correctedAt) || !nonempty(raw.note) || !longEnough(raw.note,1,500)) {
    return error('검사 정정(correction) 응답 형식이 올바르지 않습니다.');
  }
  return {
    requestId: raw.requestId,correctedJudgement:raw.correctedJudgement,
    correctedBy:raw.correctedBy,correctedAt:raw.correctedAt,note:raw.note,
  };
}
export function decodeJudgementRequestV4(raw: unknown): JudgementRequestV4 {
  if (!obj(raw) || !nonempty(raw.requestId) || !UUID.test(raw.requestId) ||
    !nonempty(raw.inspectionId) || !UUID.test(raw.inspectionId) ||
    !nonempty(raw.inspectionNo) || !NO.test(raw.inspectionNo) || !nonempty(raw.partCode) ||
    !judgement(raw.originalJudgement) || raw.originalJudgedBy !== 'SYSTEM' ||
    !judgement(raw.currentJudgement) || !judgement(raw.claimedJudgement) ||
    raw.currentJudgement === raw.claimedJudgement ||
    (raw.area != null && (typeof raw.area !== 'string' || !longEnough(raw.area,1,100))) ||
    !nonempty(raw.reason) || !longEnough(raw.reason,1,500) || !nonempty(raw.requestedBy) ||
    !iso(raw.requestedAt) ||
    (raw.status !== 'OPEN' && raw.status !== 'KEPT' && raw.status !== 'CORRECTED')) {
    return error('판정 확인 요청 응답 값이 유효하지 않습니다.');
  }
  const open=raw.status==='OPEN';
  if (open ? raw.resolvedBy != null || raw.resolvedAt != null || raw.resolveNote != null
    : !nonempty(raw.resolvedBy) || !iso(raw.resolvedAt) ||
      !nonempty(raw.resolveNote) || !longEnough(raw.resolveNote,1,500)) {
    return error('판정 요청 처리 상태 및 처리자 정보가 일치하지 않습니다.');
  }
  return {
    requestId:raw.requestId,inspectionId:raw.inspectionId,inspectionNo:raw.inspectionNo,
    partCode:raw.partCode,originalJudgement:raw.originalJudgement,
    originalJudgedBy:'SYSTEM',currentJudgement:raw.currentJudgement,
    claimedJudgement:raw.claimedJudgement,area:(raw.area??null) as string|null,
    reason:raw.reason,requestedBy:raw.requestedBy,requestedAt:raw.requestedAt,
    status:raw.status,resolvedBy:(raw.resolvedBy??null) as string|null,
    resolvedAt:(raw.resolvedAt??null) as string|null,
    resolveNote:(raw.resolveNote??null) as string|null,
  };
}
export function decodeJudgementRequestListV4(raw: unknown): JudgementRequestV4[] {
  if (raw == null) return [];
  if (!Array.isArray(raw)) return error('판정 확인 요청 목록은 배열이어야 합니다.');
  const items=raw.map(decodeJudgementRequestV4);
  const ids=new Set(items.map(x=>x.requestId));
  if (ids.size!==items.length) return error('동일한 요청 ID가 중복으로 포함됐습니다.');
  return items;
}
export function decodeJudgementResolveV4(raw: unknown, id: string): JudgementResolveResultV4 {
  assertWriteUuidV4(id);
  if (!obj(raw)) return error('관리자 처리 응답 형식이 유효하지 않습니다.');
  const request=decodeJudgementRequestV4(raw.request);
  if (request.requestId!==id || request.status==='OPEN') return error('요청 처리 결과가 현재 처리 대상과 다릅니다.');
  const correction=decodeJudgementCorrectionV4(raw.correction);
  if (request.status==='CORRECTED' &&
      (!correction || correction.requestId!==request.requestId ||
       correction.correctedJudgement!==request.claimedJudgement)) {
    return error('정정 결과와 요청 결과가 서로 다릅니다.');
  }
  return {request,correction};
}
export function decodeJudgementQueuePageV4(raw: unknown, requestedPage: number): JudgementQueuePageV4 {
  if (!obj(raw) || !Array.isArray(raw.items) || !Number.isSafeInteger(raw.page) ||
    !Number.isSafeInteger(raw.size) || !Number.isSafeInteger(raw.totalElements) ||
    !Number.isSafeInteger(raw.totalPages) ||
    (raw.page as number)<0 || (raw.size as number)<1 || (raw.size as number)>100 ||
    (raw.totalElements as number)<0 || (raw.totalPages as number)<0 ||
    raw.page!==requestedPage) {
    return error('관리자 요청 목록 페이지 응답 형식이 올바르지 않습니다.');
  }
  const items=decodeJudgementRequestListV4(raw.items);
  return {items,page:raw.page as number,size:raw.size as number,
    totalElements:raw.totalElements as number,totalPages:raw.totalPages as number};
}
export function judgementRequestStatusLabelV4(status: JudgementRequestStatusV4): string {
  return status==='OPEN'?'확인 대기':status==='KEPT'?'최초 판정 유지':'정정 완료';
}
