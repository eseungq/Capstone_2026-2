import { createImageErrorRefreshBudgetV4, imageExpiryRefreshDelayV4 } from '../api/backendV4/imageRefreshBudgetV4';
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
import type { ManualReplyV4, RetryReplyV4 } from '../api/backendV4/inspectionWriteCore';
import { createInspectionReadServiceV4 } from '../api/backendV4/inspectionReadService';
import type { FinalJudgementV4, InspectionViewV4 } from '../api/backendV4/types';
import { ApiV4RequestError } from '../api/backendV4/httpCore';
import { inspectionDwellForSessionV4 } from '../api/backendV4/inspectionDwellV4';
import { createRecheckServiceV4 } from '../api/backendV4/recheckServiceV4';

import { actorLabelV4 } from '../api/backendV4/actorLabelV4';

type DetailVisit = {
  id: string;
  epoch: number;
  loginId: string | null;
  dwell: ReturnType<typeof inspectionDwellForSessionV4> | null;
};

const recheckService = createRecheckServiceV4(authV4);

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
    if (error.httpStatus === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.';
    if (error.httpStatus === 403) return '현재 계정으로 이 검사를 조회할 수 없습니다.';
    if (error.httpStatus === 404) return '검사를 찾을 수 없습니다. 검사 이력을 다시 확인해 주세요.';
    return '검사 정보를 불러오지 못했습니다. 연결 상태를 확인하고 다시 조회해 주세요.';
  }
  return error instanceof Error ? error.message : '알 수 없는 오류가 발생했습니다.';
}

