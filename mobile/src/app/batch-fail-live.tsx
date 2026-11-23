import React, { useCallback, useEffect, useRef, useState } from 'react';
import { router, Stack } from 'expo-router';
import {
  ActivityIndicator, Alert, Image, Pressable, ScrollView, StyleSheet,
  Text, TextInput, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { authV4 } from '../api/backendV4/authRuntime';
import type { BackendRole } from '../api/backendV4/authCore';
import { createInspectionReadServiceV4 } from '../api/backendV4/inspectionReadService';
import type { QueueItemV4 } from '../api/backendV4/inspectionReadCore';
import type { InspectionViewV4 } from '../api/backendV4/types';
import {
  batchFailResultLabelV4, MAX_BATCH_FAIL_V4,
  selectableReviewForBatchV4,
  type BatchFailReplyV4, type BatchFailSelectionV4,
} from '../api/backendV4/batchFailCoreV4';
import { createBatchFailServiceV4 } from '../api/backendV4/batchFailServiceV4';

const reader = createInspectionReadServiceV4({mode: 'api', transport: authV4});
const writer = createBatchFailServiceV4(authV4);
const PAGE_SIZE = 20;

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : '요청 처리 중 오류가 발생했습니다.';
}
function percent(value: number | null): string {
  return value == null ? '미제공' : `${(value * 100).toFixed(2)}%`;
}

