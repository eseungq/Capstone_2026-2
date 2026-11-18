import React, { useCallback, useEffect, useRef, useState } from 'react';
import { router, Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { ActivityIndicator, AppState, Image, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { authV4 } from '../api/backendV4/authRuntime';
import { createInspectionReadServiceV4 } from '../api/backendV4/inspectionReadService';
import type { InspectionViewV4 } from '../api/backendV4/types';
import { ApiV4RequestError } from '../api/backendV4/httpCore';

type ImageKind = 'original' | 'gradcam';
const reader = createInspectionReadServiceV4({ mode: 'api', transport: authV4 });

function imageUrl(detail: InspectionViewV4, kind: ImageKind): string | null {
  return kind === 'original' ? detail.originalImageUrl : detail.gradcamImageUrl;
}

function missingImageText(detail: InspectionViewV4, kind: ImageKind): string {
  if (kind === 'original') return '원본 이미지가 제공되지 않았습니다.';
  if (detail.gradcamStatus === 'NOT_REQUIRED') return 'GOOD 예측에 대한 판단 근거 이미지는 생성되지 않았습니다.';
  if (detail.gradcamStatus === 'NO_ACTIVATION') return 'AI의 위치별 강조 반응이 없어 판단 근거 이미지를 제공할 수 없습니다.';
  if (detail.gradcamStatus === 'FAILED') return 'AI 판단 근거 이미지 생성에 실패했습니다.';
  return 'AI 판단 근거 이미지를 제공하지 않았습니다.';
}

function getErrorText(error: unknown): string {
  if (error instanceof ApiV4RequestError) {
    return error.code === 'IMAGE_NOT_AVAILABLE'
      ? '이미지 파일을 제공받지 못했습니다. (IMAGE_NOT_AVAILABLE)'
      : '서버에서 사진 정보를 조회하지 못했습니다. 연결 상태를 확인해 주세요.';
  }
  return error instanceof Error ? error.message : '검사 상세를 불러오지 못했습니다.';
}

/** UUID만 전달받아 GET /inspections/{id}으로 이미지 주소를 새로 발급받습니다. */
export default function InspectionImageLiveScreen() {
  const { inspectionId, kind } = useLocalSearchParams<{ inspectionId?: string; kind?: string }>();
  const id = typeof inspectionId === 'string' ? inspectionId : '';
  const [imageKind, setImageKind] = useState<ImageKind>(kind === 'gradcam' ? 'gradcam' : 'original');
  const imageKindRef = useRef<ImageKind>(imageKind);
  imageKindRef.current = imageKind;

  const [detail, setDetail] = useState<InspectionViewV4 | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const { width } = useWindowDimensions();
  const failedUrls = useRef(new Set<string>());
  const requestSerial = useRef(0);
  const lastExpiryRefresh = useRef<string | null>(null);
  const [isFocused, setIsFocused] = useState(false);
  const [isForeground, setIsForeground] = useState(
    AppState.currentState === 'active' || AppState.currentState == null,
  );

  const load = useCallback(async (initial = false, manualRetry = false) => {
    const serial = ++requestSerial.current;
    if (initial) {
      setLoading(true);
      setDetail(null);
      failedUrls.current.clear();
      lastExpiryRefresh.current = null;
    } else {
      setRefreshing(true);
    }
    if (manualRetry) failedUrls.current.clear();
    setError(null);
    setNotice(null);
    try {
      if (!id) throw new Error('검사 ID가 전달되지 않았습니다.');
      const result = (await reader.detail(id)).value;
      if (serial !== requestSerial.current) return;
      setDetail(result);
      const updatedUrl = imageUrl(result, imageKindRef.current);
      if (updatedUrl && failedUrls.current.has(updatedUrl)) {
        setNotice('새 주소를 조회했지만 사진을 표시할 수 없습니다. 다시 조회하거나 이전 화면으로 돌아가세요.');
      }
    } catch (cause) {
      if (serial === requestSerial.current) setError(getErrorText(cause));
    } finally {
      if (serial === requestSerial.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [id]);

  useFocusEffect(useCallback(() => {
    setIsFocused(true);
    void load(true);
    return () => { setIsFocused(false); requestSerial.current += 1; };
  }, [load]));

  useEffect(() => {
    const listener = AppState.addEventListener('change', (next) => setIsForeground(next === 'active'));
    return () => listener.remove();
  }, []);

  const current = detail?.inspectionId === id ? detail : null;
  const uri = current ? imageUrl(current, imageKind) : null;
  const isFailed = uri !== null && failedUrls.current.has(uri);
  const isAvailable = uri !== null && !isFailed;

  useEffect(() => {
    setLoadedUrl(null);
    setZoom(1);
  }, [uri, imageKind]);

  // 화면이 활성 상태일 때 만료 30초 전 상세 GET으로 주소 갱신. 동일 만료 시각 재요청 방지.
  useEffect(() => {
    if (!isFocused || !isForeground || loading || refreshing || !current) return;
    const expiry = current.imageUrlExpiresAt;
    if (!expiry || expiry === lastExpiryRefresh.current) return;
    const ms = Date.parse(expiry);
    if (!Number.isFinite(ms)) return;
    const timer = setTimeout(() => {
      lastExpiryRefresh.current = expiry;
      void load(false);
    }, Math.max(0, ms - Date.now() - 30_000));
    return () => clearTimeout(timer);
  }, [isFocused, isForeground, loading, refreshing, current?.imageUrlExpiresAt, load]);

  const onPhotoError = (failedUrl: string) => {
    if (failedUrl !== uri || failedUrls.current.has(failedUrl)) return;
    failedUrls.current.add(failedUrl);
    setLoadedUrl(null);
    setNotice('사진을 불러오지 못해 새 이미지 주소를 확인합니다.');
    if (isFocused && isForeground && !refreshing) void load(false);
  };

  const selectKind = (next: ImageKind) => {
    setImageKind(next);
    setLoadedUrl(null);
    setZoom(1);
    setNotice(null);
  };

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable accessibilityRole="button" onPress={() => router.back()}>
          <Text style={styles.back}>‹ 뒤로</Text>
        </Pressable>
        <Text style={styles.title}>{imageKind === 'original' ? '원본 사진 확대' : 'AI 판단 근거 확대'}</Text>
        <Text style={styles.subtitle}>{current ? current.partCode + ' · ' + current.inspectionNo : '검사 사진 조회'}</Text>
      </View>
      <View style={styles.tabs}>
        {(['original', 'gradcam'] as const).map((value) => (
          <Pressable key={value} accessibilityRole="button"
            accessibilityState={{ selected: imageKind === value }}
            style={[styles.tab, imageKind === value && styles.tabActive]}
            onPress={() => selectKind(value)}>
            <Text style={[styles.tabText, imageKind === value && styles.tabTextActive]}>
              {value === 'original' ? '원본 사진' : 'AI 판단 근거'}
            </Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.viewer}>
        {loading && <View style={styles.empty}>
          <ActivityIndicator color="#93B8FF" />
          <Text style={styles.emptyText}>사진을 불러오는 중입니다.</Text>
        </View>}
        {!loading && error && <View style={styles.empty}>
          <Text style={styles.emptyTitle}>사진을 조회하지 못했습니다</Text>
          <Text style={styles.emptyText}>{error}</Text>
          <Pressable style={styles.retryButton} accessibilityRole="button"
            disabled={refreshing} onPress={() => void load(false, true)}>
            <Text style={styles.retryText}>다시 조회</Text>
          </Pressable>
        </View>}
        {!loading && !error && current && !isAvailable && (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>{isFailed ? '이미지가 계속 제공되지 않습니다' : '표시할 이미지가 없습니다'}</Text>
            <Text style={styles.emptyText}>
              {isFailed ? '새 주소를 조회했지만 이미지를 표시할 수 없습니다.' : missingImageText(current, imageKind)}
            </Text>
            <Pressable style={styles.retryButton} accessibilityRole="button"
              disabled={refreshing} onPress={() => void load(false, true)}>
              <Text style={styles.retryText}>{refreshing ? '조회 중…' : '이미지 다시 조회'}</Text>
            </Pressable>
          </View>
        )}
        {!loading && !error && isAvailable && uri && (
          <ScrollView key={imageKind + ':' + uri} style={styles.zoomScroll}
            contentContainerStyle={styles.zoomContent}
            minimumZoomScale={1} maximumZoomScale={4} zoomScale={zoom} centerContent
            showsVerticalScrollIndicator={false} showsHorizontalScrollIndicator={false}
            scrollEventThrottle={80}
            onScroll={(event) => {
              const value = event.nativeEvent.zoomScale;
              if (typeof value === 'number' && Number.isFinite(value) && Math.abs(value - zoom) > 0.08) {
                setZoom(Math.max(1, Math.min(4, value)));
              }
            }}>
            <View style={{ width: Math.max(240, width - 50), height: 440 }}>
              <Image source={{ uri }}
                style={[styles.photo, loadedUrl !== uri && styles.photoPending]}
                resizeMode="contain"
                onLoad={() => setLoadedUrl(uri)}
                onError={() => onPhotoError(uri)}
              />
              {loadedUrl !== uri && <View pointerEvents="none" style={styles.loadingOverlay}>
                <ActivityIndicator color="#93B8FF" />
                <Text style={styles.emptyText}>사진 불러오는 중…</Text>
              </View>}
            </View>
          </ScrollView>
        )}
      </View>
      {!loading && !error && isAvailable && (
        <View style={styles.controls}>
          <Text style={styles.hint}>두 손가락으로 확대 · 이동</Text>
          <View style={styles.controlRow}>
            <Pressable accessibilityRole="button" style={styles.controlButton}
              onPress={() => setZoom((v) => Math.max(1, v - 0.5))}>
              <Text style={styles.controlText}>− 축소</Text>
            </Pressable>
            <Pressable accessibilityRole="button" style={styles.controlButton} onPress={() => setZoom(1)}>
              <Text style={styles.controlText}>원래 크기</Text>
            </Pressable>
            <Pressable accessibilityRole="button" style={styles.controlButton}
              onPress={() => setZoom((v) => Math.min(4, v + 0.5))}>
              <Text style={styles.controlText}>＋ 확대</Text>
            </Pressable>
          </View>
        </View>
      )}
      {(refreshing || notice) && <Text style={styles.bottomNotice}>
        {refreshing ? '이미지 주소를 다시 확인하는 중입니다.' : notice}
      </Text>}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#111827' },
  header: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 18, gap: 8 },
  back: { color: '#E5E7EB', fontSize: 14 },
  title: { color: '#FFFFFF', fontSize: 22, fontWeight: '700' },
  subtitle: { color: '#A8B4C8', fontSize: 12 },
  tabs: { flexDirection: 'row', gap: 8, marginHorizontal: 20, marginBottom: 12 },
  tab: { flex: 1, paddingVertical: 12, minHeight: 44, backgroundColor: '#243044', borderRadius: 10, alignItems: 'center' },
  tabActive: { backgroundColor: '#2054D8' },
  tabText: { color: '#C5D0E0', fontWeight: '700', fontSize: 13 },
  tabTextActive: { color: '#FFFFFF' },
  viewer: { flex: 1, backgroundColor: '#1F2937', marginHorizontal: 20, borderRadius: 12, overflow: 'hidden' },
  zoomScroll: { flex: 1 },
  zoomContent: { flexGrow: 1, justifyContent: 'center', alignItems: 'center' },
  photo: { width: '100%', height: '100%' },
  photoPending: { opacity: 0 },
  loadingOverlay: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, alignItems: 'center', justifyContent: 'center', gap: 12 },
  empty: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 12, padding: 20 },
  emptyTitle: { color: '#FFFFFF', fontSize: 15, fontWeight: '700', textAlign: 'center' },
  emptyText: { color: '#CBD5E1', fontSize: 12, textAlign: 'center', lineHeight: 19 },
  retryButton: { backgroundColor: '#2054D8', paddingHorizontal: 18, paddingVertical: 12, borderRadius: 9, minHeight: 44, justifyContent: 'center' },
  retryText: { color: '#FFFFFF', fontSize: 13, fontWeight: '700' },
  controls: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12, gap: 12 },
  hint: { color: '#CBD5E1', textAlign: 'center', fontSize: 12 },
  controlRow: { flexDirection: 'row', gap: 8 },
  controlButton: { flex: 1, backgroundColor: '#243044', borderRadius: 9, minHeight: 44, justifyContent: 'center', alignItems: 'center' },
  controlText: { color: '#FFFFFF', fontWeight: '600', fontSize: 12 },
  bottomNotice: { color: '#CBD5E1', fontSize: 11, lineHeight: 17, textAlign: 'center', paddingHorizontal: 20, paddingBottom: 12 },
});
