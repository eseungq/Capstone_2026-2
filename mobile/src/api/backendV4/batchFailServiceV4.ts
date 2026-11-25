/** 계약 6.7.1. 앱에서 버튼을 누른 작업자 요청만 전송하며 중복 탭을 차단합니다. */
import type { BackendRole } from './authCore';
import type { BatchFailRequestV4, BatchFailReplyV4 } from './batchFailCoreV4';
import { prepareBatchFailBodyV4, decodeBatchFailReplyV4 } from './batchFailCoreV4';
import type { BatchFailSelectionV4 } from './batchFailCoreV4';
import { WriteV4ValidationError } from './inspectionWriteCore';

export interface BatchFailTransportV4 {
  authorizedRequest<T>(path: string, options?: {method?: 'GET'|'POST'; body?: unknown}): Promise<T>;
}
export function createBatchFailServiceV4(transport: BatchFailTransportV4) {
  let inFlight = false;
  async function submit(role: BackendRole | null, selected: readonly BatchFailSelectionV4[], comment: string):
    Promise<{request: BatchFailRequestV4; value: BatchFailReplyV4}> {
    const request = prepareBatchFailBodyV4(role, selected, comment);
    if (inFlight) throw new WriteV4ValidationError('REQUEST_IN_PROGRESS_LOCAL', '일괄 판정 제출이 이미 진행 중입니다.');
    inFlight = true;
    try {
      const raw = await transport.authorizedRequest<unknown>('/inspections/confirm-batch', {
        method: 'POST', body: request,
      });
      return { request, value: decodeBatchFailReplyV4(raw, request) };
    } finally { inFlight = false; }
  }
  return {submit};
}
