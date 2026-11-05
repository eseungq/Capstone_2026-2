/** 73단계 모니터링 표시값 변환: 오직 하나의 폴링 스냅샷을 사용. */
import type { MonitorSnapshotV4 } from './monitoringPollCore';

export function buildMonitoringViewModelV4(snapshot: MonitorSnapshotV4) {
  const door = snapshot.parts.find((p) => p.partCode === 'DOOR') ?? null;
  const isStale = snapshot.status === 'error' || snapshot.status === 'paused' || snapshot.status === 'stopped';
  // 실패 시 엔진이 마지막 성공 결과를 보존하므로 화면에서는 '마지막 정상 데이터'로 명시.
  const reviewCount = snapshot.queue.filter((q) => q.partCode === 'DOOR' && q.displayState === 'REVIEW_PENDING').length;
  const failedCount = snapshot.queue.filter((q) => q.partCode === 'DOOR' && q.displayState === 'FAILED').length;
  return {
    door,
    queue: snapshot.queue.filter((q) => q.partCode === 'DOOR'),
    reviewCount,
    failedCount,
    isStale,
    hasSuccessfulRead: snapshot.lastSuccessAtMs !== null,
    lastSuccessAtMs: snapshot.lastSuccessAtMs,
    status: snapshot.status,
    source: snapshot.source,
    error: snapshot.error,
    nextDelayMs: snapshot.nextDelayMs,
    successfulPolls: snapshot.successfulPolls,
  };
}
