import { router } from 'expo-router';
import React, { useEffect, useMemo, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { API_BASE_URL } from '../api/backendV4/authRuntime';
import { liveMonitoringReaderV4 } from '../api/backendV4/monitoringLiveReaderV4';
import { useMonitoringPollV4 } from '../api/backendV4/useMonitoringPollV4';
import type { MonitorAlertV4 } from '../api/backendV4/monitoringPollCore';
import { buildMonitoringViewModelV4 } from '../api/backendV4/monitoringViewModelV4';
import { monitoringThumbnailNeedsReloadV4, resolveMonitoringThumbnailUrlV4 } from '../api/backendV4/monitoringThumbnailUrlV4';

const MONITORED_PARTS = ['DOOR', 'FRAME', 'COWL_COVER'] as const;
const INITIAL_VISIBLE_QUEUE_COUNT = 3;
type MonitoredPart = (typeof MONITORED_PARTS)[number];

function statusLabel(displayState: string): string {
  switch (displayState) {
    case 'FAILED': return 'AI 분석 실패';
    case 'REVIEW_PENDING': return '작업자 확인 필요';
    case 'REVIEW_DONE': return '판정 완료';
    case 'AUTO_PASS': return '자동 통과';
    case 'ANALYZING': return '분석 중';
    default: return '검사 상태 확인';
  }
}

type ThumbnailSlotV4 = 0 | 1;
type ThumbnailViewStateV4 = {
  inspectionId: string;
  urls: [string | null, string | null];
  visibleSlot: ThumbnailSlotV4 | null;
  pendingSlot: ThumbnailSlotV4 | null;
  failedUri: string | null;
};

function initialThumbnailState(inspectionId: string, uri: string | null): ThumbnailViewStateV4 {
  return {
    inspectionId,
    urls: [uri, null],
    visibleSlot: null,
    pendingSlot: uri ? 0 : null,
    failedUri: null,
  };
}

/**
 * 5초 폴링은 계속하지만, 같은 검사 사진의 서명 URL이 매번 바뀌었다고
 * RN Image를 다시 마운트하거나 기존 사진을 숨기지 않습니다.
 * 만료 전 갱신이 필요할 때는 보이지 않는 두 번째 슬롯을 먼저 로드합니다.
 */
function InspectionThumbnail({
  inspectionId,
  url,
}: {
  inspectionId: string;
  url: string | null;
}) {
  const uri = resolveMonitoringThumbnailUrlV4(url, API_BASE_URL);
  const [imageState, setImageState] = useState<ThumbnailViewStateV4>(
    () => initialThumbnailState(inspectionId, uri),
  );

  useEffect(() => {
    setImageState((previous) => {
      // 조회 결과가 다른 검사로 교체되면 기존 검사 사진을 보여주지 않습니다.
      if (previous.inspectionId !== inspectionId || uri === null) {
        return initialThumbnailState(inspectionId, uri);
      }

      // 다운로드 중에는 새 서명 URL이 와도 진행 중인 요청을 취소하지 않습니다.
      if (previous.pendingSlot !== null || previous.failedUri === uri) return previous;

      const active = previous.visibleSlot === null ? null : previous.urls[previous.visibleSlot];
      // 같은 원본 사진이면 유효기간이 임박하기 전까지는 기존 로드된 URL 재사용.
      if (!monitoringThumbnailNeedsReloadV4(active, uri)) return previous;

      // 새 URL을 숨긴 슬롯에 받아 놓고 onLoad 성공 시 한 번에 전환합니다.
      const nextSlot: ThumbnailSlotV4 = previous.visibleSlot === 0 ? 1 : 0;
      const urls: [string | null, string | null] = [...previous.urls];
      urls[nextSlot] = uri;
      return { ...previous, urls, pendingSlot: nextSlot, failedUri: null };
    });
  }, [inspectionId, uri]);

  // React 상위 화면이 5초마다 렌더링돼도 Image의 source 참조를 유지합니다.
  const firstSource = useMemo(
    () => imageState.urls[0] ? { uri: imageState.urls[0] } : null,
    [imageState.urls[0]],
  );
  const secondSource = useMemo(
    () => imageState.urls[1] ? { uri: imageState.urls[1] } : null,
    [imageState.urls[1]],
  );
  const sources = [firstSource, secondSource];
  const hasImage = imageState.visibleSlot !== null
    && imageState.urls[imageState.visibleSlot] !== null;
  const placeholder = uri === null
    ? '사진 없음'
    : imageState.failedUri === uri
      ? '사진을 표시할 수 없음'
      : '사진 불러오는 중';

  return (
    <View
      style={styles.thumbnail}
      accessible
      accessibilityLabel={hasImage ? '검사 사진 미리보기' : placeholder}
    >
      {sources.map((source, slotNumber) => {
        if (!source) return null;
        const slot = slotNumber as ThumbnailSlotV4;
        const slotUri = source.uri;
        return (
          <Image
            key={slot}
            source={source}
            style={[styles.thumbnailImage, slot !== imageState.visibleSlot && styles.thumbnailImageLoading]}
            resizeMode="cover"
            onLoad={() => setImageState((previous) => {
              if (previous.inspectionId !== inspectionId
                || previous.pendingSlot !== slot || previous.urls[slot] !== slotUri) return previous;

              // 새 이미지가 실제로 로딩된 뒤에만 이전 슬롯을 해제합니다.
              // 성공한 슬롯의 Image 인스턴스는 유지되어 교체 순간에도 다시 마운트되지 않습니다.
              const urls: [string | null, string | null] = [null, null];
              urls[slot] = slotUri;
              return { ...previous, urls, visibleSlot: slot, pendingSlot: null, failedUri: null };
            })}
            onError={() => setImageState((previous) => {
              if (previous.inspectionId !== inspectionId
                || previous.pendingSlot !== slot || previous.urls[slot] !== slotUri) return previous;

              // 새 URL이 실패해도 이미 표시된 사진은 지우지 않습니다.
              // 다음 폴링에서 다른 서명 URL이 제공되면 재시도할 수 있습니다.
              const urls: [string | null, string | null] = [...previous.urls];
              urls[slot] = null;
              return { ...previous, urls, pendingSlot: null, failedUri: slotUri };
            })}
          />
        );
      })}
      {!hasImage && <Text style={styles.thumbnailEmpty}>{placeholder}</Text>}
    </View>
  );
}

function openInspection(inspectionId: string) {
  router.push({ pathname: '/inspection-live', params: { inspectionId } });
}

/**
 * 실서버 업무용 모니터링. 폴링/알림/페이지 처리 로직은 그대로 사용하며
 * 서버 관측 시간·조회 횟수 같은 개발용 수치는 운영 화면에서 표시하지 않습니다.
 */
export default function MonitoringLiveDashboardV4({
  onNewAlerts,
}: {
  onNewAlerts?: (alerts: MonitorAlertV4[]) => void;
}) {
  const { snapshot, controller } = useMonitoringPollV4(liveMonitoringReaderV4);

  // 최초 조회의 과거 대기 항목은 제외하고 새 REVIEW/FAILED 이벤트만 전달합니다.
  useEffect(() => {
    if (!onNewAlerts) return;
    return controller.subscribeAlerts(onNewAlerts);
  }, [controller, onNewAlerts]);

  const [partCode, setPartCode] = useState<MonitoredPart>('DOOR');
  const [visibleQueueCount, setVisibleQueueCount] = useState(INITIAL_VISIBLE_QUEUE_COUNT);
  const vm = buildMonitoringViewModelV4(snapshot, partCode);
  const recent = vm.part?.recent[0] ?? null;

  const connectionLabel = !vm.hasSuccessfulRead
    ? snapshot.status === 'error' ? '연결 실패' : '조회 중'
    : vm.isStale ? '연결 확인 필요' : '연결됨';

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <View style={styles.headingRow}>
          <Text style={styles.title}>공정 선택</Text>
          <Text style={[styles.connection, vm.isStale && styles.connectionStale]}>{connectionLabel}</Text>
        </View>
        <View style={styles.partSelector}>
          {MONITORED_PARTS.map((code) => (
            <Pressable
              key={code}
              accessibilityRole="button"
              accessibilityState={{ selected: partCode === code }}
              style={({ pressed }) => [styles.partButton, partCode === code && styles.partButtonActive, pressed && styles.pressed]}
              onPress={() => {
                setPartCode(code);
                setVisibleQueueCount(INITIAL_VISIBLE_QUEUE_COUNT);
              }}
            >
              <Text
                style={[styles.partButtonText, partCode === code && styles.partButtonTextActive]}
                numberOfLines={1}
                adjustsFontSizeToFit
                minimumFontScale={0.85}
              >
                {code}
              </Text>
            </Pressable>
          ))}
        </View>
        {!vm.hasSuccessfulRead && !snapshot.error && (
          <Text style={styles.description}>실제 서버에서 공정 현황을 불러오는 중입니다.</Text>
        )}
        {snapshot.error ? (
          <Text style={styles.warning}>서버 연결에 문제가 있습니다. 잠시 후 다시 확인해 주세요.</Text>
        ) : vm.isStale && vm.hasSuccessfulRead ? (
          <Text style={styles.warning}>마지막으로 조회한 정보입니다. 현재 상태와 다를 수 있습니다.</Text>
        ) : null}
      </View>

      <View style={styles.card}>
        <Text style={styles.title}>{partCode} 공정 현황</Text>
        {!vm.part ? (
          <Text style={styles.description}>
            {vm.hasSuccessfulRead ? '이 공정의 정보가 제공되지 않았습니다.' : '공정 데이터를 불러오는 중입니다.'}
          </Text>
        ) : (
          <>
            <Text style={styles.description}>부품: {vm.part.partName}</Text>
            <View style={styles.metricRow}>
              <View style={styles.metric}>
                <Text style={styles.metricLabel}>작업자 확인 필요</Text>
                <Text style={styles.metricValue}>{vm.part.pendingReviewCount}건</Text>
              </View>
              <View style={styles.metric}>
                <Text style={styles.metricLabel}>AI 분석 실패</Text>
                <Text style={styles.metricValue}>{vm.part.failedCount}건</Text>
              </View>
            </View>
          </>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.title}>최근 검사 · {partCode}</Text>
        {!recent ? (
          <Text style={styles.description}>
            {vm.hasSuccessfulRead ? '최근 검사 내역이 없습니다.' : '최근 검사 조회 대기'}
          </Text>
        ) : (
          <Pressable
            style={({ pressed }) => [styles.inspectionRow, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel={'최근 검사 ' + (recent.inspectionNo ?? '검사번호 미제공') + ' 상세 보기'}
            onPress={() => openInspection(recent.inspectionId)}
          >
            <InspectionThumbnail key={recent.inspectionId} inspectionId={recent.inspectionId} url={recent.thumbnailUrl} />
            <View style={styles.rowInfo}>
              <Text style={styles.itemTitle}>{recent.inspectionNo ?? '검사번호 미제공'}</Text>
              <Text style={styles.itemStatus}>{statusLabel(recent.displayState)}</Text>
              <Text style={styles.detailLink}>상세 보기 ›</Text>
            </View>
          </Pressable>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.title}>처리 필요 검사 · {partCode}</Text>
        {vm.queue.length === 0 ? (
          <Text style={styles.description}>
            {vm.hasSuccessfulRead ? '현재 처리할 검사가 없습니다.' : '검사 목록 조회 대기'}
          </Text>
        ) : (
          <>
            {vm.queue.slice(0, visibleQueueCount).map((item) => (
              <Pressable
                key={item.inspectionId}
                style={({ pressed }) => [styles.inspectionRow, pressed && styles.pressed]}
                accessibilityRole="button"
                accessibilityLabel={(item.inspectionNo ?? '검사번호 미제공') + ' 상세 보기'}
                onPress={() => openInspection(item.inspectionId)}
              >
                <InspectionThumbnail inspectionId={item.inspectionId} url={item.thumbnailUrl} />
                <View style={styles.rowInfo}>
                  <Text style={styles.itemTitle}>{item.inspectionNo ?? '검사번호 미제공'}</Text>
                  <Text style={styles.itemStatus}>{statusLabel(item.displayState)}</Text>
                  <Text style={styles.description}>
                    {item.reviewReason === 'AI_UNAVAILABLE'
                      ? 'AI 분석 없이 작업자 판정'
                      : item.displayState === 'FAILED'
                        ? '실패 사유는 상세에서 확인'
                        : 'AI 예측: ' + (item.predictedQuality ?? '미제공')}
                  </Text>
                  <Text style={styles.detailLink}>상세 보기 ›</Text>
                </View>
              </Pressable>
            ))}
            {vm.queue.length > visibleQueueCount && (
              <Pressable
                style={({ pressed }) => [styles.moreButton, pressed && styles.pressed]}
                accessibilityRole="button"
                onPress={() => setVisibleQueueCount((count) => count + 20)}
              >
                <Text style={styles.moreButtonText}>
                  목록 더 보기 · 다음 {Math.min(20, vm.queue.length - visibleQueueCount)}건
                </Text>
              </Pressable>
            )}
            {visibleQueueCount > INITIAL_VISIBLE_QUEUE_COUNT && (
              <Pressable
                style={({ pressed }) => [styles.collapseButton, pressed && styles.pressed]}
                accessibilityRole="button"
                onPress={() => setVisibleQueueCount(INITIAL_VISIBLE_QUEUE_COUNT)}
              >
                <Text style={styles.collapseText}>처음 3건만 보기</Text>
              </Pressable>
            )}
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 12, paddingBottom: 16 },
  card: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E4E7EC', borderRadius: 14, padding: 16, gap: 10 },
  pressed: { opacity: 0.76 },
  headingRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  title: { fontSize: 17, fontWeight: '700', color: '#111827', flexShrink: 1 },
  description: { fontSize: 12, color: '#64748B', lineHeight: 18 },
  warning: { color: '#A74B12', fontSize: 12, lineHeight: 18 },
  connection: { color: '#008454', fontSize: 12, fontWeight: '700' },
  connectionStale: { color: '#A74B12' },
  partSelector: { flexDirection: 'row', gap: 6 },
  partButton: {
    flex: 1, minWidth: 0, minHeight: 44,
    paddingHorizontal: 2, paddingVertical: 12, borderWidth: 1, borderColor: '#CBD5E1',
    borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F8FAFC',
  },
  partButtonActive: { borderColor: '#2054D8', backgroundColor: '#2054D8' },
  partButtonText: { fontSize: 11, fontWeight: '700', color: '#475569', textAlign: 'center' },
  partButtonTextActive: { color: '#FFFFFF' },
  metricRow: { flexDirection: 'row', gap: 10 },
  metric: { flex: 1, backgroundColor: '#F5F7FB', padding: 12, borderRadius: 10, gap: 6 },
  metricLabel: { color: '#64748B', fontSize: 12 },
  metricValue: { color: '#111827', fontSize: 20, fontWeight: '700' },
  inspectionRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    borderTopWidth: 1, borderTopColor: '#E4E7EC', paddingTop: 12, minHeight: 100,
  },
  thumbnail: {
    width: 96, height: 84, borderRadius: 9, backgroundColor: '#EEF2F8',
    overflow: 'hidden', alignItems: 'center', justifyContent: 'center',
  },
  thumbnailImage: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, width: '100%', height: '100%' },
  thumbnailImageLoading: { opacity: 0 },
  thumbnailEmpty: { color: '#64748B', fontSize: 10, paddingHorizontal: 5, textAlign: 'center' },
  rowInfo: { flex: 1, gap: 4, justifyContent: 'center' },
  itemTitle: { color: '#111827', fontSize: 13, fontWeight: '700' },
  itemStatus: { color: '#475569', fontSize: 12, fontWeight: '600' },
  detailLink: { color: '#2054D8', fontSize: 12, fontWeight: '700' },
  moreButton: { backgroundColor: '#2054D8', borderRadius: 10, minHeight: 44, alignItems: 'center', justifyContent: 'center', padding: 10 },
  moreButtonText: { color: '#FFFFFF', fontWeight: '700', fontSize: 13 },
  collapseButton: { padding: 10, alignItems: 'center' },
  collapseText: { color: '#2054D8', fontWeight: '600', fontSize: 12 },
});
