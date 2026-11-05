import React, { useCallback, useEffect, useRef, useState } from 'react';
import { router, Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import {
  ActivityIndicator,
  AppState,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { authV4 } from '../api/backendV4/authRuntime';
import { createInspectionReadServiceV4 } from '../api/backendV4/inspectionReadService';
import type { InspectionViewV4 } from '../api/backendV4/types';
import { ApiV4RequestError } from '../api/backendV4/httpCore';

const inspectionReader = createInspectionReadServiceV4({
  mode: 'api',
  transport: authV4,
});

function formatTime(value: string | null | undefined): string {
  if (!value) return '미제공';
  const time = Date.parse(value);
  return Number.isFinite(time)
    ? new Date(time).toLocaleString('ko-KR', { hour12: false })
    : '미제공';
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiV4RequestError) {
    return `${error.message} (${error.code})${error.traceId ? `\ntraceId: ${error.traceId}` : ''}`;
  }
  return error instanceof Error ? error.message : '알 수 없는 오류가 발생했습니다.';
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

function ImagePanel({
  title,
  url,
  missingText,
  onLoadError,
}: {
  title: string;
  url: string | null;
  missingText: string;
  onLoadError: (url: string) => void;
}) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>{title}</Text>
      {url ? (
        <Image
          source={{ uri: url }}
          style={styles.inspectionImage}
          resizeMode="contain"
          onError={() => onLoadError(url)}
        />
      ) : (
        <Text style={styles.muted}>{missingText}</Text>
      )}
    </View>
  );
}

