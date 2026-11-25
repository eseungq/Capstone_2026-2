import Pressable from '../components/TouchPressable';
import LiveBottomNavV4 from '../components/LiveBottomNavV4';
import { Stack, router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { authV4 } from '../api/backendV4/authRuntime';
import React, { useCallback, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

// Figma: FyGAGiL2xkZgaDfegUk10A
// 99:772 (07 · 작업자 설정), 99:809 (07-M · 관리자 설정)
// Mock 모드와 실제 서버 세션을 분리하여 표시합니다.
type Role = 'WORKER' | 'ADMIN';
type Mode = 'live' | 'mock';
type VerifiedFocus = { epoch: number };

const color = {
  background: '#F5F7FB',
  white: '#FFFFFF',
  ink: '#111827',
  muted: '#475569',
  border: '#E4E7EC',
  blue: '#2054D8',
};

const adminDemoScreens = [
  { label: '품질 통계 보기 · Mock', href: { pathname: '/statistics', params: { role: 'ADMIN' } } },
  { label: '검사 조회 API v4 사전 점검', href: '/inspection-read-v4-preview' },
  { label: '판정·재검사 API v4 사전 점검', href: '/inspection-write-v4-preview' },
  { label: 'AI 결과·Grad-CAM 사전 점검', href: '/ai-display-v4-preview' },
  { label: '공정 모니터링 5초 갱신 사전 점검', href: '/monitoring-poll-v4-preview' },
  { label: '75단계 · 통합 연결 준비 점검', href: '/integration-readiness-v4-preview' },
] as const;

function Field({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <Text style={styles.fieldValue}>{value}</Text>
    </View>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>{title}</Text>
      {children}
    </View>
  );
}

function NavBar({ role, mode }: { role: Role; mode: Mode }) {
  return (
    <View style={styles.nav}>
      <Pressable
        style={styles.navItem}
        accessibilityRole="button"
        onPress={() => router.replace({ pathname: '/monitoring', params: { role, mode } })}
      >
        <Text style={styles.navIcon}>▣</Text>
        <Text style={styles.navText}>모니터링</Text>
      </Pressable>
      <Pressable
        style={styles.navItem}
        accessibilityRole="button"
        onPress={() => router.replace({ pathname: '/history', params: { role, mode } })}
      >
        <Text style={styles.navIcon}>▤</Text>
        <Text style={styles.navText}>이력</Text>
      </Pressable>
      <View style={styles.navItem} accessibilityLabel="현재 탭 설정">
        <Text style={[styles.navIcon, styles.active]}>⚙</Text>
        <Text style={[styles.navText, styles.active]}>설정</Text>
      </View>
    </View>
  );
}

export default function SettingsScreen() {
  const { role: rawRole, mode: rawMode } = useLocalSearchParams<{ role?: string; mode?: string }>();
  const mode: Mode = rawMode === 'live' ? 'live' : 'mock';
  const mockRole: Role = rawRole === 'ADMIN' ? 'ADMIN' : 'WORKER';
  const [liveRole, setLiveRole] = useState<Role | null>(null);
  const [checkingSession, setCheckingSession] = useState(mode === 'live');
  const [loggingOut, setLoggingOut] = useState(false);
  const logoutLock = useRef(false);
  const verifiedFocus = useRef<VerifiedFocus | null>(null);

  // 실서버 권한은 URL role 파라미터가 아니라 SecureStore의 로그인 세션으로 확인합니다.
  useFocusEffect(useCallback(() => {
    verifiedFocus.current = null;
    if (mode !== 'live') {
      setCheckingSession(false);
      return;
    }
    let active = true;
    const focus = { epoch: authV4.sessionEpoch() };
    setCheckingSession(true);
    void authV4.restore().then((session) => {
      if (!active) return;
      const verified = authV4.sessionEpoch() === focus.epoch && session.signedIn &&
        (session.role === 'WORKER' || session.role === 'ADMIN') ? session.role : null;
      verifiedFocus.current = verified ? focus : null;
      setLiveRole(verified);
    }).catch(() => {
      if (active) setLiveRole(null);
    }).finally(() => {
      if (active) setCheckingSession(false);
    });
    return () => {
      active = false;
      verifiedFocus.current = null;
    };
  }, [mode]));

  const role: Role | null = mode === 'live' ? liveRole : mockRole;
  const isAdmin = role === 'ADMIN';

  const performLiveLogout = async (origin: VerifiedFocus) => {
    if (logoutLock.current || verifiedFocus.current !== origin || authV4.sessionEpoch() !== origin.epoch) return;
    logoutLock.current = true;
    setLoggingOut(true);
    let logoutEpoch = origin.epoch;
    try {
      // 서버 Refresh Token 폐기를 시도하고, 실패해도 기기의 SecureStore는 삭제합니다.
      const completion = authV4.logout();
      logoutEpoch = authV4.sessionEpoch();
      const { remoteRevoked } = await completion;
      // Local logout already reset the stack; a later account must not receive this alert.
      if (!remoteRevoked && authV4.sessionEpoch() === logoutEpoch) {
        Alert.alert(
          '이 기기에서 로그아웃됨',
          '이 기기의 로그인 정보를 삭제했습니다. 서버에서도 로그아웃됐는지는 확인하지 못했습니다.',
        );
      }
    } catch {
      // SecureStore 삭제가 실패할 경우 로그아웃됐다고 표시하거나 화면을 이동하지 않습니다.
      if (authV4.sessionEpoch() === logoutEpoch) {
        Alert.alert(
          '로그아웃을 완료하지 못했습니다',
          '기기에 저장된 로그인 정보 삭제를 확인할 수 없습니다. 다시 시도해 주세요.',
        );
      }
    } finally {
      setLoggingOut(false);
      logoutLock.current = false;
    }
  };

  const logout = () => {
    if (loggingOut || logoutLock.current) return;
    if (mode === 'mock') {
      Alert.alert(
        '로그아웃 · Mock',
        '시연 화면을 종료하고 로그인 화면으로 돌아갈까요? 저장된 실제 서버 로그인 정보는 변경하지 않습니다.',
        [
          { text: '취소', style: 'cancel' },
          { text: '로그아웃', onPress: () => router.replace('/') },
        ],
      );
      return;
    }
    const origin = verifiedFocus.current;
    if (!origin || authV4.sessionEpoch() !== origin.epoch) return;
    Alert.alert(
      '로그아웃',
      '이 기기에서 로그아웃할까요?',
      [
        { text: '취소', style: 'cancel' },
        { text: '로그아웃', style: 'destructive', onPress: () => { void performLiveLogout(origin); } },
      ],
    );
  };

  if (mode === 'live' && (checkingSession || role === null)) {
    return (
      <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
        <Stack.Screen options={{ headerShown: false }} />
        <View style={styles.sessionGuard}>
          <Text style={styles.title}>설정</Text>
          {checkingSession ? (
            <>
              <ActivityIndicator color={color.blue} />
              <Text style={styles.cardText}>로그인 상태를 확인하고 있습니다.</Text>
            </>
          ) : (
            <>
              <Text style={styles.cardText}>작업자 또는 관리자 계정으로 다시 로그인해 주세요.</Text>
              <Pressable
                accessibilityRole="button"
                style={[styles.button, styles.primary]}
                onPress={() => router.replace('/')}>
                <Text style={[styles.buttonText, { color: color.white }]}>로그인 화면으로 이동</Text>
              </Pressable>
            </>
          )}
        </View>
      </SafeAreaView>
    );
  }
  // live 모드의 역할이 없으면 위 화면에서 차단되므로 실제 권한 없이
  // 관리자 메뉴를 노출하거나 URL role을 신뢰하는 일이 없습니다.
  const displayRole: Role = role ?? mockRole;

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Text style={styles.title}>설정</Text>
        <Text style={styles.subtitle}>
          {isAdmin ? '시스템 관리자' : '현장 작업자'}{mode === 'mock' && ' · 시연'}
        </Text>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
        <Card title="계정 정보">
          <Field label="권한" value={isAdmin ? '시스템 관리자' : '현장 작업자'} />
          <Field label="로그인 상태" value={mode === 'live' ? '로그인됨' : '시연 중'} />
        </Card>

        {isAdmin && mode === 'mock' && (
          <Pressable style={[styles.button, styles.primary]} accessibilityRole="button"
            onPress={() => router.push({ pathname: '/policy', params: { role: 'ADMIN' } })}>
            <Text style={[styles.buttonText, {color:color.white}]}>자동 통과 기준 관리 · Mock</Text>
          </Pressable>
        )}

        {isAdmin && mode === 'mock' && adminDemoScreens.map(({ label, href }) => (
          <Pressable key={label} style={[styles.button, styles.secondary]} accessibilityRole="button"
            onPress={() => router.push(href)}>
            <Text style={styles.buttonText}>{label}</Text>
          </Pressable>
        ))}

        <Pressable style={[styles.button, styles.secondary, loggingOut && styles.disabled]}
          onPress={logout} disabled={loggingOut} accessibilityRole="button">
          <Text style={styles.buttonText}>{loggingOut ? '로그아웃 처리 중…' : '로그아웃'}</Text>
        </Pressable>

        {mode === 'mock' && <Text style={styles.demoNote}>시연에서는 예시 검사와 정책을 사용합니다.</Text>}
      </ScrollView>

      {mode === 'live' ? <LiveBottomNavV4 role={displayRole} active="settings"/> : <NavBar role={displayRole} mode={mode} />}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.background },
  sessionGuard: { flex: 1, paddingHorizontal: 20, paddingTop: 36, gap: 20 },
  disabled: { opacity: 0.45 },
  header: { paddingHorizontal: 20, paddingTop: 9, paddingBottom: 26, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#CBD5E1' },
  title: { color: color.ink, fontSize: 23, fontWeight: '700', lineHeight: 34 },
  subtitle: { color: color.muted, fontSize: 13, lineHeight: 18, marginTop: 1 },
  scroll: { flex: 1 },
  body: { paddingHorizontal: 20, paddingBottom: 20, gap: 10 },
  card: { padding: 13, gap: 7, borderWidth: 1, borderColor: color.border, borderRadius: 14, backgroundColor: color.white },
  cardTitle: { fontSize: 13, lineHeight: 21, fontWeight: '700', color: color.ink },
  field: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  fieldLabel: { flex: 0.43, color: color.muted, fontSize: 13, lineHeight: 18 },
  fieldValue: { flex: 0.57, color: color.ink, textAlign: 'right', fontSize: 13, lineHeight: 18, fontWeight: '500' },
  cardText: { color: color.ink, fontSize: 13, lineHeight: 20, fontWeight: '500' },
  button: { minHeight: 44, paddingVertical: 10, paddingHorizontal: 10, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  primary: { backgroundColor: color.blue },
  secondary: { backgroundColor: color.white, borderWidth: 1, borderColor: '#64748B' },
  buttonText: { fontSize: 13, lineHeight: 20, fontWeight: '700', color: color.ink },
  demoNote: { color: color.muted, fontSize: 13, lineHeight: 16 },
  nav: { height: 58, borderWidth: 1, borderColor: color.border, borderRadius: 15, backgroundColor: color.white, marginHorizontal: 20, marginBottom: 6, flexDirection: 'row', justifyContent: 'space-evenly', alignItems: 'center' },
  navItem: { flex: 1, height: 46, alignItems: 'center', justifyContent: 'center', gap: 1 },
  navIcon: { color: color.muted, fontSize: 16, lineHeight: 24, fontWeight: '700' },
  navText: { color: color.muted, fontSize: 13, lineHeight: 17, fontWeight: '500' },
  active: { color: color.blue, fontWeight: '700' },
});