function actionErrorMessage(error: unknown): string {
  if (error instanceof ApiV4RequestError) {
    const guidance = writeErrorLabelV4(error.code);
    return guidance;
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
  title, url, missingText, caption, onLoadError, onOpen, compact = false,
}: {
  title: string; url: string | null; missingText: string; caption?: string;
  onLoadError: (url: string) => void; onOpen: () => void; compact?: boolean;
}) {
  return (
    <View style={[styles.card, compact && styles.imageCard]}>
      <Text style={styles.cardTitle}>{title}</Text>
      {url ? (
        <Pressable accessibilityRole="button" accessibilityLabel={title + ' 크게 보기'}
          onPress={onOpen} style={({ pressed }) => [styles.photoTouch, pressed && styles.photoTouchPressed]}>
          <Image source={{ uri: url }} resizeMode="contain"
            style={[styles.inspectionImage, compact && styles.compactImage]}
            onError={() => onLoadError(url)} />
          <Text style={styles.imageOpenText}>사진을 눌러 확대 ›</Text>
        </Pressable>
      ) : <Text style={styles.muted}>{missingText}</Text>}
      {caption && url && <Text style={styles.muted}>{caption}</Text>}
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
  const imageErrorBudget = useRef(createImageErrorRefreshBudgetV4());
  const lastExpiryAttempt = useRef<number | null>(null);
  const [imageRetryRevision, setImageRetryRevision] = useState(0);
  const lastAutoRefreshedExpiry = useRef<string | null>(null);
  const pendingImageRefreshOnResume = useRef(false);
  const [role, setRole] = useState<BackendRole | null>(null);
  const [roleLoading, setRoleLoading] = useState(true);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState<'confirm' | 'retry' | 'manual' | 'recheck' | 'acknowledge' | null>(null);
  const [recheckComment, setRecheckComment] = useState('');
  const [acknowledgeNote, setAcknowledgeNote] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [retryResult, setRetryResult] = useState<RetryReplyV4 | null>(null);
  const [manualResult, setManualResult] = useState<ManualReplyV4 | null>(null);
  const [modelAvailable, setModelAvailable] = useState<boolean | null>(null);
  const submitLock = useRef(false);
  const visitRef = useRef<DetailVisit | null>(null);
  const previousVisit = useRef<{ id: string; epoch: number } | null>(null);
  const isCurrentVisit = useCallback((visit: DetailVisit | null) =>
    visit !== null && visitRef.current === visit && visit.epoch === authV4.sessionEpoch(), []);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (state) => {
      setIsForeground(state === 'active');
    });
    return () => subscription.remove();
  }, []);

  const load = useCallback(async (initial = false) => {
    const visit = visitRef.current;
    if (!isCurrentVisit(visit)) return;
    const serial = ++requestSerial.current;
    if (initial) {
      setLoading(true);
      setDetail(null);
      failedImageUrls.current.clear();
      imageErrorBudget.current.reset();
      lastExpiryAttempt.current = null;
      lastAutoRefreshedExpiry.current = null;
      pendingImageRefreshOnResume.current = false;
      setImageNotice(null);
    } else {
      setRefreshing(true);
    }
    setError(null);
    try {
      if (!id) throw new Error('조회할 검사를 다시 선택해 주세요.');
      const response = await inspectionReader.detail(id);
      if (serial !== requestSerial.current || !isCurrentVisit(visit)) return;
      const next = response.value;
      if (next.inspectionId !== id) throw new Error('선택한 검사 정보를 확인할 수 없습니다. 다시 조회해 주세요.');
      setDetail(next);
      // 서버가 실패했던 이미지 URL을 그대로 재발급해도 성공으로 표시하지 않습니다.
      const urls = [next.originalImageUrl, next.gradcamImageUrl].filter(
        (url): url is string => typeof url === 'string',
      );
      const stillBroken = urls.some((url) => failedImageUrls.current.has(url));
      setImageNotice(stillBroken
        ? '사진을 다시 불러왔지만 표시할 수 없습니다. 잠시 후 다시 조회해 주세요.'
        : null);
    } catch (cause) {
      if (serial !== requestSerial.current || !isCurrentVisit(visit)) return;
      setError(errorMessage(cause));
    } finally {
      if (serial === requestSerial.current && isCurrentVisit(visit)) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [id, isCurrentVisit]);

  // 상세로 돌아올 때마다 요청·정정 이력을 갱신하고 이전 방문의 읽기와 제출 콜백을 무효화합니다.
  useFocusEffect(useCallback(() => {
    const visit: DetailVisit = { id, epoch: authV4.sessionEpoch(), loginId: null, dwell: null };
    if (previousVisit.current?.id !== id || previousVisit.current.epoch !== visit.epoch) {
      setComment('');
      setRecheckComment('');
      setAcknowledgeNote('');
      setActionError(null);
      setActionMessage(null);
      setRetryResult(null);
      setManualResult(null);
      setModelAvailable(null);
    }
    previousVisit.current = { id, epoch: visit.epoch };
    visitRef.current = visit;
    setIsFocused(true);
    setRole(null);
    setRoleLoading(true);
    setDetail(null);
    setError(null);
    setLoading(true);
    setSubmitting(null);
    void authV4.restore().then(session => {
      if (!isCurrentVisit(visit)) return;
      if (!session.signedIn || (session.role !== 'WORKER' && session.role !== 'ADMIN')) {
        throw new Error('검사 상세를 보려면 작업자 또는 관리자 계정으로 로그인해 주세요.');
      }
      visit.loginId = session.loginId;
      setRole(session.role);
      if (session.role === 'WORKER' && session.loginId && id) {
        visit.dwell = inspectionDwellForSessionV4(session.loginId, visit.epoch);
        visit.dwell.focus(id, AppState.currentState === 'active' || AppState.currentState == null);
      }
      void load(true);
    }).catch(cause => {
      if (isCurrentVisit(visit)) {
        setError(errorMessage(cause));
        setLoading(false);
      }
    }).finally(() => {
      if (isCurrentVisit(visit)) setRoleLoading(false);
    });
    const subscription = AppState.addEventListener('change', state => {
      if (isCurrentVisit(visit)) visit.dwell?.setForeground(id, state === 'active');
    });
    return () => {
      subscription.remove();
      visit.dwell?.blur(id);
      visitRef.current = null;
      requestSerial.current += 1;
      setIsFocused(false);
    };
  }, [id, isCurrentVisit, load]));

  // 화면이 활성 상태인 동안에만 만료 30초 전 상세를 다시 조회합니다.
  // 복귀 시 이미 만료됐으면 즉시 조회하되, 같은 만료 시각은 자동 재시도하지 않습니다.
  useEffect(() => {
    if (!isFocused || !isForeground || loading || refreshing) return;
    const expiry = detail?.imageUrlExpiresAt;
    if (!expiry || lastAutoRefreshedExpiry.current === expiry) return;
    if (imageErrorBudget.current.exhausted() &&
        [detail?.originalImageUrl, detail?.gradcamImageUrl].some(url => !!url && failedImageUrls.current.has(url))) return;
    const expiryMs = Date.parse(expiry);
    if (!Number.isFinite(expiryMs)) return;
    const delay = imageExpiryRefreshDelayV4(expiryMs, lastExpiryAttempt.current, Date.now());
    const timer = setTimeout(() => {
      lastAutoRefreshedExpiry.current = expiry;
      lastExpiryAttempt.current = Date.now();
      void load(false);
    }, delay);
    return () => clearTimeout(timer);
  }, [detail?.imageUrlExpiresAt, isFocused, isForeground, loading, refreshing, load]);

  // 비활성 상태에서 발생한 이미지 실패는 복귀 후 재조회합니다.
  useEffect(() => {
    if (!isFocused || !isForeground || loading || refreshing || !pendingImageRefreshOnResume.current) return;
    pendingImageRefreshOnResume.current = false;
    if (imageErrorBudget.current.take()) void load(false);
    else setImageNotice('사진을 표시할 수 없습니다. 검사 상세 다시 조회를 눌러 주세요.');
  }, [isFocused, isForeground, loading, refreshing, load, imageNotice]);

  const handleImageError = (url: string) => {
    // 과거 검사 또는 만료된 이전 이미지의 늦은 콜백은 무시합니다.
    if (url !== detail?.originalImageUrl && url !== detail?.gradcamImageUrl) return;
    if (failedImageUrls.current.has(url)) return;
    failedImageUrls.current.add(url);
    if (imageErrorBudget.current.exhausted()) {
      setImageNotice('사진을 표시할 수 없습니다. 검사 상세 다시 조회를 눌러 주세요.');
      return;
    }
    pendingImageRefreshOnResume.current = true;
    setImageNotice('사진을 표시할 수 없어 다시 불러오는 중입니다.');
  };

  // 새 검사로 이동하는 첫 렌더에서도 이전 검사의 데이터를 숨깁니다.
  const visibleDetail = detail?.inspectionId === id ? detail : null;
  const isManualInspection = visibleDetail?.source === 'MANUAL' ||
    visibleDetail?.reviewReasonCode === 'AI_UNAVAILABLE';

  // /monitoring/parts의 AI 가용성은 버튼 우선순위에만 사용합니다.
  // 조회 실패/AI 중지 상태라도 수동 전환 자체는 허용됩니다.
  useEffect(() => {
    if (!visibleDetail?.canOfferManual) {
      setModelAvailable(null);
      return;
    }
    let active = true;
    setModelAvailable(null);
    void inspectionReader.parts().then((result) => {
      if (active) {
        setModelAvailable(result.value.find((part) => part.partCode === visibleDetail.partCode)?.modelAvailable ?? null);
      }
    }).catch(() => {
      if (active) setModelAvailable(null);
    });
    return () => { active = false; };
  }, [visibleDetail?.inspectionId, visibleDetail?.partCode, visibleDetail?.canOfferManual]);

  // 실제 서버 POST 이전에 GET으로 현재 상태를 확인합니다.
  // 오류나 타임아웃이 발생하면 자동 재전송하지 않습니다.
  const displayedVisit = visitRef.current;
  const submitAction = async (action: 'confirm' | 'retry' | 'manual', judgement?: FinalJudgementV4) => {
    let manualNewInspectionId: string | null = null;
    if (submitLock.current || !visibleDetail || !displayedVisit || displayedVisit.id !== id || !isCurrentVisit(displayedVisit)) return;
    const submittedId = id;
    submitLock.current = true;
    setSubmitting(action);
    setActionError(null);
    setActionMessage(null);
    if (action === 'retry') setRetryResult(null);
    if (action === 'manual') setManualResult(null);
    try {
      const session = await authV4.restore();
      if (!isCurrentVisit(displayedVisit)) return;
      if (!session.signedIn || !session.role || session.loginId !== displayedVisit.loginId) throw new Error('실제 서버 로그인 상태와 역할을 다시 확인해 주세요.');
      if (action === 'confirm' && session.role !== 'WORKER') {
        throw new Error('최종 PASS/FAIL 판정은 작업자 계정에서만 가능합니다.');
      }
      if (action === 'retry' && session.role !== 'WORKER' && session.role !== 'ADMIN') {
        throw new Error('FAILED 재검사는 작업자 또는 관리자만 요청할 수 있습니다.');
      }
      if (action === 'manual' && session.role !== 'WORKER') {
        throw new Error('수동 판정 전환은 작업자 계정에서만 가능합니다.');
      }
      const latest = (await inspectionReader.detail(submittedId)).value;
      if (!isCurrentVisit(displayedVisit)) return;
      if (latest.inspectionId !== submittedId) throw new Error('선택한 검사와 조회 결과가 다릅니다. 다시 조회해 주세요.');
      setDetail(latest);
      const origin = {
        inspectionId: latest.inspectionId,
        displayState: latest.displayState,
        finalJudgement: latest.finalJudgement,
        retriedBy: latest.followUp?.inspectionId ?? null,
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
          ...(displayedVisit.dwell?.snapshot(submittedId) ?? {}),
        });
        displayedVisit.dwell?.clear(submittedId);
        if (!isCurrentVisit(displayedVisit)) return;
        setActionMessage(`${reply.value.inspectionNo}: ${reply.value.finalJudgement} 판정이 서버에 저장됐습니다. (${formatTime(reply.value.confirmedAt)})`);
      } else if (action === 'retry') {
        if (!latest.canOfferRetry) {
          throw new Error('이미 후속 검사가 있거나 재검사할 수 없는 상태입니다. 최신 검사 정보를 확인해 주세요.');
        }
        const reply = await writer.retry(origin);
        if (!isCurrentVisit(displayedVisit)) return;
        setRetryResult(reply.value);
        setActionMessage(`새 검사 ${reply.value.inspectionNo} 접수 완료 (RECEIVED). 원본 FAILED 기록은 유지됩니다.`);
      } else {
        if (!latest.canOfferManual) {
          throw new Error('이미 후속 검사가 있거나 수동 판정으로 전환할 수 없는 상태입니다. 최신 검사 정보를 확인해 주세요.');
        }
        const reply = await writer.manual(origin);
        if (!isCurrentVisit(displayedVisit)) return;
        setManualResult(reply.value);
        manualNewInspectionId = reply.value.inspectionId;
        setActionMessage(`수동 판정 검사 ${reply.value.inspectionNo} 생성 완료. 원본 FAILED 기록은 유지됩니다.`);
      }
      // 성공 후 화면의 상태/URL을 서버에서 다시 조회합니다.
      await load(false);
      if (manualNewInspectionId && isCurrentVisit(displayedVisit)) {
        router.push({ pathname: '/inspection-live', params: { inspectionId: manualNewInspectionId } });
      }
    } catch (cause) {
      if (isCurrentVisit(displayedVisit)) {
        // 다른 기기/작업자가 먼저 원본 FAILED를 전환했다면 최신 followUp을 가져와
        // 원본 상세의 '후속 검사 상세 보기' 카드가 즉시 나타나게 합니다.
        // POST를 재전송하지 않으며, 최초 409 오류 메시지는 유지합니다.
        setActionError(actionErrorMessage(cause));
        if (
          cause instanceof ApiV4RequestError &&
          cause.httpStatus === 409 &&
          (cause.code === 'ALREADY_RETRIED' || cause.code === 'NOT_MANUAL_CONVERTIBLE')
        ) {
          await load(false);
        }
      }
    } finally {
      submitLock.current = false;
      if (isCurrentVisit(displayedVisit)) setSubmitting(null);
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

  const requestManual = () => {
    if (!visibleDetail || submitting || !visibleDetail.canOfferManual || role !== 'WORKER') return;
    Alert.alert(
      '실제 서버 수동 판정 전환',
      `${visibleDetail.inspectionNo}의 FAILED 기록은 유지하고, AI 분석 없이 작업자 판정용 새 검사를 만들까요? 재검사와 수동 전환은 원본당 한 번만 가능합니다.`,
      [
        { text: '취소', style: 'cancel' },
        { text: '수동 판정으로 전환', onPress: () => { void submitAction('manual'); } },
      ],
    );
  };

  const submitRecheckAction = async (action: 'recheck' | 'acknowledge', result?: FinalJudgementV4) => {
    if (submitLock.current || !visibleDetail || !displayedVisit || displayedVisit.id !== id || !isCurrentVisit(displayedVisit) || submitting) return;
    const submittedId = id;
    submitLock.current = true;
    setSubmitting(action);
    setActionError(null);
    setActionMessage(null);
    try {
      const session = await authV4.restore();
      if (!isCurrentVisit(displayedVisit)) return;
      if (!session.signedIn || !session.role || session.loginId !== displayedVisit.loginId) throw new Error('실제 서버 계정으로 다시 로그인해 주세요.');
      if (action === 'recheck' && session.role !== 'WORKER') {
        throw new Error('표본 재확인 제출은 작업자만 가능합니다.');
      }
      if (action === 'acknowledge' && session.role !== 'ADMIN') {
        throw new Error('재확인 FAIL 확인함 처리는 관리자만 가능합니다.');
      }
      const latest = (await inspectionReader.detail(submittedId)).value;
      if (!isCurrentVisit(displayedVisit)) return;
      if (latest.inspectionId !== submittedId) throw new Error('선택한 검사와 조회 결과가 다릅니다. 다시 조회해 주세요.');
      setDetail(latest);
      if (latest.displayState !== 'AUTO_PASS' || latest.finalJudgement !== 'PASS' ||
          latest.judgedBy !== 'SYSTEM' || !latest.recheck) {
        throw new Error('현재 검사는 AUTO_PASS 재확인 표본이 아닙니다.');
      }
      if (action === 'recheck') {
        if (latest.recheck.result !== null || !result) {
          throw new Error('이미 재확인했거나 제출할 수 없는 검사입니다.');
        }
        const reply = await recheckService.recheck(submittedId, result,
          recheckComment, displayedVisit.dwell?.snapshot(submittedId) ?? null);
        displayedVisit.dwell?.clear(submittedId);
        if (!isCurrentVisit(displayedVisit)) return;
        setActionMessage(
          reply.inspectionNo + ': 재확인 ' + reply.recheck.result +
          '이 별도로 저장됐습니다. 원래 시스템의 PASS 판정은 유지됩니다.',
        );
      } else {
        if (latest.recheck.result !== 'FAIL' || latest.recheck.acknowledgedAt !== null) {
          throw new Error('관리자 확인함은 아직 확인하지 않은 재확인 FAIL에만 가능합니다.');
        }
        const reply = await recheckService.acknowledge(submittedId, acknowledgeNote);
        if (!isCurrentVisit(displayedVisit)) return;
        setActionMessage(
          reply.inspectionNo + ': 관리자가 확인함으로 기록했습니다. 문제 해결 완료를 뜻하지 않습니다.',
        );
      }
      await load(false);
    } catch (cause) {
      if (isCurrentVisit(displayedVisit)) {
        setActionError(actionErrorMessage(cause));
        // 오류에서는 체류 시간과 메모를 유지하며 POST를 자동 재시도하지 않습니다.
      }
    } finally {
      submitLock.current = false;
      if (isCurrentVisit(displayedVisit)) setSubmitting(null);
    }
  };

  const requestRecheck = (result: FinalJudgementV4) => {
    if (!visibleDetail?.recheck || visibleDetail.recheck.result !== null || submitting) return;
    Alert.alert(
      'AUTO_PASS 표본 재확인 제출',
      visibleDetail.inspectionNo + '의 재확인 결과를 ' + result +
        '로 제출할까요? 원래 PASS · SYSTEM은 바뀌지 않습니다.',
      [
        { text: '취소', style: 'cancel' },
        { text: result + ' 제출', onPress: () => { void submitRecheckAction('recheck', result); } },
      ],
    );
  };

  const requestAcknowledge = () => {
    if (!visibleDetail?.recheck || visibleDetail.recheck.result !== 'FAIL' ||
        visibleDetail.recheck.acknowledgedAt !== null || submitting) return;
    Alert.alert(
      '재확인 FAIL · 관리자 확인함',
      '이 결과를 확인했다는 사실만 기록할까요? 문제 해결 완료나 원래 판정 변경은 아닙니다.',
      [
        { text: '취소', style: 'cancel' },
        { text: '확인함 기록', onPress: () => { void submitRecheckAction('acknowledge'); } },
      ],
    );
  };

  const canShowRetry = !roleLoading && (role === 'WORKER' || role === 'ADMIN') &&
    visibleDetail?.canOfferRetry === true;
  const canShowManual = !roleLoading && role === 'WORKER' &&
    visibleDetail?.canOfferManual === true;
  const followUpSubmitted = submitting !== null || retryResult !== null || manualResult !== null;
  const retryButton = canShowRetry ? (
    <Pressable
      style={({ pressed }) => [styles.button, pressed && styles.buttonPressed, followUpSubmitted && styles.disabledButton]}
      disabled={followUpSubmitted}
      onPress={requestRetry}
      accessibilityRole="button"
    >
      <Text style={styles.buttonText}>{retryResult ? '재검사 접수됨' : 'FAILED 재검사 요청'}</Text>
    </Pressable>
  ) : null;
  const manualButton = canShowManual ? (
    <Pressable
      style={({ pressed }) => [modelAvailable === true ? styles.secondaryButton : styles.button,
        pressed && (modelAvailable === true ? styles.secondaryButtonPressed : styles.buttonPressed),
        followUpSubmitted && styles.disabledButton]}
      disabled={followUpSubmitted}
      onPress={requestManual}
      accessibilityRole="button"
    >
      <Text style={modelAvailable === true ? styles.secondaryButtonText : styles.buttonText}>
        {manualResult ? '수동 검사 생성됨' : '수동 판정으로 전환'}
      </Text>
    </Pressable>
  ) : null;

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
        <Pressable onPress={() => router.back()} accessibilityRole="button"
          style={({ pressed }) => [styles.backTouch, pressed && styles.backTouchPressed]}>
          <Text style={styles.back}>‹ 뒤로</Text>
        </Pressable>
        <Text style={styles.title}>검사 상세{visibleDetail ? ' · ' + visibleDetail.displayStateLabel : ''}</Text>
        <Text style={styles.muted}>{visibleDetail ? visibleDetail.partCode + ' · ' + visibleDetail.inspectionNo : '검사 결과 조회'}</Text>
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
          <Pressable style={({ pressed }) => [styles.button, pressed && styles.buttonPressed]} onPress={() => void load(true)}>
            <Text style={styles.buttonText}>다시 조회</Text>
          </Pressable>
        )}

        {visibleDetail && (
          <>
            <View style={styles.card}>
              <Text style={styles.cardTitle}>검사 상태</Text>
              <Field label="부품 · 검사번호" value={visibleDetail.partCode + ' · ' + visibleDetail.inspectionNo} />
              <Field label="상태" value={visibleDetail.displayStateLabel} />
              <Field label="접수 시각" value={formatTime(visibleDetail.receivedAt)} />
              {visibleDetail.source === 'MANUAL' && <Field label="검사 유형" value="수동 판정" />}
            </View>

            {isManualInspection && (
              <View style={styles.card}>
                <Text style={styles.cardTitle}>AI 분석 없이 작업자 판정</Text>
                <Text style={styles.muted}>
                  AI 결과가 없는 수동 검사입니다. 원본 사진을 확인하고 작업자가 PASS/FAIL을 직접 판정합니다.
                </Text>
                {visibleDetail.manualOf && (
                  <>
                    <Field label="원래 FAILED 검사" value={visibleDetail.manualOf.inspectionNo} />
                    <Field label="원본 AI 오류 코드" value={visibleDetail.manualOf.errorCode} />
                    <Text style={styles.muted}>{visibleDetail.manualOf.errorMessage}</Text>
                    <Pressable
                      style={({ pressed }) => [styles.secondaryButton, pressed && styles.secondaryButtonPressed]}
                      onPress={() => router.push({
                        pathname: '/inspection-live',
                        params: { inspectionId: visibleDetail.manualOf!.inspectionId },
                      })}
                      accessibilityRole="button"
                    >
                      <Text style={styles.secondaryButtonText}>원본 {visibleDetail.manualOf.inspectionNo} 상세 보기 ›</Text>
                    </Pressable>
                  </>
                )}
              </View>
            )}
            {visibleDetail.followUp && (
              <View style={styles.card}>
                <Text style={styles.cardTitle}>이미 생성된 후속 검사</Text>
                <Text style={styles.muted}>
                  원본 FAILED 기록은 유지됩니다. 이미 후속 검사가 있어 재검사·수동 판정 전환을 다시 요청할 수 없습니다.
                </Text>
                <Field label="후속 검사 유형" value={visibleDetail.followUp.source === 'MANUAL' ? '수동 판정' : '재검사'} />
                <Pressable
                  style={({ pressed }) => [styles.secondaryButton, pressed && styles.secondaryButtonPressed]}
                  onPress={() => router.push({
                    pathname: '/inspection-live',
                    params: { inspectionId: visibleDetail.followUp!.inspectionId },
                  })}
                  accessibilityRole="button"
                >
                  <Text style={styles.secondaryButtonText}>후속 검사 {visibleDetail.followUp.inspectionNo} 상세 보기 ›</Text>
                </Pressable>
              </View>
            )}

            {imageNotice && (
              <View style={styles.staleCard}>
                <Text style={styles.staleText}>{imageNotice}</Text>
              </View>
            )}

            {(isManualInspection || visibleDetail.displayState === 'FAILED') ? (
              <ImagePanel key={`original-${imageRetryRevision}`} title="원본 사진" url={visibleDetail.originalImageUrl}
                missingText="원본 이미지가 제공되지 않았습니다."
                onLoadError={handleImageError}
                onOpen={() => router.push({
                  pathname: '/inspection-image-live',
                  params: { inspectionId: id, kind: 'original' },
                })}
              />
            ) : (
              <View style={styles.imageRow}>
                <ImagePanel key={`original-${imageRetryRevision}`} title="원본 사진" url={visibleDetail.originalImageUrl}
                  missingText="원본 이미지가 제공되지 않았습니다." compact
                  onLoadError={handleImageError}
                  onOpen={() => router.push({
                    pathname: '/inspection-image-live',
                    params: { inspectionId: id, kind: 'original' },
                  })}
                />
                <ImagePanel key={`gradcam-${imageRetryRevision}`} title="AI 판단 근거" url={visibleDetail.gradcamImageUrl}
                  missingText={gradcamMissing} compact
                  onLoadError={handleImageError}
                  onOpen={() => router.push({
                    pathname: '/inspection-image-live',
                    params: { inspectionId: id, kind: 'gradcam' },
                  })}
                />
              </View>
            )}

            <View style={styles.card}>
              <Text style={styles.cardTitle}>{isManualInspection ? '수동 판정 · 최종 판정' : 'AI 분석 · 정책 · 최종 판정'}</Text>
              {isManualInspection ? (
                <Field label="판정 방식" value="AI 분석 없이 작업자 판정" />
              ) : (
                <>
                  <Field label="AI 예측" value={visibleDetail.prediction ?? '미제공'} />
                  <Field
                    label="보정 불량 확률"
                    value={visibleDetail.calibratedDefectProbability === null
                      ? '미준비 / 미제공'
                      : `${(visibleDetail.calibratedDefectProbability * 100).toFixed(2)}%`}
                  />
                  <Field label="REVIEW 사유" value={visibleDetail.reviewReasonText ?? '해당 없음'} />
                </>
              )}
              <Field label={visibleDetail.judgedBy === 'SYSTEM' ? '최초 시스템 판정' : '최종 작업자 판정'}
                value={visibleDetail.finalJudgement ?? '미확정'} />
              {visibleDetail.correction && (
                <>
                  <Field label="최종 정정 판정" value={visibleDetail.correction.correctedJudgement} />
                  <Field label="관리자 정정자" value={visibleDetail.correction.correctedBy} />
                  <Field label="정정 시각" value={formatTime(visibleDetail.correction.correctedAt)} />
                  <Text style={styles.muted}>정정 근거: {visibleDetail.correction.note}</Text>
                </>
              )}
              <Field label="최초 판정 주체" value={actorLabelV4(visibleDetail.judgedBy)} />
              <Field label="최초 판정 시각" value={formatTime(visibleDetail.confirmedAt)} />
              {visibleDetail.errorCode && <Field label="오류 코드" value={visibleDetail.errorCode} />}
              {visibleDetail.errorMessage && <Text style={styles.errorText}>{visibleDetail.errorMessage}</Text>}
            </View>


            {visibleDetail.recheck && (
              <View style={styles.card}>
                <Text style={styles.cardTitle}>AUTO_PASS 표본 재확인</Text>
                <Text style={styles.muted}>
                  원래 검사 판정: 시스템 판정 PASS. 재확인 결과는 별도 기록입니다.
                </Text>
                <Field label="표본 구간" value={visibleDetail.recheck.stratum} />
                <Field label="표본 추출 비율" value={(visibleDetail.recheck.samplingRate * 100).toFixed(0) + '%'} />
                <Field label="규칙 버전" value={visibleDetail.recheck.ruleVersion ?? '구버전 기록 / 미제공'} />
                <Field label="시험 이름" value={visibleDetail.recheck.trialName ?? '미지정'} />
                <Field label="선정 시각" value={formatTime(visibleDetail.recheck.sampledAt)} />
                <Field label="재확인 결과" value={visibleDetail.recheck.result ?? '작업자 재확인 대기'} />
                <Field label="재확인자" value={visibleDetail.recheck.recheckedBy ?? '미완료'} />
                <Field label="재확인 시각" value={formatTime(visibleDetail.recheck.recheckedAt)} />
                {visibleDetail.recheck.comment && <Field label="재확인 메모" value={visibleDetail.recheck.comment} />}
                {visibleDetail.recheck.result === 'FAIL' && (
                  <View style={styles.staleCard}>
                    <Text style={styles.errorText}>{visibleDetail.recheck.acknowledgedAt
                      ? '재확인 불량 · 관리자 확인함 (해결 완료 아님)'
                      : '재확인 불량 · 관리자의 추가 확인이 필요합니다.'}</Text>
                    <Text style={styles.muted}>원래 AUTO_PASS 상태와 시스템의 PASS 판정은 유지됩니다.</Text>
                  </View>
                )}
                {visibleDetail.recheck.result === 'FAIL' && (
                  <Field label="관리자 확인" value={
                    visibleDetail.recheck.acknowledgedAt ? '확인함 (해결 완료 아님)' : '미확인'
                  } />
                )}
                {visibleDetail.recheck.acknowledgedAt && (
                  <>
                    <Field label="확인한 관리자" value={visibleDetail.recheck.acknowledgedBy ?? '미제공'} />
                    <Field label="확인 시각" value={formatTime(visibleDetail.recheck.acknowledgedAt)} />
                    {visibleDetail.recheck.acknowledgeNote && (
                      <Field label="확인 메모" value={visibleDetail.recheck.acknowledgeNote} />
                    )}
                  </>
                )}
                {!roleLoading && role === 'WORKER' && visibleDetail.recheck.result === null && (
                  <>
                    <Text style={styles.label}>재확인 메모 (선택, 200자 이내)</Text>
                    <TextInput style={styles.commentInput} maxLength={200} multiline
                      placeholder="재확인 결과에 대한 설명을 남겨주세요."
                      placeholderTextColor="#64748B"
                      value={recheckComment} onChangeText={setRecheckComment} editable={!submitting} />
                    <View style={styles.buttonRow}>
                      <Pressable accessibilityRole="button"
                        disabled={submitting !== null}
                        style={({ pressed }) => [styles.button, styles.buttonFlex,
                          pressed && styles.buttonPressed, submitting && styles.disabledButton]}
                        onPress={() => requestRecheck('PASS')}>
                        <Text style={styles.buttonText}>재확인 PASS</Text>
                      </Pressable>
                      <Pressable accessibilityRole="button"
                        disabled={submitting !== null}
                        style={({ pressed }) => [styles.button, styles.buttonFlex, styles.failButton,
                          pressed && styles.failButtonPressed, submitting && styles.disabledButton]}
                        onPress={() => requestRecheck('FAIL')}>
                        <Text style={styles.buttonText}>재확인 FAIL</Text>
                      </Pressable>
                    </View>
                  </>
                )}
                {!roleLoading && role === 'ADMIN' && visibleDetail.recheck.result === null && (
                  <Text style={styles.muted}>재확인 PASS/FAIL 제출은 작업자 전용입니다.</Text>
                )}
                {!roleLoading && role === 'ADMIN' && visibleDetail.recheck.result === 'FAIL' &&
                  visibleDetail.recheck.acknowledgedAt === null && (
                  <>
                    <Text style={styles.label}>관리자 확인 메모 (선택, 200자 이내)</Text>
                    <TextInput style={styles.commentInput} maxLength={200} multiline
                      placeholder="예: 라인 담당자에게 전달"
                      placeholderTextColor="#64748B"
                      value={acknowledgeNote} onChangeText={setAcknowledgeNote} editable={!submitting} />
                    <Pressable accessibilityRole="button" disabled={submitting !== null}
                      style={({ pressed }) => [styles.button, pressed && styles.buttonPressed,
                        submitting && styles.disabledButton]}
                      onPress={requestAcknowledge}>
                      <Text style={styles.buttonText}>확인함 기록 (해결 완료 아님)</Text>
                    </Pressable>
                  </>
                )}
                {submitting === 'recheck' || submitting === 'acknowledge' ? (
                  <Text style={styles.muted}>서버 기록 처리 중… 중복 제출하지 마세요.</Text>
                ) : null}
              </View>
            )}

            {visibleDetail.judgedBy === 'SYSTEM' && (
              <View style={styles.card}>
                <Text style={styles.cardTitle}>시스템 판정 확인 요청 · 정정 이력</Text>
                <Text style={styles.muted}>
                  최초 시스템 판정은 변경하지 않고, 확인 요청과 관리자 정정을 별도로 기록합니다.
                </Text>
                <Field label="현재 판정" value={visibleDetail.correctedJudgement ?? visibleDetail.finalJudgement ?? '미제공'} />
                {visibleDetail.judgementRequests.length === 0 ? (
                  <Text style={styles.muted}>판정 확인 요청 기록이 없습니다.</Text>
                ) : visibleDetail.judgementRequests.map(request => (
                  <View key={request.requestId} style={styles.field}>
                    <Text style={styles.muted}>
                      {request.status === 'OPEN' ? '검토 대기' : request.status === 'KEPT' ? '유지 처리' : '정정 완료'}
                      {' · '}작업자 주장 {request.claimedJudgement}
                    </Text>
                    <Text style={styles.muted}>근거: {request.reason}</Text>
                    {request.resolveNote && <Text style={styles.muted}>관리자 판단: {request.resolveNote}</Text>}
                  </View>
                ))}
                {!roleLoading && role === 'WORKER' && !visibleDetail.judgementRequests.some(r => r.status === 'OPEN') && (
                  <Pressable style={({pressed}) => [styles.secondaryButton, pressed && styles.secondaryButtonPressed]}
                    accessibilityRole="button"
                    onPress={() => router.push({
                      pathname: '/judgement-request-live',
                      params: { inspectionId: visibleDetail.inspectionId },
                    })}>
                    <Text style={styles.secondaryButtonText}>시스템 판정 확인 요청 ›</Text>
                  </Pressable>
                )}
              </View>
            )}
            <View style={styles.card}>
              <Text style={styles.cardTitle}>작업자 판정 · 후속 처리</Text>
              <Text style={styles.muted}>요청 전 내용을 확인해 주세요. 중복 제출은 하지 않습니다.</Text>
              {roleLoading && <Text style={styles.muted}>로그인 역할 확인 중…</Text>}
              {!roleLoading && role !== 'WORKER' && role !== 'ADMIN' && (
                <Text style={styles.errorText}>작업자 또는 관리자 계정으로 로그인해 주세요.</Text>
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
                      style={({ pressed }) => [styles.button, styles.buttonFlex, pressed && styles.buttonPressed, submitting && styles.disabledButton]}
                      disabled={submitting !== null}
                      onPress={() => requestConfirm('PASS')}
                      accessibilityRole="button"
                    >
                      <Text style={styles.buttonText}>PASS 확정</Text>
                    </Pressable>
                    <Pressable
                      style={({ pressed }) => [styles.button, styles.buttonFlex, styles.failButton, pressed && styles.failButtonPressed, submitting && styles.disabledButton]}
                      disabled={submitting !== null}
                      onPress={() => requestConfirm('FAIL')}
                      accessibilityRole="button"
                    >
                      <Text style={styles.buttonText}>FAIL 확정</Text>
                    </Pressable>
                  </View>
                </>
              )}
              {visibleDetail.canOfferManual && (
                <Text style={styles.muted}>
                  AI 모델 사용 가능: {modelAvailable === true ? '예 · 재검사 우선' :
                    modelAvailable === false ? '아니요 · 수동 판정 우선' : '확인 중/미확인 · 수동 전환 가능'}
                  {'\n'}재검사와 수동 판정 전환은 둘 중 하나만 가능합니다.
                </Text>
              )}
              {modelAvailable === true ? (
                <>{retryButton}{manualButton}</>
              ) : (
                <>{manualButton}{retryButton}</>
              )}
              {!visibleDetail.canOfferConfirm && !visibleDetail.canOfferRetry && !visibleDetail.canOfferManual && !visibleDetail.followUp && (
                <Text style={styles.muted}>{visibleDetail.recheck?.result === null
                    ? (role === 'ADMIN'
                      ? '관리자 계정은 표본 재확인 상태를 조회만 할 수 있습니다. 재확인 PASS/FAIL은 작업자 전용입니다.'
                      : role === 'WORKER'
                        ? '일반 REVIEW 판정이나 FAILED 후속 요청은 없습니다. 표본 재확인은 위 카드에서 제출해 주세요.'
                        : '재확인 PASS/FAIL 제출은 작업자 계정에서만 가능합니다.')
                    : '현재 서버 상태에서는 제출 가능한 일반 판정 또는 후속 검사 요청이 없습니다.'}</Text>
              )}
              {!roleLoading && role === 'ADMIN' && visibleDetail.canOfferManual && (
                <Text style={styles.muted}>수동 판정으로 전환하려면 작업자 계정으로 로그인해 주세요.</Text>
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
              {manualResult && (
                <Pressable
                  style={({ pressed }) => [styles.secondaryButton, pressed && styles.secondaryButtonPressed]}
                  onPress={() => router.push({
                    pathname: '/inspection-live',
                    params: { inspectionId: manualResult.inspectionId },
                  })}
                  accessibilityRole="button"
                >
                  <Text style={styles.secondaryButtonText}>수동 검사 {manualResult.inspectionNo} 상세 보기 ›</Text>
                </Pressable>
              )}
              {retryResult && (
                <Pressable
                  style={({ pressed }) => [styles.secondaryButton, pressed && styles.secondaryButtonPressed]}
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
              <Text style={styles.cardTitle}>검사 상세 새로고침</Text>
              <Text style={styles.muted}>현재 판정과 사진을 다시 불러옵니다.</Text>
              <Pressable accessibilityRole="button"
                style={({ pressed }) => [styles.secondaryButton, pressed && styles.secondaryButtonPressed, refreshing && styles.disabledButton]}
                disabled={refreshing}
                onPress={() => {
                  lastAutoRefreshedExpiry.current = visibleDetail.imageUrlExpiresAt;
                  lastExpiryAttempt.current = null;
                  imageErrorBudget.current.reset();
                  pendingImageRefreshOnResume.current = false;
                  failedImageUrls.current.clear();
                  setImageRetryRevision(value => value + 1);
                  void load(false);
                }}>
                <Text style={styles.secondaryButtonText}>{refreshing ? '조회 중…' : '검사 상세 다시 조회'}</Text>
              </Pressable>
            </View>
            <Text style={styles.muted}>
              이 화면은 실제 서버 데이터만 사용합니다. 판정·재검사·수동 전환은 서버가 최종 검증합니다.
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
  backTouch: { alignSelf: 'flex-start', borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, marginLeft: -8 },
  backTouchPressed: { backgroundColor: '#E9EFFC' },
  title: { color: '#111827', fontSize: 23, fontWeight: '700' },
  body: { paddingHorizontal: 20, paddingBottom: 35, gap: 12 },
  card: { backgroundColor: '#FFF', borderRadius: 14, borderWidth: 1, borderColor: '#E4E7EC', padding: 16, gap: 10 },
  cardTitle: { color: '#111827', fontSize: 17, fontWeight: '700' },
  field: { gap: 3 },
  label: { color: '#64748B', fontSize: 12 },
  value: { color: '#111827', fontSize: 14, fontWeight: '500' },
  muted: { color: '#64748B', fontSize: 12, lineHeight: 18 },
  inspectionImage: { height: 265, width: '100%', backgroundColor: '#EEF2F8', borderRadius: 10 },
  imageRow: { flexDirection: 'row', gap: 8, alignItems: 'stretch' },
  imageCard: { flex: 1, minWidth: 0, padding: 10 },
  compactImage: { height: 137 },
  imageOpenText: { color: '#2054D8', fontSize: 11, marginTop: 7, fontWeight: '600' },
  photoTouch: { borderRadius: 10, overflow: 'hidden' },
  photoTouchPressed: { opacity: 0.84, backgroundColor: '#EDF2FF' },
  button: { backgroundColor: '#2054D8', padding: 13, borderRadius: 10, alignItems: 'center' },
  buttonPressed: { backgroundColor: '#193EAA' },
  buttonText: { color: '#FFF', fontSize: 13, fontWeight: '700' },
  disabledButton: { opacity: 0.5 },
  buttonRow: { flexDirection: 'row', gap: 8 },
  buttonFlex: { flex: 1 },
  failButton: { backgroundColor: '#B42318' },
  failButtonPressed: { backgroundColor: '#8E1D16' },
  commentInput: { minHeight: 70, backgroundColor: '#F5F7FB', borderWidth: 1, borderColor: '#E4E7EC', borderRadius: 10, padding: 12, color: '#111827', textAlignVertical: 'top' },
  submitStatus: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  successText: { color: '#067647', fontSize: 13, lineHeight: 20 },
  secondaryButton: { borderWidth: 1, borderColor: '#2054D8', borderRadius: 10, padding: 12 },
  secondaryButtonPressed: { backgroundColor: '#E9EFFC' },
  secondaryButtonText: { color: '#2054D8', fontSize: 13, fontWeight: '700' },
  errorCard: { backgroundColor: '#FFF0ED' },
  staleCard: { backgroundColor: '#FFF3E5', borderRadius: 12, padding: 12 },
  staleText: { color: '#92400E', fontSize: 12, lineHeight: 18 },
  errorText: { color: '#B42318', fontSize: 13 },
});
