import { router } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { liveMonitoringReaderV4 } from '../api/backendV4/monitoringLiveReaderV4';
import { useMonitoringPollV4 } from '../api/backendV4/useMonitoringPollV4';
import { buildMonitoringViewModelV4 } from '../api/backendV4/monitoringViewModelV4';
import {
  advanceMonitoringObservationV4,
  createMonitoringObservationStateV4,
  elapsedFromReceiptV4,
} from '../api/backendV4/monitoringObservationV4';

function timeText(ms: number | null): string {
  return ms === null ? '미관측' : new Date(ms).toLocaleTimeString('ko-KR', { hour12: false });
}
function receiptText(iso: string): string {
  const parsed = Date.parse(iso);
  return Number.isFinite(parsed) ? timeText(parsed) : '미제공';
}
function secondsText(receivedAt: string, detectedAtMs: number): string {
  const elapsed = elapsedFromReceiptV4(receivedAt, detectedAtMs);
  return elapsed === null
    ? '측정 불가(서버·기기 시계 확인)'
    : `${(elapsed / 1000).toFixed(1)}초`;
}

const MONITORED_PARTS = ['DOOR', 'FRAME', 'COWL_COVER'] as const;
type MonitoredPart = (typeof MONITORED_PARTS)[number];

export default function MonitoringLiveDashboardV4() {
  const { snapshot } = useMonitoringPollV4(liveMonitoringReaderV4);
  const [partCode, setPartCode] = useState<MonitoredPart>('DOOR');
  const vm = buildMonitoringViewModelV4(snapshot, partCode);
  // 두 공정 모두 매 폴링에 관측해, 공정 선택 시 과거 데이터를 신규 접수로 오인하지 않습니다.
  const [observationsByPart, setObservationsByPart] = useState(() => ({
    DOOR: createMonitoringObservationStateV4(),
    FRAME: createMonitoringObservationStateV4(),
    COWL_COVER: createMonitoringObservationStateV4(),
  }));
  const [visibleQueueCount, setVisibleQueueCount] = useState(20);

  useEffect(() => {
    setObservationsByPart((previous) => {
      const door = advanceMonitoringObservationV4(previous.DOOR, snapshot, 'DOOR');
      const frame = advanceMonitoringObservationV4(previous.FRAME, snapshot, 'FRAME');
      const cowlCover = advanceMonitoringObservationV4(previous.COWL_COVER, snapshot, 'COWL_COVER');
      return door === previous.DOOR && frame === previous.FRAME && cowlCover === previous.COWL_COVER
        ? previous : { DOOR: door, FRAME: frame, COWL_COVER: cowlCover };
    });
  }, [snapshot]);

  const observation = observationsByPart[partCode];
  const lastSuccess = timeText(snapshot.lastSuccessAtMs);
  const countChange = observation.latestReviewCountChange;
  const latestDetection = observation.latestDetection;
  const latestTransition = observation.latestStateChange;
  const recentStates = [...observation.observations]
    .filter((item) => item.partCode === partCode)
    .sort((a, b) => Date.parse(b.receivedAt) - Date.parse(a.receivedAt))
    .slice(0, 5);

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>실제 서버 모니터링</Text>
        <Text style={styles.note}>SERVER · 백엔드 API · 기본 5초 갱신</Text>
        <Text>조회 상태: {snapshot.status}</Text>
        <Text>성공 조회: {snapshot.successfulPolls}회</Text>
        <Text>마지막 정상 조회: {lastSuccess}</Text>
        {snapshot.error && <Text style={styles.error}>서버 오류: {snapshot.error}</Text>}
        {vm.isStale && vm.hasSuccessfulRead && (
          <Text style={styles.warning}>마지막 정상 데이터입니다. 현재 상태와 다를 수 있습니다.</Text>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.title}>공정 선택</Text>
        <View style={styles.partSelector}>
          {MONITORED_PARTS.map((code) => (
            <Pressable
              key={code}
              accessibilityRole="button"
              accessibilityState={{ selected: partCode === code }}
              style={[styles.partButton, partCode === code && styles.partButtonActive]}
              onPress={() => {
                setPartCode(code);
                setVisibleQueueCount(20);
              }}
            >
              <Text style={[styles.partButtonText, partCode === code && styles.partButtonTextActive]}>
                {code}
              </Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.note}>선택한 공정의 실서버 현황과 대기열을 표시합니다.</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.title}>{partCode} 공정 현황</Text>
        {!vm.part ? (
          <Text>{vm.hasSuccessfulRead ? '서버 응답에 해당 부품 정보가 없습니다.' : '공정 데이터 조회 대기'}</Text>
        ) : (
          <>
            <Text>부품: {vm.part.partName}</Text>
            <Text>작업자 확인 필요: {vm.reviewCount}건</Text>
            <Text>AI 분석 실패: {vm.failedCount}건</Text>
          </>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.title}>검사 상태·앱 반영 시각 · {partCode}</Text>
        <Text style={styles.note}>
          서버 접수(receivedAt)와 iPhone이 정상 폴링 응답을 받은 시각을 기록합니다.
          접수→앱 관측 시간에는 AI 분석 시간도 포함되므로 순수 폴링 지연이 아닙니다.
        </Text>
        {observation.lastSuccessfulPolls === 0 ? (
          <Text style={styles.note}>정상 서버 조회를 기다리는 중입니다.</Text>
        ) : (
          <>
            {countChange ? (
              <View style={styles.eventBox}>
                <Text style={styles.eventTitle}>
                  확인 필요 건수 변경: {countChange.previous} → {countChange.current}건
                </Text>
                <Text style={styles.note}>앱 변경 관측: {timeText(countChange.observedAtMs)}</Text>
                {countChange.newlyDetectedReceivedAt ? (
                  <>
                    <Text style={styles.note}>
                      함께 새로 관측한 검사: {countChange.newlyDetectedReviewNo ?? countChange.newlyDetectedReviewId}
                    </Text>
                    <Text style={styles.note}>
                      서버 접수: {receiptText(countChange.newlyDetectedReceivedAt)}
                      {' · '}접수→관측: {secondsText(countChange.newlyDetectedReceivedAt, countChange.observedAtMs)}
                    </Text>
                  </>
                ) : (
                  <Text style={styles.note}>해당 건수 변화에 대응하는 신규 검사 1건은 특정하지 못했습니다.</Text>
                )}
              </View>
            ) : (
              <Text style={styles.note}>첫 정상 조회를 기준으로 삼았습니다. 이후 건수 변경이 생기면 관측 시각을 기록합니다.</Text>
            )}

            {latestDetection && (
              <View style={styles.smallEvent}>
                <Text style={styles.eventTitle}>신규 검사 첫 관측</Text>
                <Text style={styles.note}>
                  {latestDetection.inspectionNo ?? latestDetection.inspectionId} · {latestDetection.displayState}
                </Text>
                <Text style={styles.note}>
                  서버 접수: {receiptText(latestDetection.receivedAt)}
                  {' · '}앱 첫 관측: {timeText(latestDetection.observedAtMs)}
                </Text>
                <Text style={styles.note}>
                  접수→첫 관측: {secondsText(latestDetection.receivedAt, latestDetection.observedAtMs)}
                </Text>
              </View>
            )}
            {latestTransition && (
              <View style={styles.smallEvent}>
                <Text style={styles.eventTitle}>검사 상태 변경 관측</Text>
                <Text style={styles.note}>
                  {latestTransition.inspectionNo ?? latestTransition.inspectionId}
                  {' · '}{latestTransition.previousState} → {latestTransition.displayState}
                </Text>
                <Text style={styles.note}>앱이 변경을 관측한 시각: {timeText(latestTransition.observedAtMs)}</Text>
              </View>
            )}

            <Text style={styles.subtitle}>최근 {partCode} 검사별 관측 기록</Text>
            {recentStates.length === 0 ? (
              <Text style={styles.note}>최근 검사 없음</Text>
            ) : recentStates.map((item) => (
              <View key={item.inspectionId} style={styles.observationRow}>
                <Text style={styles.itemTitle}>
                  {item.inspectionNo ?? item.inspectionId} · {item.displayState}
                </Text>
                <Text style={styles.note}>
                  서버 접수 {receiptText(item.receivedAt)}
                  {' · '}앱 상태 관측 {timeText(item.stateObservedAtMs)}
                </Text>
                <Text style={styles.note}>
                  {item.firstSeenAfterBaseline
                    ? `접수→첫 앱 관측: ${secondsText(item.receivedAt, item.firstObservedAtMs)}`
                    : '앱 첫 조회에 이미 존재하던 기록 · 지연 측정 제외'}
                </Text>
              </View>
            ))}
            <Text style={styles.note}>
              앱을 켠 첫 조회의 기존 데이터는 측정에서 제외합니다.
              5초는 기본 폴링 간격이며 실제 반영 시간 보장은 아닙니다.
              서버·기기 시계가 어긋나면 계산값도 부정확할 수 있습니다.
            </Text>
          </>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.title}>확인 필요 · 분석 실패 · {partCode}</Text>
        {vm.hasSuccessfulRead && (
          <Text style={styles.note}>
            표시 {Math.min(visibleQueueCount, vm.queue.length)} / {vm.queue.length}건
            {' · '}서버 nextCursor 페이지 수집 후 20건씩 표시
          </Text>
        )}
        {vm.queue.length === 0 ? (
          <Text>{vm.hasSuccessfulRead ? '현재 대기 항목 없음' : '서버 조회 대기'}</Text>
        ) : (
          vm.queue.slice(0, visibleQueueCount).map((item) => (
            <Pressable
              key={item.inspectionId}
              style={styles.row}
              accessibilityRole="button"
              onPress={() => router.push({
                pathname: '/inspection-live',
                params: { inspectionId: item.inspectionId },
              })}
            >
              <Text style={styles.itemTitle}>{item.inspectionNo ?? '검사번호 미제공'}</Text>
              <Text>{item.displayState === 'FAILED' ? 'AI 분석 실패' : '작업자 확인 필요'}</Text>
              {item.reviewReason === 'AI_UNAVAILABLE' ? (
                <Text>AI 분석 없이 작업자 판정</Text>
              ) : (
                <Text>AI 예측: {item.predictedQuality ?? '미제공'}</Text>
              )}
              <Text style={styles.detailLink}>상세 보기 ›</Text>
            </Pressable>
          ))
        )}
        {vm.queue.length > visibleQueueCount && (
          <Pressable
            style={styles.moreButton}
            accessibilityRole="button"
            onPress={() => setVisibleQueueCount((count) => count + 20)}
          >
            <Text style={styles.moreButtonText}>
              목록 더 보기 · 다음 {Math.min(20, vm.queue.length - visibleQueueCount)}건
            </Text>
          </Pressable>
        )}
        {visibleQueueCount > 20 && (
          <Pressable
            style={styles.collapseButton}
            accessibilityRole="button"
            onPress={() => setVisibleQueueCount(20)}
          >
            <Text style={styles.collapseText}>처음 20건만 보기</Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 12, paddingBottom: 16 },
  card: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E4E7EC', borderRadius: 14, padding: 16, gap: 10 },
  partSelector: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  partButton: { flexGrow: 1, flexBasis: '40%', minWidth: 120, paddingVertical: 12, borderWidth: 1, borderColor: '#CBD5E1', borderRadius: 10, alignItems: 'center', backgroundColor: '#F8FAFC' },
  partButtonActive: { borderColor: '#2054D8', backgroundColor: '#2054D8' },
  partButtonText: { fontSize: 14, fontWeight: '700', color: '#475569' },
  partButtonTextActive: { color: '#FFFFFF' },
  title: { fontSize: 17, fontWeight: '700', color: '#111827' },
  subtitle: { fontSize: 13, fontWeight: '700', color: '#111827' },
  note: { fontSize: 12, color: '#64748B', lineHeight: 18 },
  error: { fontSize: 12, color: '#B42318' },
  warning: { fontSize: 12, color: '#A74B12' },
  eventBox: { borderRadius: 10, backgroundColor: '#EEF4FF', padding: 12, gap: 5 },
  smallEvent: { borderRadius: 10, backgroundColor: '#F8FAFC', padding: 10, gap: 4 },
  eventTitle: { fontSize: 13, fontWeight: '700', color: '#1E40AF' },
  observationRow: { borderTopWidth: 1, borderTopColor: '#E4E7EC', paddingTop: 8, gap: 3 },
  row: { borderTopWidth: 1, borderTopColor: '#E4E7EC', paddingTop: 10, gap: 5 },
  itemTitle: { fontSize: 13, fontWeight: '700', color: '#111827' },
  detailLink: { color: '#2054D8', fontSize: 13, fontWeight: '600', marginTop: 4 },
  moreButton: { padding: 13, backgroundColor: '#2054D8', borderRadius: 10, alignItems: 'center' },
  moreButtonText: { color: '#FFFFFF', fontWeight: '700', fontSize: 13 },
  collapseButton: { padding: 10, alignItems: 'center' },
  collapseText: { color: '#2054D8', fontWeight: '600', fontSize: 12 },
});
