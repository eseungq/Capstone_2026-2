import { router, useFocusEffect } from 'expo-router';
import { partLabelV4, qualityLabelV4 } from './partLabelV4';
import { createRecheckServiceV4 } from '../api/backendV4/recheckServiceV4';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { API_BASE_URL, authV4 } from '../api/backendV4/authRuntime';
import { createInspectionReadServiceV4 } from '../api/backendV4/inspectionReadService';
import {
  createReviewQueueBrowserV4, MONITORED_PARTS, type ReviewQueueSortV4,
  type ReviewQueueBrowseSnapshotV4,
} from '../api/backendV4/reviewQueueBrowseCoreV4';
import { liveMonitoringReaderV4 } from '../api/backendV4/monitoringLiveReaderV4';
import { useMonitoringPollV4 } from '../api/backendV4/useMonitoringPollV4';
import type { MonitorAlertV4 } from '../api/backendV4/monitoringPollCore';
import { buildMonitoringViewModelV4 } from '../api/backendV4/monitoringViewModelV4';
import { monitoringThumbnailNeedsReloadV4, resolveMonitoringThumbnailUrlV4 } from '../api/backendV4/monitoringThumbnailUrlV4';

const INITIAL_VISIBLE_QUEUE_COUNT = 3;
const recheckReader = createRecheckServiceV4(authV4);
const reviewQueueReaderV4 = createInspectionReadServiceV4({ mode: 'api', transport: authV4 });
function probabilityLabelV4(value: number | null | undefined): string {
  return value == null ? '미제공' : `${(value * 100).toFixed(2)}%`;
}
type MonitoredPart = (typeof MONITORED_PARTS)[number];

