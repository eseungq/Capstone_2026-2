/**
 * 69단계 · v4 모니터링 폴링 엔진 (순수 TypeScript / 브라우저·RN 의존성 없음)
 * 계약: GET /monitoring/parts + GET /monitoring/queue?type=ALL&size=20&cursor=...
 * 기본 5초 / 오류 재시도 최대 30초. 백그라운드·화면 이탈 시 정지.
 * 이벤트는 앱 실행 중 UI에 전달하는 로컬 알림 후보이며, Expo Push API를 호출하지 않습니다.
 */
import type { MonitoringPartV4, QueueItemV4, QueuePageV4, InspectionReadSourceV4 } from './inspectionReadCore';

export const MONITOR_POLL_INTERVAL_V4 = 5_000;
export const MONITOR_MAX_BACKOFF_V4 = 30_000;
export const MONITOR_QUEUE_PAGE_LIMIT_V4 = 20; // 20*20=400개까지만 안전하게 전체 수집

export type MonitorAlertKindV4 = 'REVIEW_REQUIRED' | 'ANALYSIS_FAILED';
export interface MonitorAlertV4 {
  kind: MonitorAlertKindV4;
  inspectionId: string; // UUID; inspectionNo 로 API를 호출하지 않음
  inspectionNo: string | null;
  partCode: string;
  receivedAt: string; // 접수 시각이지 알림 발생 시각이 아님
}
export type MonitorStatusV4 = 'stopped' | 'paused' | 'loading' | 'ready' | 'error';
export interface MonitorSnapshotV4 {
  status: MonitorStatusV4;
  source: InspectionReadSourceV4;
  parts: MonitoringPartV4[];
  queue: QueueItemV4[];
  lastSuccessAtMs: number | null;
  successfulPolls: number;
  failureStreak: number;
  nextDelayMs: number | null;
  error: string | null;
  alerts: MonitorAlertV4[]; // 마지막 성공 폴링에서 *새로* 발견한 항목만
}
export interface MonitorQueueRequestV4 { type?: 'ALL' | 'REVIEW' | 'FAILED'; partCode?: string; cursor?: string | null; size?: number; }
export interface MonitorReaderV4 {
  source: InspectionReadSourceV4;
  parts(): Promise<{source: InspectionReadSourceV4; value: MonitoringPartV4[]}>;
  queue(request?: MonitorQueueRequestV4): Promise<{source: InspectionReadSourceV4; value: QueuePageV4}>;
}
export interface MonitoringSchedulerV4 {
  setTimeout(callback: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
  now(): number;
}
const realScheduler: MonitoringSchedulerV4 = {
  setTimeout: (cb, ms) => setTimeout(cb, ms),
  clearTimeout: (id) => clearTimeout(id as ReturnType<typeof setTimeout>),
  now: () => Date.now(),
};
export interface MonitorOptionsV4 {
  reader: MonitorReaderV4;
  scheduler?: MonitoringSchedulerV4;
  onChange?: (state: MonitorSnapshotV4) => void;
  onAlert?: (alerts: MonitorAlertV4[]) => void;
  intervalMs?: number;
  maxQueuePages?: number;
}
export function monitorAlertKeyV4(item: QueueItemV4): string {
  return `${item.inspectionId}:${item.displayState}`;
}
export function monitorAlertFromQueueV4(item: QueueItemV4): MonitorAlertV4 {
  return {
    kind: item.displayState === 'FAILED' ? 'ANALYSIS_FAILED' : 'REVIEW_REQUIRED',
    inspectionId: item.inspectionId, inspectionNo: item.inspectionNo,
    partCode: item.partCode, receivedAt: item.receivedAt,
  };
}
export function monitorRetryDelayV4(failureStreak: number, intervalMs = MONITOR_POLL_INTERVAL_V4): number {
  if (!Number.isSafeInteger(failureStreak) || failureStreak < 0) throw new Error('failureStreak는 0 이상 정수여야 합니다.');
  if (!Number.isSafeInteger(intervalMs) || intervalMs < 1000) throw new Error('폴링 간격은 1초 이상이어야 합니다.');
  return Math.min(MONITOR_MAX_BACKOFF_V4, intervalMs * 2 ** Math.min(10, Math.max(0, failureStreak - 1)));
}
export function createMonitoringPollControllerV4(options: MonitorOptionsV4) {
  const scheduler = options.scheduler ?? realScheduler;
  const interval = options.intervalMs ?? MONITOR_POLL_INTERVAL_V4;
  const maxQueuePages = options.maxQueuePages ?? MONITOR_QUEUE_PAGE_LIMIT_V4;
  monitorRetryDelayV4(0, interval);
  if (!Number.isSafeInteger(maxQueuePages) || maxQueuePages < 1 || maxQueuePages > 50) {
    throw new Error('maxQueuePages는 1~50이어야 합니다.');
  }
  let state: MonitorSnapshotV4 = {
    status: 'stopped', source: options.reader.source,
    parts: [], queue: [], lastSuccessAtMs: null, successfulPolls: 0,
    failureStreak: 0, nextDelayMs: null, error: null, alerts: [],
  };
  let active = false;
  let foreground = true;
  let timer: unknown = null;
  let generation = 0;
  let fetching = false;
  let baselineTaken = false;
  const seenAlertKeys = new Set<string>(); // 이 controller 인스턴스 생존 중 중복 알림 방지
  const listeners = new Set<(next: MonitorSnapshotV4) => void>();
  const alertListeners = new Set<(alerts: MonitorAlertV4[]) => void>();
  if (options.onChange) listeners.add(options.onChange);
  if (options.onAlert) alertListeners.add(options.onAlert);

  function update(patch: Partial<MonitorSnapshotV4>) {
    state = {...state, ...patch};
    listeners.forEach((fn) => fn({...state, parts:[...state.parts], queue:[...state.queue], alerts:[...state.alerts]}));
  }
  function clearScheduled() {
    if (timer !== null) { scheduler.clearTimeout(timer); timer = null; }
  }
  function schedule(delayMs: number) {
    if (!active || !foreground || fetching || timer !== null) return;
    timer = scheduler.setTimeout(() => {
      timer = null;
      void poll();
    }, delayMs);
    update({nextDelayMs: delayMs});
  }
  async function readFullQueue(): Promise<QueueItemV4[]> {
    let cursor: string | null = null;
    const cursors = new Set<string>();
    const ids = new Set<string>();
    const all: QueueItemV4[] = [];
    for (let page = 0; page < maxQueuePages; page++) {
      const response = await options.reader.queue({type:'ALL', size:20, ...(cursor ? {cursor} : {})});
      if (response.source !== options.reader.source) throw new Error('queue 데이터 출처 불일치');
      const value = response.value;
      if (!value || !Array.isArray(value.items) || (value.nextCursor !== null && typeof value.nextCursor !== 'string')) {
        throw new Error('queue 응답 형태 오류');
      }
      for (const item of value.items) {
        if (item.displayState !== 'FAILED' && item.displayState !== 'REVIEW_PENDING') throw new Error('queue 상태 오류');
        if (ids.has(item.inspectionId)) throw new Error('queue 페이지에 중복 검사 ID가 있습니다.');
        ids.add(item.inspectionId); all.push(item);
      }
      if (value.nextCursor === null) return all;
      if (!value.nextCursor || cursors.has(value.nextCursor)) throw new Error('queue 커서 반복/공백 오류');
      cursors.add(value.nextCursor); cursor = value.nextCursor;
    }
    throw new Error('확인 필요 목록이 페이지 상한에 도달했습니다. 누락 방지를 위해 갱신 실패로 처리합니다.');
  }
  async function poll() {
    if (!active || !foreground || fetching) return;
    fetching = true;
    const myGeneration = generation;
    update({status:'loading', error:null, nextDelayMs:null, alerts:[]});
    let nextDelay = interval;
    try {
      const [partsResult, queue] = await Promise.all([options.reader.parts(), readFullQueue()]);
      if (myGeneration !== generation || !active || !foreground) return;
      if (partsResult.source !== options.reader.source || !Array.isArray(partsResult.value)) {
        throw new Error('parts 데이터 출처/형태 오류');
      }
      const alerts: MonitorAlertV4[] = [];
      for (const item of queue) {
        const key = monitorAlertKeyV4(item);
        if (baselineTaken && !seenAlertKeys.has(key)) alerts.push(monitorAlertFromQueueV4(item));
        seenAlertKeys.add(key);
      }
      baselineTaken = true; // 첫 성공 응답에 이미 존재한 과거 대기 항목은 새 알림을 띄우지 않음
      update({
        status:'ready', parts:partsResult.value, queue, successfulPolls:state.successfulPolls + 1,
        lastSuccessAtMs:scheduler.now(), failureStreak:0, nextDelayMs:null, error:null, alerts,
      });
      if (alerts.length) alertListeners.forEach((fn) => fn(alerts));
    } catch (error) {
      if (myGeneration !== generation || !active || !foreground) return;
      const failures = state.failureStreak + 1;
      nextDelay = monitorRetryDelayV4(failures, interval);
      // 마지막 정상 데이터 보존: 오류가 났다는 이유로 정상/불량 건수나 대기 건수를 0으로 만들지 않음
      update({status:'error', error:error instanceof Error ? error.message : '모니터링 조회 오류', failureStreak:failures, alerts:[]});
    } finally {
      fetching = false;
      if (active && foreground) schedule(myGeneration === generation ? nextDelay : 0);
    }
  }
  function start() {
    if (active) return;
    active = true; generation++;
    if (foreground) schedule(0);
    else update({status:'paused', nextDelayMs:null, alerts:[]});
  }
  function stop() {
    active = false; generation++; clearScheduled();
    update({status:'stopped', nextDelayMs:null, alerts:[]});
    // 진행 중인 HTTP 요청은 버리지 못하지만, 응답 결과는 generation으로 무시됨.
  }
  function setForeground(next: boolean) {
    if (foreground === next) return;
    foreground = next;
    generation++; clearScheduled();
    if (active) {
      if (foreground) schedule(0); // 포그라운드 복귀 시 즉시 조회
      else update({status:'paused', nextDelayMs:null, alerts:[]});
    }
  }
  function subscribe(listener: (next: MonitorSnapshotV4) => void) {
    listeners.add(listener); listener(getSnapshot());
    return () => { listeners.delete(listener); };
  }
  function subscribeAlerts(listener: (alerts: MonitorAlertV4[]) => void) {
    alertListeners.add(listener);
    return () => { alertListeners.delete(listener); };
  }
  function getSnapshot(): MonitorSnapshotV4 {
    return {...state, parts:[...state.parts], queue:[...state.queue], alerts:[...state.alerts]};
  }
  return {start, stop, setForeground, subscribe, subscribeAlerts, getSnapshot};
}