export default function InspectionLiveScreen() {
  const { inspectionId } = useLocalSearchParams<{ inspectionId?: string }>();
  const id = typeof inspectionId === 'string' ? inspectionId : '';
  const [detail, setDetail] = useState<InspectionViewV4 | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imageNotice, setImageNotice] = useState<string | null>(null);
  const [isFocused, setIsFocused] = useState(false);
  const [isForeground, setIsForeground] = useState(
    AppState.currentState === 'active' || AppState.currentState == null,
  );
  const requestSerial = useRef(0);
  const failedImageUrls = useRef(new Set<string>());
  const lastAutoRefreshedExpiry = useRef<string | null>(null);
  const pendingImageRefreshOnResume = useRef(false);

  // 화면 이탈이나 앱 백그라운드 진입 시 자동 이미지 갱신을 정지합니다.
  useFocusEffect(useCallback(() => {
    setIsFocused(true);
    return () => setIsFocused(false);
  }, []));

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (state) => {
      setIsForeground(state === 'active');
    });
    return () => subscription.remove();
  }, []);

  const load = useCallback(async (initial = false) => {
    const serial = ++requestSerial.current;
    if (initial) {
      setLoading(true);
      setDetail(null);
      failedImageUrls.current.clear();
      lastAutoRefreshedExpiry.current = null;
      pendingImageRefreshOnResume.current = false;
      setImageNotice(null);
    } else {
      setRefreshing(true);
    }
    setError(null);
    try {
      if (!id) throw new Error('검사 UUID가 전달되지 않았습니다.');
      const response = await inspectionReader.detail(id);
      if (serial !== requestSerial.current) return;
      const next = response.value;
      setDetail(next);
      // 서버가 실패했던 이미지 URL을 그대로 재발급해도 성공으로 표시하지 않습니다.
      const urls = [next.originalImageUrl, next.gradcamImageUrl].filter(
        (url): url is string => typeof url === 'string',
      );
      const stillBroken = urls.some((url) => failedImageUrls.current.has(url));
      setImageNotice(stillBroken
        ? '서버에서 같은 이미지 주소를 받았습니다. 계속 실패하면 서명 URL과 저장소 연결을 확인해 주세요.'
        : null);
    } catch (cause) {
      if (serial !== requestSerial.current) return;
      setError(errorMessage(cause));
    } finally {
      if (serial === requestSerial.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [id]);

  useEffect(() => {
    void load(true);
    return () => { requestSerial.current += 1; };
  }, [load]);

  // 화면이 활성 상태인 동안에만 만료 30초 전 상세를 다시 조회합니다.
  // 복귀 시 이미 만료됐으면 즉시 조회하되, 같은 만료 시각은 자동 재시도하지 않습니다.
  useEffect(() => {
    if (!isFocused || !isForeground || loading || refreshing) return;
    const expiry = detail?.imageUrlExpiresAt;
    if (!expiry || lastAutoRefreshedExpiry.current === expiry) return;
    const expiryMs = Date.parse(expiry);
    if (!Number.isFinite(expiryMs)) return;
    const delay = Math.max(0, expiryMs - Date.now() - 30_000);
    const timer = setTimeout(() => {
      lastAutoRefreshedExpiry.current = expiry;
      void load(false);
    }, delay);
    return () => clearTimeout(timer);
  }, [detail?.imageUrlExpiresAt, isFocused, isForeground, loading, refreshing, load]);

  // 비활성 상태에서 발생한 이미지 실패는 복귀 후 재조회합니다.
  useEffect(() => {
    if (!isFocused || !isForeground || loading || refreshing || !pendingImageRefreshOnResume.current) return;
    pendingImageRefreshOnResume.current = false;
    void load(false);
  }, [isFocused, isForeground, loading, refreshing, load]);

  const handleImageError = (url: string) => {
    // 과거 검사 또는 만료된 이전 이미지의 늦은 콜백은 무시합니다.
    if (url !== detail?.originalImageUrl && url !== detail?.gradcamImageUrl) return;
    if (failedImageUrls.current.has(url)) return;
    failedImageUrls.current.add(url);
    setImageNotice('이미지 접근에 실패하여 새 주소를 조회합니다. 같은 주소가 실패하면 저장소 접근을 확인해 주세요.');
    if (!isFocused || !isForeground) {
      pendingImageRefreshOnResume.current = true;
      return;
    }
    void load(false);
  };

  // 새 검사로 이동하는 첫 렌더에서도 이전 검사의 데이터를 숨깁니다.
  const visibleDetail = detail?.inspectionId === id ? detail : null;

  const gradcamMissing = visibleDetail?.gradcamStatus === 'NO_ACTIVATION'
    ? 'AI 예측은 완료됐지만, 위치별 강조 반응이 없어 판단 근거 이미지를 제공하기 어렵습니다.'
    : visibleDetail?.gradcamStatus === 'NOT_REQUIRED'
      ? 'AI가 GOOD으로 예측하여 Grad-CAM을 생성하지 않았습니다.'
      : visibleDetail?.gradcamStatus === 'FAILED'
        ? 'Grad-CAM 생성에 실패했습니다. 원본 사진과 AI 예측을 참고하세요.'
        : 'Grad-CAM 이미지가 제공되지 않았습니다.';

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} accessibilityRole="button">
          <Text style={styles.back}>‹ 모니터링으로 돌아가기</Text>
        </Pressable>
        <Text style={styles.title}>실제 서버 검사 상세</Text>
        <Text style={styles.muted}>SERVER · 검사 UUID로 조회 · 읽기 전용</Text>
      </View>

      <ScrollView contentContainerStyle={styles.body}>
        {refreshing && !loading && (
          <Text style={styles.muted}>서버에서 최신 상세 정보를 확인하는 중…</Text>
        )}
        {loading && (
          <View style={styles.card}>
            <ActivityIndicator />
            <Text style={styles.muted}>실제 검사 데이터를 불러오는 중입니다.</Text>
          </View>
        )}

        {error && (
          <View style={[styles.card, styles.errorCard]}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {error && visibleDetail && (
          <View style={styles.staleCard}>
            <Text style={styles.staleText}>
              서버 조회에 실패했습니다. 아래 내용은 마지막으로 조회한 정보이며 최신 상태가 아닐 수 있습니다.
            </Text>
          </View>
        )}

        {!loading && !visibleDetail && (
          <Pressable style={styles.button} onPress={() => void load(true)}>
            <Text style={styles.buttonText}>다시 조회</Text>
          </Pressable>
        )}

        {visibleDetail && (
          <>
            <View style={styles.card}>
              <Text style={styles.cardTitle}>{visibleDetail.inspectionNo}</Text>
              <Field label="부품" value={visibleDetail.partCode} />
              <Field label="상태" value={`${visibleDetail.displayStateLabel} (${visibleDetail.displayState})`} />
              <Field label="접수 시각" value={formatTime(visibleDetail.receivedAt)} />
              <Field label="검사 UUID" value={visibleDetail.inspectionId} />
            </View>

            {imageNotice && (
              <View style={styles.staleCard}>
                <Text style={styles.staleText}>{imageNotice}</Text>
              </View>
            )}

            <ImagePanel
              title="원본 사진"
              url={visibleDetail.originalImageUrl}
              missingText="원본 이미지 주소가 제공되지 않았습니다."
              onLoadError={handleImageError}
            />

            <ImagePanel
              title="AI 판단 근거 · Grad-CAM"
              url={visibleDetail.gradcamImageUrl}
              missingText={gradcamMissing}
              onLoadError={handleImageError}
            />

            <View style={styles.card}>
              <Text style={styles.cardTitle}>AI 분석 · 정책 · 최종 판정</Text>
              <Field label="AI 예측" value={visibleDetail.prediction ?? '미제공'} />
              <Field
                label="보정 불량 확률"
                value={visibleDetail.calibratedDefectProbability === null
                  ? '미준비 / 미제공'
                  : `${(visibleDetail.calibratedDefectProbability * 100).toFixed(2)}%`}
              />
              <Field label="AI 모델" value={visibleDetail.modelVersion ?? '미제공'} />
              <Field label="REVIEW 사유" value={visibleDetail.reviewReasonText ?? '해당 없음'} />
              <Field label="최종 작업자 판정" value={visibleDetail.finalJudgement ?? '미확정'} />
              <Field label="판정 주체" value={visibleDetail.judgedBy ?? '미제공'} />
              <Field label="판정 시각" value={formatTime(visibleDetail.confirmedAt)} />
              {visibleDetail.errorCode && <Field label="오류 코드" value={visibleDetail.errorCode} />}
              {visibleDetail.errorMessage && <Text style={styles.errorText}>{visibleDetail.errorMessage}</Text>}
            </View>

            <View style={styles.card}>
              <Text style={styles.cardTitle}>이미지 접근 주소</Text>
              <Field label="서명 URL 만료 시각" value={formatTime(visibleDetail.imageUrlExpiresAt)} />
              <Text style={styles.muted}>
                화면이 활성 상태일 때 만료 30초 전 새 주소를 조회합니다.
                백그라운드에서는 자동 조회를 중단하며, 복귀하면 만료 여부를 다시 확인합니다.
                이미지 로딩 실패 시에도 새 주소를 다시 조회합니다.
              </Text>
              <Pressable
                style={[styles.button, refreshing && styles.disabledButton]}
                disabled={refreshing}
                onPress={() => {
                  lastAutoRefreshedExpiry.current = visibleDetail.imageUrlExpiresAt;
                  void load(false);
                }}
              >
                <Text style={styles.buttonText}>
                  {refreshing ? '조회 중…' : '상세 · 이미지 URL 다시 조회'}
                </Text>
              </Pressable>
            </View>
            <Text style={styles.muted}>
              이 화면은 실제 서버 조회 전용입니다. 판정·재검사는 별도 작업에서 연결합니다.
              Grad-CAM은 판단 근거이지 결함 좌표나 마스크가 아닙니다.
            </Text>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F5F7FB' },
  header: { paddingHorizontal: 20, paddingTop: 14, paddingBottom: 14, gap: 8 },
  back: { color: '#2054D8', fontSize: 13, fontWeight: '600' },
  title: { color: '#111827', fontSize: 23, fontWeight: '700' },
  body: { paddingHorizontal: 20, paddingBottom: 35, gap: 12 },
  card: { backgroundColor: '#FFF', borderRadius: 14, borderWidth: 1, borderColor: '#E4E7EC', padding: 16, gap: 10 },
  cardTitle: { color: '#111827', fontSize: 17, fontWeight: '700' },
  field: { gap: 3 },
  label: { color: '#64748B', fontSize: 12 },
  value: { color: '#111827', fontSize: 14, fontWeight: '500' },
  muted: { color: '#64748B', fontSize: 12, lineHeight: 18 },
  inspectionImage: { height: 265, width: '100%', backgroundColor: '#EEF2F8', borderRadius: 10 },
  button: { backgroundColor: '#2054D8', padding: 13, borderRadius: 10, alignItems: 'center' },
  buttonText: { color: '#FFF', fontSize: 13, fontWeight: '700' },
  disabledButton: { opacity: 0.5 },
  errorCard: { backgroundColor: '#FFF0ED' },
  staleCard: { backgroundColor: '#FFF3E5', borderRadius: 12, padding: 12 },
  staleText: { color: '#92400E', fontSize: 12, lineHeight: 18 },
  errorText: { color: '#B42318', fontSize: 13 },
});
