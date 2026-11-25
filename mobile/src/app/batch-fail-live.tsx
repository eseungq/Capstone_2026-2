import React, { useCallback, useEffect, useRef, useState } from 'react';
import { router, Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import {
  ActivityIndicator, Alert, Image, Keyboard, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet,
  Text, TextInput, View,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { authV4 } from '../api/backendV4/authRuntime';
import { actorLabelV4 } from '../api/backendV4/actorLabelV4';
import { createReviewQueueBrowserV4, type ReviewQueueFiltersV4 } from '../api/backendV4/reviewQueueBrowseCoreV4';
import type { BackendRole } from '../api/backendV4/authCore';
import { createInspectionReadServiceV4 } from '../api/backendV4/inspectionReadService';
import type { QueueItemV4 } from '../api/backendV4/inspectionReadCore';
import type { InspectionViewV4 } from '../api/backendV4/types';
import {
  batchFailResultLabelV4, batchQueueFiltersFromRouteV4, createBatchConfirmationGuardV4, MAX_BATCH_FAIL_V4,
  selectableReviewForBatchV4, canReviewBatchImagesV4, type BatchReviewImageStateV4,
  type BatchFailReplyV4, type BatchFailSelectionV4,
} from '../api/backendV4/batchFailCoreV4';
import { createBatchFailServiceV4 } from '../api/backendV4/batchFailServiceV4';

const reader = createInspectionReadServiceV4({mode: 'api', transport: authV4});
const writer = createBatchFailServiceV4(authV4);

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : '요청 처리 중 오류가 발생했습니다.';
}
function percent(value: number | null): string {
  return value == null ? '미제공' : `${(value * 100).toFixed(2)}%`;
}

export default function BatchFailLiveScreen() {
  const filters = batchQueueFiltersFromRouteV4(useLocalSearchParams());
  if (!filters) {
    return (
      <SafeAreaView style={s.screen}>
        <Stack.Screen options={{headerShown:false}} />
        <View style={s.heading}>
          <Text style={s.title}>대기열 조회 조건을 확인할 수 없습니다.</Text>
          <Pressable accessibilityRole="button" onPress={()=>router.back()}>
            <Text style={s.back}>‹ 돌아가기</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }
  const routeKey = [filters.partCode, filters.sort, filters.aiDefectOnly].join('|');
  return <BatchFailQueue key={routeKey} initialFilters={filters} />;
}

function BatchFailQueue({initialFilters}: {initialFilters: ReviewQueueFiltersV4}) {
  const [browser] = useState(() => createReviewQueueBrowserV4(reader, {reviewOnly:true}));
  const [entryFilters] = useState(initialFilters);
  const [confirmation] = useState(() => createBatchConfirmationGuardV4(authV4.sessionEpoch));
  useFocusEffect(useCallback(() => () => confirmation.invalidate(), [confirmation]));
  const [browse, setBrowse] = useState(browser.getSnapshot);
  const filters = browse.filters ?? entryFilters;
  const [role, setRole] = useState<BackendRole | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [preview, setPreview] = useState<InspectionViewV4 | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [originalState,setOriginalState] = useState<BatchReviewImageStateV4>('loading');
  const [camState,setCamState] = useState<BatchReviewImageStateV4>('loading');
  const previewItem = useRef<QueueItemV4 | null>(null);
  const [selected, setSelected] = useState<BatchFailSelectionV4[]>([]);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [reply, setReply] = useState<BatchFailReplyV4 | null>(null);
  const detailRequestId = useRef(0);
  const mountedRef = useRef(true);
  const submitLock = useRef(false);
  const scrollRef = useRef<React.ComponentRef<typeof ScrollView>>(null);
  const commentRef = useRef<React.ComponentRef<typeof TextInput>>(null);
  // KeyboardAvoidingView resizes the viewport, but it does not scroll a
  // focused input at the end of a long inspection list into that viewport.
  const revealComment = useCallback(() => {
    const field = commentRef.current;
    const content = scrollRef.current?.getInnerViewRef();
    if (!field?.isFocused() || !content) return;
    field.measureLayout(content, (_x, y) => {
      if (commentRef.current === field && field.isFocused()) {
        scrollRef.current?.scrollTo({ y: Math.max(0, y - 12), animated: false });
      }
    });
  }, []);
  // Re-measure after iOS finishes its keyboard animation as well as on focus
  // and viewport layout; don't alter the selection, comment or confirmation.
  useFocusEffect(useCallback(() => {
    if (Platform.OS !== 'ios') return;
    const subscription = Keyboard.addListener('keyboardDidShow', revealComment);
    return () => subscription.remove();
  }, [revealComment]));

  useEffect(() => {
    mountedRef.current = true;
    let cancelled = false;
    const unsubscribe = browser.subscribe(setBrowse);
    void authV4.restore().then(session => {
      if (cancelled) return;
      setRole(session.signedIn ? session.role : null);
      if (session.signedIn && session.role === 'WORKER') {
        browser.setFilters(entryFilters);
        void browser.refresh();
      }
    }).catch(() => { if (!cancelled) setRole(null); })
      .finally(() => { if (!cancelled) setAuthLoading(false); });
    return () => {
      cancelled = true;
      mountedRef.current = false;
      confirmation.invalidate();
      detailRequestId.current++;
      unsubscribe();
      browser.clear();
    };
  }, [browser, entryFilters, confirmation]);

  // 상세 검토는 별도 모달에 표시해 검사 목록의 현재 스크롤 위치를 보존합니다.
  // 닫은 뒤 늦게 도착한 서버 응답이 모달을 다시 열지 않도록 요청 세대를 무효화합니다.
  const closeDetail = () => {
    detailRequestId.current += 1;
    previewItem.current = null;
    setPreview(null);
    setPreviewError(null);
    setReviewed(false);
    setPreviewLoading(false);
  };

  const changeFilters = (next: ReviewQueueFiltersV4) => {
    if (submitLock.current || (filters.sort === next.sort && filters.aiDefectOnly === next.aiDefectOnly)) return;
    const changesScope = filters.aiDefectOnly !== next.aiDefectOnly;
    const stillCurrent = confirmation.capture();
    const apply = () => {
      if (!mountedRef.current || !stillCurrent() || submitLock.current) return;
      confirmation.invalidate();
      closeDetail();
      if (changesScope) {
        setSelected([]);
        setComment('');
        setSubmitError(null);
      }
      browser.setFilters(next);
      void browser.refresh();
    };
    if (changesScope && (selected.length > 0 || comment.trim())) {
      Alert.alert('조회 조건을 바꿀까요?', '선택한 검사와 작성한 공통 판정 사유가 지워집니다.', [
        {text:'취소',style:'cancel'}, {text:'조건 변경',onPress:apply},
      ]);
    } else {
      apply();
    }
  };

  const openDetail = async (item: QueueItemV4) => {
    if (previewLoading || submitting) return;
    const serial = ++detailRequestId.current;
    previewItem.current = item;
    setOriginalState('loading');
    setCamState('loading');
    setPreview(null);
    setPreviewError(null);
    setReviewed(false);
    setPreviewLoading(true);
    try {
      const result = await reader.detail(item.inspectionId);
      if (!mountedRef.current || serial !== detailRequestId.current) return;
      if (result.source !== 'SERVER') throw new Error('실제 서버 검사 상세가 아닙니다.');
      const detail = result.value;
      if (detail.inspectionId !== item.inspectionId || detail.partCode !== item.partCode ||
          (filters.aiDefectOnly && detail.prediction !== 'DEFECT')) {
        throw new Error('검사 정보가 목록과 달라졌습니다. 대기열을 새로고침해 주세요.');
      }
      setPreview(detail);
    } catch(cause) {
      if (mountedRef.current && serial === detailRequestId.current) setPreviewError(errorText(cause));
    } finally {
      if (mountedRef.current && serial === detailRequestId.current) setPreviewLoading(false);
    }
  };

  const imageSerial=detailRequestId.current;
  const imagesReady=!!preview&&canReviewBatchImagesV4(preview.originalImageUrl??null,originalState,preview.gradcamImageUrl??null,camState);
  const imageResult=(kind:'original'|'cam',state:BatchReviewImageStateV4)=>{
    if(!mountedRef.current || imageSerial!==detailRequestId.current) return;
    if(kind==='original')setOriginalState(state);else setCamState(state);
    if(state!=='loaded')setReviewed(false);
  };
  const retryDetail=()=>{
    if(previewItem.current&&!previewLoading)void openDetail(previewItem.current);
  };

  const addSelection = () => {
    if (!preview || !reviewed || role !== 'WORKER' || !imagesReady) return;
    try {
      const item = selectableReviewForBatchV4(preview);
      confirmation.invalidate();
      setSelected(old => {
        if (old.some(x => x.inspectionId === item.inspectionId)) return old;
        if (old.length >= MAX_BATCH_FAIL_V4) return old;
        return [...old, item];
      });
      closeDetail();
    } catch(cause) { Alert.alert('선택 불가', errorText(cause)); }
  };

  const submit = async (stillCurrent: () => boolean) => {
    if (!mountedRef.current || !stillCurrent() || submitLock.current || submitting || role !== 'WORKER') return;
    submitLock.current = true;
    setSubmitting(true);
    setSubmitError(null);
    try {
      // 서버가 최종 권위: 경쟁 제출·상태 변경은 건별 CONFLICT/NOT_REVIEWABLE로 응답.
      const session = await authV4.restore();
      if (!mountedRef.current || !stillCurrent()) return;
      if (!session.signedIn || session.role !== 'WORKER') throw new Error('작업자 계정으로 다시 로그인해 주세요.');
      const response = await writer.submit(session.role, selected, comment);
      if (!mountedRef.current || !stillCurrent()) return;
      setReply(response.value);
      setSelected([]);
      setComment('');
      // Refresh reports read failures through browse.error; the submitted result remains available.
      await browser.refresh();
    } catch(cause) {
      if (mountedRef.current && stillCurrent()) setSubmitError(errorText(cause));
    } finally {
      confirmation.invalidate();
      submitLock.current = false;
      if (mountedRef.current) setSubmitting(false);
    }
  };

  const confirmSubmit = () => {
    if (role !== 'WORKER' || selected.length === 0 || submitting) return;
    const stillCurrent = confirmation.capture();
    Alert.alert(
      `선택한 ${selected.length}건을 FAIL로 확정할까요?`,
      '아래 화면에 표시된 검사번호와 원본 사진을 다시 확인해 주세요.\n' +
        selected.slice(0, 7).map(x => x.inspectionNo).join(', ') +
        (selected.length > 7 ? ` 외 ${selected.length - 7}건` : '') +
        '\n이 작업은 실제 서버 판정 기록을 변경합니다. 개별 실패 건은 따로 표시됩니다.',
      [
        {text:'취소',style:'cancel'},
        {text:'선택 검사 FAIL 제출',style:'destructive',onPress:()=>{void submit(stillCurrent);}},
      ],
    );
  };

  return (
    <SafeAreaView style={s.screen}>
      <Stack.Screen options={{headerShown:false}} />
      <View style={s.heading}>
        <Pressable accessibilityRole="button" onPress={()=>router.back()}>
          <Text style={s.back}>‹ 모니터링으로 돌아가기</Text>
        </Pressable>
        <Text style={s.title}>REVIEW 일괄 FAIL 판정</Text>
        <Text style={s.muted}>
          검사를 하나씩 상세 검토한 뒤 직접 선택합니다. 서버에 제출하면 건별로 FAIL 판정이 기록됩니다.
        </Text>
      </View>
      <KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView ref={scrollRef} style={{flex:1}} contentContainerStyle={s.body}
        onLayout={revealComment} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
        {authLoading ? <ActivityIndicator /> : role !== 'WORKER' ? (
          <View style={s.card}><Text style={s.error}>작업자 계정으로 로그인하면 일괄 판정을 사용할 수 있습니다.</Text></View>
        ) : (
          <>
            <View style={s.card}>
              <Text style={s.cardTitle}>확인 대기 검사 · {filters.partCode ?? '전체 부품'}</Text>
              <View style={s.choices}>
                {(['RECEIVED', 'PRIORITY'] as const).map(sort => (
                  <Pressable key={sort} accessibilityRole="button"
                    accessibilityState={{selected:filters.sort===sort}} disabled={submitting}
                    style={[s.outline, filters.sort===sort && s.activeChoice]}
                    onPress={()=>changeFilters({...filters, sort})}>
                    <Text style={[s.outlineText, filters.sort===sort && s.activeChoiceText]}>
                      {sort==='RECEIVED' ? '접수순' : '우선 검토'}
                    </Text>
                  </Pressable>
                ))}
                <Pressable accessibilityRole="checkbox"
                  accessibilityState={{checked:filters.aiDefectOnly}} disabled={submitting}
                  style={[s.outline, filters.aiDefectOnly && s.activeChoice]}
                  onPress={()=>changeFilters({...filters, aiDefectOnly:!filters.aiDefectOnly})}>
                  <Text style={[s.outlineText, filters.aiDefectOnly && s.activeChoiceText]}>AI 불량 의심만</Text>
                </Pressable>
              </View>
              <Pressable accessibilityRole="button" style={s.outline} disabled={browse.status==='loading' || submitting}
                onPress={()=>{void browser.refresh();}}>
                <Text style={s.outlineText}>대기열 새로고침</Text>
              </Pressable>
              {browse.status==='loading' && <ActivityIndicator />}
              {browse.error && <Text style={s.error}>대기열을 불러오지 못했습니다. 다시 조회해 주세요.</Text>}
              {browse.status==='ready' && browse.items.length===0 && <Text style={s.muted}>이 조건에 해당하는 확인 대기 검사가 없습니다.</Text>}
              {browse.items.map(item=>(
                <View key={item.inspectionId} style={s.line}>
                  <View style={s.rowText}>
                    <Text style={s.strong}>{item.inspectionNo ?? '검사번호 미제공'} · {item.partCode}</Text>
                    <Text style={s.muted}>AI 예측: {item.predictedQuality ?? '미제공'} · REVIEW</Text>
                  </View>
                  <Pressable accessibilityRole="button" style={s.outline}
                    disabled={previewLoading || submitting} onPress={()=>{void openDetail(item);}}>
                    <Text style={s.outlineText}>상세 검토</Text>
                  </Pressable>
                </View>
              ))}
              {browse.nextCursor && (
                <Pressable accessibilityRole="button" style={s.outline}
                  disabled={browse.status==='loading' || submitting} onPress={()=>{void browser.loadNext();}}>
                  <Text style={s.outlineText}>다음 20건 조회</Text>
                </Pressable>
              )}
            </View>
            <View style={s.card}>
              <Text style={s.cardTitle}>선택 검사 · {selected.length}/{MAX_BATCH_FAIL_V4}건</Text>
              <Text style={s.muted}>제출 전 검사번호를 확인하세요. 이 목록의 검사만 한 번에 FAIL을 요청합니다.</Text>
              {selected.length === 0 && <Text style={s.muted}>선택된 검사가 없습니다.</Text>}
              {selected.map((item,index)=>(
                <View key={item.inspectionId} style={s.line}>
                  <Text style={s.strong}>{index+1}. {item.inspectionNo} · {item.partCode}</Text>
                  <Pressable accessibilityRole="button" disabled={submitting}
                    onPress={()=>{
                      confirmation.invalidate();
                      setSelected(old=>old.filter(x=>x.inspectionId!==item.inspectionId));
                    }}>
                    <Text style={s.remove}>제외</Text>
                  </Pressable>
                </View>
              ))}
              <Text style={s.strong}>공통 판정 사유 (선택, 최대 200자)</Text>
              <TextInput ref={commentRef} onFocus={revealComment} value={comment} editable={!submitting} onChangeText={value=>{confirmation.invalidate();setComment(value);}} style={s.input}
                placeholder="예: 고정핀 들뜸" placeholderTextColor="#94A3B8"
                maxLength={200} multiline />
              <Text style={s.muted}>제출 후에는 정상 처리·기존 FAIL·충돌·서버 오류가 검사별로 구분됩니다.</Text>
              <Pressable accessibilityRole="button" disabled={selected.length===0 || submitting}
                style={[s.danger, (selected.length===0 || submitting) && s.disabled]}
                onPress={confirmSubmit}>
                <Text style={s.actionText}>
                  {submitting ? '서버 제출 중…' : `선택한 ${selected.length}건 FAIL 확정 전 최종 확인`}
                </Text>
              </Pressable>
              {submitError && <Text style={s.error}>제출 결과 확인 실패: {submitError}</Text>}
            </View>
            {reply && (
              <View style={s.card}>
                <Text style={s.cardTitle}>일괄 FAIL 제출 결과 · {reply.results.length}건</Text>
                <Text style={s.muted}>일괄 판정 번호 · {reply.batchId}</Text>
                {reply.results.map(row=>(
                  <View key={row.inspectionId} style={s.result}>
                    <Text style={s.strong}>{row.inspectionNo ?? row.inspectionId}</Text>
                    <Text style={s.muted}>{batchFailResultLabelV4(row.result)}</Text>
                    <Text style={s.muted}>
                      현재 기록: {row.finalJudgement ?? '미판정'} · {actorLabelV4(row.judgedBy)}
                      {row.errorCode ? ` · ${row.errorCode}` : ''}
                    </Text>
                  </View>
                ))}
              </View>
            )}
          </>
        )}
      </ScrollView>
      </KeyboardAvoidingView>
      {/* 목록과 독립된 상세 검토 화면: 뒤로 가면 기존 목록 스크롤 위치 유지. */}
      <Modal
        visible={previewLoading || preview !== null || previewError !== null}
        animationType="slide"
        presentationStyle="fullScreen"
        onRequestClose={closeDetail}
      >
        {/* RN Modal은 별도의 네이티브 창이므로 모달 안에서 안전 영역을 다시 측정합니다. */}
        <SafeAreaProvider>
          <SafeAreaView style={s.screen} edges={['top', 'bottom', 'left', 'right']}>
          <View style={s.modalHeading}>
            <Pressable accessibilityRole="button" style={s.modalBackButton}
              hitSlop={10} onPress={closeDetail}>
              <Text style={s.back}>‹ 검사 목록으로 돌아가기</Text>
            </Pressable>
            <Text style={s.title}>검사 상세 검토</Text>
            <Text style={s.muted}>원본 사진과 AI 판단 근거를 확인한 뒤에만 검사를 선택할 수 있습니다.</Text>
          </View>
          <ScrollView contentContainerStyle={s.body} keyboardShouldPersistTaps="handled">
            <View style={s.card}>
              <Text style={s.cardTitle}>검사 상세 검토</Text>
              {previewLoading && <ActivityIndicator />}
              {previewError && <>
                <Text style={s.error}>상세 조회 실패: {previewError}</Text>
                <Pressable accessibilityRole="button" style={s.outline} onPress={retryDetail}><Text style={s.outlineText}>상세 다시 조회</Text></Pressable>
              </>}
              {!preview && !previewLoading && !previewError && (
                <Text style={s.muted}>위 목록에서 '상세 검토'를 눌러 원본과 AI 정보를 먼저 확인하세요.</Text>
              )}
              {preview && (
                <>
                  <Text style={s.strong}>{preview.inspectionNo} · {preview.partCode}</Text>
                  <Text style={s.muted}>상태: {preview.displayStateLabel}</Text>
                  <Text style={s.muted}>AI 예측: {preview.prediction ?? '미제공'} · 보정 불량 확률 {percent(preview.calibratedDefectProbability)}</Text>
                  <Text style={s.muted}>현재 판정: {preview.finalJudgement ?? '미판정'}</Text>
                  <Text style={s.strong}>원본 사진</Text>
                  {preview.originalImageUrl ? (
                    <>
                      {originalState==='loading'&&<Text style={s.muted}>원본 사진을 불러오는 중…</Text>}
                      <Image key={`original-${imageSerial}`} style={s.photo} resizeMode="contain" source={{uri:preview.originalImageUrl}}
                        onLoad={()=>imageResult('original','loaded')} onError={()=>imageResult('original','failed')}/>
                      {originalState==='failed'&&<Text style={s.error}>원본 사진 표시 실패. 이미지 다시 조회가 필요합니다.</Text>}
                    </>
                  ) : <Text style={s.error}>원본 사진을 제공받지 못해 일괄 선택할 수 없습니다.</Text>}
                  <Text style={s.strong}>AI 판단 근거 이미지</Text>
                  {preview.gradcamImageUrl ? (
                    <>
                      {camState==='loading'&&<Text style={s.muted}>AI 판단 근거를 불러오는 중…</Text>}
                      <Image key={`cam-${imageSerial}`} style={s.photo} resizeMode="contain" source={{uri:preview.gradcamImageUrl}}
                        onLoad={()=>imageResult('cam','loaded')} onError={()=>imageResult('cam','failed')}/>
                      {camState==='failed'&&<Text style={s.error}>AI 판단 근거 표시 실패. 이미지 다시 조회가 필요합니다.</Text>}
                    </>
                  ) : <Text style={s.muted}>AI 판단 근거 이미지 없음 또는 제공 대상 아님</Text>}
                  <Pressable accessibilityRole="button" style={s.outline} disabled={previewLoading} onPress={retryDetail}>
                    <Text style={s.outlineText}>이미지 다시 조회</Text>
                  </Pressable>
                  {!imagesReady && <Text style={s.muted}>원본과 제공된 AI 판단 근거가 모두 표시되어야 검토 확인 및 선택할 수 있습니다.</Text>}
                  {preview.displayState === 'REVIEW_PENDING' && preview.originalImageUrl && (
                    <>
                      <Pressable accessibilityRole="checkbox"
                        accessibilityState={{checked:reviewed,disabled:!imagesReady}} disabled={!imagesReady}
                        style={[s.line,!imagesReady&&s.disabled]} onPress={()=>{if(imagesReady)setReviewed(value=>!value);}}>
                        <Text style={s.strong}>{reviewed ? '☑' : '□'} 이 검사의 원본과 AI 결과를 직접 검토했습니다.</Text>
                      </Pressable>
                      <Pressable accessibilityRole="button" style={[s.action, (!reviewed||!imagesReady) && s.disabled]}
                        disabled={!reviewed || !imagesReady || selected.length >= MAX_BATCH_FAIL_V4 ||
                          selected.some(x=>x.inspectionId === preview.inspectionId)}
                        onPress={addSelection}>
                        <Text style={s.actionText}>
                          {selected.some(x=>x.inspectionId === preview.inspectionId)
                            ? '이미 선택한 검사' : '이 검사를 일괄 FAIL 대상에 추가'}
                        </Text>
                      </Pressable>
                    </>
                  )}
                  {preview.displayState !== 'REVIEW_PENDING' &&
                    <Text style={s.error}>현재 REVIEW 대기가 아니어서 선택할 수 없습니다.</Text>}
                </>
              )}
            </View>
          </ScrollView>
          </SafeAreaView>
        </SafeAreaProvider>
      </Modal>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen:{flex:1,backgroundColor:'#F5F7FB'},
  heading:{paddingHorizontal:18,paddingTop:10,paddingBottom:14,gap:7},
  back:{color:'#2054D8',fontSize:13,fontWeight:'700'},
  modalHeading:{paddingHorizontal:18,paddingTop:12,paddingBottom:16,gap:9},
  modalBackButton:{alignSelf:'flex-start',minHeight:44,justifyContent:'center',paddingVertical:7},
  title:{color:'#111827',fontSize:23,fontWeight:'700'},
  body:{paddingHorizontal:18,paddingBottom:30,gap:12},
  card:{backgroundColor:'#FFFFFF',borderColor:'#E4E7EC',borderWidth:1,borderRadius:14,padding:14,gap:11},
  cardTitle:{color:'#111827',fontSize:16,fontWeight:'700'},
  strong:{color:'#111827',fontSize:12,fontWeight:'700',flexShrink:1},
  muted:{color:'#64748B',fontSize:11,lineHeight:17},
  error:{color:'#B42318',fontSize:12,lineHeight:18},
  line:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:8,paddingVertical:8,
    borderTopColor:'#E4E7EC',borderTopWidth:1},
  rowText:{flex:1,gap:5},
  outline:{borderColor:'#CBD5E1',borderWidth:1,borderRadius:8,paddingHorizontal:10,paddingVertical:9,
    alignSelf:'flex-start',backgroundColor:'#FFFFFF'},
  choices:{flexDirection:'row',flexWrap:'wrap',gap:6},
  activeChoice:{backgroundColor:'#2054D8',borderColor:'#2054D8'},
  activeChoiceText:{color:'#FFFFFF'},
  outlineText:{color:'#2054D8',fontSize:12,fontWeight:'700'},
  photo:{width:'100%',height:250,backgroundColor:'#EEF2F8',borderRadius:8},
  action:{backgroundColor:'#2054D8',borderRadius:9,padding:12,alignItems:'center'},
  actionText:{color:'#FFFFFF',fontSize:13,fontWeight:'700',textAlign:'center'},
  danger:{backgroundColor:'#B42318',borderRadius:10,padding:13,alignItems:'center'},
  disabled:{opacity:0.45},
  remove:{color:'#B42318',fontSize:12,fontWeight:'700'},
  input:{backgroundColor:'#F8FAFC',borderColor:'#CBD5E1',borderWidth:1,borderRadius:9,
    padding:11,color:'#111827',minHeight:62,textAlignVertical:'top',fontSize:12},
  result:{borderTopWidth:1,borderTopColor:'#E4E7EC',paddingVertical:10,gap:5},
});
