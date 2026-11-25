import React, { useEffect, useMemo, useState } from 'react';
import { router, useGlobalSearchParams, usePathname } from 'expo-router';
import { AppState, Pressable, StyleSheet, Text, View } from 'react-native';

import { authV4 } from '../api/backendV4/authRuntime';
import { partLabelV4 } from './partLabelV4';
import { createInspectionReadServiceV4 } from '../api/backendV4/inspectionReadService';
import {
  createAutoFailInAppControllerV4,
  type AutoFailInAppAlertV4,
} from '../api/backendV4/autoFailInAppCoreV4';

const reader = createInspectionReadServiceV4({ mode: 'api', transport: authV4 });

/** Mock/로그인/프리뷰에서는 서버 알림 폴링을 절대 시작하지 않습니다. */
export function AutoFailInAppAlertHostV4() {
  const pathname = usePathname();
  const { mode } = useGlobalSearchParams<{ mode?: string }>();
  const isLive = (
    (['/monitoring', '/history', '/settings', '/statistics', '/policy-adjust'].includes(pathname) && mode === 'live')
    || pathname.endsWith('-live')
  );
  const [sessionKey, setSessionKey] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    if (!isLive) { setSessionKey(null); return; }
    void authV4.restore().then((session) => {
      if (!active) return;
      setSessionKey(
        session.signedIn && (session.role === 'WORKER' || session.role === 'ADMIN')
          ? `${session.loginId ?? ''}:${session.role}`
          : null,
      );
    }).catch(() => { if (active) setSessionKey(null); });
    return () => { active = false; };
  }, [isLive, pathname]);

  return isLive && sessionKey !== null
    ? <AutoFailInAppBannerV4 key={sessionKey} isMonitoring={pathname === '/monitoring'} />
    : null;
}

function AutoFailInAppBannerV4({ isMonitoring }: { isMonitoring: boolean }) {
  const [pending, setPending] = useState<AutoFailInAppAlertV4[]>([]);
  const controller = useMemo(() => createAutoFailInAppControllerV4({
    reader,
    onAlert: (alerts) => {
      setPending((old) => [...old, ...alerts].sort(
        (a, b) => Date.parse(b.receivedAt) - Date.parse(a.receivedAt),
      ));
    },
  }), []);

  useEffect(() => {
    const syncAppState = (state: string) => controller.setForeground(state === 'active');
    controller.setForeground(AppState.currentState == null || AppState.currentState === 'active');
    controller.start();
    const subscription = AppState.addEventListener('change', syncAppState);
    return () => { subscription.remove(); controller.stop(); };
  }, [controller]);

  const alert = pending[0];
  if (!alert) return null;
  const close = () => setPending((old) => old.slice(1));
  const open = () => {
    const inspectionId = alert.inspectionId;
    close();
    router.push({ pathname: '/inspection-live', params: { inspectionId } });
  };
  return (
    <View style={[s.banner, isMonitoring && s.monitorBanner]} accessibilityLiveRegion="polite">
      <View style={s.row}>
        <Text style={s.title}>
          자동 불량{pending.length > 1 ? ` · 외 ${pending.length - 1}건` : ''}
        </Text>
        <Pressable accessibilityRole="button" accessibilityLabel="자동 불량 알림 닫기"
          onPress={close} style={s.dismissButton}>
          <Text style={s.dismiss}>닫기</Text>
        </Pressable>
      </View>
      <Text style={s.description}>
        {partLabelV4(alert.partCode)} · {alert.inspectionNo ?? '검사번호 확인 필요'} · 자동 불량
      </Text>
      <Text style={s.note}>앱 실행 중 확인된 자동 불량입니다.</Text>
      <Pressable accessibilityRole="button" style={s.open} onPress={open}>
        <Text style={s.openText}>검사 상세 보기 ›</Text>
      </Pressable>
    </View>
  );
}

const s = StyleSheet.create({
  banner: {
    position: 'absolute', bottom: 92, left: 18, right: 18, zIndex: 40, elevation: 12,
    backgroundColor: '#FFFFFF', borderWidth: 1, borderLeftWidth: 5, borderColor: '#CBD5E1',
    borderLeftColor: '#B42318', borderRadius: 14, padding: 14, gap: 7,
    shadowColor: '#000000', shadowOpacity: 0.15, shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
  },
  monitorBanner: { bottom: 235 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  title: { flex: 1, fontSize: 15, fontWeight: '700', color: '#B42318' },
  dismissButton: { minWidth:44,minHeight:44,justifyContent:'center',alignItems:'center' },
  dismiss: { fontSize: 13, fontWeight: '600', color: '#475569', padding: 5 },
  description: { fontSize: 13, fontWeight: '600', color: '#111827' },
  note: { fontSize: 13, color: '#475569' },
  open: { minHeight:44,justifyContent:'center',backgroundColor: '#B42318', borderRadius: 9, padding: 10, alignItems: 'center' },
  openText: { fontSize: 13, color: '#FFFFFF', fontWeight: '700' },
});
