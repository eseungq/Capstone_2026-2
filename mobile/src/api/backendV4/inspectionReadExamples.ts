/** 모든 값은 계약 기반 가상 표본. 실제 검사·자동통과 결과가 아닙니다. */
import { sampleV4Responses } from './examples';
import type { InspectionDetailV4 } from './types';
import type { HistoryRowV4, MonitoringPartV4, QueueItemV4 } from './inspectionReadCore';

export const contractDetailExamplesV4: InspectionDetailV4[] = sampleV4Responses.map((x) => x.response.data);
export const contractHistoryExamplesV4: HistoryRowV4[] = contractDetailExamplesV4.map((x) => ({
  inspectionId: x.inspectionId, inspectionNo: x.inspectionNo, partCode: x.partCode,
  displayState: x.displayState, receivedAt: x.receivedAt,
  predictedQuality: x.ai?.predictedQuality ?? null,
  reviewReason: x.policy?.reviewReason ?? null,
  errorCode: x.error?.code ?? null,
  thumbnailUrl: null, finalJudgement: x.judgement?.finalJudgement ?? null,
  judgedBy: x.judgement?.judgedBy ?? null, confirmedAt: x.judgement?.confirmedAt ?? null,
}));
export const contractQueueExamplesV4: QueueItemV4[] = contractHistoryExamplesV4
  .filter((x) => x.displayState === 'REVIEW_PENDING' || x.displayState === 'FAILED')
  .map(({ inspectionId, inspectionNo, partCode, displayState, predictedQuality, reviewReason, errorCode, receivedAt, thumbnailUrl }) => ({
    inspectionId, inspectionNo, partCode, displayState: displayState as 'REVIEW_PENDING' | 'FAILED',
    predictedQuality, reviewReason, errorCode, receivedAt, thumbnailUrl,
  }));
export const contractPartsExamplesV4: MonitoringPartV4[] = [
  { partCode: 'DOOR', partName: '도어', modelAvailable: true, policyActive: false,
    lastReceivedAt: contractDetailExamplesV4[0].receivedAt,
    pendingReviewCount: 1, failedCount: 1,
    recent: contractHistoryExamplesV4.map(({ inspectionId, inspectionNo, displayState, receivedAt }) => ({
      inspectionId, inspectionNo, displayState, receivedAt, thumbnailUrl: null,
    })),
  },
];
