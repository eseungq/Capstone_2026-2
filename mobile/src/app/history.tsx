import React, { useCallback, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack, router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { getMockInspectionHistory, useMockStoreState, type Inspection } from '../data/mockInspections';
import HistoryLiveScreenV4 from '../components/HistoryLiveScreenV4';

// Figma: 99:506 (WORKER), 99:561 (ADMIN) 검사 이력 목록.
// 본 화면은 동일 Mock store를 읽으며 실제 조회 API와 연결되어 있지 않습니다.
const C = { bg: '#F5F7FB', white: '#FFF', border: '#E4E7EC', ink: '#111827',
  muted: '#64748B', blue: '#2054D8', amber: '#A74B12', red: '#B42318', green: '#067647' };
type Role = 'WORKER' | 'ADMIN';
function loadHistory(): Inspection[] {
  return getMockInspectionHistory();
}
function state(it: Inspection): string {
  if (it.status === 'AUTO_PASS_EXAMPLE') return 'AUTO_PASS · 시연 예시 (정책 미검증, 미확정)';
  if (it.status === 'REVIEW' && it.finalJudgement) return `REVIEW_DONE · ${it.finalJudgement}`;
  if (it.status === 'REVIEW') return 'REVIEW · 작업자 확인 대기';
  if (it.status === 'FAILED') return 'FAILED · 분석 오류';
  if (it.status === 'ANALYZING') return 'AI 분석 중 · 접수 완료';
  return 'RECEIVED · 분석 대기';
}
function HistoryMockScreen() {
  const p = useLocalSearchParams<{ role?: string }>();
  const role: Role = p.role === 'ADMIN' ? 'ADMIN' : 'WORKER';
  const { ready, revision, warning } = useMockStoreState();
  const [items,setItems] = useState<Inspection[]>([]);
  useFocusEffect(useCallback(() => { if (ready) setItems(loadHistory()); }, [ready, revision]));
  const toMonitor = () => router.replace({ pathname: '/monitoring', params: { role } });
  return <SafeAreaView style={s.screen} edges={['top','bottom']}>
    <Stack.Screen options={{ headerShown: false }} />
    <View style={s.heading}>
      <Text style={s.title}>검사 이력</Text>
      <Text style={s.subtitle}>{role === 'ADMIN' ? '전체 검사·오류 기록 조회 · Mock' : '담당 범위 검사 기록 조회 · Mock'}</Text>
    </View>
    <ScrollView style={s.scroller} contentContainerStyle={s.body}>
      <View style={s.filterBox}>
        <Text style={s.boxTitle}>조회 조건</Text>
        <Text style={s.filterText}>기간: 전체     부품: 전체     상태: 전체</Text>
      </View>
      <Text style={s.sectionTitle}>최근 검사 · 선택 시 상세 이동</Text>
      {!ready ? <Text style={s.itemDescription}>저장된 Mock 기록 불러오는 중...</Text> : null}
      {warning ? <Text style={s.itemDescription}>{warning}</Text> : null}
      {items.map(it => <Pressable key={it.id} accessibilityRole="button"
        accessibilityLabel={`${it.id} 검사 상세 열기`}
        onPress={() => router.push({ pathname: '/inspection/[id]', params: { id: it.id, role } })}
        style={({ pressed }) => [s.item, pressed && { opacity: 0.72 }]}>
        <View style={s.itemTitleRow}>
          <View style={[s.detailPill, { backgroundColor: it.status === 'FAILED' ? '#FFF0ED' : it.status === 'REVIEW' ? '#FFF3E5' : it.status === 'AUTO_PASS_EXAMPLE' ? '#EAFBF2' : '#EBF1FF' }]}>
            <Text style={[s.detailPillText, { color: it.status === 'FAILED' ? C.red : it.status === 'REVIEW' ? C.amber : it.status === 'AUTO_PASS_EXAMPLE' ? C.green : C.blue }]}>상세 ›</Text>
          </View>
          <Text style={s.inspectionId}>{it.id} · {it.partCode}</Text>
        </View>
        <Text style={s.itemDescription}>{state(it)} · Mock</Text>
        <Text style={s.itemDate}>접수 시각: {it.capturedAt} · Mock</Text>
        {it.retryOf ? <Text style={s.itemDescription}>이전 FAILED 검사: {it.retryOf}</Text> : null}
      </Pressable>)}
      <Text style={s.disclaimer}>시연용 Mock 이력 · 기기에만 저장 · API/DB 미연동 · 삭제/재설치 시 초기화 가능</Text>
    </ScrollView>
    <View style={s.bottomNav}>
      <Pressable onPress={toMonitor} accessibilityRole="button" accessibilityLabel="모니터링" style={s.navItem}>
        <Text style={s.navIcon}>▣</Text><Text style={s.navText}>모니터링</Text>
      </Pressable>
      <View style={s.navItem} accessibilityLabel="현재 검사 이력 화면">
        <Text style={[s.navIcon,s.active]}>▤</Text><Text style={[s.navText,s.active]}>이력</Text>
      </View>
      <View style={s.navItem} accessibilityLabel="설정: 연결 예정">
        <Text style={s.navIcon}>⚙</Text><Text style={s.navText}>설정</Text>
      </View>
    </View>
  </SafeAreaView>;
}
/** 실제 로그인 화면은 SERVER 이력을, Mock 시연은 기존 로컬 이력을 사용합니다. */
export default function HistoryScreen() {
  const { mode } = useLocalSearchParams<{ mode?: string }>();
  return mode === 'live' ? <HistoryLiveScreenV4 /> : <HistoryMockScreen />;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  heading: { paddingHorizontal: 20, paddingTop: 9, paddingBottom: 22 },
  title: { color: C.ink, fontSize: 23, fontWeight: '700', lineHeight: 34 },
  subtitle: { color: C.muted, fontSize: 11, lineHeight: 18, marginTop: 1 },
  scroller: { flex: 1 }, body: { paddingHorizontal: 20, paddingBottom: 25, gap: 7 },
  filterBox: { borderWidth: 1, borderColor: C.border, backgroundColor: C.white, borderRadius: 14, padding: 13, gap: 7 },
  boxTitle: { fontSize: 13, lineHeight: 21, color: C.ink, fontWeight: '700' },
  filterText: { fontSize: 11, lineHeight: 18, color: C.muted },
  sectionTitle: { fontSize: 14, lineHeight: 23, color: C.ink, fontWeight: '700', marginTop: 4 },
  item: { borderWidth: 1, borderColor: C.border, backgroundColor: C.white, borderRadius: 13, paddingHorizontal: 12, paddingVertical: 8, gap: 3 },
  itemTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  detailPill: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 50 },
  detailPillText: { fontSize: 11, lineHeight: 16, fontWeight: '600' },
  inspectionId: { fontSize: 12, lineHeight: 20, color: C.ink, fontWeight: '700' },
  itemDescription: { fontSize: 11, lineHeight: 16, color: C.muted },
  itemDate: { fontSize: 10, lineHeight: 16, color: C.muted },
  disclaimer: { textAlign: 'center', color: C.muted, fontSize: 10, lineHeight: 16, paddingVertical: 9 },
  bottomNav: { marginHorizontal: 20, marginBottom: 6, height: 58, borderRadius: 15, backgroundColor: C.white, borderWidth: 1, borderColor: C.border, flexDirection: 'row' },
  navItem: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 1 },
  navIcon: { fontSize: 16, lineHeight: 24, color: C.muted },
  navText: { fontSize: 11, lineHeight: 17, color: C.muted },
  active: { color: C.blue, fontWeight: '700' },
});
