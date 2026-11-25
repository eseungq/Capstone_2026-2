/**
 * 계약 6.11: 포그라운드의 실제 상세 화면 체류 시간만 측정합니다.
 * 서버에는 제출 시에만 세 필드를 함께 보냅니다. 미제출 세션은 기기 메모리에만 있습니다.
 */
export interface InspectionDwellV4 {
  screenDwellMs: number;
  firstOpenedAt: string;
  openCount: number;
}

interface SessionV4 {
  firstMs: number;
  accumulatedMs: number;
  activeSinceMs: number | null;
  focused: boolean;
  foreground: boolean;
  openCount: number;
}

export function createInspectionDwellTrackerV4() {
  const sessions = new Map<string, SessionV4>();
  const stop = (s: SessionV4, nowMs: number) => {
    if (s.activeSinceMs !== null) {
      s.accumulatedMs += Math.max(0, nowMs - s.activeSinceMs);
      s.activeSinceMs = null;
    }
  };
  function focus(id: string, foreground: boolean, nowMs = Date.now()): void {
    let s = sessions.get(id);
    if (!s) {
      s = { firstMs: nowMs, accumulatedMs: 0, activeSinceMs: null,
        focused: false, foreground, openCount: 0 };
      sessions.set(id, s);
    }
    if (s.focused) return;
    s.focused = true;
    s.foreground = foreground;
    s.openCount += 1; // 백그라운드 복귀는 별도로 처리하므로 증가하지 않습니다.
    if (foreground) s.activeSinceMs = nowMs;
  }
  function blur(id: string, nowMs = Date.now()): void {
    const s = sessions.get(id);
    if (!s) return;
    stop(s, nowMs);
    s.focused = false;
  }
  function setForeground(id: string, foreground: boolean, nowMs = Date.now()): void {
    const s = sessions.get(id);
    if (!s) return;
    if (!foreground) stop(s, nowMs);
    else if (s.focused && s.activeSinceMs === null) s.activeSinceMs = nowMs;
    s.foreground = foreground;
  }
  function snapshot(id: string, nowMs = Date.now()): InspectionDwellV4 | null {
    const s = sessions.get(id);
    if (!s || !Number.isFinite(nowMs)) return null;
    const ongoing = s.activeSinceMs === null ? 0 : Math.max(0, nowMs - s.activeSinceMs);
    const screenDwellMs = Math.floor(s.accumulatedMs + ongoing);
    if (!Number.isSafeInteger(screenDwellMs) || screenDwellMs < 0 || screenDwellMs > 86_400_000 ||
        s.openCount < 1 || s.openCount > 1000) return null;
    return { screenDwellMs, firstOpenedAt: new Date(s.firstMs).toISOString(), openCount: s.openCount };
  }
  function clear(id: string): void { sessions.delete(id); }
  return { focus, blur, setForeground, snapshot, clear };
}

// 상세 화면 사이를 이동하면 같은 로그인에서만 체류 시간을 이어서 측정합니다.
export function createSessionDwellStoreV4() {
  let active: { loginId: string; epoch: number; tracker: ReturnType<typeof createInspectionDwellTrackerV4> } | null = null;
  return function forSession(loginId: string, epoch: number) {
    if (!active || active.loginId !== loginId || active.epoch !== epoch) {
      active = { loginId, epoch, tracker: createInspectionDwellTrackerV4() };
    }
    return active.tracker;
  };
}

export const inspectionDwellForSessionV4 = createSessionDwellStoreV4();
