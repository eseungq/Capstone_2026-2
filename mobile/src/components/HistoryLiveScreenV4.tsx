import Pressable from './TouchPressable';
import LiveBottomNavV4 from './LiveBottomNavV4';
import { useVerifiedRoleV4 } from './useVerifiedRoleV4';
import { partLabelV4, qualityLabelV4 } from './partLabelV4';
import { reviewListReasonV4 } from './reviewReasonCopyV4';
import React, { useCallback, useRef, useState } from 'react';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { authV4 } from '../api/backendV4/authRuntime';
import { createInspectionReadServiceV4 } from '../api/backendV4/inspectionReadService';
import type { HistoryPageV4, HistoryRowV4 } from '../api/backendV4/inspectionReadCore';
import { historyJudgementLabelV4 } from '../api/backendV4/judgementRequestCoreV4';
import type { DisplayStateV4 } from '../api/backendV4/types';

const reader = createInspectionReadServiceV4({ mode: 'api', transport: authV4 });
const PAGE_SIZE = 20;

type StateFilter = DisplayStateV4 | 'ALL';
type PeriodFilter = 0 | 7 | 30;
type PartFilter = '' | 'DOOR' | 'FRAME' | 'COWL_COVER';

const states: { value: StateFilter; label: string }[] = [
  { value: 'ALL', label: '전체' },
  { value: 'ANALYZING', label: '분석 중' },
  { value: 'REVIEW_PENDING', label: '판정 대기' },
  { value: 'REVIEW_DONE', label: '판정 완료' },
  { value: 'FAILED', label: '분석 실패' },
  { value: 'AUTO_PASS', label: '자동 통과' },
  { value: 'AUTO_FAIL', label: '자동 불량' },
];
const periods: { value: PeriodFilter; label: string }[] = [
  { value: 0, label: '전체 기간' },
  { value: 7, label: '최근 7일' },
  { value: 30, label: '최근 30일' },
];
const parts: { value: PartFilter; label: string }[] = [
  { value: '', label: '전체 부품' },
  { value: 'DOOR', label: '도어' },
  { value: 'FRAME', label: '프레임' },
  { value: 'COWL_COVER', label: '카울커버' },
];
const stateLabels: Record<DisplayStateV4, string> = {
  ANALYZING: '분석 중',
  REVIEW_PENDING: '판정 대기',
  REVIEW_DONE: '판정 완료',
  FAILED: '분석 실패',
  AUTO_PASS: '자동 통과',
  AUTO_FAIL: '자동 불량',
};


const badgeTone: Record<DisplayStateV4, { bg: string; fg: string }> = {
  ANALYZING: { bg: '#EAF0FF', fg: '#2054D8' },
  REVIEW_PENDING: { bg: '#FFF3E5', fg: '#A74B12' },
  REVIEW_DONE: { bg: '#F0F3F8', fg: '#334155' },
  FAILED: { bg: '#FFF0ED', fg: '#B42318' },
  AUTO_PASS: { bg: '#EAFBF2', fg: '#067647' },
  AUTO_FAIL: { bg: '#FFF0ED', fg: '#B42318' },
};

function dateText(value: string | null): string {
  if (!value) return '미제공';
  const ms = Date.parse(value);
  return Number.isFinite(ms)
    ? new Date(ms).toLocaleString('ko-KR', { hour12: false })
    : '미제공';
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : '검사 이력 조회에 실패했습니다.';
}

