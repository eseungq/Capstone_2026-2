/**
 * 73단계: 모니터링 요약, DOOR, REVIEW/FAILED 목록, 신규 이벤트가 동일한
 * CONTRACT_EXAMPLE 폴링 스냅샷을 공유합니다. 실제 설비/서버/푸시와 무관합니다.
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useMonitoringDemoSessionV4 } from '../api/backendV4/monitoringDemoSessionV4';
import { buildMonitoringViewModelV4 } from '../api/backendV4/monitoringViewModelV4';

function statusLabel(status: string): string {
  switch (status) {
    case 'ready': return '정상 조회';
    case 'loading': return '조회 중';
    case 'error': return '조회 실패 · 마지막 정상 데이터 유지';
    case 'paused': return '일시정지';
    case 'stopped': return '중단';
    default: return '첫 조회 대기';
  }
}
function dateLabel(value: string | null): string {
  if (!value) return '미제공';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '시각 미확인' : d.toLocaleString('ko-KR');
}

export default function MonitoringDashboardV4() {
  const { snapshot, events, diagnostics, addReview, addFailed, failOnce, added } = useMonitoringDemoSessionV4();
  const vm = buildMonitoringViewModelV4(snapshot);
  const lastSuccess = snapshot.lastSuccessAtMs === null
    ? '아직 없음' : new Date(snapshot.lastSuccessAtMs).toLocaleTimeString('ko-KR');

  return (
    <View style={s.wrapper}>
      <View style={s.card}>
        <Text style={s.title}>공정 모니터링 · 5초 갱신</Text>
        <Text style={s.description}>CONTRACT_EXAMPLE · 가상 시연 · 서버·푸시 미연결</Text>
        <View style={s.row}><Text style={s.muted}>갱신 상태</Text><Text style={[s.value, snapshot.status === 'error' && s.danger]}>{statusLabel(vm.status)}</Text></View>
        <View style={s.row}><Text style={s.muted}>성공 조회</Text><Text style={s.value}>{vm.successfulPolls}회</Text></View>
        <View style={s.row}><Text style={s.muted}>마지막 정상 조회</Text><Text style={s.value}>{lastSuccess}</Text></View>
        <View style={s.row}><Text style={s.muted}>다음 조회</Text><Text style={s.value}>{vm.nextDelayMs === null ? '예약 없음' : `${vm.nextDelayMs / 1000}초`}</Text></View>
        {snapshot.error && <Text style={s.errorText}>가상 조회 오류: {snapshot.error}</Text>}
        {vm.isStale && vm.hasSuccessfulRead && <Text style={s.warning}>마지막 정상 데이터입니다. 현재 상태와 다를 수 있습니다.</Text>}
      </View>

      <View style={s.card}>
        <Text style={s.title}>74단계 · 화면 이탈·백그라운드 진단</Text>
        <Text style={s.description}>실제 탭 이동과 앱 비활성 전환을 기록합니다. 서버 통신을 하지 않는 Mock 진단입니다.</Text>
        <View style={s.row}><Text style={s.muted}>현재 화면</Text><Text style={s.value}>{diagnostics.screenFocused ? '모니터링 활성' : '이탈 상태'}</Text></View>
        <View style={s.row}><Text style={s.muted}>앱 상태</Text><Text style={s.value}>{diagnostics.appForeground ? '전면 (활성)' : '비활성 / 백그라운드'}</Text></View>
        <View style={s.row}><Text style={s.muted}>누적 조회 시도</Text><Text style={s.value}>{diagnostics.totalAttempts}회</Text></View>
        <View style={s.row}><Text style={s.muted}>화면 이동 중 조회 중단</Text>
          <Text style={[s.value, diagnostics.screenCheck && !diagnostics.screenCheck.passed && s.danger]}>
            {diagnostics.screenCheck === null ? '미검증' : diagnostics.screenCheck.passed
              ? `확인 (이탈 중 ${diagnostics.screenCheck.unexpectedAttempts}회)` : `확인 필요 (${diagnostics.screenCheck.unexpectedAttempts}회)`}
          </Text>
        </View>
        {diagnostics.screenCheck && <Text style={s.smallNote}>최근 화면 이탈 유지: {(diagnostics.screenCheck.pauseMs / 1000).toFixed(1)}초 · 이탈 중 완료된 조회: {diagnostics.screenCheck.unexpectedSuccesses}회</Text>}
        <View style={s.row}><Text style={s.muted}>앱 비활성 중 조회 중단</Text>
          <Text style={[s.value, diagnostics.backgroundCheck && !diagnostics.backgroundCheck.passed && s.danger]}>
            {diagnostics.backgroundCheck === null ? '미검증' : diagnostics.backgroundCheck.passed
              ? `확인 (비활성 중 ${diagnostics.backgroundCheck.unexpectedAttempts}회)` : `확인 필요 (${diagnostics.backgroundCheck.unexpectedAttempts}회)`}
          </Text>
        </View>
        {diagnostics.backgroundCheck && <Text style={s.smallNote}>최근 비활성 유지: {(diagnostics.backgroundCheck.pauseMs / 1000).toFixed(1)}초 · 비활성 중 완료된 조회: {diagnostics.backgroundCheck.unexpectedSuccesses}회</Text>}
        <Text style={s.smallNote}>최근 기록 (최대 6개)</Text>
        {diagnostics.recentEvents.slice(0, 6).map((event, index) => (
          <Text key={`${event.timestampMs}-${index}`} style={s.logLine}>
            {new Date(event.timestampMs).toLocaleTimeString('ko-KR')} · {event.event}
          </Text>
        ))}
        <Text style={s.notice}>검증 절차: 이력 탭 20초 → 모니터링 복귀, 이어서 iPhone에서 다른 앱/홈 화면 20초 → 복귀. 각 항목이 '확인 (0회)'로 바뀌는지 살펴보세요. 서버 API 및 푸시 미연결 상태입니다.</Text>
      </View>

      <Text style={s.sectionTitle}>부품별 단일 라인</Text>
      <View style={s.card}>
        <Text style={s.title}>DOOR · {vm.door?.partName ?? '첫 조회 대기'}</Text>
        <Text style={s.description}>모델 지원: {vm.door ? (vm.door.modelAvailable ? '확인됨' : '미지원') : '조회 전'} · 정책: {vm.door ? (vm.door.policyActive ? '적용 중' : '미적용') : '조회 전'}</Text>
        <Text style={s.description}>최근 접수: {dateLabel(vm.door?.lastReceivedAt ?? null)}</Text>
        <View style={s.miniRow}>
          <View style={s.mini}><Text style={s.blueCount}>{vm.hasSuccessfulRead ? `${vm.reviewCount}건` : '—'}</Text><Text style={s.muted}>작업자 REVIEW 대기</Text></View>
          <View style={s.mini}><Text style={s.redCount}>{vm.hasSuccessfulRead ? `${vm.failedCount}건` : '—'}</Text><Text style={s.muted}>AI 분석 FAILED</Text></View>
        </View>
        <Text style={s.smallNote}>REVIEW는 최종 FAIL이 아니며, FAILED는 제품 불량 판정이 아닙니다.</Text>
      </View>

      <Text style={s.sectionTitle}>최근 접수 · 가상 데이터</Text>
      <View style={s.card}>
        {!vm.door || vm.door.recent.length === 0 ? <Text style={s.description}>최근 접수 기록 없음 / 조회 대기</Text> :
          [...vm.door.recent].reverse().slice(0, 5).map((item) => (
            <View style={s.listRow} key={item.inspectionId}>
              <Text style={s.value}>{item.inspectionNo ?? '검사번호 미제공'} · {item.displayState}</Text>
              <Text style={s.description}>{dateLabel(item.receivedAt)} · 원본/썸네일 미제공</Text>
            </View>
          ))}
        <Text style={s.smallNote}>이 목록의 DEMO ID는 서버 검사 UUID로 화면 상세 조회하지 않습니다.</Text>
      </View>

      <Text style={s.sectionTitle}>확인 필요 및 분석 오류 · 가상 대기열</Text>
      <View style={s.card}>
        {!vm.hasSuccessfulRead ? <Text style={s.description}>조회 전입니다.</Text> : vm.queue.length === 0 ? <Text style={s.description}>대기·분석 실패 항목이 없습니다.</Text> :
          vm.queue.slice(0, 20).map((item) => (
            <View key={item.inspectionId} style={s.listRow}>
              <View style={s.badgeRow}>
                <Text style={[s.pill, item.displayState === 'FAILED' ? s.failedPill : s.reviewPill]}>{item.displayState === 'FAILED' ? 'FAILED' : 'REVIEW'}</Text>
                <Text style={s.value}>{item.inspectionNo ?? '검사번호 미제공'} · {item.partCode}</Text>
              </View>
              <Text style={s.description}>{item.displayState === 'FAILED' ? `AI 분석 오류 · ${item.errorCode ?? '상세 미제공'}` : `AI 예측: ${item.predictedQuality ?? '미제공'} · 작업자 확인 대기`}</Text>
              <Text style={s.description}>접수: {dateLabel(item.receivedAt)}</Text>
            </View>
          ))}
        {vm.queue.length > 20 && <Text style={s.smallNote}>대기열 총 {vm.queue.length}건 중 20건만 미리보기로 표시합니다. 요약 건수는 전체 수집 결과 기준입니다.</Text>}
      </View>

      <View style={s.card}>
        <Text style={s.title}>새로 감지한 알림 후보 · {events.length}건</Text>
        {events.length ? events.slice(0, 8).map((event) => <Text key={`${event.inspectionId}:${event.kind}`} style={s.event}>{event.kind} · {event.inspectionNo ?? '검사번호 미제공'}</Text>) :
          <Text style={s.description}>새 알림 없음 · 최초 조회의 기존 대기 항목은 제외</Text>}
        <View style={s.buttonRow}>
          <Pressable accessibilityRole="button" style={s.button} onPress={addReview}><Text style={s.buttonText}>가상 REVIEW 추가</Text></Pressable>
          <Pressable accessibilityRole="button" style={s.button} onPress={addFailed}><Text style={s.buttonText}>가상 FAILED 추가</Text></Pressable>
        </View>
        <Pressable accessibilityRole="button" style={s.outline} onPress={failOnce}><Text style={s.outlineText}>다음 조회에서 가상 오류 1회</Text></Pressable>
        <Text style={s.description}>이 세션에서 추가한 가상 검사 {added}건 · 화면 이동 후에도 유지 (앱 재시작 시 초기화)</Text>
        <Text style={s.notice}>이 화면의 공정 카드·대기열·알림은 동일한 가상 조회 결과를 사용합니다. 기존 INS 검사 기록·PASS/FAIL·AsyncStorage·품질 통계에는 반영되지 않습니다.</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrapper: { gap: 9, paddingBottom: 8 },
  card: { backgroundColor: '#FFFFFF', borderColor: '#E4E7EC', borderWidth: 1, borderRadius: 15, padding: 16, gap: 12 },
  title: { fontWeight: '700', color: '#111827', fontSize: 17, lineHeight: 24 },
  sectionTitle: { fontWeight: '700', color: '#111827', fontSize: 15, marginTop: 3 },
  muted: { color: '#64748B', fontSize: 12, lineHeight: 19 },
  description: { color: '#64748B', fontSize: 12, lineHeight: 19, flexShrink: 1 },
  value: { color: '#111827', fontSize: 12, fontWeight: '600', flexShrink: 1, textAlign: 'right' },
  row: { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
  miniRow: { flexDirection: 'row', gap: 8 },
  mini: { flex: 1, backgroundColor: '#F2F5FC', padding: 12, borderRadius: 12, gap: 3 },
  blueCount: { fontSize: 22, fontWeight: '800', color: '#2458D8' },
  redCount: { fontSize: 22, fontWeight: '800', color: '#B42318' },
  smallNote: { color: '#74829B', fontSize: 11, lineHeight: 17 },
  listRow: { borderTopWidth: 1, borderTopColor: '#EDF0F5', paddingTop: 10, gap: 5 },
  badgeRow: { flexDirection: 'row', gap: 9, alignItems: 'center' },
  pill: { overflow: 'hidden', borderRadius: 99, paddingVertical: 5, paddingHorizontal: 10, fontSize: 11, fontWeight: '700' },
  failedPill: { backgroundColor: '#FFF0ED', color: '#B42318' },
  reviewPill: { backgroundColor: '#FFF3E5', color: '#A74B12' },
  event: { color: '#24304B', backgroundColor: '#F1F4FA', padding: 10, borderRadius: 8, fontSize: 12 },
  buttonRow: { flexDirection: 'row', gap: 8 },
  button: { flex: 1, paddingVertical: 12, paddingHorizontal: 7, borderRadius: 10, backgroundColor: '#2457E1', alignItems: 'center' },
  buttonText: { fontSize: 11, fontWeight: '700', color: '#FFFFFF', textAlign: 'center' },
  outline: { borderRadius: 10, borderWidth: 1, borderColor: '#C2CDE3', padding: 12, alignItems: 'center' },
  outlineText: { color: '#2457E1', fontSize: 12, fontWeight: '700', textAlign: 'center' },
  errorText: { color: '#B42318', fontSize: 12 },
  danger: { color: '#B42318' },
  warning: { color: '#A74B12', fontSize: 12, lineHeight: 19 },
  logLine: { color: '#64748B', fontSize: 11, lineHeight: 17 },
  notice: { fontSize: 12, lineHeight: 19, color: '#2356B6', backgroundColor: '#ECF1FF', padding: 10, borderRadius: 9 },
});
