import React, { useMemo } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Stack, router, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { getMockInspectionHistory, useMockStoreState } from '../data/mockInspections';
import { calculateQualityStatistics } from '../data/qualityStatistics';

// Figma 공정 모니터링 디자인 톤을 적용한 추가 품질 통계 화면입니다.
// 실제 운영 통계나 AI 정확도가 아닌 로컬 Mock 검사 이력의 집계입니다.
type Role = 'ADMIN' | 'WORKER';
const C = {
  bg: '#F5F7FB', white: '#FFFFFF', line: '#E4E7EC', ink: '#111827',
  muted: '#64748B', blue: '#2054D8', bluePale: '#EBF1FF',
  red: '#B42318', redPale: '#FFF0ED', green: '#067647', greenPale: '#EAFBF2',
  amber: '#A74B12', amberPale: '#FFF3E5',
};

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return <View style={s.card}>
    <Text style={s.cardTitle}>{title}</Text>
    {children}
  </View>;
}
function Line({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <View style={s.line}>
    <Text style={s.lineLabel}>{label}</Text>
    <Text style={[s.lineValue, tone ? { color: tone } : undefined]}>{value}</Text>
  </View>;
}
function MiniCard({ label, value, tint, foreground }: { label: string; value: number; tint: string; foreground: string }) {
  return <View style={[s.miniCard, { backgroundColor: tint }]}>
    <Text style={[s.miniValue, { color: foreground }]}>{value}건</Text>
    <Text style={s.miniLabel}>{label}</Text>
  </View>;
}
function NavBar({ role }: { role: Role }) {
  return <View style={s.nav}>
    <Pressable accessibilityRole="button" style={s.navItem} onPress={() => router.replace({ pathname: '/monitoring', params: { role } })}>
      <Text style={s.navIcon}>▣</Text><Text style={s.navText}>모니터링</Text>
    </Pressable>
    <Pressable accessibilityRole="button" style={s.navItem} onPress={() => router.replace({ pathname: '/history', params: { role } })}>
      <Text style={s.navIcon}>▤</Text><Text style={s.navText}>이력</Text>
    </Pressable>
    <Pressable accessibilityRole="button" style={s.navItem} onPress={() => router.replace({ pathname: '/settings', params: { role } })}>
      <Text style={[s.navIcon, s.active]}>⚙</Text><Text style={[s.navText, s.active]}>설정</Text>
    </Pressable>
  </View>;
}

export default function QualityStatisticsScreen() {
  const params = useLocalSearchParams<{ role?: string }>();
  // 라우트의 역할 값은 시연 전용입니다. 실제 인증/인가로 사용하면 안 됩니다.
  const role: Role = params.role === 'ADMIN' ? 'ADMIN' : 'WORKER';
  const { ready, revision, warning } = useMockStoreState();
  const stats = useMemo(
    () => calculateQualityStatistics(ready ? getMockInspectionHistory() : []),
    [ready, revision],
  );
  const pct = stats.defectRatePercent === null ? '산출 불가' : `${stats.defectRatePercent.toFixed(1)}%`;

  return <SafeAreaView style={s.screen} edges={['top','bottom']}>
    <Stack.Screen options={{ headerShown: false }} />
    <View style={s.header}>
      <Text style={s.title}>품질 통계</Text>
      <Text style={s.subtitle}>검사·판정·오류 구분 · 시연용 로컬 Mock</Text>
    </View>
    {role !== 'ADMIN' ? (
      <View style={s.content}>
        <Card title="관리자 전용 화면">
          <Text style={s.note}>현장 작업자 역할에서는 전체 품질 통계를 조회할 수 없습니다.</Text>
          <Pressable accessibilityRole="button" style={s.primaryButton} onPress={() => router.replace({ pathname: '/settings', params: { role } })}>
            <Text style={s.primaryText}>설정으로 돌아가기</Text>
          </Pressable>
        </Card>
      </View>
    ) : (
      <ScrollView style={s.content} contentContainerStyle={s.body} showsVerticalScrollIndicator={false}>
        {!ready && <Text style={s.note}>기기에 저장된 시연 기록을 불러오는 중...</Text>}
        {warning && <Text style={s.warning}>{warning}</Text>}
        <Card title="검사 현황 · Mock">
          <Text style={s.note}>검사 ID 기준 접수 건수입니다. 재검사 접수는 새 검사로 계산합니다.</Text>
          <Line label="검사 접수 건수" value={ready ? `${stats.receivedTotal}건` : '불러오는 중'} tone={C.blue} />
          <View style={s.miniRow}>
            <MiniCard label="최종 정상 · PASS" value={stats.finalizedPass} tint={C.greenPale} foreground={C.green} />
            <MiniCard label="최종 불량 · FAIL" value={stats.finalizedFail} tint={C.redPale} foreground={C.red} />
          </View>
          <View style={s.miniRow}>
            <MiniCard label="작업자 확인 대기" value={stats.waitingForReview} tint={C.amberPale} foreground={C.amber} />
            <MiniCard label="AI 분석 실패" value={stats.analysisFailed} tint={C.redPale} foreground={C.red} />
          </View>
          <Line label="분석 중" value={`${stats.analyzing}건`} />
          <Line label="분석 접수·대기" value={`${stats.receivedPending}건`} />
          <Line label="재검사 신규 접수 (전체에 포함)" value={`${stats.retryInspections}건`} />
        </Card>
        <Card title="최종 불량률 · Mock">
          <View style={s.rateRow}>
            <Text style={[s.bigRate, { color: stats.defectRatePercent === null ? C.muted : C.ink }]}>{ready ? pct : '—'}</Text>
            <Text style={s.rateCaption}>최종 FAIL ÷ (최종 PASS + 최종 FAIL)</Text>
          </View>
          <Line label="확정 판정 분모" value={`${stats.finalizedTotal}건`} />
          <Line label="최종 불량 분자" value={`${stats.finalizedFail}건`} tone={C.red} />
          <Text style={s.note}>REVIEW 대기·분석 실패·분석 중·접수 대기 기록은 최종 정상/불량 및 불량률 분모에 포함하지 않습니다.</Text>
          {stats.finalizedTotal === 0 && ready ? <Text style={s.warning}>확정된 최종 판정이 없어 불량률을 계산하지 않습니다. 0%가 아닙니다.</Text> : null}
          {stats.finalizedTotal > 0 && ready ? <Text style={s.note}>확정 표본 {stats.finalizedTotal}건에 대한 단순 비율로, 전체 생산라인 품질을 대표하지 않습니다.</Text> : null}
        </Card>
        <Card title="집계에서 제외한 시연 예시">
          <Line label="AUTO_PASS · 시연 예시" value={`${stats.excludedAutoPassExamples}건`} />
          <Text style={s.note}>검증되지 않은 AUTO_PASS 예시는 운영 검사로 집계하지 않습니다. 실제 확정 AUTO_PASS 건수는 현재 데이터에 존재하지 않습니다.</Text>
        </Card>
        <View style={s.notice}><Text style={s.noticeText}>이 통계는 AI 정확도가 아닙니다. 로컬 Mock 검사 기록만 계산하며 실제 서버·DB·검증된 자동 통과 정책과 연결되어 있지 않습니다.</Text></View>
        <Pressable accessibilityRole="button" style={s.primaryButton} onPress={() => router.push({ pathname: '/history', params: { role } })}>
          <Text style={s.primaryText}>검사 이력에서 개별 기록 확인</Text>
        </Pressable>
      </ScrollView>
    )}
    <NavBar role={role} />
  </SafeAreaView>;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  header: { paddingHorizontal: 20, paddingTop: 9, paddingBottom: 25 },
  title: { fontSize: 23, lineHeight: 34, fontWeight: '700', color: C.ink },
  subtitle: { color: C.muted, fontSize: 11, lineHeight: 18, marginTop: 1 },
  content: { flex: 1 },
  body: { paddingHorizontal: 20, paddingBottom: 28, gap: 10 },
  card: { backgroundColor: C.white, borderWidth: 1, borderColor: C.line, borderRadius: 14, padding: 13, gap: 9 },
  cardTitle: { fontSize: 13, lineHeight: 21, fontWeight: '700', color: C.ink },
  line: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  lineLabel: { color: C.muted, fontSize: 11, lineHeight: 18, flex: 0.56 },
  lineValue: { color: C.ink, fontSize: 11, lineHeight: 18, flex: 0.44, textAlign: 'right', fontWeight: '600' },
  miniRow: { flexDirection: 'row', gap: 8 },
  miniCard: { flex: 1, minWidth: 0, borderRadius: 12, padding: 11, gap: 6 },
  miniValue: { fontSize: 21, lineHeight: 28, fontWeight: '700' },
  miniLabel: { fontSize: 10, lineHeight: 16, fontWeight: '500', color: C.ink },
  rateRow: { gap: 5, paddingVertical: 3 },
  bigRate: { fontSize: 30, lineHeight: 38, fontWeight: '700' },
  rateCaption: { color: C.muted, fontSize: 11, lineHeight: 18 },
  note: { color: C.muted, fontSize: 11, lineHeight: 18 },
  warning: { color: C.red, fontSize: 11, lineHeight: 18 },
  notice: { borderRadius: 10, padding: 10, backgroundColor: C.bluePale },
  noticeText: { fontSize: 10, lineHeight: 17, color: C.blue },
  primaryButton: { minHeight: 44, backgroundColor: C.blue, borderRadius: 12, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12, marginTop: 3 },
  primaryText: { fontSize: 13, lineHeight: 20, color: C.white, fontWeight: '700' },
  nav: { height: 58, marginHorizontal: 20, marginBottom: 6, backgroundColor: C.white, borderWidth: 1, borderColor: C.line, borderRadius: 15, flexDirection: 'row', alignItems: 'center' },
  navItem: { flex: 1, minHeight: 46, alignItems: 'center', justifyContent: 'center', gap: 1 },
  navIcon: { fontSize: 16, lineHeight: 24, color: C.muted },
  navText: { fontSize: 11, lineHeight: 17, color: C.muted, fontWeight: '500' },
  active: { color: C.blue, fontWeight: '700' },
});
