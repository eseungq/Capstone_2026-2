import React, { useCallback, useEffect, useRef, useState } from 'react';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import {
  ActivityIndicator,
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
  const requestSerial = useRef(0);
  const failedImageUrls = useRef(new Set<string>());
  const lastAutoRefreshedExpiry = useRef<string | null>(null);

  const load = useCallback(async (initial = false) => {
    const serial = ++requestSerial.current;
    if (initial) {
      setLoading(true);
      setDetail(null);
      failedImageUrls.current.clear();
      lastAutoRefreshedExpiry.current = null;
    } else {
      setRefreshing(true);
    }
    setError(null);
    try {
      if (!id) throw new Error('검사 UUID가 전달되지 않았습니다.');
      const response = await inspectionReader.detail(id);
      if (serial !== requestSerial.current) return;
      setDetail(response.value);
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

  // 접근 URL이 만료되기 30초 전에 GET 상세를 재조회합니다.
  // 서버가 같은 만료 시각을 반환해도 무한 재조회하지 않습니다.
  useEffect(() => {
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
  }, [detail?.imageUrlExpiresAt, load]);

  const handleImageError = (url: string) => {
    if (failedImageUrls.current.has(url)) return;
    failedImageUrls.current.add(url);
    void load(false);
  };

  const gradcamMissing = detail?.gradcamStatus === 'NO_ACTIVATION'
    ? 'AI 예측은 완료됐지만, 위치별 강조 반응이 없어 판단 근거 이미지를 제공하기 어렵습니다.'
    : detail?.gradcamStatus === 'NOT_REQUIRED'
      ? 'AI가 GOOD으로 예측하여 Grad-CAM을 생성하지 않았습니다.'
      : detail?.gradcamStatus === 'FAILED'
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

        {!loading && !detail && (
          <Pressable style={styles.button} onPress={() => void load(true)}>
            <Text style={styles.buttonText}>다시 조회</Text>
          </Pressable>
        )}

        {detail && (
          <>
            <View style={styles.card}>
              <Text style={styles.cardTitle}>{detail.inspectionNo}</Text>
              <Field label="부품" value={detail.partCode} />
              <Field label="상태" value={`${detail.displayStateLabel} (${detail.displayState})`} />
              <Field label="접수 시각" value={formatTime(detail.receivedAt)} />
              <Field label="검사 UUID" value={detail.inspectionId} />
            </View>

            <ImagePanel
              title="원본 사진"
              url={detail.originalImageUrl}
              missingText="원본 이미지 주소가 제공되지 않았습니다."
              onLoadError={handleImageError}
            />

            <ImagePanel
              title="AI 판단 근거 · Grad-CAM"
              url={detail.gradcamImageUrl}
              missingText={gradcamMissing}
              onLoadError={handleImageError}
            />

            <View style={styles.card}>
              <Text style={styles.cardTitle}>AI 분석 · 정책 · 최종 판정</Text>
              <Field label="AI 예측" value={detail.prediction ?? '미제공'} />
              <Field
                label="보정 불량 확률"
                value={detail.calibratedDefectProbability === null
                  ? '미준비 / 미제공'
                  : `${(detail.calibratedDefectProbability * 100).toFixed(2)}%`}
              />
              <Field label="AI 모델" value={detail.modelVersion ?? '미제공'} />
              <Field label="REVIEW 사유" value={detail.reviewReasonText ?? '해당 없음'} />
              <Field label="최종 작업자 판정" value={detail.finalJudgement ?? '미확정'} />
              <Field label="판정 주체" value={detail.judgedBy ?? '미제공'} />
              <Field label="판정 시각" value={formatTime(detail.confirmedAt)} />
              {detail.errorCode && <Field label="오류 코드" value={detail.errorCode} />}
              {detail.errorMessage && <Text style={styles.errorText}>{detail.errorMessage}</Text>}
            </View>

            <View style={styles.card}>
              <Text style={styles.cardTitle}>이미지 접근 주소</Text>
              <Field label="서명 URL 만료 시각" value={formatTime(detail.imageUrlExpiresAt)} />
              <Text style={styles.muted}>
                만료되기 30초 전 자동으로 새 주소를 조회합니다.
                이미지 로드 실패 시에도 다시 조회합니다.
              </Text>
              <Pressable
                style={[styles.button, refreshing && styles.disabledButton]}
                disabled={refreshing}
                onPress={() => void load(false)}
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
  errorText: { color: '#B42318', fontSize: 13 },
});
