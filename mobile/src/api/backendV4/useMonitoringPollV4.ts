/** 화면 focus + AppState 활성일 때만 동작하는 React Native 연결 후크.
 * Preview에서는 가상 Reader를 넘겨 네트워크를 호출하지 않습니다.
 * 실제 서버 연동은 9~10주차에 인증/URL 계약 확정 후 별도 활성화.
 */
import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { AppState } from 'react-native';
import type { MonitorReaderV4, MonitorSnapshotV4 } from './monitoringPollCore';
import { createMonitoringPollControllerV4 } from './monitoringPollCore';

export function useMonitoringPollV4(reader: MonitorReaderV4, enabled = true) {
  const controller = useMemo(() => createMonitoringPollControllerV4({reader}), [reader]);
  const [snapshot, setSnapshot] = useState<MonitorSnapshotV4>(() => controller.getSnapshot());
  useEffect(() => controller.subscribe(setSnapshot), [controller]);
  useFocusEffect(useCallback(() => {
    if (!enabled) return;
    const sync = (state: string | null) => controller.setForeground(state==='active' || state===null);
    sync(AppState.currentState ?? null);
    controller.start();
    const subscription = AppState.addEventListener('change', sync);
    return () => { subscription.remove(); controller.stop(); };
  }, [controller, enabled]));
  return {snapshot, controller};
}
