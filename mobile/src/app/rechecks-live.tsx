import React, { useCallback, useRef, useState } from 'react';
import { router, Stack, useFocusEffect } from 'expo-router';
import {
  ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { authV4 } from '../api/backendV4/authRuntime';
import { ApiV4RequestError } from '../api/backendV4/httpCore';
import { createRecheckServiceV4 } from '../api/backendV4/recheckServiceV4';
import type { RecheckPageV4, RecheckStatusV4 } from '../api/backendV4/recheckCoreV4';

type Role = 'WORKER' | 'ADMIN';
type Filter = 'PENDING' | 'DONE' | 'FAIL_UNACKNOWLEDGED';
type Part = 'ALL' | 'DOOR' | 'FRAME' | 'COWL_COVER';
const service = createRecheckServiceV4(authV4);

function formatTime(value: string | null): string {
  if (!value) return '미제공';
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp)
    ? new Date(timestamp).toLocaleString('ko-KR', { hour12: false }) : '미제공';
}

function describeError(cause: unknown): string {
  if (cause instanceof ApiV4RequestError) {
    if (cause.httpStatus === 404) {
      return '재확인 기록을 불러올 수 없습니다. 잠시 후 다시 조회해 주세요.';
    }
    return cause.message;
  }
  return cause instanceof Error ? cause.message : '재확인 목록을 불러오지 못했습니다.';
}

