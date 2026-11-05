import { router } from 'expo-router';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { liveMonitoringReaderV4 } from '../api/backendV4/monitoringLiveReaderV4';
import { useMonitoringPollV4 } from '../api/backendV4/useMonitoringPollV4';
import { buildMonitoringViewModelV4 } from '../api/backendV4/monitoringViewModelV4';

export default function MonitoringLiveDashboardV4() {
  const { snapshot } = useMonitoringPollV4(liveMonitoringReaderV4);
  const vm = buildMonitoringViewModelV4(snapshot);

  const lastSuccess =
    snapshot.lastSuccessAtMs === null
      ? '아직 없음'
      : new Date(snapshot.lastSuccessAtMs).toLocaleTimeString('ko-KR');

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>실제 서버 모니터링</Text>
        <Text style={styles.note}>
          SERVER · 백엔드 API · 기본 5초 갱신
        </Text>

        <Text>조회 상태: {snapshot.status}</Text>
        <Text>성공 조회: {snapshot.successfulPolls}회</Text>
        <Text>마지막 정상 조회: {lastSuccess}</Text>

        {snapshot.error && (
          <Text style={styles.error}>
            서버 오류: {snapshot.error}
          </Text>
        )}

        {vm.isStale && vm.hasSuccessfulRead && (
          <Text style={styles.warning}>
            마지막 정상 데이터입니다. 현재 상태와 다를 수 있습니다.
          </Text>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.title}>DOOR 공정 현황</Text>

        {!vm.door ? (
          <Text>공정 데이터 조회 대기</Text>
        ) : (
          <>
            <Text>부품: {vm.door.partName}</Text>
            <Text>
              작업자 확인 필요: {vm.reviewCount}건
            </Text>
            <Text>
              AI 분석 실패: {vm.failedCount}건
            </Text>
          </>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.title}>확인 필요 · 분석 실패</Text>

        {vm.queue.length === 0 ? (
          <Text>
            {vm.hasSuccessfulRead
              ? '현재 대기 항목 없음'
              : '서버 조회 대기'}
          </Text>
        ) : (
          
vm.queue.slice(0, 20).map((item) => (
  <Pressable
    key={item.inspectionId}
    style={styles.row}
    accessibilityRole="button"
    onPress={() =>
      router.push({
        pathname: '/inspection-live',
        params: {
          inspectionId: item.inspectionId,
        },
      })
    }
  >
    <Text style={styles.itemTitle}>
      {item.inspectionNo ?? '검사번호 미제공'}
    </Text>

    <Text>
      {item.displayState === 'FAILED'
        ? 'AI 분석 실패'
        : '작업자 확인 필요'}
    </Text>

    <Text>
      AI 예측: {item.predictedQuality ?? '미제공'}
    </Text>

    <Text style={styles.detailLink}>
      상세 보기 ›
    </Text>
  </Pressable>
))

        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  detailLink: {
  color: '#2054D8',
  fontSize: 13,
  fontWeight: '600',
  marginTop: 4,
},
    container: {
    gap: 12,
    paddingBottom: 16,
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E4E7EC',
    borderRadius: 14,
    padding: 16,
    gap: 10,
  },
  title: {
    fontSize: 17,
    fontWeight: '700',
    color: '#111827',
  },
  note: {
    fontSize: 12,
    color: '#64748B',
  },
  error: {
    fontSize: 12,
    color: '#B42318',
  },
  warning: {
    fontSize: 12,
    color: '#A74B12',
  },
  row: {
    borderTopWidth: 1,
    borderTopColor: '#E4E7EC',
    paddingTop: 10,
    gap: 5,
  },
  itemTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#111827',
  },
});
