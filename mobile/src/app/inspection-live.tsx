import React, { useCallback, useEffect, useRef, useState } from 'react';
import { router, Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import {
  ActivityIndicator,
  Alert,
  AppState,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { authV4 } from '../api/backendV4/authRuntime';
import type { BackendRole } from '../api/backendV4/authCore';
import { createInspectionWriteServiceV4 } from '../api/backendV4/inspectionWriteService';
import { WriteV4ValidationError, writeErrorLabelV4 } from '../api/backendV4/inspectionWriteCore';
import type { RetryReplyV4 } from '../api/backendV4/inspectionWriteCore';
import { createInspectionReadServiceV4 } from '../api/backendV4/inspectionReadService';
import type { FinalJudgementV4, InspectionViewV4 } from '../api/backendV4/types';
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

function actionErrorMessage(error: unknown): string {
  if (error instanceof ApiV4RequestError) {
    const guidance = writeErrorLabelV4(error.code);
    return `${guidance}\n${error.message} (HTTP ${error.httpStatus}, ${error.code})${error.traceId ? `\ntraceId: ${error.traceId}` : ''}`;
  }
  if (error instanceof WriteV4ValidationError) {
    return `${writeErrorLabelV4(error.code)}\n${error.message} (${error.code})`;
  }
  return error instanceof Error ? error.message : '검사 처리에 실패했습니다.';
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
  caption,
  onLoadError,
}: {
  title: string;
  url: string | null;
  missingText: string;
  caption?: string;
  onLoadError: (url: string) => void;
}) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>{title}</Text>
      {url ? (
        <>
          <Image
            source={{ uri: url }}
            style={styles.inspectionImage}
            resizeMode="contain"
            onError={() => onLoadError(url)}
          />
          {caption && <Text style={styles.muted}>{caption}</Text>}
        </>
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
  const [role, setRole] = useState<BackendRole | null>(null);
  const [roleLoading, setRoleLoading] = useState(true);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState<'confirm' | 'retry' | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [retryResult, setRetryResult] = useState<RetryReplyV4 | null>(null);
  const submitLock = useRef(false);
  const currentIdRef = useRef(id);
  currentIdRef.current = id;

  // URL/파라미터의 role 값이 아닌 보안 저장소의 로그인 역할만 사용합니다.
  useFocusEffect(useCallback(() => {
    let cancelled = false;
    setRoleLoading(true);
    void authV4.restore().then((session) => {
      if (!cancelled) setRole(session.role);
    }).catch(() => {
      if (!cancelled) setRole(null);
    }).finally(() => {
      if (!cancelled) setRoleLoading(false);
    });
    return () => { cancelled = true; };
  }, []));

  useEffect(() => {
    setActionError(null);
    setActionMessage(null);
    setRetryResult(null);
    setComment('');
  }, [id]);

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

  // 실제 서버 POST 이전에 GET으로 현재 상태를 확인합니다.
  // 오류나 타임아웃이 발생하면 자동 재전송하지 않습니다.
  const submitAction = async (action: 'confirm' | 'retry', judgement?: FinalJudgementV4) => {
    if (submitLock.current || !visibleDetail || !id) return;
    const submittedId = id;
    submitLock.current = true;
    setSubmitting(action);
    setActionError(null);
    setActionMessage(null);
    if (action === 'retry') setRetryResult(null);
    try {
      const session = await authV4.restore();
      if (!session.signedIn || !session.role) throw new Error('실제 서버 로그인 상태와 역할을 다시 확인해 주세요.');
      if (action === 'confirm' && session.role !== 'WORKER') {
        throw new Error('최종 PASS/FAIL 판정은 WORKER 계정에서만 가능합니다.');
      }
      if (action === 'retry' && session.role !== 'WORKER' && session.role !== 'ADMIN') {
        throw new Error('FAILED 재검사는 WORKER 또는 ADMIN만 요청할 수 있습니다.');
      }
      const latest = (await inspectionReader.detail(submittedId)).value;
      if (currentIdRef.current !== submittedId) return;
      setDetail(latest);
      const origin = {
        inspectionId: latest.inspectionId,
        displayState: latest.displayState,
        finalJudgement: latest.finalJudgement,
      };
      const writer = createInspectionWriteServiceV4({
        mode: 'api',
        role: session.role,
        transport: authV4,
      });
      if (action === 'confirm') {
        if (!judgement || latest.displayState !== 'REVIEW_PENDING' || latest.finalJudgement !== null) {
          throw new Error('검사 상태가 변경되었습니다. REVIEW_PENDING 검사만 최종 판정할 수 있습니다.');
        }
        const reply = await writer.confirm(origin, {
          finalJudgement: judgement,
          comment,
        });
        if (currentIdRef.current !== submittedId) return;
        setActionMessage(`${reply.value.inspectionNo}: ${reply.value.finalJudgement} 판정이 서버에 저장됐습니다. (${formatTime(reply.value.confirmedAt)})`);
      } else {
        if (latest.displayState !== 'FAILED') {
          throw new Error('검사 상태가 변경되었습니다. FAILED 검사만 재검사할 수 있습니다.');
        }
        const reply = await writer.retry(origin);
        if (currentIdRef.current !== submittedId) return;
        setRetryResult(reply.value);
        setActionMessage(`새 검사 ${reply.value.inspectionNo} 접수 완료 (RECEIVED). 원본 FAILED 기록은 유지됩니다.`);
      }
      // 성공 후 화면의 상태/URL을 서버에서 다시 조회합니다.
      await load(false);
    } catch (cause) {
      if (currentIdRef.current === submittedId) setActionError(actionErrorMessage(cause));
    } finally {
      submitLock.current = false;
      if (currentIdRef.current === submittedId) setSubmitting(null);
    }
  };

  const requestConfirm = (judgement: FinalJudgementV4) => {
    if (!visibleDetail || submitting) return;
    Alert.alert(
      '실제 서버 최종 판정',
      `${visibleDetail.inspectionNo}을(를) ${judgement}로 확정할까요? 서버에 실제 판정이 저장됩니다.`,
      [
        { text: '취소', style: 'cancel' },
        { text: `${judgement} 제출`, onPress: () => { void submitAction('confirm', judgement); } },
      ],
    );
  };

  const requestRetry = () => {
    if (!visibleDetail || submitting) return;
    Alert.alert(
      '실제 서버 재검사 접수',
      `${visibleDetail.inspectionNo}의 FAILED 상태를 유지하면서 새 검사를 접수할까요?`,
      [
        { text: '취소', style: 'cancel' },
        { text: '재검사 요청', onPress: () => { void submitAction('retry'); } },
      ],
    );
  };

  const gradcamMissing = visibleDetail?.gradcamStatus === 'NO_ACTIVATION'
    ? 'AI 예측은 완료됐지만, 위치별 강조 반응이 없어 판단 근거 이미지를 제공하기 어렵습니다.'
    : visibleDetail?.gradcamStatus === 'NOT_REQUIRED'
      ? 'AI가 GOOD으로 예측하여 판단 근거 이미지를 생성하지 않았습니다.'
      : visibleDetail?.gradcamStatus === 'FAILED'
        ? '판단 근거 이미지 생성에 실패했습니다. 원본 사진과 AI 예측을 참고하세요.'
        : 'AI 판단 근거 이미지가 제공되지 않았습니다.';

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} accessibilityRole="button">
          <Text style={styles.back}>‹ 모니터링으로 돌아가기</Text>
        </Pressable>
        <Text style={styles.title}>실제 서버 검사 상세</Text>
        <Text style={styles.muted}>SERVER · 검사 UUID로 조회 · 권한별 판정/재검사</Text>
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
              title="AI 판단 근거"
              url={visibleDetail.gradcamImageUrl}
              missingText={gradcamMissing}
              caption="AI가 반응한 영역입니다. 원본 사진과 함께 확인해 주세요."
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
              <Text style={styles.cardTitle}>실제 서버 판정 · 재검사</Text>
              <Text style={styles.muted}>
                서버가 최종 권한과 상태를 검증합니다. 제출 후 자동으로 재전송하지 않습니다.
              </Text>
              {roleLoading && <Text style={styles.muted}>로그인 역할 확인 중…</Text>}
              {!roleLoading && role !== 'WORKER' && role !== 'ADMIN' && (
                <Text style={styles.errorText}>WORKER 또는 ADMIN 실제 서버 계정으로 로그인해 주세요.</Text>
              )}
              {!roleLoading && role === 'ADMIN' && visibleDetail.canOfferConfirm && (
                <Text style={styles.muted}>관리자 계정은 REVIEW를 조회할 수 있지만 PASS/FAIL 판정은 제출할 수 없습니다.</Text>
              )}
              {!roleLoading && role === 'WORKER' && visibleDetail.canOfferConfirm && (
                <>
                  <Text style={styles.label}>판정 메모 (선택, 최대 200자)</Text>
                  <TextInput
                    style={styles.commentInput}
                    placeholder="판정 근거를 입력하세요."
                    placeholderTextColor="#64748B"
                    value={comment}
                    onChangeText={setComment}
                    maxLength={200}
                    multiline
                    editable={!submitting}
                  />
                  <View style={styles.buttonRow}>
                    <Pressable
                      style={[styles.button, styles.buttonFlex, submitting && styles.disabledButton]}
                      disabled={submitting !== null}
                      onPress={() => requestConfirm('PASS')}
                      accessibilityRole="button"
                    >
                      <Text style={styles.buttonText}>PASS 확정</Text>
                    </Pressable>
                    <Pressable
                      style={[styles.button, styles.buttonFlex, styles.failButton, submitting && styles.disabledButton]}
                      disabled={submitting !== null}
                      onPress={() => requestConfirm('FAIL')}
                      accessibilityRole="button"
                    >
                      <Text style={styles.buttonText}>FAIL 확정</Text>
                    </Pressable>
                  </View>
                </>
              )}
              {!roleLoading && (role === 'WORKER' || role === 'ADMIN') && visibleDetail.canOfferRetry && (
                <Pressable
                  style={[styles.button, (submitting || retryResult) && styles.disabledButton]}
                  disabled={submitting !== null || retryResult !== null}
                  onPress={requestRetry}
                  accessibilityRole="button"
                >
                  <Text style={styles.buttonText}>
                    {retryResult ? '재검사 접수됨' : 'FAILED 재검사 요청'}
                  </Text>
                </Pressable>
              )}
              {!visibleDetail.canOfferConfirm && !visibleDetail.canOfferRetry && (
                <Text style={styles.muted}>현재 서버 상태에서는 제출 가능한 판정 또는 재검사 요청이 없습니다.</Text>
              )}
              {submitting && (
                <View style={styles.submitStatus}>
                  <ActivityIndicator />
                  <Text style={styles.muted}>실제 서버에 요청하는 중입니다. 중복 제출하지 마세요.</Text>
                </View>
              )}
              {actionMessage && <Text style={styles.successText}>{actionMessage}</Text>}
              {actionError && (
                <Text style={styles.errorText}>
                  {actionError}{'\n'}
                  제출 여부가 불확실하면 새 요청 전에 서버의 최신 검사 상세를 조회해 주세요.
                </Text>
              )}
              {retryResult && (
                <Pressable
                  style={styles.secondaryButton}
                  onPress={() => router.push({
                    pathname: '/inspection-live',
                    params: { inspectionId: retryResult.inspectionId },
                  })}
                  accessibilityRole="button"
                >
                  <Text style={styles.secondaryButtonText}>신규 검사 {retryResult.inspectionNo} 상세 보기 ›</Text>
                </Pressable>
              )}
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
              이 화면은 실제 서버 데이터만 사용합니다. 판정·재검사는 서버가 최종 검증합니다.
              판단 근거 이미지는 결함 위치를 확정하는 좌표나 마스크가 아닙니다.
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
  buttonRow: { flexDirection: 'row', gap: 8 },
  buttonFlex: { flex: 1 },
  failButton: { backgroundColor: '#B42318' },
  commentInput: { minHeight: 70, backgroundColor: '#F5F7FB', borderWidth: 1, borderColor: '#E4E7EC', borderRadius: 10, padding: 12, color: '#111827', textAlignVertical: 'top' },
  submitStatus: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  successText: { color: '#067647', fontSize: 13, lineHeight: 20 },
  secondaryButton: { borderWidth: 1, borderColor: '#2054D8', borderRadius: 10, padding: 12 },
  secondaryButtonText: { color: '#2054D8', fontSize: 13, fontWeight: '700' },
  errorCard: { backgroundColor: '#FFF0ED' },
  staleCard: { backgroundColor: '#FFF3E5', borderRadius: 12, padding: 12 },
  staleText: { color: '#92400E', fontSize: 12, lineHeight: 18 },
  errorText: { color: '#B42318', fontSize: 13 },
});