function statusLabel(displayState: string): string {
  switch (displayState) {
    case 'FAILED': return 'AI 분석 실패';
    case 'REVIEW_PENDING': return '작업자 확인 필요';
    case 'REVIEW_DONE': return '판정 완료';
    case 'AUTO_PASS': return '자동 통과';
    case 'AUTO_FAIL': return '자동 불량';
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
  const [verifiedRole, setVerifiedRole] = useState<'WORKER'|'ADMIN'|null>(null);
  const isAuthenticatedWorker = verifiedRole === 'WORKER';
  const [recheckCount,setRecheckCount] = useState<number|null>(null);
  const [recheckError,setRecheckError] = useState(false);
  useFocusEffect(useCallback(() => {
    let current = true;
    const epoch = authV4.sessionEpoch();
    const stillCurrent = () => current && authV4.sessionEpoch()===epoch;
    setVerifiedRole(null);
    setRecheckCount(null);
    setRecheckError(false);
    void (async()=>{
      try{
        const session=await authV4.restore();
        if(!stillCurrent() || !session.signedIn || (session.role!=='WORKER'&&session.role!=='ADMIN'))return;
        setVerifiedRole(session.role);
        if(session.role!=='WORKER')return;
        const result=await recheckReader.list({status:'PENDING',page:0,size:1});
        if(stillCurrent())setRecheckCount(result.totalElements);
      }catch{
        if(stillCurrent())setRecheckError(true);
      }
    })();
    return ()=>{current=false;};
  }, []));
  const [visibleQueueCount, setVisibleQueueCount] = useState(INITIAL_VISIBLE_QUEUE_COUNT);
  const [queueSort, setQueueSort] = useState<ReviewQueueSortV4>('RECEIVED');
  const [aiDefectOnly, setAiDefectOnly] = useState(false);
  const queueBrowser = useMemo(() => createReviewQueueBrowserV4(reviewQueueReaderV4), []);
  const [browse, setBrowse] = useState<ReviewQueueBrowseSnapshotV4>(() => queueBrowser.getSnapshot());
  useEffect(() => queueBrowser.subscribe(setBrowse), [queueBrowser]);

  // 선택한 정렬·필터만 별도 읽기 전용 조회. 기본 목록/알림 5초 폴링은 변경하지 않습니다.
  const filteredMode = queueSort === 'PRIORITY' || aiDefectOnly;
  useEffect(() => {
    if (!filteredMode) { queueBrowser.clear(); return; }
    queueBrowser.setFilters({ partCode, sort: queueSort, aiDefectOnly });
    void queueBrowser.refresh();
  }, [queueBrowser, partCode, queueSort, aiDefectOnly, filteredMode]);

  const vm = buildMonitoringViewModelV4(snapshot, partCode);
  const matchingBrowse = browse.filters?.partCode === partCode &&
    browse.filters.sort === queueSort && browse.filters.aiDefectOnly === aiDefectOnly;
  const queueItems = filteredMode ? (matchingBrowse ? browse.items : []) : vm.queue;
  const queueReady = filteredMode ? matchingBrowse && browse.loaded : vm.hasSuccessfulRead;
  const queueLoading = filteredMode && (!matchingBrowse || browse.status === 'loading');
  const queueError = filteredMode && matchingBrowse ? browse.error : null;
  const recent = vm.part?.recent[0] ?? null;
  const canOpenBatch = isAuthenticatedWorker && queueReady && !queueLoading && !queueError &&
    !vm.isStale && vm.part?.pendingReviewCount !== 0 &&
    queueItems.some(item => item.displayState === 'REVIEW_PENDING');
  const openFilteredHistory=(displayState:'REVIEW_PENDING'|'FAILED')=>{
    if(!verifiedRole)return;
    router.push({pathname:'/history',params:{mode:'live',role:verifiedRole,partCode,displayState}});
  };
  const lastRefresh=vm.lastSuccessAtMs===null?'미조회':new Date(vm.lastSuccessAtMs).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false,timeZone:'Asia/Seoul'});

  const connectionLabel = !vm.hasSuccessfulRead
    ? snapshot.status === 'error' ? '연결 실패' : '조회 중'
    : vm.isStale ? '연결 확인 필요' : '연결됨';

  // 작업자는 처리 대기열부터 확인하고, 관리자는 기존 관측 순서를 유지합니다.
  // 동일한 카드와 key를 사용해 권한 확인 중 순서가 바뀌어도 내용은 중복되지 않습니다.
  const recentCard = (
    <View key="recent" style={styles.card}>
        <Text style={styles.title}>최근 검사</Text>
        {!recent ? (
          <Text style={styles.description}>
            {vm.hasSuccessfulRead ? '최근 검사 내역이 없습니다.' : '최근 검사 조회 대기'}
          </Text>
        ) : (
          <Pressable
            style={({ pressed }) => [styles.inspectionRow, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel={`최근 검사 ${recent.inspectionNo ?? '검사번호 미제공'}, ${statusLabel(recent.displayState)}, 상세 보기`}
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
  );
  const queueCard = (
    <View key="queue" style={styles.card}>
        <Text style={styles.title}>처리 필요 검사</Text>
        <Text style={styles.filterLabel}>정렬</Text>
        <View style={styles.filterControls}>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: queueSort === 'RECEIVED' }}
            style={[styles.filterButton, queueSort === 'RECEIVED' && styles.filterButtonActive]}
            onPress={() => { setQueueSort('RECEIVED'); setVisibleQueueCount(INITIAL_VISIBLE_QUEUE_COUNT); }}
          >
            <Text style={[styles.filterButtonText, queueSort === 'RECEIVED' && styles.filterButtonTextActive]}>
              접수순
            </Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: queueSort === 'PRIORITY' }}
            style={[styles.filterButton, queueSort === 'PRIORITY' && styles.filterButtonActive]}
            onPress={() => { setQueueSort('PRIORITY'); setVisibleQueueCount(INITIAL_VISIBLE_QUEUE_COUNT); }}
          >
            <Text style={[styles.filterButtonText, queueSort === 'PRIORITY' && styles.filterButtonTextActive]}>
              우선 검토
            </Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: aiDefectOnly }}
            style={[styles.filterButton, aiDefectOnly && styles.filterButtonActive]}
            onPress={() => { setAiDefectOnly((prev) => !prev); setVisibleQueueCount(INITIAL_VISIBLE_QUEUE_COUNT); }}
          >
            <Text style={[styles.filterButtonText, aiDefectOnly && styles.filterButtonTextActive]}>
              AI 불량 의심만
            </Text>
          </Pressable>
        </View>
        {queueSort === 'PRIORITY' && (
          <Text style={styles.description}>
            GOOD 예측·자동 통과 기준 초과 REVIEW를 먼저, 나머지는 뒤에 표시합니다. 각 그룹은 오래된 순입니다.
          </Text>
        )}
        {aiDefectOnly && (
          <Text style={styles.description}>
            AI가 DEFECT로 예측한 REVIEW 검사만 조회합니다. 작업자 최종 불량 판정과는 다릅니다.
          </Text>
        )}
        {filteredMode && (
          <Pressable
            accessibilityRole="button"
            disabled={queueLoading}
            style={[styles.refreshFilterButton, queueLoading && styles.disabled]}
            onPress={() => { setVisibleQueueCount(INITIAL_VISIBLE_QUEUE_COUNT); void queueBrowser.refresh(); }}
          >
            <Text style={styles.refreshFilterText}>필터 목록 새로고침</Text>
          </Pressable>
        )}
        {queueError && (
          <Text style={styles.warning}>
            정렬·필터 조회 실패: {queueError} · 서버 기능 적용 여부와 네트워크를 확인해 주세요.
          </Text>
        )}
        {queueLoading && <Text style={styles.description}>정렬·필터 목록 조회 중...</Text>}
        {!queueLoading && queueItems.length === 0 && (
          <Text style={styles.description}>
            {!queueReady ? '검사 목록 조회 대기' : '해당 조건의 처리 필요 검사가 없습니다.'}
          </Text>
        )}
        {queueItems.slice(0, visibleQueueCount).map((item) => (
          <Pressable
            key={item.inspectionId}
            style={({ pressed }) => [styles.inspectionRow, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel={`${item.inspectionNo ?? '검사번호 미제공'}, ${statusLabel(item.displayState)}, 상세 보기`}
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
                    : 'AI 예측: ' + qualityLabelV4(item.predictedQuality)}
              </Text>
              {item.reviewReason === 'ABOVE_THRESHOLD' && (
                <Text style={styles.priorityHint}>자동 통과 기준 초과 · REVIEW</Text>
              )}
              {item.displayState === 'REVIEW_PENDING' && (
                <Text style={styles.description}>
                  보정 불량 확률: {probabilityLabelV4(item.calibratedDefectProbability)}
                  {' · '}적용된 통과 기준: {probabilityLabelV4(item.passThresholdApplied)}
                </Text>
              )}
              <Text style={styles.detailLink}>상세 보기 ›</Text>
            </View>
          </Pressable>
        ))}
        {queueItems.length > visibleQueueCount && (
          <Pressable
            style={({ pressed }) => [styles.moreButton, pressed && styles.pressed]}
            accessibilityRole="button"
            onPress={() => setVisibleQueueCount((count) => count + 20)}
          >
            <Text style={styles.moreButtonText}>
              목록 더 보기 · 다음 {Math.min(20, queueItems.length - visibleQueueCount)}건
            </Text>
          </Pressable>
        )}
        {filteredMode && matchingBrowse && browse.loaded && !queueLoading &&
          queueItems.length <= visibleQueueCount && browse.nextCursor !== null && (
          <Pressable
            style={({ pressed }) => [styles.moreButton, pressed && styles.pressed]}
            accessibilityRole="button"
            onPress={() => { void queueBrowser.loadNext(); setVisibleQueueCount((count) => count + 20); }}
          >
            <Text style={styles.moreButtonText}>서버 다음 페이지 20건 불러오기</Text>
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
        <Text style={styles.description}>{filteredMode?'선택한 필터 · 새로고침 시 갱신':`마지막 갱신 ${lastRefresh} (서울)`}</Text>
        {queueReady && !queueLoading && !queueError && queueItems.length>0 && <Text style={styles.description}>
          현재 목록 {Math.min(visibleQueueCount,queueItems.length)}/{queueItems.length}건{filteredMode&&browse.nextCursor!==null?' · 다음 페이지 있음':''}
        </Text>}
        {canOpenBatch && (
          <Pressable accessibilityRole="button" style={styles.batchFailEntry}
            onPress={() => router.push({
              pathname: '/batch-fail-live',
              params: {partCode, sort: queueSort, aiDefectOnly: String(aiDefectOnly)},
            })}>
            <Text style={styles.batchFailEntryText}>REVIEW 상세 검토 후 일괄 FAIL 판정 ›</Text>
          </Pressable>
        )}
      </View>
  );

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
              testID={'monitor-part-' + code}
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
              >
                {partLabelV4(code)}
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
        <Text style={styles.title}>{partLabelV4(partCode)} 공정 현황</Text>
        {!vm.part ? (
          <Text style={styles.description}>
            {vm.hasSuccessfulRead ? '이 공정의 정보가 제공되지 않았습니다.' : '공정 데이터를 불러오는 중입니다.'}
          </Text>
        ) : (
          <>
            <View style={styles.metricRow}>
              <Pressable testID="monitor-review-history" accessibilityRole="button"
                accessibilityLabel={`확인 대기 ${vm.part.pendingReviewCount}건, 이력 보기`}
                disabled={!verifiedRole} onPress={()=>openFilteredHistory('REVIEW_PENDING')} style={styles.metric}>
                <Text style={styles.metricLabel}>작업자 확인 필요</Text>
                <Text style={styles.metricValue}>{vm.part.pendingReviewCount}건 ›</Text>
              </Pressable>
              <Pressable testID="monitor-failed-history" accessibilityRole="button"
                accessibilityLabel={`분석 실패 ${vm.part.failedCount}건, 이력 보기`}
                disabled={!verifiedRole} onPress={()=>openFilteredHistory('FAILED')} style={styles.metric}>
                <Text style={styles.metricLabel}>AI 분석 실패</Text>
                <Text style={styles.metricValue}>{vm.part.failedCount}건 ›</Text>
              </Pressable>
            </View>
            {vm.isStale&&<Text style={styles.warning}>마지막 조회 기준 건수입니다.</Text>}
          </>
        )}
      </View>

      {isAuthenticatedWorker && <Pressable testID="monitor-recheck-entry" style={styles.card}
        accessibilityRole="button" accessibilityLabel="자동 통과 표본 재확인 목록"
        onPress={()=>router.push('/rechecks-live')}>
        <View style={styles.headingRow}>
          <Text style={styles.title}>표본 재확인</Text>
          <Text style={styles.detailLink}>{recheckCount===null?(recheckError?'조회 실패 ›':'조회 중… ›'):`${recheckCount}건 ›`}</Text>
        </View>
        <Text style={styles.description}>전체 부품 재확인 대기 · 목록에서 최신 상태 확인</Text>
      </Pressable>}
      {isAuthenticatedWorker ? [queueCard, recentCard] : [recentCard, queueCard]}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 12, paddingBottom: 16 },
  card: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E4E7EC', borderRadius: 14, padding: 16, gap: 10 },
  batchFailEntry: { borderRadius: 9, backgroundColor: '#FFFFFF', borderWidth: 1,
    borderColor: '#FECACA', padding: 10, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  batchFailEntryText: { color: '#B42318', fontSize: 13, fontWeight: '700', textAlign: 'center' },
  filterLabel: { color: '#334155', fontSize: 13, fontWeight: '700' },
  filterControls: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  filterButton: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 11, paddingVertical: 10, borderRadius: 9,
    backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#64748B' },
  filterButtonActive: { backgroundColor: '#1E293B', borderColor: '#1E293B' },
  filterButtonText: { color: '#475569', fontSize: 13, fontWeight: '700' },
  filterButtonTextActive: { color: '#FFFFFF' },
  refreshFilterButton: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start', paddingHorizontal: 11, paddingVertical: 8,
    borderWidth: 1, borderColor: '#2054D8', borderRadius: 9 },
  refreshFilterText: { color: '#2054D8', fontSize: 13, fontWeight: '700' },
  disabled: { opacity: 0.5 },
  priorityHint: { color: '#A74B12', fontSize: 13, fontWeight: '600' },
  pressed: { opacity: 0.76 },
  headingRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  title: { fontSize: 17, fontWeight: '700', color: '#111827', flexShrink: 1 },
  description: { fontSize: 13, color: '#475569', lineHeight: 19 },
  warning: { color: '#A74B12', fontSize: 13, lineHeight: 18 },
  connection: { color: '#067647', fontSize: 13, fontWeight: '700' },
  connectionStale: { color: '#A74B12' },
  partSelector: { flexDirection: 'row', gap: 6 },
  partButton: {
    flex: 1, minWidth: 0, minHeight: 44,
    paddingHorizontal: 2, paddingVertical: 12, borderWidth: 1, borderColor: '#64748B',
    borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F8FAFC',
  },
  partButtonActive: { borderColor: '#1E293B', backgroundColor: '#1E293B' },
  partButtonText: { fontSize: 13, fontWeight: '700', color: '#475569', textAlign: 'center' },
  partButtonTextActive: { color: '#FFFFFF' },
  metricRow: { flexDirection: 'row', gap: 10 },
  metric: { flex: 1, backgroundColor: '#F5F7FB', padding: 12, borderRadius: 10, gap: 6 },
  metricLabel: { color: '#475569', fontSize: 13 },
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
  thumbnailEmpty: { color: '#475569', fontSize: 13, paddingHorizontal: 5, textAlign: 'center' },
  rowInfo: { flex: 1, gap: 4, justifyContent: 'center' },
  itemTitle: { color: '#111827', fontSize: 14, fontWeight: '700' },
  itemStatus: { color: '#475569', fontSize: 13, fontWeight: '600' },
  detailLink: { color: '#2054D8', fontSize: 13, fontWeight: '700' },
  moreButton: { backgroundColor: '#2054D8', borderRadius: 10, minHeight: 44, alignItems: 'center', justifyContent: 'center', padding: 10 },
  moreButtonText: { color: '#FFFFFF', fontWeight: '700', fontSize: 13 },
  collapseButton: { minHeight: 44, justifyContent: 'center', padding: 10, alignItems: 'center' },
  collapseText: { color: '#2054D8', fontWeight: '600', fontSize: 13 },
});