export default function RechecksLiveScreen() {
  const [role, setRole] = useState<Role | null>(null);
  const [filter, setFilter] = useState<Filter>('PENDING');
  const [part, setPart] = useState<Part>('ALL');
  const [page, setPage] = useState(0);
  const [data, setData] = useState<RecheckPageV4 | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestSerial = useRef(0);

  const load = useCallback(async () => {
    const serial = ++requestSerial.current;
    setLoading(true);
    setError(null);
    setData(null); // 다른 필터의 예전 결과를 최신 목록으로 오해하지 않도록 숨깁니다.
    try {
      const session = await authV4.restore();
      if (serial !== requestSerial.current) return;
      if (!session.signedIn || (session.role !== 'WORKER' && session.role !== 'ADMIN')) {
        setRole(null);
        throw new Error('실제 서버 WORKER 또는 ADMIN 계정으로 로그인해 주세요.');
      }
      setRole(session.role);
      const status: RecheckStatusV4 = filter === 'PENDING' ? 'PENDING' : 'DONE';
      const result = await service.list({
        status, page, size: 20,
        ...(filter === 'FAIL_UNACKNOWLEDGED' ? {result: 'FAIL' as const, acknowledged: false} : {}),
        ...(part !== 'ALL' ? {partCode: part} : {}),
      });
      if (serial !== requestSerial.current) return;
      setData(result);
    } catch (cause) {
      if (serial === requestSerial.current) setError(describeError(cause));
    } finally {
      if (serial === requestSerial.current) setLoading(false);
    }
  }, [filter, part, page]);

  useFocusEffect(useCallback(() => {
    void load();
    return () => { requestSerial.current += 1; };
  }, [load]));

  const changeFilter = (next: Filter) => { setPage(0); setFilter(next); };
  const changePart = (next: Part) => { setPage(0); setPart(next); };

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} accessibilityRole="button" style={styles.backTouch}>
          <Text style={styles.link}>‹ 뒤로</Text>
        </Pressable>
        <Text style={styles.title}>AUTO_PASS 표본 재확인</Text>
        <Text style={styles.sub}>
          {role === 'ADMIN' ? '관리자 조회 · 확인함 처리' : role === 'WORKER' ? '작업자 조회 · 재확인' : '권한 확인 중'}
        </Text>
      </View>
      <ScrollView contentContainerStyle={styles.body}>
        <View style={styles.notice}>
          <Text style={styles.noticeText}>
            원래 AUTO_PASS의 PASS · SYSTEM 판정은 유지됩니다. REVIEW 업무 대기열과 재확인 대기열은 별도입니다.
          </Text>
        </View>
        {role === 'ADMIN' && (
          <Pressable accessibilityRole="button"
            style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}
            onPress={() => router.push('/recheck-summary-live')}>
            <Text style={styles.link}>관리자 공동시험 요약 · AUTO_PASS 추정 불량률 보기 ›</Text>
          </Pressable>
        )}
        <Text style={styles.sectionTitle}>조회 유형</Text>
        <View style={styles.row}>
          {([
            ['PENDING', '재확인 대기'], ['DONE', '재확인 완료'], ['FAIL_UNACKNOWLEDGED', '미확인 FAIL'],
          ] as const).map(([value, label]) => (
            <Pressable key={value} accessibilityRole="button"
              accessibilityState={{ selected: filter === value }}
              onPress={() => changeFilter(value)}
              style={[styles.filter, filter === value && styles.selected]}>
              <Text style={[styles.filterText, filter === value && styles.selectedText]}>{label}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.sectionTitle}>부품</Text>
        <View style={styles.row}>
          {(['ALL', 'DOOR', 'FRAME', 'COWL_COVER'] as const).map((code) => (
            <Pressable key={code} accessibilityRole="button"
              accessibilityState={{ selected: part === code }}
              onPress={() => changePart(code)}
              style={[styles.filter, part === code && styles.selected]}>
              <Text style={[styles.filterText, part === code && styles.selectedText]}>{code}</Text>
            </Pressable>
          ))}
        </View>

        {loading && <View style={styles.card}>
          <ActivityIndicator />
          <Text style={styles.muted}>실제 서버의 재확인 목록 조회 중…</Text>
        </View>}
        {error && <View style={[styles.card, styles.error]}>
          <Text style={styles.errorText}>{error}</Text>
        </View>}
        {!loading && <Pressable accessibilityRole="button" onPress={() => void load()}
          style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}>
          <Text style={styles.link}>목록 다시 조회</Text>
        </Pressable>}
        {!loading && data && (
          <>
            <Text style={styles.muted}>
              {filter === 'FAIL_UNACKNOWLEDGED' ? '재확인 FAIL 중 관리자가 아직 확인하지 않은 건만 표시' :
                filter === 'PENDING' ? '선정된 AUTO_PASS 중 작업자 재확인 대기' : '재확인이 제출된 기록'}
              {' · 총 '}{data.totalElements}건
            </Text>
            {data.items.length === 0 && (
              <View style={styles.card}>
                <Text style={styles.muted}>
                  {filter === 'PENDING'
                    ? '현재 재확인 대기 건이 없습니다. 시험 기능이 비활성 상태이거나 아직 표본이 생성되지 않았을 수 있습니다.'
                    : '이 조건에 해당하는 재확인 기록이 없습니다.'}
                </Text>
              </View>
            )}
            {data.items.map((item) => (
              <Pressable key={item.inspectionId} accessibilityRole="button"
                accessibilityLabel={item.inspectionNo + ' 검사 상세'}
                onPress={() => router.push({ pathname: '/inspection-live',
                  params: {inspectionId: item.inspectionId} })}
                style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
                <View style={styles.rowBetween}>
                  <Text style={styles.itemTitle}>{item.inspectionNo} · {item.partCode}</Text>
                  <Text style={[
                    styles.statusText,
                    item.result === 'FAIL' && styles.errorText,
                  ]}>{item.result === 'FAIL' ? '재확인 FAIL' :
                    item.result === 'PASS' ? '재확인 PASS' : '재확인 대기'}</Text>
                </View>
                <Text style={styles.muted}>
                  표본 구간: {item.stratum} · 선정: {formatTime(item.sampledAt)}
                </Text>
                {item.result === 'FAIL' && (
                  <Text style={styles.errorText}>
                    {item.acknowledgedAt ? '관리자 확인함 · 해결 완료 아님' : '관리자 확인 필요'}
                  </Text>
                )}
                {item.acknowledgedAt && <Text style={styles.muted}>
                  확인 관리자: {item.acknowledgedBy ?? '미제공'} · {formatTime(item.acknowledgedAt)}
                </Text>}
                <Text style={styles.link}>검사 상세 및 원래 판정 함께 보기 ›</Text>
              </Pressable>
            ))}
            <View style={styles.pagination}>
              <Pressable accessibilityRole="button" disabled={page === 0}
                onPress={() => setPage((v) => Math.max(0, v - 1))}
                style={[styles.secondaryButton, page === 0 && styles.disabled]}>
                <Text style={styles.link}>이전</Text>
              </Pressable>
              <Text style={styles.muted}>{page + 1} / {Math.max(1, data.totalPages)} 페이지</Text>
              <Pressable accessibilityRole="button" disabled={page + 1 >= data.totalPages}
                onPress={() => setPage((v) => v + 1)}
                style={[styles.secondaryButton, page + 1 >= data.totalPages && styles.disabled]}>
                <Text style={styles.link}>다음</Text>
              </Pressable>
            </View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  backTouch: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' },
  screen: { flex: 1, backgroundColor: '#F5F7FB' },
  header: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 12, gap: 7 },
  title: { fontSize: 22, color: '#111827', fontWeight: '700' },
  sub: { fontSize: 13, color: '#64748B' },
  body: { paddingHorizontal: 20, paddingBottom: 28, gap: 12 },
  notice: { backgroundColor: '#EBF1FF', borderRadius: 12, padding: 12 },
  noticeText: { fontSize: 13, lineHeight: 19, color: '#2054D8' },
  sectionTitle: { fontSize: 14, color: '#111827', fontWeight: '700' },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  filter: { justifyContent: 'center', minHeight: 44, borderWidth: 1, borderColor: '#CBD5E1', backgroundColor: '#FFF',
    borderRadius: 10, paddingHorizontal: 11, paddingVertical: 11 },
  selected: { backgroundColor: '#2054D8', borderColor: '#2054D8' },
  filterText: { fontSize: 12, color: '#475569', fontWeight: '600' },
  selectedText: { color: '#FFF' },
  card: { padding: 14, borderRadius: 13, borderWidth: 1, borderColor: '#E4E7EC',
    backgroundColor: '#FFF', gap: 9 },
  itemTitle: { fontSize: 14, color: '#111827', fontWeight: '700' },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  statusText: { fontSize: 12, fontWeight: '700', color: '#067647' },
  muted: { fontSize: 13, color: '#64748B', lineHeight: 19 },
  link: { fontSize: 14, color: '#2054D8', fontWeight: '700' },
  errorText: { fontSize: 12, color: '#B42318', lineHeight: 18 },
  error: { backgroundColor: '#FFF0ED' },
  secondaryButton: { justifyContent: 'center', minHeight: 44, borderWidth: 1, borderColor: '#CBD5E1', borderRadius: 10,
    paddingHorizontal: 13, paddingVertical: 11, alignItems: 'center' },
  pressed: { opacity: 0.75 },
  disabled: { opacity: 0.35 },
  pagination: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
});
