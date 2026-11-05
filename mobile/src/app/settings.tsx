import { Stack, router, useLocalSearchParams } from 'expo-router';
import React from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

// Figma: FyGAGiL2xkZgaDfegUk10A
// 99:772 (07 · 작업자 설정), 99:809 (07-M · 관리자 설정)
// 실제 인증 서비스에 연결되지 않은 Mock 역할 선택 화면입니다.
type Role = 'WORKER' | 'ADMIN';

const color = {
  background: '#F5F7FB',
  white: '#FFFFFF',
  ink: '#111827',
  muted: '#64748B',
  border: '#E4E7EC',
  blue: '#2054D8',
  info: '#EBF1FF',
};

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

function NavBar({ role }: { role: Role }) {
  return (
    <View style={styles.nav}>
      <Pressable
        style={styles.navItem}
        accessibilityRole="button"
        onPress={() => router.replace({ pathname: '/monitoring', params: { role } })}
      >
        <Text style={styles.navIcon}>▣</Text>
        <Text style={styles.navText}>모니터링</Text>
      </Pressable>
      <Pressable
        style={styles.navItem}
        accessibilityRole="button"
        onPress={() => router.replace({ pathname: '/history', params: { role } })}
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
  const { role: rawRole } = useLocalSearchParams<{ role?: string }>();
  // 현재는 화면 이동 파라미터에 따른 Mock 역할 표시입니다. 서버 권한 검증과 무관합니다.
  const role: Role = rawRole === 'ADMIN' ? 'ADMIN' : 'WORKER';
  const isAdmin = role === 'ADMIN';

  const logout = () => {
    Alert.alert(
      '로그아웃 · Mock',
      '로그인 화면으로 돌아갈까요? 이 동작은 시연용이며 기기에 저장된 Mock 판정 기록은 지우지 않습니다.',
      [
        { text: '취소', style: 'cancel' },
        { text: '로그아웃', onPress: () => router.replace('/') },
      ],
    );
  };

  const openPolicy = () => {
    Alert.alert(
      '관리자 정책 화면 · 연결 전',
      'Figma의 자동 통과 기준 관리 화면은 다음 단계에서 구현합니다. 검증된 자동 통과 정책이 없으며 passThreshold를 임의로 설정하지 않습니다.',
      [{ text: '확인' }],
    );
  };

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Text style={styles.title}>설정</Text>
        <Text style={styles.subtitle}>
          {isAdmin ? '시스템 관리자 계정 · Mock' : '현장 작업자 계정 · Mock'}
        </Text>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
        <Card title="계정 정보">
          <Field label="권한" value={isAdmin ? '시스템 관리자' : '현장 작업자'} />
          <Field label="로그인 상태" value="시연용" />
        </Card>

        <Card title="사용 가능한 메뉴">
          <Text style={styles.cardText}>
            {isAdmin ? '모니터링 · 전체 이력 · 설정' : '모니터링 · 담당 이력 · REVIEW 확인 · 설정'}
          </Text>
        </Card>

        <Card title={isAdmin ? '관리자 전용' : '작업자 업무'}>
          <Text style={styles.cardText}>
            {isAdmin
              ? '자동 통과 기준치 · 준비·적용 상태 관리'
              : '확인 필요 알림 → 검사 상세 → PASS/FAIL 제출'}
          </Text>
        </Card>

        {isAdmin && (
          <Pressable style={[styles.button, styles.primary]} 
onPress={() =>
  router.push({
    pathname: '/policy',
    params: { role: 'ADMIN' },
  })
}
 accessibilityRole="button">
            <Text style={[styles.buttonText, { color: color.white }]}>자동 통과 기준 관리로 이동</Text>
          </Pressable>
        )}

{isAdmin && (
  <Pressable
    style={[styles.button, styles.secondary]}
    onPress={() =>
      router.push({
        pathname: '/statistics',
        params: { role: 'ADMIN' },
      })
    }
    accessibilityRole="button"
  >
    <Text style={styles.buttonText}>
      품질 통계 보기 · Mock
    </Text>
  </Pressable>
)}

{isAdmin && (
  <Pressable
    style={[styles.button, styles.secondary]}
    onPress={() =>
      router.push({
        pathname: '/inspection-read-v4-preview',
      })
    }
    accessibilityRole="button"
  >
    <Text style={styles.buttonText}>
      검사 조회 API v4 사전 점검
    </Text>
  </Pressable>
)}

{isAdmin && (
  <Pressable
    style={[styles.button, styles.secondary]}
    onPress={() =>
      router.push({
        pathname: '/inspection-write-v4-preview',
      })
    }
    accessibilityRole="button"
  >
    <Text style={styles.buttonText}>
      판정·재검사 API v4 사전 점검
    </Text>
  </Pressable>
)}

{isAdmin && (
  <Pressable
    style={[styles.button, styles.secondary]}
    onPress={() =>
      router.push({
        pathname: '/ai-display-v4-preview',
      })
    }
    accessibilityRole="button"
  >
    <Text style={styles.buttonText}>
      AI 결과·Grad-CAM 사전 점검
    </Text>
  </Pressable>
)}

{isAdmin && (
  <Pressable
    style={[styles.button, styles.secondary]}
    onPress={() =>
      router.push({
        pathname: '/monitoring-poll-v4-preview',
      })
    }
    accessibilityRole="button"
  >
    <Text style={styles.buttonText}>
      공정 모니터링 5초 갱신 사전 점검
    </Text>
  </Pressable>
)}

{isAdmin && (
  <Pressable
    style={[styles.button, styles.secondary]}
    onPress={() =>
      router.push({
        pathname: '/integration-readiness-v4-preview',
      })
    }
    accessibilityRole="button"
  >
    <Text style={styles.buttonText}>
      75단계 · 통합 연결 준비 점검
    </Text>
  </Pressable>
)}

        <Pressable style={[styles.button, styles.secondary]} onPress={logout} accessibilityRole="button">
          <Text style={styles.buttonText}>로그아웃</Text>
        </Pressable>

        <View style={styles.notice}>
          <Text style={styles.noticeText}>
            {isAdmin ? '정책 관리 화면은 연결 전 · ' : ''}로그아웃 후 로그인 화면 이동 · 인증 연동 여부는 별도 확인
          </Text>
        </View>
      </ScrollView>

      <NavBar role={role} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.background },
  header: { paddingHorizontal: 20, paddingTop: 9, paddingBottom: 26 },
  title: { color: color.ink, fontSize: 23, fontWeight: '700', lineHeight: 34 },
  subtitle: { color: color.muted, fontSize: 11, lineHeight: 18, marginTop: 1 },
  scroll: { flex: 1 },
  body: { paddingHorizontal: 20, paddingBottom: 20, gap: 10 },
  card: { padding: 13, gap: 7, borderWidth: 1, borderColor: color.border, borderRadius: 14, backgroundColor: color.white },
  cardTitle: { fontSize: 13, lineHeight: 21, fontWeight: '700', color: color.ink },
  field: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  fieldLabel: { flex: 0.43, color: color.muted, fontSize: 11, lineHeight: 18 },
  fieldValue: { flex: 0.57, color: color.ink, textAlign: 'right', fontSize: 11, lineHeight: 18, fontWeight: '500' },
  cardText: { color: color.ink, fontSize: 12, lineHeight: 20, fontWeight: '500' },
  button: { height: 44, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  primary: { backgroundColor: color.blue },
  secondary: { backgroundColor: color.white, borderWidth: 1, borderColor: color.border },
  buttonText: { fontSize: 13, lineHeight: 20, fontWeight: '700', color: color.ink },
  notice: { backgroundColor: color.info, borderRadius: 10, padding: 9 },
  noticeText: { fontSize: 10, lineHeight: 15, fontWeight: '500', color: color.blue },
  nav: { height: 58, borderWidth: 1, borderColor: color.border, borderRadius: 15, backgroundColor: color.white, marginHorizontal: 20, marginBottom: 6, flexDirection: 'row', justifyContent: 'space-evenly', alignItems: 'center' },
  navItem: { flex: 1, height: 46, alignItems: 'center', justifyContent: 'center', gap: 1 },
  navIcon: { color: color.muted, fontSize: 16, lineHeight: 24, fontWeight: '700' },
  navText: { color: color.muted, fontSize: 11, lineHeight: 17, fontWeight: '500' },
  active: { color: color.blue, fontWeight: '700' },
});
