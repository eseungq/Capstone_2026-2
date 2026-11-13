import React, { useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Stack, router, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { DOOR_AUTOPASS_DEMO_V4 as DEMO } from '../api/backendV4/demoPolicyScenarioV4';

// Figma: FyGAGiL2xkZgaDfegUk10A / 99:720, 99:616, 99:668 (2026-10-27)
// 운영 정책 조회/변경 화면이 아닙니다. 시연 상태 탭은 Mock 화면 예시입니다.
// 실제 e02 보정값/보정기 버전은 null이며 시연용 0.84~0.92% 기준을 운영에 사용하지 않습니다.

type Scenario = 'UNREADY' | 'READY_DEMO' | 'ACTIVE_DEMO';
type Role = 'ADMIN' | 'WORKER';

const C = {
  bg: '#F5F7FB',
  surface: '#FFFFFF',
  border: '#E4E7EC',
  text: '#111827',
  muted: '#64748B',
  blue: '#2054D8',
  bluePale: '#EBF1FF',
  red: '#B42318',
  redPale: '#FFF0ED',
  green: '#067647',
  greenPale: '#EAFBF2',
  neutralPale: '#EEF2F8',
};

function InfoRow({ title, value, color }: { title: string; value: string; color?: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{title}</Text>
      <Text style={[styles.infoValue, color ? { color } : undefined]}>{value}</Text>
    </View>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.panel}>
      <Text style={styles.panelTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Pill({ label, tint, foreground }: { label: string; tint: string; foreground: string }) {
  return (
    <View style={[styles.pill, { backgroundColor: tint }]}>
      <Text style={[styles.pillText, { color: foreground }]}>{label}</Text>
    </View>
  );
}

function BottomNav({ role }: { role: Role }) {
  return (
    <View style={styles.bottomNav}>
      <Pressable
        accessibilityRole="button"
        onPress={() => router.replace({ pathname: '/monitoring', params: { role } })}
        style={styles.navItem}
      >
        <Text style={styles.navIcon}>▣</Text>
        <Text style={styles.navLabel}>모니터링</Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        onPress={() => router.replace({ pathname: '/history', params: { role } })}
        style={styles.navItem}
      >
        <Text style={styles.navIcon}>▤</Text>
        <Text style={styles.navLabel}>이력</Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        onPress={() => router.replace({ pathname: '/settings', params: { role } })}
        style={styles.navItem}
      >
        <Text style={[styles.navIcon, styles.navActive]}>⚙</Text>
        <Text style={[styles.navLabel, styles.navActive]}>설정</Text>
      </Pressable>
    </View>
  );
}

const examples: { key: Scenario; label: string }[] = [
  { key: 'UNREADY', label: '운영 미준비' },
  { key: 'READY_DEMO', label: '시연 준비' },
  { key: 'ACTIVE_DEMO', label: '시연 적용' },
];

export default function PolicyScreen() {
  const params = useLocalSearchParams<{ role?: string }>();
  // 역할은 시연용 라우트 값입니다. 실제 서비스에서는 인증 토큰/서버에서 검증해야 합니다.
  const role: Role = params.role === 'ADMIN' ? 'ADMIN' : 'WORKER';
  const [scenario, setScenario] = useState<Scenario>('UNREADY');
  const unready = scenario === 'UNREADY';
  const active = scenario === 'ACTIVE_DEMO';

  if (role !== 'ADMIN') {
    return (
      <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
        <Stack.Screen options={{ headerShown: false }} />
        <View style={styles.header}>
          <Text style={styles.pageTitle}>자동 통과 기준</Text>
          <Text style={styles.subtitle}>관리자 전용 화면 · Mock</Text>
        </View>
        <View style={styles.contentArea}>
          <Panel title="접근할 수 없는 화면">
            <Text style={styles.note}>현재 시연 역할은 WORKER입니다. 관리자 역할로 다시 진입해야 합니다.</Text>
            <Pressable onPress={() => router.replace({ pathname: '/settings', params: { role } })} style={styles.secondaryButton}>
              <Text style={styles.secondaryText}>설정으로 돌아가기</Text>
            </Pressable>
          </Panel>
        </View>
        <BottomNav role={role} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Text style={styles.pageTitle}>자동 통과 기준</Text>
        <Text style={styles.subtitle}>
          {unready ? '미준비 상태' : active ? '적용 중 상태' : '준비됨 상태'} · 관리자 전용 · 예시
        </Text>
      </View>
      <ScrollView
        style={styles.contentArea}
        contentContainerStyle={styles.body}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.tabs} accessibilityRole="tablist">
          {examples.map(({ key, label }) => (
            <Pressable
              key={key}
              accessibilityRole="tab"
              accessibilityState={{ selected: scenario === key }}
              onPress={() => setScenario(key)}
              style={[styles.tab, scenario === key ? styles.tabSelected : undefined]}
            >
              <Text style={styles.tabText}>{label}</Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.blueNote}>
          <Text style={styles.blueNoteText}>실제 e02의 운영 보정기와 적용 정책은 미준비입니다. 다른 탭은 11/09 Mock 시연 정책 예시이며 DGX/e02 상태를 변경하지 않습니다.</Text>
        </View>
        <Panel title="정책 연결 정보">
          <InfoRow title="부품 / 검사 범위" value="DOOR · 모델 지원 범위" />
          <InfoRow title="정책 버전" value={unready ? '실제 e02 활성 정책 없음' : `${DEMO.basePolicyVersion} · 시연 Mock`} />
          <InfoRow title="기준 관리" value="passThreshold" />
          <InfoRow title="모델 버전" value={unready ? 'door-swin-tiny-e02-28a2dd1cb40b-dev' : `${DEMO.mockModelVersion} · Mock`} />
          <InfoRow title="서버 구분" value={unready ? '실제 e02 · 정책 미준비' : '독립 Mock 시연 (운영 미적용)'} />
        </Panel>

        <Panel title="정책 준비 · 적용 상태">
          <Pill
            label={`ready: ${unready ? '미준비' : '준비됨 · Mock'}`}
            tint={unready ? C.redPale : C.greenPale}
            foreground={unready ? C.red : C.green}
          />
          <Pill
            label={`active: ${active ? '적용 중 · Mock' : '미적용'}`}
            tint={active ? C.greenPale : C.neutralPale}
            foreground={active ? C.green : C.muted}
          />
        </Panel>

        <Panel title="기준치와 검증 근거 · Mock">
          {unready ? (
            <>
              <InfoRow title="적용 가능 후보 값" value="검증 전 · 없음" />
              <InfoRow title="passThreshold" value="확정 전" />
              <Text style={styles.warningText}>유효한 정책이 없어 분석 완료 건은 REVIEW와 확인 필요 알림으로 처리합니다.</Text>
              <InfoRow title="운영 검증 범위" value="미제공" />
            </>
          ) : (
            <>
              <InfoRow title="비교 시작 기준치" value={`${(DEMO.initialThreshold*100).toFixed(2)}% · 시연 Mock`} color={C.blue} />
              <InfoRow title="정책 기본값·조정 후" value={`${(DEMO.defaultThreshold*100).toFixed(2)}% · Mock`} color={C.blue} />
              <InfoRow title="시연 조정 허용 범위" value={`${(DEMO.validatedMin*100).toFixed(2)}~${(DEMO.validatedMax*100).toFixed(2)}% · Mock`} color={C.blue} />
              <InfoRow title="조정 시연 예시" value="0.84% → 0.92%, GOOD/0.88% 재접수" />
              <Text style={styles.warningText}>
                이 범위는 도현님의 내부 평가에 따른 시연 전용 수치입니다. 실제 e02 운영 정책이나 독립적인 운영 안전성 검증 결과는 아닙니다.
              </Text>
            </>
          )}
        </Panel>

        <Pressable
          accessibilityRole="button"
          onPress={() => router.push({
            pathname: '/policy-adjust',
            params: { role: 'ADMIN', scenario },
          })}
          style={[styles.actionButton, unready ? styles.previewButton : styles.activePreviewButton]}
        >
          <Text style={[styles.actionText, unready ? styles.previewText : styles.activePreviewText]}>
            {unready ? '정책 조정 화면 · 운영 미준비' : '0.84% → 0.92% 조정 시연 · Mock'}
          </Text>
        </Pressable>

        <View style={styles.blueNote}>
          <Text style={styles.blueNoteText}>
            목표 미검출률 입력을 통한 후보 계산은 10/14 합의에 따라 사용하지 않습니다. 운영 정책 저장·적용은 아직 연결되지 않았으며, Mock 조정 시연은 다음 화면에서만 진행합니다.
          </Text>
        </View>
      </ScrollView>
      <BottomNav role={role} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  header: { paddingHorizontal: 20, paddingTop: 9, paddingBottom: 25 },
  pageTitle: { fontSize: 23, fontWeight: '700', color: C.text, lineHeight: 34 },
  subtitle: { fontSize: 11, color: C.muted, lineHeight: 18, marginTop: 1 },
  contentArea: { flex: 1 },
  body: { paddingHorizontal: 20, paddingTop: 3, paddingBottom: 18, gap: 7 },
  tabs: { height: 37, flexDirection: 'row', backgroundColor: C.surface, borderRadius: 10, padding: 2, gap: 5 },
  tab: { flex: 1, justifyContent: 'center', alignItems: 'center', borderRadius: 10, minWidth: 0 },
  tabSelected: { backgroundColor: C.bluePale },
  tabText: { color: C.blue, fontSize: 11, lineHeight: 17, textAlign: 'center' },
  panel: { backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 14, padding: 13, gap: 7 },
  panelTitle: { fontSize: 13, lineHeight: 21, fontWeight: '700', color: C.text },
  infoRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  infoLabel: { flex: 0.44, color: C.muted, fontSize: 11, lineHeight: 18 },
  infoValue: { flex: 0.56, color: C.text, fontSize: 11, lineHeight: 18, fontWeight: '500', textAlign: 'right' },
  pill: { alignSelf: 'flex-start', borderRadius: 100, paddingHorizontal: 10, paddingVertical: 5 },
  pillText: { fontSize: 10, lineHeight: 15, fontWeight: '500' },
  warningText: { color: C.red, fontSize: 12, lineHeight: 19 },
  note: { color: C.muted, fontSize: 12, lineHeight: 19 },
  actionButton: { height: 44, borderRadius: 12, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 10 },
  previewButton: { backgroundColor: '#E5EDFC' },
  activePreviewButton: { backgroundColor: C.blue },
  actionText: { fontSize: 13, fontWeight: '700', textAlign: 'center' },
  previewText: { color: '#2159D1' },
  activePreviewText: { color: C.surface },
  secondaryButton: { minHeight: 44, justifyContent: 'center', alignItems: 'center', backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 12, marginTop: 10 },
  secondaryText: { color: C.text, fontWeight: '700', fontSize: 13 },
  blueNote: { backgroundColor: C.bluePale, borderRadius: 10, padding: 9 },
  blueNoteText: { color: C.blue, fontSize: 10, lineHeight: 16 },
  bottomNav: { height: 58, marginHorizontal: 20, marginBottom: 6, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 15, flexDirection: 'row', alignItems: 'center' },
  navItem: { flex: 1, alignItems: 'center', justifyContent: 'center', minHeight: 46, gap: 1 },
  navIcon: { color: C.muted, fontSize: 16, lineHeight: 24 },
  navLabel: { color: C.muted, fontSize: 11, lineHeight: 17, fontWeight: '500' },
  navActive: { color: C.blue, fontWeight: '700' },
});
