/** 실제 판정이나 접수가 아닌 API v4 계약 예제. 서버 및 기존 Mock 저장소와 별개. */
import type { ConfirmReplyV4, RetryReplyV4, WriteInspectionContextV4 } from './inspectionWriteCore';

export const writeExampleIdsV4 = {
  pending: '8f3c1e2a-1234-4123-8123-111111111111',
  confirmed: '8f3c1e2a-1234-4123-8123-222222222222',
  autoPass: '8f3c1e2a-1234-4123-8123-333333333333',
  failed: '8f3c1e2a-1234-4123-8123-444444444444',
  analyzing: '8f3c1e2a-1234-4123-8123-555555555555',
  retried: '8f3c1e2a-1234-4123-8123-999999999999',
} as const;
export const writeExampleContextV4: Record<'pending'|'confirmed'|'autoPass'|'failed'|'analyzing', WriteInspectionContextV4> = {
  pending: { inspectionId: writeExampleIdsV4.pending, displayState: 'REVIEW_PENDING', finalJudgement: null },
  confirmed: { inspectionId: writeExampleIdsV4.confirmed, displayState: 'REVIEW_DONE', finalJudgement: 'FAIL' },
  autoPass: { inspectionId: writeExampleIdsV4.autoPass, displayState: 'AUTO_PASS', finalJudgement: 'PASS' },
  failed: { inspectionId: writeExampleIdsV4.failed, displayState: 'FAILED', finalJudgement: null },
  analyzing: { inspectionId: writeExampleIdsV4.analyzing, displayState: 'ANALYZING', finalJudgement: null },
};
export const writeExampleConfirmReplyV4: ConfirmReplyV4 = {
  inspectionId: writeExampleIdsV4.pending, inspectionNo: 'INS-000006',
  predictedQuality: 'DEFECT', recommendedAction: 'REVIEW', finalJudgement: 'FAIL',
  judgedBy: 'WORKER', confirmedBy: 'mock-worker', confirmedAt: '2026-10-28T11:00:00+09:00',
};
export const writeExampleRetryReplyV4: RetryReplyV4 = {
  inspectionId: writeExampleIdsV4.retried, inspectionNo: 'INS-999001', status: 'RECEIVED', retryOf: writeExampleIdsV4.failed,
};
