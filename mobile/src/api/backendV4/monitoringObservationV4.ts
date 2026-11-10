/**
 * 모니터링 폴링 성공 시점에 앱이 관측한 검사 상태와 건수 변화를 기록합니다.
 * receivedAt(서버)과 observedAtMs(기기)를 구분합니다.
 * 이 값은 접수→앱 관측 소요 시간이며 AI 처리 시간/서버 완료→앱 반영 지연이 아닙니다.
 * 첫 성공 폴링 이전부터 존재하던 검사는 측정에서 제외합니다.
 */
import type { MonitorSnapshotV4 } from './monitoringPollCore';
import type { DisplayStateV4 } from './types';

export interface InspectionObservationV4 {
  inspectionId: string;
  inspectionNo: string | null;
  partCode: string;
  receivedAt: string;
  displayState: DisplayStateV4;
  firstObservedAtMs: number;
  stateObservedAtMs: number;
  firstSeenAfterBaseline: boolean;
}

export interface InspectionDetectionV4 {
  inspectionId: string;
  inspectionNo: string | null;
  partCode: string;
  receivedAt: string;
  observedAtMs: number;
  displayState: DisplayStateV4;
  kind: 'first-seen' | 'state-changed';
  previousState: DisplayStateV4 | null;
}

export interface ReviewCountChangeV4 {
  previous: number;
  current: number;
  observedAtMs: number;
  // 해당 폴링에서 처음 확인된 REVIEW_PENDING 검사.
  // 감소나 동시 변동에는 이 값이 null일 수 있으므로 원인이라고 단정하지 않습니다.
  newlyDetectedReviewId: string | null;
  newlyDetectedReviewNo: string | null;
  newlyDetectedReceivedAt: string | null;
}

export interface MonitoringObservationStateV4 {
  lastSuccessfulPolls: number;
  observations: InspectionObservationV4[];
  reviewCount: number | null;
  latestDetection: InspectionDetectionV4 | null;
  latestStateChange: InspectionDetectionV4 | null;
  latestReviewCountChange: ReviewCountChangeV4 | null;
}

export function createMonitoringObservationStateV4(): MonitoringObservationStateV4 {
  return {
    lastSuccessfulPolls: 0,
    observations: [],
    reviewCount: null,
    latestDetection: null,
    latestStateChange: null,
    latestReviewCountChange: null,
  };
}

export function elapsedFromReceiptV4(receivedAt: string, observedAtMs: number): number | null {
  const receivedAtMs = Date.parse(receivedAt);
  if (!Number.isFinite(receivedAtMs) || !Number.isFinite(observedAtMs)) return null;
  const elapsed = observedAtMs - receivedAtMs;
  // 음수는 기기/서버 시계 차이 또는 시각 데이터 오류로 취급합니다.
  return elapsed >= 0 ? elapsed : null;
}

