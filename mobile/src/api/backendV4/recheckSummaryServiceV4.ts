/** 계약 6.11 관리자 표본 재확인 요약 GET — 읽기 전용. */
import { decodeRecheckSummaryV4, makeRecheckSummaryPathV4 } from './recheckSummaryCoreV4';
import type { RecheckSummaryQueryV4, RecheckSummaryV4 } from './recheckSummaryCoreV4';
export interface RecheckSummaryTransportV4 {
  authorizedRequest<T>(path: string, options?: { method?: 'GET' | 'POST'; body?: unknown }): Promise<T>;
}
export function createRecheckSummaryServiceV4(transport: RecheckSummaryTransportV4) {
  return {
    async get(query: RecheckSummaryQueryV4): Promise<RecheckSummaryV4> {
      const path = makeRecheckSummaryPathV4(query);
      const raw = await transport.authorizedRequest<unknown>(path, { method: 'GET' });
      return decodeRecheckSummaryV4(raw);
    },
  };
}
