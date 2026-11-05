/**
 * 65단계: 판정/재검사 서비스. 기존 src/data/mockInspections.ts에는 접근하지 않음.
 * contract-example 모드는 서비스 인스턴스 내 가상 상태만 변경(앱 재실행 시 사라짐).
 * API 모드는 createAuthV4().authorizedRequest 와 호환. 외부 연결은 명시적 모드일 때만.
 */
import {
  decodeConfirmReplyV4, decodeRetryReplyV4, ensureConfirmAllowedV4, ensureRetryAllowedV4,
  makeConfirmBodyV4, makeWritePathV4, WriteV4ValidationError,
} from './inspectionWriteCore';
import type {
  ConfirmInputV4, ConfirmReplyV4, RetryReplyV4, WriteInspectionContextV4, WriteRoleV4, WriteSourceV4,
} from './inspectionWriteCore';
import { writeExampleConfirmReplyV4, writeExampleContextV4, writeExampleRetryReplyV4, writeExampleIdsV4 } from './inspectionWriteExamples';

export interface InspectionWriteTransportV4 {
  /** 60단계 authCore.authorizedRequest와 호환. {data} 해제된 응답 객체를 반환. */
  authorizedRequest<T>(path: string, options?: { method?: 'GET' | 'POST'; body?: unknown }): Promise<T>;
}
export type InspectionWriteConfigV4 =
  | { mode: 'contract-example'; role: WriteRoleV4 }
  | { mode: 'api'; role: WriteRoleV4; transport: InspectionWriteTransportV4 };
export interface WriteResultV4<T> { source: WriteSourceV4; value: T; }

export function createInspectionWriteServiceV4(config: InspectionWriteConfigV4) {
  const source: WriteSourceV4 = config.mode === 'api' ? 'SERVER' : 'CONTRACT_EXAMPLE';
  const inFlight = new Set<string>(); // 버튼 연타 중복 POST 방지 (백엔드 검증 대체 안 함)
  const demo = new Map<string, WriteInspectionContextV4>();
  if (config.mode === 'contract-example') {
    for (const value of Object.values(writeExampleContextV4)) demo.set(value.inspectionId, {...value});
  }

  function viewForDemo(origin: WriteInspectionContextV4): WriteInspectionContextV4 {
    const current = demo.get(origin.inspectionId);
    if (!current) throw new WriteV4ValidationError('DEMO_NOT_FOUND', '예시 레코드가 없습니다.');
    return current;
  }

  async function once<T>(key: string, fn: () => Promise<T>): Promise<T> {
    if (inFlight.has(key)) throw new WriteV4ValidationError('REQUEST_IN_PROGRESS_LOCAL', '동일한 검사 요청이 진행 중입니다.');
    inFlight.add(key);
    try { return await fn(); } finally { inFlight.delete(key); }
  }

  async function confirm(origin: WriteInspectionContextV4, input: ConfirmInputV4): Promise<WriteResultV4<ConfirmReplyV4>> {
    const body = makeConfirmBodyV4(input);
    const path = makeWritePathV4(origin.inspectionId, 'confirm');
    return once(`confirm:${origin.inspectionId}`, async () => {
      const current = config.mode === 'contract-example' ? viewForDemo(origin) : origin;
      ensureConfirmAllowedV4(config.role, current, body.finalJudgement);
      if (config.mode === 'contract-example') {
        const raw: ConfirmReplyV4 = {
          ...writeExampleConfirmReplyV4, inspectionId: origin.inspectionId,
          inspectionNo: origin.inspectionId === writeExampleIdsV4.confirmed ? 'INS-000005' : 'INS-000006',
          finalJudgement: body.finalJudgement,
        };
        const value = decodeConfirmReplyV4(raw, origin.inspectionId, body.finalJudgement);
        demo.set(origin.inspectionId, { ...current, displayState: 'REVIEW_DONE', finalJudgement: body.finalJudgement });
        return {source, value};
      }
      // 실서버가 판단의 최종 권위: 오래된 목록 상태와 경쟁 조건은 403/409 반환.
      const raw = await config.transport.authorizedRequest<unknown>(path, { method: 'POST', body });
      return { source, value: decodeConfirmReplyV4(raw, origin.inspectionId, body.finalJudgement) };
    });
  }

  async function retry(origin: WriteInspectionContextV4): Promise<WriteResultV4<RetryReplyV4>> {
    const path = makeWritePathV4(origin.inspectionId, 'retry');
    return once(`retry:${origin.inspectionId}`, async () => {
      const current = config.mode === 'contract-example' ? viewForDemo(origin) : origin;
      ensureRetryAllowedV4(config.role, current);
      if (config.mode === 'contract-example') {
        const raw: RetryReplyV4 = { ...writeExampleRetryReplyV4, retryOf: origin.inspectionId };
        const value = decodeRetryReplyV4(raw, origin.inspectionId);
        demo.set(origin.inspectionId, { ...current, retriedBy: value.inspectionId });
        return {source, value};
      }
      // 원본 사진 재업로드 없음, POST body 미전달. 재검사 서버 응답은 202 + {data}.
      const raw = await config.transport.authorizedRequest<unknown>(path, { method: 'POST' });
      return { source, value: decodeRetryReplyV4(raw, origin.inspectionId) };
    });
  }
  return { source, confirm, retry };
}