export function advanceMonitoringObservationV4(
  previous: MonitoringObservationStateV4,
  snapshot: MonitorSnapshotV4,
): MonitoringObservationStateV4 {
  if (snapshot.status !== 'ready' ||
      snapshot.lastSuccessAtMs === null ||
      snapshot.successfulPolls <= previous.lastSuccessfulPolls) return previous;

  const at = snapshot.lastSuccessAtMs;
  const baseline = previous.lastSuccessfulPolls === 0;
  const map = new Map<string, InspectionObservationV4>(
    previous.observations.map((item) => [item.inspectionId, item] as const),
  );
  // 최근 검사(분석 중/확정 완료 포함)와 대기열(오래된 REVIEW/FAILED 포함)을 함께 관측합니다.
  const current = new Map<string, {
    inspectionId: string;
    inspectionNo: string | null;
    partCode: string;
    receivedAt: string;
    displayState: DisplayStateV4;
  }>();
  for (const part of snapshot.parts) {
    for (const item of part.recent) {
      current.set(item.inspectionId, {
        inspectionId: item.inspectionId,
        inspectionNo: item.inspectionNo,
        partCode: part.partCode,
        receivedAt: item.receivedAt,
        displayState: item.displayState,
      });
    }
  }
  // 같은 폴링의 /queue 응답이 /parts와 순간적으로 다를 수 있습니다.
  // 대기 상태에 대해서는 현재 화면 건수의 출처인 /queue 항목을 우선합니다.
  for (const item of snapshot.queue) {
    current.set(item.inspectionId, {
      inspectionId: item.inspectionId,
      inspectionNo: item.inspectionNo ?? current.get(item.inspectionId)?.inspectionNo ?? null,
      partCode: item.partCode,
      receivedAt: item.receivedAt,
      displayState: item.displayState,
    });
  }

  let latestDetection = previous.latestDetection;
  let latestStateChange = previous.latestStateChange;
  const newPending: Array<{ inspectionId: string; inspectionNo: string | null; receivedAt: string }> = [];

  for (const item of current.values()) {
    const existing = map.get(item.inspectionId);
    if (!existing) {
      map.set(item.inspectionId, {
        ...item,
        firstObservedAtMs: at,
        stateObservedAtMs: at,
        firstSeenAfterBaseline: !baseline,
      });
      if (!baseline) {
        const event: InspectionDetectionV4 = {
          ...item,
          observedAtMs: at,
          kind: 'first-seen',
          previousState: null,
        };
        // 마지막 이벤트 하나를 남기되 첫 접수 기준으로 가장 최근 항목을 선택합니다.
        if (!latestDetection || latestDetection.observedAtMs !== at ||
            Date.parse(item.receivedAt) > Date.parse(latestDetection.receivedAt)) {
          latestDetection = event;
        }
        if (item.displayState === 'REVIEW_PENDING' && item.partCode === 'DOOR') {
          newPending.push(item);
        }
      }
    } else if (existing.displayState !== item.displayState) {
      map.set(item.inspectionId, {
        ...existing,
        ...item,
        stateObservedAtMs: at,
      });
      if (!baseline) {
        const event: InspectionDetectionV4 = {
          ...item,
          observedAtMs: at,
          kind: 'state-changed',
          previousState: existing.displayState,
        };
        latestStateChange = event;
        if (item.displayState === 'REVIEW_PENDING' && item.partCode === 'DOOR') {
          newPending.push(item);
        }
      }
    } else {
      // 번호는 /parts에 없을 수 있으므로 기존의 검사번호를 보존합니다.
      map.set(item.inspectionId, {
        ...existing,
        inspectionNo: item.inspectionNo ?? existing.inspectionNo,
      });
    }
  }

  const reviewCount = snapshot.queue.filter(
    (item) => item.partCode === 'DOOR' && item.displayState === 'REVIEW_PENDING',
  ).length;
  let latestReviewCountChange = previous.latestReviewCountChange;
  if (!baseline && previous.reviewCount !== null && previous.reviewCount !== reviewCount) {
    const newest = newPending.sort(
      (a, b) => Date.parse(b.receivedAt) - Date.parse(a.receivedAt),
    )[0] ?? null;
    latestReviewCountChange = {
      previous: previous.reviewCount,
      current: reviewCount,
      observedAtMs: at,
      newlyDetectedReviewId: newest?.inspectionId ?? null,
      newlyDetectedReviewNo: newest?.inspectionNo ?? null,
      newlyDetectedReceivedAt: newest?.receivedAt ?? null,
    };
  }

  // 기기 메모리 무한 증가 방지. 최근 관측 항목 위주 최대 500건 유지.
  const observations = [...map.values()]
    .sort((a, b) => b.firstObservedAtMs - a.firstObservedAtMs)
    .slice(0, 500);

  return {
    lastSuccessfulPolls: snapshot.successfulPolls,
    observations,
    reviewCount,
    latestDetection,
    latestStateChange,
    latestReviewCountChange,
  };
}