export default function HistoryLiveScreenV4() {
  const {role} = useVerifiedRoleV4();
  const params=useLocalSearchParams<{partCode?:string;displayState?:string}>();
  const [partCode, setPartCode] = useState<PartFilter>(()=>parts.find(option=>option.value===params.partCode)?.value??'');
  const [stateFilter, setStateFilter] = useState<StateFilter>(()=>states.find(option=>option.value===params.displayState)?.value??'ALL');
  const [filtersExpanded,setFiltersExpanded]=useState(false);
  const [period, setPeriod] = useState<PeriodFilter>(0);
  const [page, setPage] = useState(0);
  const [data, setData] = useState<HistoryPageV4 | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSerial = useRef(0);

  const load = useCallback(async (initial: boolean) => {
    const serial = ++requestSerial.current;
    if (initial) {
      setData(null);
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);

    try {
      const from = period
        ? new Date(Date.now() - period * 24 * 60 * 60 * 1000).toISOString()
        : undefined;
      const result = await reader.history({
        page,
        size: PAGE_SIZE,
        ...(partCode ? { partCode } : {}),
        ...(stateFilter !== 'ALL' ? { displayState: stateFilter } : {}),
        ...(from ? { from } : {}),
      });
      if (requestSerial.current !== serial) return;
      setData(result.value);
    } catch (cause) {
      if (requestSerial.current !== serial) return;
      setError(errorText(cause));
    } finally {
      if (requestSerial.current === serial) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [page, partCode, stateFilter, period]);

  useFocusEffect(useCallback(() => {
    void load(true);
    return () => { requestSerial.current += 1; };
  }, [load]));

  // Invalidate an in-flight read immediately when the user changes filters.
  // The existing focus effect loads the new query; no client-side filtering.
  const resetForFilter = () => {
    requestSerial.current += 1;
    setPage(0);
    setData(null);
    setError(null);
    setLoading(true);
    setRefreshing(false);
  };
  const setStatus = (next: StateFilter) => {
    if (next === stateFilter) return;
    resetForFilter();
    setStateFilter(next);
  };
  const setRange = (next: PeriodFilter) => {
    if (next === period) return;
    resetForFilter();
    setPeriod(next);
  };
  const selectPart = (next: PartFilter) => {
    if (next === partCode) return;
    resetForFilter();
    setPartCode(next);
  };
  const toDetail = (row: HistoryRowV4) => router.push({
    pathname: '/inspection-live',
    params: { inspectionId: row.inspectionId },
  });

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <Text style={styles.title}>검사 이력</Text>
        <Text style={styles.subtitle}>상태 · 기간 · 부품별 검사 기록 조회</Text>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.body}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={()=>{if(!loading&&!refreshing)void load(false);}}/>}>
        <View style={styles.card}>
          <Pressable testID="history-filter-toggle" style={styles.filterSummary} accessibilityRole="button"
            accessibilityState={{expanded:filtersExpanded}} accessibilityLabel="검사 이력 검색 조건"
            onPress={()=>setFiltersExpanded(value=>!value)}>
            <View style={styles.resultInfo}>
              <Text style={styles.cardTitle}>검색 조건</Text>
              <Text style={styles.caption}>{states.find(option=>option.value===stateFilter)?.label} · {periods.find(option=>option.value===period)?.label} · {parts.find(option=>option.value===partCode)?.label}</Text>
            </View>
            <Text style={styles.refreshText}>{filtersExpanded?'접기 −':'변경 +'}</Text>
          </Pressable>
          {filtersExpanded&&<>
          <Text style={styles.filterTitle}>검사 상태</Text>
          <View style={styles.chipRow}>
            {states.map((option) => (
              <Pressable
                key={option.value}
                style={[styles.chip, stateFilter === option.value && styles.chipActive]}
                onPress={() => setStatus(option.value)}
                accessibilityRole="button"
                accessibilityState={{ selected: stateFilter === option.value }}
              >
                <Text style={[styles.chipText, stateFilter === option.value && styles.chipTextActive]}>
                  {option.label}
                </Text>
              </Pressable>
            ))}
          </View>

          <Text style={styles.filterTitle}>접수 기간</Text>
          <View style={styles.chipRow}>
            {periods.map((option) => (
              <Pressable
                key={option.value}
                style={[styles.chip, period === option.value && styles.chipActive]}
                onPress={() => setRange(option.value)}
                accessibilityRole="button"
                accessibilityState={{ selected: period === option.value }}
              >
                <Text style={[styles.chipText, period === option.value && styles.chipTextActive]}>
                  {option.label}
                </Text>
              </Pressable>
            ))}
          </View>

          <Text style={styles.filterTitle}>부품 선택</Text>
          <View style={styles.chipRow}>
            {parts.map((option) => (
              <Pressable
                key={option.value || 'ALL_PARTS'}
                testID={'history-part-' + (option.value || 'ALL')}
                style={[styles.chip, partCode === option.value && styles.chipActive]}
                onPress={() => selectPart(option.value)}
                accessibilityRole="button"
                accessibilityState={{ selected: partCode === option.value }}
              >
                <Text style={[styles.chipText, partCode === option.value && styles.chipTextActive]}>
                  {option.label}
                </Text>
              </Pressable>
            ))}
          </View>
          </>}
        </View>

        <View style={styles.resultsCard}>
          <View style={styles.resultHeader}>
            <View style={styles.resultInfo}>
              <Text style={styles.sectionTitle}>검사 기록</Text>
              <Text style={styles.caption}>
                {data?.totalElements == null ? '총 건수 · 서버 조회' : '총 ' + data.totalElements + '건'}
              </Text>
            </View>
            <Pressable
              style={[styles.refreshButton, (loading || refreshing) && styles.disabled]}
              disabled={loading || refreshing}
              onPress={() => { void load(false); }}
              accessibilityRole="button"
            >
              <Text style={styles.refreshText}>새로고침</Text>
            </Pressable>
          </View>

          {loading && (
            <View style={styles.messageBox}>
              <ActivityIndicator />
              <Text style={styles.caption}>검사 이력을 불러오는 중입니다.</Text>
            </View>
          )}
          {refreshing && <Text style={styles.caption}>최신 검사 기록을 불러오는 중…</Text>}
          {error && (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{error}</Text>
              {data && <Text style={styles.warningText}>마지막으로 조회한 기록입니다. 현재와 다를 수 있습니다.</Text>}
              <Pressable style={styles.retryButton} onPress={() => { void load(!data); }} accessibilityRole="button">
                <Text style={styles.retryText}>다시 조회</Text>
              </Pressable>
            </View>
          )}
          {!loading && data?.items.length === 0 && (
            <View style={styles.messageBox}>
              <Text style={styles.caption}>현재 조건에 해당하는 검사 기록이 없습니다.</Text>
            </View>
          )}

          {data?.items.map((item, index) => (
            <Pressable
              key={item.inspectionId}
              style={[styles.recordRow, index !== 0 && styles.recordDivider]}
              onPress={() => toDetail(item)}
              accessibilityRole="button"
              accessibilityLabel={`${item.inspectionNo ?? '검사번호 미제공'}, ${stateLabels[item.displayState]}, ${partLabelV4(item.partCode)}${item.displayState==='REVIEW_PENDING'?', '+reviewListReasonV4(item.displayState,item.reviewReason):''}, 검사 상세 열기`}
            >
              <View style={styles.recordTop}>
                <View style={[styles.stateBadge, { backgroundColor: badgeTone[item.displayState].bg }]}>
                  <Text style={[styles.stateBadgeText, { color: badgeTone[item.displayState].fg }]}>
                    {stateLabels[item.displayState]}
                  </Text>
                </View>
                <Text style={styles.itemTitle}>
                  {item.inspectionNo ?? '검사번호 미제공'}
                </Text>
                <Text style={styles.recordArrow}>›</Text>
              </View>
              <Text style={styles.itemState}>{partLabelV4(item.partCode)}</Text>
              <Text style={styles.caption}>
                {item.displayState === 'REVIEW_PENDING'
                  ? reviewListReasonV4(item.displayState,item.reviewReason)
                  : item.source === 'MANUAL' || item.reviewReason === 'AI_UNAVAILABLE'
                  ? '수동 판정 · AI 분석 없음'
                  : item.displayState === 'FAILED'
                    ? 'AI 분석 실패'
                    : 'AI 예측 ' + qualityLabelV4(item.predictedQuality)}
                {' · 접수 '}{dateText(item.receivedAt)}
              </Text>
              {(item.correctedJudgement || item.finalJudgement) && (
                <View>
                  {historyJudgementLabelV4(item)?.split('\n').map((label, lineIndex) => (
                    <Text key={lineIndex} style={[
                      styles.recordOutcome,
                      (lineIndex === 0 ? item.correctedJudgement ?? item.finalJudgement : item.finalJudgement) === 'PASS'
                        ? styles.recordPass : styles.recordFail,
                    ]}>
                      {label}
                    </Text>
                  ))}
                </View>
              )}
              {item.errorCode && <Text style={[styles.errorText, styles.recordErrorCode]}>오류 코드: {item.errorCode}</Text>}
            </Pressable>
          ))}
        </View>

        {data && (
          <View style={styles.pagination}>
            <Pressable
              style={[styles.pageButton, page === 0 && styles.disabled]}
              disabled={page === 0 || loading || refreshing}
              onPress={() => setPage((current) => Math.max(0, current - 1))}
              accessibilityRole="button"
            >
              <Text style={styles.pageButtonText}>이전</Text>
            </Pressable>
            <Text style={styles.pageNumber}>{page + 1}페이지</Text>
            <Pressable
              style={[styles.pageButton, data.hasNext !== true && styles.disabled]}
              disabled={data.hasNext !== true || loading || refreshing}
              onPress={() => setPage((current) => current + 1)}
              accessibilityRole="button"
            >
              <Text style={styles.pageButtonText}>다음</Text>
            </Pressable>
          </View>
        )}
        {data?.hasNext === null && (
          <Text style={styles.caption}>서버가 다음 페이지 여부를 제공하지 않아 임의로 다음 페이지를 추정하지 않습니다.</Text>
        )}
      </ScrollView>

      {role && <LiveBottomNavV4 role={role} active="history"/>}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F5F7FB' },
  header: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#CBD5E1' },
  title: { fontSize: 23, fontWeight: '700', color: '#111827' },
  subtitle: { fontSize: 13, color: '#475569', marginTop: 5 },
  scroll: { flex: 1 },
  body: { paddingHorizontal: 20, paddingBottom: 35, gap: 12 },
  card: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E4E7EC', borderRadius: 14, padding: 14, gap: 10 },
  resultsCard: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E4E7EC', borderRadius: 14, padding: 14, gap: 10 },
  recordRow: { paddingVertical: 12, gap: 7, borderRadius: 7 },
  recordDivider: { borderTopWidth: 1, borderTopColor: '#E4E7EC' },
  recordTop: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 },
  stateBadge: { borderRadius: 999, minWidth: 70, paddingVertical: 6, paddingHorizontal: 8, alignItems: 'center' },
  stateBadgeText: { fontSize: 13, fontWeight: '700' },
  recordArrow: { marginLeft: 'auto', color: '#475569', fontSize: 20, fontWeight: '600' },
  recordOutcome: { fontSize: 13, fontWeight: '600' },
  recordPass: { color: '#2054D8' },
  recordFail: { color: '#B42318' },
  recordErrorCode: { fontWeight: '600' },
  cardTitle: { fontSize: 16, color: '#111827', fontWeight: '700' },
  filterSummary: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 8 },
  filterTitle: { fontSize: 13, fontWeight: '700', color: '#111827', marginTop: 4 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { justifyContent: 'center', paddingHorizontal: 12, paddingVertical: 11, minHeight: 44, borderRadius: 24, borderWidth: 1, borderColor: '#64748B', backgroundColor: '#EEF2F8' },
  chipActive: { backgroundColor: '#1E293B', borderColor: '#1E293B' },
  chipText: { fontSize: 13, color: '#334155', fontWeight: '600' },
  chipTextActive: { color: '#FFFFFF' },
  caption: { fontSize: 13, lineHeight: 18, color: '#475569' },
  resultHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  resultInfo: { flex: 1, gap: 3 },
  sectionTitle: { fontSize: 17, fontWeight: '700', color: '#111827' },
  refreshButton: { justifyContent: 'center', minHeight: 44, borderWidth: 1, borderColor: '#2054D8', padding: 9, borderRadius: 9 },
  refreshText: { color: '#2054D8', fontSize: 13, fontWeight: '700' },
  disabled: { opacity: 0.4 },
  messageBox: { backgroundColor: '#FFFFFF', borderRadius: 12, padding: 18, alignItems: 'center', gap: 12 },
  errorBox: { padding: 15, borderRadius: 12, backgroundColor: '#FFF0ED', gap: 10 },
  errorText: { fontSize: 13, lineHeight: 18, color: '#B42318' },
  warningText: { fontSize: 13, lineHeight: 18, color: '#92400E' },
  retryButton: { justifyContent: 'center', minHeight: 44, padding: 9, borderRadius: 8, borderWidth: 1, borderColor: '#B42318', alignSelf: 'flex-start' },
  retryText: { color: '#B42318', fontSize: 13, fontWeight: '700' },
  itemCard: { backgroundColor: '#FFFFFF', borderRadius: 13, borderWidth: 1, borderColor: '#E4E7EC', padding: 14, gap: 5 },
  itemTitleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 6 },
  itemTitle: { fontSize: 14, fontWeight: '700', color: '#111827', flexGrow: 1, flexShrink: 1, minWidth: 0 },
  detailLink: { fontSize: 13, fontWeight: '700', color: '#2054D8' },
  itemState: { fontSize: 13, fontWeight: '600', color: '#334155' },
  pagination: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginTop: 4 },
  pageButton: { justifyContent: 'center', minHeight: 44, borderWidth: 1, borderColor: '#2054D8', borderRadius: 9, paddingHorizontal: 18, paddingVertical: 10 },
  pageButtonText: { color: '#2054D8', fontSize: 13, fontWeight: '700' },
  pageNumber: { color: '#475569', fontSize: 13 },
  footer: { color: '#475569', fontSize: 13, textAlign: 'center', paddingTop: 5 },
  bottomNav: { height: 58, flexDirection: 'row', marginHorizontal: 20, marginBottom: 6, backgroundColor: '#FFFFFF', borderRadius: 15, borderWidth: 1, borderColor: '#E4E7EC' },
  navItem: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 2 },
  navIcon: { fontSize: 17, color: '#475569' },
  navText: { fontSize: 13, color: '#475569' },
  active: { color: '#2054D8', fontWeight: '700' },
});
