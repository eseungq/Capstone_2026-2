/**
 * AUTO_FAIL 앱 내부 알림 전용 폴링.
 * 계약 6.6/8.2: GET /inspections?displayState=AUTO_FAIL, 5초, 읽기 전용.
 * 백그라운드·종료 시 동작하지 않으며 Expo/APNs 푸시를 사용하지 않습니다.
 * REVIEW/FAILED 큐 엔진과 독립: AUTO_FAIL은 /monitoring/queue에 나오지 않습니다.
 */
import type { HistoryPageV4, HistoryRowV4 } from './inspectionReadCore';

export const AUTO_FAIL_POLL_MS_V4 = 5_000;
export const AUTO_FAIL_PAGE_SIZE_V4 = 100;

export interface AutoFailInAppAlertV4 {
  kind: 'AUTO_FAILED';
  inspectionId: string;
  inspectionNo: string | null;
  partCode: string;
  receivedAt: string; // 접수 시각. 알림 발송 시각으로 표현하지 않습니다.
}
export interface AutoFailHistoryReaderV4 {
  history(request: { page: number; size: number; displayState: 'AUTO_FAIL' }): Promise<{
    source: string;
    value: HistoryPageV4;
  }>;
}
export interface AutoFailAlertSchedulerV4 {
  setTimeout(cb: () => void, delayMs: number): unknown;
  clearTimeout(handle: unknown): void;
}
export interface AutoFailAlertOptionsV4 {
  reader: AutoFailHistoryReaderV4;
  onAlert: (alerts: AutoFailInAppAlertV4[]) => void;
  scheduler?: AutoFailAlertSchedulerV4;
  intervalMs?: number;
}
const realScheduler: AutoFailAlertSchedulerV4 = {
  setTimeout: (cb, ms) => setTimeout(cb, ms),
  clearTimeout: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

/**
 * 최초 정상 조회는 기존 기록을 기준선으로 삼아 알리지 않습니다.
 * 이후 한 번 감지한 inspectionId는 화면 전환·앱 재활성화·폴링 실패에도 중복 알리지 않습니다.
 * 관찰 대상은 서버가 접수 최신순으로 반환하는 첫 100건입니다.
 * 5초 안에 100건 넘게 발생하는 환경은 별도 커서/이벤트 API가 필요합니다.
 */
export function createAutoFailInAppControllerV4(options: AutoFailAlertOptionsV4) {
  const scheduler = options.scheduler ?? realScheduler;
  const intervalMs = options.intervalMs ?? AUTO_FAIL_POLL_MS_V4;
  if (!Number.isSafeInteger(intervalMs) || intervalMs < 1_000) {
    throw new Error('AUTO_FAIL 폴링 간격은 1초 이상이어야 합니다.');
  }
  let running = false;
  let foreground = true;
  let timer: unknown = null;
  let generation = 0;
  let fetching = false;
  let initialized = false;
  const seenIds = new Set<string>();

  function clearTimer() {
    if (timer !== null) { scheduler.clearTimeout(timer); timer = null; }
  }
  function schedule(ms: number) {
    if (!running || !foreground || fetching || timer !== null) return;
    timer = scheduler.setTimeout(() => { timer = null; void poll(); }, ms);
  }
  async function poll() {
    if (!running || !foreground || fetching) return;
    const myGeneration = generation;
    fetching = true;
    try {
      const result = await options.reader.history({
        page: 0, size: AUTO_FAIL_PAGE_SIZE_V4, displayState: 'AUTO_FAIL',
      });
      if (myGeneration !== generation || !running || !foreground) return;
      if (result.source !== 'SERVER' || !result.value || !Array.isArray(result.value.items)) {
        throw new Error('AUTO_FAIL 이력 응답 출처/형식 오류');
      }
      // 응답 전체를 먼저 검증해야 불완전한 페이지로 기준선이 부분 생성되지 않습니다.
      if (result.value.items.some((item) => item.displayState !== 'AUTO_FAIL')) {
        throw new Error('AUTO_FAIL 이력 필터 결과에 다른 상태가 포함됐습니다.');
      }
      const alerts: AutoFailInAppAlertV4[] = [];
      for (const item of result.value.items) {
        if (!seenIds.has(item.inspectionId)) {
          seenIds.add(item.inspectionId);
          if (initialized) {
            alerts.push({
              kind: 'AUTO_FAILED', inspectionId: item.inspectionId, inspectionNo: item.inspectionNo,
              partCode: item.partCode, receivedAt: item.receivedAt,
            });
          }
        }
      }
      initialized = true;
      if (alerts.length) options.onAlert(alerts);
    } catch {
      // 아직 V13 미배포(400)·네트워크 장애·인증 오류에서는
      // 최초 기준선을 만들지 않고, 판정이나 저장 작업 없이 다음 조회에서 재시도합니다.
    } finally {
      fetching = false;
      // 백그라운드 진입 중 시작한 요청의 결과가 늦게 돌아왔으면 복귀 직후 재조회합니다.
      if (running && foreground) schedule(myGeneration === generation ? intervalMs : 0);
    }
  }
  function start() {
    if (running) return;
    running = true;
    generation += 1;
    if (foreground) schedule(0);
  }
  function stop() {
    running = false;
    generation += 1;
    clearTimer();
  }
  function setForeground(value: boolean) {
    if (foreground === value) return;
    foreground = value;
    generation += 1;
    clearTimer();
    if (running && foreground) schedule(0);
  }
  return { start, stop, setForeground };
}
