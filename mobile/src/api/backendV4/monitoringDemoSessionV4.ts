/**
 * 73단계: 화면 수명과 별개로 유지되는 가상 모니터링 세션.
 * 실서버/푸시/AsyncStorage/기존 검사 Mock을 변경하지 않습니다.
 * 앱 실행 중의 화면 이동에만 상태를 보존합니다(앱 재시작/새로고침 시 초기화).
 */
import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { AppState } from 'react-native';
import type { LifecycleDiagnosticsV4 } from './monitoringLifecycleDiagnosticsV4';
import { createMonitoringLifecycleDiagnosticsV4 } from './monitoringLifecycleDiagnosticsV4';
import type { MonitorAlertV4, MonitorSnapshotV4 } from './monitoringPollCore';
import { createMonitoringPollControllerV4 } from './monitoringPollCore';
import { createMonitoringDemoReaderV4 } from './monitoringPollExamples';

const reader = createMonitoringDemoReaderV4();
const controller = createMonitoringPollControllerV4({ reader });
const lifecycle = createMonitoringLifecycleDiagnosticsV4(controller);
let alertHistory: MonitorAlertV4[] = [];
const alertObservers = new Set<(next: MonitorAlertV4[]) => void>();

// 화면이 사라져도 유지. controller는 UUID + displayState 기준으로 재알림을 막습니다.
controller.subscribeAlerts((batch) => {
  const seen = new Set(alertHistory.map((a) => `${a.inspectionId}:${a.kind}`));
  const fresh = batch.filter((a) => !seen.has(`${a.inspectionId}:${a.kind}`));
  if (!fresh.length) return;
  alertHistory = [...fresh, ...alertHistory].slice(0, 20);
  alertObservers.forEach((fn) => fn([...alertHistory]));
});

function subscribeAlerts(fn: (next: MonitorAlertV4[]) => void) {
  alertObservers.add(fn);
  fn([...alertHistory]);
  return () => { alertObservers.delete(fn); };
}

export function useMonitoringDemoSessionV4() {
  const [snapshot, setSnapshot] = useState<MonitorSnapshotV4>(() => controller.getSnapshot());
  const [events, setEvents] = useState<MonitorAlertV4[]>(() => [...alertHistory]);
  const [diagnostics, setDiagnostics] = useState<LifecycleDiagnosticsV4>(() => lifecycle.getSnapshot());

  useEffect(() => controller.subscribe(setSnapshot), []);
  useEffect(() => subscribeAlerts(setEvents), []);
  useEffect(() => lifecycle.subscribe(setDiagnostics), []);

  useFocusEffect(useCallback(() => {
    lifecycle.updateAppState(AppState.currentState ?? null);
    lifecycle.enterScreen();
    const appStateSubscription = AppState.addEventListener('change', lifecycle.updateAppState);
    return () => {
      appStateSubscription.remove();
      lifecycle.leaveScreen(); // 화면 이탈 시 중단 + 이탈 중 조회를 진단 로그로 추적
    };
  }, []));

  return {
    snapshot,
    events,
    diagnostics,
    addReview: () => reader.addReview(),
    addFailed: () => reader.addFailed(),
    failOnce: () => reader.failOnce(),
    added: reader.getDemoCounts().added,
  };
}
