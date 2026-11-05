import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack, router, useLocalSearchParams } from 'expo-router';
import { getMockInspection, useMockStoreState } from '../../data/mockInspections';

// Figma: 99:464 판정 제출 결과, 2026-10-27 검토.
// 화면의 판정 결과는 시연용 메모리 저장이며 서버/API 응답이 아닙니다.
const C = { bg: '#F5F7FB', white: '#FFFFFF', border: '#E4E7EC',
  ink: '#111827', muted: '#64748B', blue: '#2054D8', pale: '#EEF2F8',
  red: '#B42318', green: '#067647' };
type Role = 'WORKER' | 'ADMIN';

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return <View style={s.row}>
    <Text style={s.rowLabel}>{label}</Text>
    <Text style={[s.rowValue, color ? { color } : undefined]}>{value}</Text>
  </View>;
}
function Button({ title, secondary = false, onPress }: {
  title: string; secondary?: boolean; onPress: () => void;
}) {
  return <Pressable accessibilityRole="button" onPress={onPress}
    style={({ pressed }) => [s.button, secondary ? s.buttonSecondary : s.buttonPrimary, pressed && { opacity: 0.8 }]}>
    <Text style={[s.buttonText, secondary ? { color: C.ink } : { color: C.white }]}>{title}</Text>
  </Pressable>;
}

export default function InspectionResultScreen() {
  const params = useLocalSearchParams<{ id?: string; role?: string }>();
  const id = typeof params.id === 'string' ? params.id : '';
  const role: Role = params.role === 'ADMIN' ? 'ADMIN' : 'WORKER';
  const { ready, revision, warning } = useMockStoreState();
  // revision 구독으로 로컬 저장소 복원 및 판정 변경 후 자동 재조회됩니다.
  void revision;
  const inspection = ready ? getMockInspection(id) : null;
  const finalized = inspection?.status === 'REVIEW' && !!inspection.finalJudgement;
  const toHistory = () => router.replace({ pathname: '/history', params: { role } });
  const toMonitoring = () => router.replace({ pathname: '/monitoring', params: { role } });
  return <SafeAreaView style={s.screen} edges={['top','bottom']}>
    <Stack.Screen options={{ headerShown: false }} />
    <View style={s.heading}>
      <Text style={s.title}>판정 제출 결과</Text>
      <Text style={s.subtitle}>작업자 확인 · 저장 성공 시연 · Mock</Text>
    </View>
    <ScrollView style={s.scroller} contentContainerStyle={s.body}>
      {!ready ? <View style={s.summary}><Text style={s.cardTitle}>저장된 기록 불러오는 중</Text></View> : !finalized ? <View style={s.summary}>
        <Text style={s.cardTitle}>판정 기록을 확인할 수 없습니다</Text>
        <Text style={s.note}>저장된 판정이 없거나 아직 최종 판정을 제출하지 않았습니다.</Text>
        <Text style={s.note}>모니터링으로 돌아가 WORKER로 REVIEW 판정을 다시 제출해 주세요.</Text>
      </View> : <View style={s.summary}>
        <Text style={s.cardTitle}>판정 제출 성공 · 시연 예시</Text>
        <Text style={s.note}>실제 API·DB 저장 완료 근거가 아닙니다.</Text>
        <View style={s.pill}>
          <Text style={[s.pillText, { color: inspection.finalJudgement === 'FAIL' ? C.red : C.green }]}>
            {inspection.finalJudgement} · 작업자 선택
          </Text>
        </View>
        <Row label="검사 ID" value={inspection.id} />
        <Row label="AI 최초 예측" value={inspection.prediction === 'DEFECT' ? '불량 쪽 예측 · Mock' : inspection.prediction === 'GOOD' ? '정상 쪽 예측 · Mock' : '미제공'} />
        <Row label="정책 결과" value="REVIEW" />
        <Row label="작업자 최종 판정" value={`${inspection.finalJudgement} · Mock`}
          color={inspection.finalJudgement === 'FAIL' ? C.red : C.green} />
        <Row label="확인 시각" value={inspection.confirmedAt ?? '미제공'} />
      </View>}
      <Button title="검사 이력에서 확인" onPress={toHistory} />
      <Button title="모니터링으로 이동" secondary onPress={toMonitoring} />
      <View style={s.notice}>
        <Text style={s.noticeText}>시연용 Mock 기록 · 이 기기에만 저장됩니다. 실제 서버/API·DB와 연결되지 않았으며 앱 삭제·데이터 초기화 시 사라질 수 있습니다.</Text>
        {warning ? <Text style={s.noticeText}>{warning}</Text> : null}
      </View>
    </ScrollView>
    <View style={s.bottomNav}>
      <Pressable accessibilityRole="button" accessibilityLabel="모니터링" style={s.navItem} onPress={toMonitoring}>
        <Text style={s.navIcon}>▣</Text><Text style={s.navText}>모니터링</Text>
      </Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="이력" style={s.navItem} onPress={toHistory}>
        <Text style={[s.navIcon,s.active]}>▤</Text><Text style={[s.navText,s.active]}>이력</Text>
      </Pressable>
      <View style={s.navItem} accessibilityLabel="설정: 연결 예정">
        <Text style={s.navIcon}>⚙</Text><Text style={s.navText}>설정</Text>
      </View>
    </View>
  </SafeAreaView>;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  heading: { paddingHorizontal: 20, paddingTop: 9, paddingBottom: 22 },
  title: { fontSize: 23, lineHeight: 34, fontWeight: '700', color: C.ink },
  subtitle: { fontSize: 11, lineHeight: 18, color: C.muted, marginTop: 1 },
  scroller: { flex: 1 }, body: { paddingHorizontal: 20, gap: 10, paddingBottom: 24 },
  summary: { backgroundColor: C.pale, borderRadius: 14, padding: 13, borderColor: C.border, borderWidth: 1, gap: 7 },
  cardTitle: { color: C.ink, fontSize: 13, fontWeight: '700', lineHeight: 20 },
  note: { color: C.muted, fontSize: 11, lineHeight: 18 },
  pill: { backgroundColor: '#FFF0ED', paddingVertical: 5, paddingHorizontal: 10, borderRadius: 50, alignSelf: 'flex-start' },
  pillText: { fontSize: 11, fontWeight: '600' },
  row: { flexDirection: 'row', gap: 8, justifyContent: 'space-between', alignItems: 'flex-start' },
  rowLabel: { color: C.muted, fontSize: 11, lineHeight: 18, flex: 0.45 },
  rowValue: { color: C.ink, fontSize: 11, fontWeight: '500', textAlign: 'right', lineHeight: 18, flex: 0.55 },
  button: { height: 44, justifyContent: 'center', alignItems: 'center', borderRadius: 12 },
  buttonPrimary: { backgroundColor: C.blue },
  buttonSecondary: { backgroundColor: C.white, borderWidth: 1, borderColor: C.border },
  buttonText: { fontSize: 13, fontWeight: '700' },
  notice: { backgroundColor: '#EBF1FF', borderRadius: 10, padding: 9 },
  noticeText: { fontSize: 10, color: C.blue, lineHeight: 16 },
  bottomNav: { height: 58, marginHorizontal: 20, marginBottom: 6, backgroundColor: C.white, borderRadius: 15, borderWidth: 1, borderColor: C.border, flexDirection: 'row' },
  navItem: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 1 },
  navIcon: { fontSize: 16, lineHeight: 24, color: C.muted },
  navText: { fontSize: 11, color: C.muted, lineHeight: 17 },
  active: { color: C.blue, fontWeight: '700' },
});
