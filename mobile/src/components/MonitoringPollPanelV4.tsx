/**
 * 71단계: 기존 모니터링 화면에 '가상 5초 갱신' 상태를 안전하게 추가하는 카드.
 * 기존 monitoring.tsx, Mock 기록, AsyncStorage, 품질 통계는 변경하지 않습니다.
 * 실제 API/푸시 연동이 아니며, 이 카드의 자료는 CONTRACT_EXAMPLE입니다.
 *
 * 한 화면에 하나의 인스턴스만 렌더링하세요.
 * 활성 탭이 모니터링이 아닐 땐 컴포넌트를 언마운트하거나 enabled=false로 사용하세요.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { createMonitoringDemoReaderV4 } from '../api/backendV4/monitoringPollExamples';
import { useMonitoringPollV4 } from '../api/backendV4/useMonitoringPollV4';
import type { MonitorAlertV4 } from '../api/backendV4/monitoringPollCore';

type Props = { enabled?: boolean };

function stateText(status: string) {
  switch (status) {
    case 'ready': return '정상 조회';
    case 'loading': return '조회 중';
    case 'error': return '조회 실패 · 마지막 정상 데이터 유지';
    case 'paused': return '일시정지';
    case 'stopped': return '중단';
    default: return '상태 확인 중';
  }
}

export default function MonitoringPollPanelV4({ enabled = true }: Props) {
  // 렌더링마다 reader가 바뀌면 컨트롤러와 기준선이 리셋됩니다. 반드시 안정적으로 고정.
  const reader = useMemo(() => createMonitoringDemoReaderV4(), []);
  const { snapshot, controller } = useMonitoringPollV4(reader, enabled);
  const [events, setEvents] = useState<MonitorAlertV4[]>([]);
  const [added, setAdded] = useState(0);

  // snapshot.alerts는 '마지막 조회의 신규 이벤트'만 담으므로 별도 목록으로 누적.
  useEffect(() => controller.subscribeAlerts((batch) => {
    setEvents((previous) => {
      const existing = new Set(previous.map((x) => `${x.inspectionId}:${x.kind}`));
      const fresh = batch.filter((x) => !existing.has(`${x.inspectionId}:${x.kind}`));
      return [...fresh, ...previous].slice(0, 10);
    });
  }), [controller]);

  const reviewCount = snapshot.queue.filter(x => x.displayState === 'REVIEW_PENDING').length;
  const failedCount = snapshot.queue.filter(x => x.displayState === 'FAILED').length;
  const lastSuccess = snapshot.lastSuccessAtMs === null
    ? '아직 없음'
    : new Date(snapshot.lastSuccessAtMs).toLocaleTimeString('ko-KR');
  const firstPart = snapshot.parts.find(x => x.partCode === 'DOOR');

  return (
    <View style={styles.card} accessibilityLabel="가상 5초 갱신 상태 카드">
      <Text style={styles.heading}>5초 자동 갱신 · 화면 연동 시연</Text>
      <Text style={styles.description}>CONTRACT_EXAMPLE (가상) · 서버·푸시 연결 전</Text>
      <View style={styles.line}>
        <Text style={styles.label}>갱신 상태</Text>
        <Text style={[styles.value, snapshot.status === 'error' && styles.error]}>{stateText(snapshot.status)}</Text>
      </View>
      <View style={styles.line}>
        <Text style={styles.label}>성공 조회</Text>
        <Text style={styles.value}>{snapshot.successfulPolls}회</Text>
      </View>
      <View style={styles.line}>
        <Text style={styles.label}>최근 정상 조회</Text>
        <Text style={styles.value}>{lastSuccess}</Text>
      </View>
      <View style={styles.line}>
        <Text style={styles.label}>다음 조회</Text>
        <Text style={styles.value}>{snapshot.nextDelayMs === null ? '예약 없음' : `${snapshot.nextDelayMs / 1000}초`}</Text>
      </View>
      <View style={styles.summary}>
        <View style={styles.miniCard}>
          <Text style={styles.miniValue}>{reviewCount}건</Text>
          <Text style={styles.miniLabel}>REVIEW 대기</Text>
        </View>
        <View style={styles.miniCard}>
          <Text style={[styles.miniValue, styles.error]}>{failedCount}건</Text>
          <Text style={styles.miniLabel}>FAILED</Text>
        </View>
      </View>
      <Text style={styles.description}>
        {firstPart ? `DOOR · 모델 지원 ${firstPart.modelAvailable ? '표시됨' : '미확인'} · 정책 ${firstPart.policyActive ? '적용 중' : '미적용'}` : 'DOOR 카드 첫 조회 대기 중'}
      </Text>
      {snapshot.error !== null && <Text style={styles.errorText}>가상 조회 오류: {snapshot.error} · 기존 조회 결과 보존</Text>}
      <Text style={styles.sectionTitle}>새로 감지한 알림 후보 · {events.length}건</Text>
      {events.length === 0 ? <Text style={styles.description}>신규 이벤트 없음 (첫 조회의 기존 대기 건 제외)</Text> :
        events.slice(0, 4).map((event) => (
          <Text style={styles.event} key={`${event.inspectionId}:${event.kind}`}>
            {event.kind} · {event.inspectionNo ?? '검사번호 미제공'}
          </Text>
        ))}
      <View style={styles.buttons}>
        <Pressable accessibilityRole="button" style={styles.button} onPress={() => { reader.addReview(); setAdded(n => n + 1); }}>
          <Text style={styles.buttonText}>가상 REVIEW 추가</Text>
        </Pressable>
        <Pressable accessibilityRole="button" style={styles.button} onPress={() => { reader.addFailed(); setAdded(n => n + 1); }}>
          <Text style={styles.buttonText}>가상 FAILED 추가</Text>
        </Pressable>
      </View>
      <Pressable accessibilityRole="button" style={styles.outline} onPress={() => reader.failOnce()}>
        <Text style={styles.outlineText}>다음 조회에서 가상 오류 1회</Text>
      </Pressable>
      <Text style={styles.description}>이번 카드에서 추가한 가상 검사 {added}건 · 다음 조회 때 반영</Text>
      <Text style={styles.notice}>
        이 카드의 대기·실패·알림 수치는 다른 Mock 검사 이력 및 품질 통계에 반영되지 않습니다. 실제 공정 상태를 나타내지 않습니다.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: '#FFFFFF', borderRadius: 18, borderWidth: 1, borderColor: '#DDE3ED', padding: 16, marginVertical: 10, gap: 12 },
  heading: { color: '#182236', fontSize: 18, fontWeight: '700', lineHeight: 26 },
  sectionTitle: { color: '#182236', fontSize: 15, fontWeight: '700' },
  description: { color: '#6E7E98', fontSize: 12, lineHeight: 19 },
  line: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 },
  label: { color: '#6E7E98', fontSize: 13, flexShrink: 1 },
  value: { color: '#182236', fontSize: 13, fontWeight: '600', textAlign: 'right', flexShrink: 1 },
  summary: { flexDirection: 'row', gap: 8 },
  miniCard: { flex: 1, backgroundColor: '#F2F5FC', borderRadius: 12, padding: 12, gap: 4 },
  miniValue: { fontSize: 20, color: '#2458D8', fontWeight: '800' },
  miniLabel: { fontSize: 12, color: '#64748B' },
  event: { backgroundColor: '#F1F4FA', padding: 10, borderRadius: 8, color: '#24304B', fontSize: 12 },
  buttons: { flexDirection: 'row', gap: 8 },
  button: { flex: 1, paddingVertical: 12, paddingHorizontal: 7, backgroundColor: '#2457E1', borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  buttonText: { color: '#FFFFFF', fontWeight: '700', fontSize: 11, textAlign: 'center' },
  outline: { padding: 12, borderWidth: 1, borderRadius: 10, borderColor: '#C2CDE3', alignItems: 'center' },
  outlineText: { color: '#2457E1', fontSize: 12, fontWeight: '700' },
  error: { color: '#B42318' },
  errorText: { color: '#B42318', fontSize: 12, lineHeight: 19 },
  notice: { color: '#2356B6', backgroundColor: '#ECF1FF', fontSize: 12, lineHeight: 20, padding: 10, borderRadius: 9 },
});
