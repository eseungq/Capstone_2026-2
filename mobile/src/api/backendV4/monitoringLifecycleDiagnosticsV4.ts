/**
 * 74단계 · 실제 화면 포커스 / 앱 활성 상태에서 모니터링 폴링 중단을 확인하는 진단기.
 * 순수 TypeScript. 실제 서버, AsyncStorage, Push, 사용자 판정에 접근하지 않음.
 * 화면 이탈/백그라운드 이전과 복귀 직전의 조회 시도 수를 비교해 검증함.
 */
import type { MonitorSnapshotV4 } from './monitoringPollCore';

export interface LifecyclePollControllerV4 {
  start(): void;
  stop(): void;
  setForeground(foreground: boolean): void;
  getSnapshot(): MonitorSnapshotV4;
  subscribe(listener: (snapshot: MonitorSnapshotV4) => void): () => void;
}

export interface LifecyclePauseCheckV4 {
  pauseMs: number;
  unexpectedAttempts: number;
  unexpectedSuccesses: number;
  passed: boolean;
}
export interface LifecycleLogV4 {
  timestampMs: number;
  event: string;
}
export interface LifecycleDiagnosticsV4 {
  screenFocused: boolean;
  appForeground: boolean;
  totalAttempts: number;
  lastAttemptAtMs: number | null;
  focusTransitions: number;
  backgroundTransitions: number;
  screenCheck: LifecyclePauseCheckV4 | null;
  backgroundCheck: LifecyclePauseCheckV4 | null;
  recentEvents: LifecycleLogV4[];
}
interface PauseStart {at: number; attempts: number; successes: number}

export function createMonitoringLifecycleDiagnosticsV4(
  controller: LifecyclePollControllerV4,
  options: { now?: () => number } = {},
) {
  const now = options.now ?? Date.now;
  let state: LifecycleDiagnosticsV4 = {
    screenFocused: false, appForeground: true,
    totalAttempts: 0, lastAttemptAtMs: null,
    focusTransitions: 0, backgroundTransitions: 0,
    screenCheck: null, backgroundCheck: null, recentEvents: [],
  };
  let focused = false;
  let foreground = true;
  let screenPause: PauseStart | null = null;
  let backgroundPause: PauseStart | null = null;
  let lastSuccesses = controller.getSnapshot().successfulPolls;
  const listeners = new Set<(next: LifecycleDiagnosticsV4) => void>();

  function getSnapshot(): LifecycleDiagnosticsV4 {
    return {...state, recentEvents: [...state.recentEvents],
      screenCheck: state.screenCheck && {...state.screenCheck},
      backgroundCheck: state.backgroundCheck && {...state.backgroundCheck}};
  }
  function emit() { const next = getSnapshot(); listeners.forEach((fn) => fn(next)); }
  function log(event: string) {
    state = {...state, recentEvents: [{timestampMs: now(), event}, ...state.recentEvents].slice(0, 12)};
    emit();
  }
  function markPause(): PauseStart {
    return {at: now(), attempts: state.totalAttempts, successes: controller.getSnapshot().successfulPolls};
  }
  function verifyPause(start: PauseStart): LifecyclePauseCheckV4 {
    const unexpectedAttempts = state.totalAttempts - start.attempts;
    const unexpectedSuccesses = controller.getSnapshot().successfulPolls - start.successes;
    return {pauseMs: Math.max(0, now() - start.at),
      unexpectedAttempts, unexpectedSuccesses,
      passed: unexpectedAttempts === 0 && unexpectedSuccesses === 0};
  }
  // 상태 변경은 관찰만 함. 여기에 새로운 타이머나 폴링을 시작하지 않음.
  const unsubscribeController = controller.subscribe((snapshot) => {
    if (snapshot.status === 'loading') {
      state = {...state, totalAttempts: state.totalAttempts + 1, lastAttemptAtMs: now()};
      log('조회 시도');
    }
    if (snapshot.successfulPolls !== lastSuccesses) {
      lastSuccesses = snapshot.successfulPolls;
      log('정상 조회 완료');
    }
    if (snapshot.status === 'error') log('조회 오류 · 마지막 정상 데이터 유지');
  });

  function enterScreen() {
    if (focused) return;
    if (screenPause !== null) {
      const check = verifyPause(screenPause);
      state = {...state, screenCheck: check};
      screenPause = null;
      log(check.passed ? '화면 복귀 · 이탈 중 조회 0회 확인' : '화면 복귀 · 조회 발생 감지');
    }
    focused = true;
    state = {...state, screenFocused: true, focusTransitions: state.focusTransitions + 1};
    log('모니터링 화면 진입');
    controller.start();
  }
  function leaveScreen() {
    if (!focused) return;
    focused = false;
    // 먼저 엔진을 정지하고 카운터 기준선을 저장한다.
    controller.stop();
    screenPause = markPause();
    state = {...state, screenFocused: false};
    log('모니터링 화면 이탈 · 조회 중단');
  }
  function updateAppState(nextState: string | null) {
    // RN의 초기 null은 알 수 없는 상태이므로 임의의 전환으로 기록하지 않는다.
    if (nextState === null) return;
    const isActive = nextState === 'active';
    if (isActive === foreground) return;
    foreground = isActive;
    controller.setForeground(isActive);
    if (!isActive) {
      backgroundPause = markPause();
      state = {...state, appForeground: false, backgroundTransitions: state.backgroundTransitions + 1};
      log(`앱 비활성(${nextState}) · 조회 일시정지`);
    } else {
      if (backgroundPause !== null) {
        const check = verifyPause(backgroundPause);
        state = {...state, backgroundCheck: check};
        backgroundPause = null;
        log(check.passed ? '앱 복귀 · 비활성 중 조회 0회 확인' : '앱 복귀 · 조회 발생 감지');
      }
      state = {...state, appForeground: true};
      log('앱 활성 · 조회 재개');
    }
  }
  function subscribe(listener: (next: LifecycleDiagnosticsV4) => void) {
    listeners.add(listener); listener(getSnapshot());
    return () => { listeners.delete(listener); };
  }
  function dispose() { unsubscribeController(); listeners.clear(); }
  return { enterScreen, leaveScreen, updateAppState, getSnapshot, subscribe, dispose };
}