export default function BatchFailLiveScreen() {
  const [role, setRole] = useState<BackendRole | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [queue, setQueue] = useState<QueueItemV4[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [queueLoading, setQueueLoading] = useState(false);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [preview, setPreview] = useState<InspectionViewV4 | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [selected, setSelected] = useState<BatchFailSelectionV4[]>([]);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [reply, setReply] = useState<BatchFailReplyV4 | null>(null);
  const loadingRef = useRef(false);
  const requestId = useRef(0);
  const mountedRef = useRef(true);
  const submitLock = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    let cancelled = false;
    void authV4.restore().then(session => {
      if (!cancelled) setRole(session.signedIn ? session.role : null);
    }).catch(() => { if (!cancelled) setRole(null); })
      .finally(() => { if (!cancelled) setAuthLoading(false); });
    return () => { cancelled = true; mountedRef.current = false; requestId.current += 1; };
  }, []);

  const loadQueue = useCallback(async (append: boolean) => {
    if (loadingRef.current) return;
    const nextCursor = append ? cursor : null;
    if (append && !nextCursor) return;
    loadingRef.current = true;
    const serial = ++requestId.current;
    setQueueLoading(true);
    setQueueError(null);
    try {
      const result = await reader.queue({type:'REVIEW',size:PAGE_SIZE,...(nextCursor ? {cursor:nextCursor} : {})});
      if (!mountedRef.current || serial !== requestId.current) return;
      if (result.source !== 'SERVER') throw new Error('실제 서버 응답이 아닙니다.');
      if (result.value.items.some(row => row.displayState !== 'REVIEW_PENDING')) {
        throw new Error('REVIEW가 아닌 검사가 포함됐습니다.');
      }
      setQueue(old => {
        const before = append ? old : [];
        const seen = new Set(before.map(row => row.inspectionId));
        return [...before, ...result.value.items.filter(row => !seen.has(row.inspectionId))];
      });
      setCursor(result.value.nextCursor);
      setLoaded(true);
    } catch (cause) {
      if (mountedRef.current && serial === requestId.current) setQueueError(errorText(cause));
    } finally {
      loadingRef.current = false;
      if (mountedRef.current && serial === requestId.current) setQueueLoading(false);
    }
  }, [cursor]);

  useEffect(() => {
    if (!authLoading && role === 'WORKER') void loadQueue(false);
    // 최초 로그인 확인 직후에만 실행. 이후 새로고침은 사용자가 명시적으로 선택합니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, role]);

  const openDetail = async (item: QueueItemV4) => {
    if (previewLoading || submitting) return;
    setPreview(null);
    setPreviewError(null);
    setReviewed(false);
    setPreviewLoading(true);
    try {
      const result = await reader.detail(item.inspectionId);
      if (!mountedRef.current) return;
      if (result.source !== 'SERVER') throw new Error('실제 서버 검사 상세가 아닙니다.');
      setPreview(result.value);
    } catch(cause) {
      if (mountedRef.current) setPreviewError(errorText(cause));
    } finally {
      if (mountedRef.current) setPreviewLoading(false);
    }
  };

  const addSelection = () => {
    if (!preview || !reviewed || role !== 'WORKER' || !preview.originalImageUrl) return;
    try {
      const item = selectableReviewForBatchV4(preview);
      setSelected(old => {
        if (old.some(x => x.inspectionId === item.inspectionId)) return old;
        if (old.length >= MAX_BATCH_FAIL_V4) return old;
        return [...old, item];
      });
      setPreview(null);
      setReviewed(false);
    } catch(cause) { Alert.alert('선택 불가', errorText(cause)); }
  };

  const submit = async () => {
    if (submitLock.current || submitting || role !== 'WORKER') return;
    submitLock.current = true;
    setSubmitting(true);
    setSubmitError(null);
    setReply(null);
    try {
      // 서버가 최종 권위: 경쟁 제출·상태 변경은 건별 CONFLICT/NOT_REVIEWABLE로 응답.
      const session = await authV4.restore();
      if (!session.signedIn || session.role !== 'WORKER') throw new Error('WORKER 로그인 상태를 다시 확인해 주세요.');
      const response = await writer.submit(session.role, selected, comment);
      if (!mountedRef.current) return;
      setReply(response.value);
      setSelected([]);
      setComment('');
      // 기존 서버 대기열은 추후 수동 새로고침에서 상태를 확인합니다.
    } catch(cause) {
      if (mountedRef.current) setSubmitError(errorText(cause));
    } finally {
      submitLock.current = false;
      if (mountedRef.current) setSubmitting(false);
    }
  };

  const confirmSubmit = () => {
    if (role !== 'WORKER' || selected.length === 0 || submitting) return;
    Alert.alert(
      `선택한 ${selected.length}건을 FAIL로 확정할까요?`,
      '아래 화면에 표시된 검사번호와 원본 사진을 다시 확인해 주세요.\n' +
        selected.slice(0, 7).map(x => x.inspectionNo).join(', ') +
        (selected.length > 7 ? ` 외 ${selected.length - 7}건` : '') +
        '\n이 작업은 실제 서버 판정 기록을 변경합니다. 개별 실패 건은 따로 표시됩니다.',
      [
        {text:'취소',style:'cancel'},
        {text:'선택 검사 FAIL 제출',style:'destructive',onPress:()=>{void submit();}},
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
      <ScrollView contentContainerStyle={s.body} keyboardShouldPersistTaps="handled">
        {authLoading ? <ActivityIndicator /> : role !== 'WORKER' ? (
          <View style={s.card}><Text style={s.error}>WORKER 로그인 계정만 사용할 수 있습니다.</Text></View>
        ) : (
          <>
            <View style={s.card}>
              <Text style={s.cardTitle}>확인 대기 REVIEW 검사</Text>
              <Text style={s.muted}>조회 전용 목록입니다. 상세 검토 없이 일괄 선택할 수 없습니다.</Text>
              <Pressable accessibilityRole="button" style={s.outline} disabled={queueLoading}
                onPress={()=>{void loadQueue(false);}}>
                <Text style={s.outlineText}>대기열 새로고침</Text>
              </Pressable>
              {queueLoading && <ActivityIndicator />}
              {queueError && <Text style={s.error}>목록 조회 실패: {queueError}</Text>}
              {loaded && queue.length === 0 && <Text style={s.muted}>확인 대기 검사가 없습니다.</Text>}
              {queue.map(item=>(
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
              {cursor && (
                <Pressable accessibilityRole="button" style={s.outline}
                  disabled={queueLoading} onPress={()=>{void loadQueue(true);}}>
                  <Text style={s.outlineText}>다음 20건 조회</Text>
                </Pressable>
              )}
            </View>
            <View style={s.card}>
              <Text style={s.cardTitle}>검사 상세 검토</Text>
              {previewLoading && <ActivityIndicator />}
              {previewError && <Text style={s.error}>상세 조회 실패: {previewError}</Text>}
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
                    <Image style={s.photo} resizeMode="contain" source={{uri:preview.originalImageUrl}} />
                  ) : <Text style={s.error}>원본 사진을 제공받지 못해 일괄 선택할 수 없습니다.</Text>}
                  <Text style={s.strong}>AI 판단 근거 이미지</Text>
                  {preview.gradcamImageUrl ? (
                    <Image style={s.photo} resizeMode="contain" source={{uri:preview.gradcamImageUrl}} />
                  ) : <Text style={s.muted}>AI 판단 근거 이미지 없음 또는 제공 대상 아님</Text>}
                  {preview.displayState === 'REVIEW_PENDING' && preview.originalImageUrl && (
                    <>
                      <Pressable accessibilityRole="checkbox"
                        accessibilityState={{checked:reviewed}}
                        style={s.line} onPress={()=>setReviewed(value=>!value)}>
                        <Text style={s.strong}>{reviewed ? '☑' : '□'} 이 검사의 원본과 AI 결과를 직접 검토했습니다.</Text>
                      </Pressable>
                      <Pressable accessibilityRole="button" style={[s.action, !reviewed && s.disabled]}
                        disabled={!reviewed || selected.length >= MAX_BATCH_FAIL_V4 ||
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
            <View style={s.card}>
              <Text style={s.cardTitle}>선택 검사 · {selected.length}/{MAX_BATCH_FAIL_V4}건</Text>
              <Text style={s.muted}>제출 전 검사번호를 확인하세요. 이 목록의 검사만 한 번에 FAIL을 요청합니다.</Text>
              {selected.length === 0 && <Text style={s.muted}>선택된 검사가 없습니다.</Text>}
              {selected.map((item,index)=>(
                <View key={item.inspectionId} style={s.line}>
                  <Text style={s.strong}>{index+1}. {item.inspectionNo} · {item.partCode}</Text>
                  <Pressable accessibilityRole="button"
                    onPress={()=>setSelected(old=>old.filter(x=>x.inspectionId!==item.inspectionId))}>
                    <Text style={s.remove}>제외</Text>
                  </Pressable>
                </View>
              ))}
              <Text style={s.strong}>공통 판정 사유 (선택, 최대 200자)</Text>
              <TextInput value={comment} onChangeText={setComment} style={s.input}
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
                <Text style={s.muted}>batchId: {reply.batchId}</Text>
                {reply.results.map(row=>(
                  <View key={row.inspectionId} style={s.result}>
                    <Text style={s.strong}>{row.inspectionNo ?? row.inspectionId}</Text>
                    <Text style={s.muted}>{batchFailResultLabelV4(row.result)}</Text>
                    <Text style={s.muted}>
                      현재 기록: {row.finalJudgement ?? '미판정'} · {row.judgedBy ?? '미제공'}
                      {row.errorCode ? ` · ${row.errorCode}` : ''}
                    </Text>
                  </View>
                ))}
              </View>
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen:{flex:1,backgroundColor:'#F5F7FB'},
  heading:{paddingHorizontal:18,paddingTop:10,paddingBottom:14,gap:7},
  back:{color:'#2054D8',fontSize:13,fontWeight:'700'},
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
