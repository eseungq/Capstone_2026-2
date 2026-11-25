/** AUTO_PASS 재확인 및 관리자 '확인함' — 백엔드 계약 6.11 API 래퍼. */
import {
  decodeRecheckPageV4, decodeRecheckReplyV4, makeAcknowledgeBodyV4,
  makeRecheckListPathV4, makeRecheckPostPathV4, makeRecheckSubmitBodyV4,
} from './recheckCoreV4';
import type { RecheckFiltersV4, RecheckPageV4, RecheckReplyV4 } from './recheckCoreV4';
import type { FinalJudgementV4 } from './types';
import type { InspectionDwellV4 } from './inspectionDwellV4';

export interface RecheckTransportV4 {
  authorizedRequest<T>(path: string, options?: { method?: 'GET' | 'POST'; body?: unknown }): Promise<T>;
}
export function createRecheckServiceV4(transport: RecheckTransportV4) {
  const inFlight = new Set<string>();
  async function once<T>(key: string, fn: () => Promise<T>): Promise<T> {
    if (inFlight.has(key)) throw new Error('같은 검사에 대한 요청이 이미 진행 중입니다.');
    inFlight.add(key);
    try { return await fn(); } finally { inFlight.delete(key); }
  }
  return {
    async list(filters: RecheckFiltersV4): Promise<RecheckPageV4> {
      const raw = await transport.authorizedRequest<unknown>(makeRecheckListPathV4(filters), { method: 'GET' });
      return decodeRecheckPageV4(raw, filters.status);
    },
    async recheck(id: string, result: FinalJudgementV4, comment?: string,
      timing?: InspectionDwellV4 | null): Promise<RecheckReplyV4> {
      const path = makeRecheckPostPathV4(id, 'recheck');
      const body = makeRecheckSubmitBodyV4(result, comment, timing);
      return once('recheck:' + id, async () => {
        const raw = await transport.authorizedRequest<unknown>(path, { method: 'POST', body });
        return decodeRecheckReplyV4(raw, id, result);
      });
    },
    async acknowledge(id: string, note?: string): Promise<RecheckReplyV4> {
      const path = makeRecheckPostPathV4(id, 'acknowledge');
      const body = makeAcknowledgeBodyV4(note);
      return once('acknowledge:' + id, async () => {
        const raw = await transport.authorizedRequest<unknown>(path, { method: 'POST', body });
        const reply = decodeRecheckReplyV4(raw, id);
        if (reply.recheck.result !== 'FAIL' || !reply.recheck.acknowledgedBy ||
            !reply.recheck.acknowledgedAt) {
          throw new Error('관리자 확인함 응답의 FAIL·확인 기록이 올바르지 않습니다.');
        }
        return reply;
      });
    },
  };
}
