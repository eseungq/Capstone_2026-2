import React, { useEffect, useState } from 'react';
import {
  Alert,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack, router, useLocalSearchParams } from 'expo-router';
import {
  confirmMockInspection,
  getMockInspection,
  retryMockInspection,
  type FinalJudgement,
  type Inspection,
  type InspectionStatus,
  useMockStoreState,
} from '../../data/mockInspections';

// 기준: Figma FyGAGiL2xkZgaDfegUk10A / 99:230, 107:34, 107:104,
// 107:170, 187:236, 99:425, 114:153 (2026-10-27 확인)
// 실제 API / AI 모델과 연결되지 않은 시연 전용 코드입니다.
type Role = 'WORKER' | 'ADMIN';
type Choice = 'PASS' | 'FAIL';

const C = {
  background: '#F5F7FB',
  white: '#FFFFFF',
  border: '#E4E7EC',
  ink: '#111827',
  muted: '#64748B',
  faint: '#EEF2F8',
  blue: '#2054D8',
  amber: '#A74B12',
  amberBg: '#FFF3E5',
  green: '#067647',
  greenBg: '#EAFBF2',
  greenSelected: '#B6F5D2',
  red: '#B42318',
  redBg: '#FFF0ED',
  redSelected: '#FECACA',
  disabled: '#CBD5E1',
};

function stateLabel(status: InspectionStatus, finalJudgement: FinalJudgement): string {
  if (status === 'REVIEW' && finalJudgement) return 'REVIEW_DONE';
  return status;
}

function StatusTag({ status, finalJudgement }: {
  status: InspectionStatus;
  finalJudgement: FinalJudgement;
}) {
  const label = stateLabel(status, finalJudgement);
  const isFailure = status === 'FAILED';
  const isReview = status === 'REVIEW' && !finalJudgement;
  const isDone = status === 'REVIEW' && Boolean(finalJudgement);
  return (
    <View style={[
      styles.tag,
      { backgroundColor: isFailure ? C.redBg : isReview ? C.amberBg : isDone ? C.greenBg : C.faint },
    ]}>
      <Text style={[
        styles.tagText,
        { color: isFailure ? C.red : isReview ? C.amber : isDone ? C.green : C.muted },
      ]}>{label}</Text>
    </View>
  );
}

function Card({ title, children, tint }: {
  title?: string;
  children: React.ReactNode;
  tint?: string;
}) {
  return (
    <View style={[styles.card, tint ? { backgroundColor: tint } : undefined]}>
      {title ? <Text style={styles.cardTitle}>{title}</Text> : null}
      {children}
    </View>
  );
}

function Field({ label, value, highlight }: {
  label: string;
  value: string;
  highlight?: 'warning' | 'danger' | 'success';
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <Text style={[
        styles.fieldValue,
        highlight === 'warning' ? { color: C.amber } :
          highlight === 'danger' ? { color: C.red } :
          highlight === 'success' ? { color: C.green } : undefined,
      ]}>{value}</Text>
    </View>
  );
}

function ActionButton({ label, onPress, disabled = false, secondary = false }: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  secondary?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.actionButton,
        secondary ? styles.secondaryAction : disabled ? styles.disabledAction : styles.primaryAction,
        pressed && !disabled ? { opacity: 0.75 } : undefined,
      ]}
    >
      <Text style={[
        styles.actionLabel,
        secondary ? { color: C.ink } : disabled ? { color: C.muted } : { color: C.white },
      ]}>{label}</Text>
    </Pressable>
  );
}

function BottomNav({ role }: { role: Role }) {
  return (
    <View style={styles.bottomNav}>
      <Pressable
        onPress={() => router.replace({ pathname: '/monitoring', params: { role } })}
        accessibilityRole="button"
        accessibilityLabel="모니터링으로 돌아가기"
        style={styles.navItem}
      >
        <Text style={[styles.navIcon, { color: C.blue }]}>▣</Text>
        <Text style={[styles.navText, { color: C.blue, fontWeight: '700' }]}>모니터링</Text>
      </Pressable>
      <Pressable
        onPress={() => router.push({ pathname: '/history', params: { role } })}
        accessibilityRole="button"
        accessibilityLabel="검사 이력으로 이동"
        style={styles.navItem}
      >
        <Text style={styles.navIcon}>▤</Text>
        <Text style={styles.navText}>이력</Text>
      </Pressable>
      <View style={styles.navItem} accessibilityLabel="설정 탭 연결 예정">
        <Text style={styles.navIcon}>⚙</Text>
        <Text style={styles.navText}>설정</Text>
      </View>
    </View>
  );
}

export default function InspectionDetailScreen() {
  const params = useLocalSearchParams<{ id?: string; role?: string }>();
  const id = typeof params.id === 'string' ? params.id : '';
  // 시연용 라우트 정보. 실제 앱에서는 로그인 인증/서버에서도 권한을 검증해야 합니다.
  const role: Role = params.role === 'WORKER' ? 'WORKER' : 'ADMIN';
  const { ready, revision, warning } = useMockStoreState();
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [selection, setSelection] = useState<Choice | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (ready) setInspection(getMockInspection(id));
    setSelection(null);
    setSubmitting(false);
  }, [id, ready, revision]);

  const navigateTo = (nextId: string) => {
    router.push({ pathname: '/inspection/[id]', params: { id: nextId, role } });
  };

  const submitJudgement = () => {
    if (!ready || !selection || submitting || role !== 'WORKER' || inspection?.status !== 'REVIEW' || inspection.finalJudgement) {
      return;
    }
    const judgement = selection;
    Alert.alert(
      '최종 판정 제출 · Mock',
      `${judgement}로 최종 판정하시겠습니까?\nAI 예측 결과는 변경되지 않습니다.`,
      [
        { text: '취소', style: 'cancel' },
        {
          text: '제출',
          onPress: async () => {
            setSubmitting(true);
            try {
              // 로컬 저장 성공을 확인한 뒤 결과 화면으로 이동합니다.
              const updated = await confirmMockInspection(id, judgement, role);
              setInspection(updated);
              setSelection(null);
              router.replace({ pathname: '/inspection/result', params: { id, role } });
            } catch (error) {
              setInspection(getMockInspection(id));
              Alert.alert('제출 실패', error instanceof Error ? error.message : '알 수 없는 오류');
            } finally {
              setSubmitting(false);
            }
          },
        },
      ],
    );
  };

  const requestRetry = () => {
    Alert.alert(
      '재검사 요청 · Mock',
      '기존 FAILED 기록을 보존하고 저장된 원본으로 새 검사를 생성할까요?',
      [
        { text: '취소', style: 'cancel' },
        {
          text: '재검사',
          onPress: async () => {
            try {
              const next = await retryMockInspection(id);
              setInspection(getMockInspection(id));
              navigateTo(next.id);
            } catch (error) {
              setInspection(getMockInspection(id));
              Alert.alert('재검사 불가', error instanceof Error ? error.message : '알 수 없는 오류');
            }
          },
        },
      ],
    );
  };

  const status = inspection?.status;
  const isReview = status === 'REVIEW';
  const isAutoPassExample = status === 'AUTO_PASS_EXAMPLE';
  const isFailed = status === 'FAILED';
  const isInProgress = status === 'RECEIVED' || status === 'ANALYZING';
  const canJudge = ready && role === 'WORKER' && isReview && !inspection?.finalJudgement;

  const headerTitle = isAutoPassExample ? '검사 상세 · AUTO_PASS 예시' : isFailed
    ? (role === 'ADMIN' ? '검사 상세 · 관리자 FAILED' : '검사 상세 · FAILED')
    : role === 'ADMIN' && isReview ? '검사 상세 · 관리자 조회'
      : isReview && inspection?.finalJudgement ? '검사 상세 · 판정 완료'
        : selection ? `REVIEW · ${selection} 선택`
          : isReview ? '검사 상세 · REVIEW'
            : '검사 처리 상태';

  const headerSubtitle = isAutoPassExample ? '정책 미검증 · 실제 자동 통과 기록 아님' : isFailed
    ? 'AI 분석 실패 · 오류 알림과 재시도'
    : isInProgress ? '접수 성공은 분석 완료가 아닙니다 · Mock'
      : role === 'ADMIN' ? '전체 검사 조회 · 작업자 판정 수정 불가'
        : selection ? '작업자 판정 선택 완료 · Mock'
          : '원본과 AI 판단 근거 확인 · Mock';

  const displayPrediction = !(isReview || isAutoPassExample)
    ? '분석 결과 없음'
    : inspection?.prediction === 'DEFECT' ? '불량 쪽 예측'
      : inspection?.prediction === 'GOOD' ? '정상 쪽 예측' : '미제공';

  const displayProbability = inspection?.calibratedDefectProbability == null
    ? '미제공'
    : `${inspection.calibratedDefectProbability.toFixed(2)} · Mock`;

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.heading}>
        <Text style={styles.pageTitle} numberOfLines={2}>{headerTitle}</Text>
        <Text style={styles.pageSubtitle}>{headerSubtitle}</Text>
      </View>
      <ScrollView
        style={styles.scroller}
        contentContainerStyle={styles.body}
        showsVerticalScrollIndicator={false}
      >
        {warning ? (
          <View style={styles.infoNote}><Text style={styles.infoNoteText}>{warning}</Text></View>
        ) : null}
        {!ready ? (
          <Card title="로컬 Mock 기록 불러오는 중">
            <Text style={styles.note}>저장된 판정과 재검사 이력을 불러온 뒤 조작할 수 있습니다.</Text>
          </Card>
        ) : !inspection ? (
          <Card title="검사 정보를 찾을 수 없습니다">
            <Text style={styles.note}>{id}는 현재 시연용 데이터에 없습니다.</Text>
            <ActionButton label="모니터링으로 돌아가기" onPress={() => router.back()} />
          </Card>
        ) : isFailed ? (
          <>
            <Card title="분석 실패 · FAILED" tint={C.redBg}>
              <Text style={styles.note}>{inspection.partCode} · {inspection.id}</Text>
              <StatusTag status={inspection.status} finalJudgement={inspection.finalJudgement} />
              <Field label="오류 코드" value="미제공 (Mock)" highlight="danger" />
              <Field label="최종 판정" value="없음" />
            </Card>
            <Card>
              <Text style={styles.failureHeading}>{inspection.errorMessage ?? 'AI 분석에 실패했습니다.'}</Text>
              <Text style={styles.note}>재검사하면 새 검사 ID가 생성되고, 기존 FAILED 기록은 그대로 유지됩니다.</Text>
            </Card>
            {inspection.retriedBy ? (
              <ActionButton label={`새 검사 ${inspection.retriedBy} 조회`} onPress={() => navigateTo(inspection.retriedBy!)} />
            ) : (
              <ActionButton label={role === 'ADMIN' ? '재검사 · Mock (API v4 제안)' : '재검사'} onPress={requestRetry} />
            )}
            <ActionButton label="모니터링으로 돌아가기" secondary onPress={() => router.replace({ pathname: '/monitoring', params: { role } })} />
            <View style={styles.infoNote}>
              <Text style={styles.infoNoteText}>
                {role === 'ADMIN'
                  ? 'Figma: 관리자 재검사 권한 확인 필요 / API v4: 관리자 허용 제안 · 현재 기존 Mock 기능 유지'
                  : '신규 ID 발급 · 원본 FAILED 보존 · retryOf 연결 · Mock'}
              </Text>
            </View>
          </>
        ) : (
          <>
            <Card title={isInProgress ? '접수 완료 · AI 분석 대기' : '검사 상태'}>
              <Field label="부품 / 검사 ID" value={`${inspection.partCode} · ${inspection.id}`} />
              {isAutoPassExample ? (
                <View style={[styles.tag, { backgroundColor: C.greenBg }]}>
                  <Text style={[styles.tagText, { color: C.green }]}>AUTO_PASS · 시연 예시 (미확정)</Text>
                </View>
              ) : (
                <StatusTag status={inspection.status} finalJudgement={inspection.finalJudgement} />
              )}
            </Card>

            <Card>
              <View style={styles.compareRow}>
                <View style={styles.imageColumn}>
                  <Text style={styles.imageCaption}>원본 사진</Text>
                  <View style={styles.imageFrame}>
                    <Image source={inspection.originalImage} style={styles.image} resizeMode="cover" />
                  </View>
                </View>
                <View style={styles.imageColumn}>
                  <Text style={styles.imageCaption}>AI 판단 근거 · {inspection.gradcamAvailable ? '확인' : '미제공'}</Text>
                  <View style={styles.gradcamEmpty}>
                    <Text style={styles.gradcamEmptyText}>
                      {inspection.gradcamAvailable
                        ? '근거 이미지 연결이 필요합니다.'
                        : isInProgress ? '이미지 준비 중' : '판단 근거 이미지를 제공할 수 없습니다. 원본과 분류 결과를 확인해 주세요.'}
                    </Text>
                  </View>
                </View>
              </View>
              <Text style={styles.smallNote}>
                Grad-CAM은 AI 판단 근거이며 정확한 결함 좌표·마스크가 아닙니다. 미제공만으로 FAILED 처리하지 않습니다.
              </Text>
            </Card>

            <Card title={isInProgress ? '처리 단계' : 'AI 분석 결과 · 예시'}>
              {isInProgress ? (
                <>
                  <Field label="사진 입력" value="접수됨 · Mock" />
                  <Field label="AI 분류" value={status === 'ANALYZING' ? '분석 중' : '대기'} />
                  <Field label="정책 결과" value="대기" />
                  <Field label="최종 판정" value="없음" />
                </>
              ) : (
                <>
                  <Field label="AI 분류" value={displayPrediction} />
                  <Field label="판단 근거" value={inspection.gradcamAvailable ? '제공됨 · Mock' : '이미지 미제공'} />
                  <Field label="보정 불량 확률" value={displayProbability} />
                </>
              )}
            </Card>

            {isAutoPassExample && (
              <Card title="AUTO_PASS 시연 예시 · 확정 아님">
                <Field label="AI 예측" value="GOOD · Mock" />
                <Field label="정책 상태" value="검증된 정책 없음" highlight="warning" />
                <Field label="최종 판정" value="없음 · 확정하지 않음" />
                <Text style={styles.policyNote}>
                  Figma의 AUTO_PASS 예시를 보여주기 위한 가상 상태입니다. 실제 자동 통과로 처리하거나 정상 통계에 포함하지 않습니다.
                </Text>
              </Card>
            )}

            {isReview && (
              <Card title="정책 및 최종 판정">
                <Field label="백엔드 처리 결과" value="REVIEW" highlight="warning" />
                <Field label="최종 판정" value={inspection.finalJudgement ?? '작업자 확인 전 · 미정'} />
                <Field label="REVIEW 사유" value={inspection.reviewReason ?? '미제공'} highlight="warning" />
                <Text style={styles.policyNote}>
                  {inspection.prediction === 'DEFECT'
                    ? 'AI가 불량 쪽으로 예측했으며 작업자의 확인이 필요합니다.'
                    : 'AI 예측과 별개로 정책 검토가 필요해 작업자 확인을 기다립니다.'}
                </Text>
              </Card>
            )}

            {canJudge && (
              <>
                <Card title="작업자 최종 판정">
                  <View style={styles.choiceRow}>
                    {(['PASS', 'FAIL'] as const).map((choice) => {
                      const chosen = selection === choice;
                      const pass = choice === 'PASS';
                      return (
                        <Pressable
                          key={choice}
                          accessibilityRole="radio"
                          accessibilityState={{ selected: chosen }}
                          onPress={() => setSelection(choice)}
                          style={[
                            styles.choice,
                            { backgroundColor: pass ? C.greenBg : C.redBg },
                            chosen ? {
                              backgroundColor: pass ? C.greenSelected : C.redSelected,
                              borderWidth: 1.5,
                              borderColor: pass ? C.green : C.red,
                            } : undefined,
                          ]}
                        >
                          <Text style={[styles.choiceText, { color: pass ? C.green : C.red }]}>{choice}</Text>
                        </Pressable>
                      );
                    })}
                  </View>
                  <Text style={styles.smallNote}>
                    {selection ? `${selection} 선택 완료 · 아래 제출 버튼으로 최종 확정 · Mock` : '판정 미선택 · 선택 후 제출 활성화 · Mock'}
                  </Text>
                </Card>
                <ActionButton
                  label={selection ? `${selection} 최종 판정 제출 · Mock` : 'PASS/FAIL 선택 후 제출'}
                  disabled={!selection || submitting}
                  onPress={submitJudgement}
                />
              </>
            )}

            {isReview && inspection.finalJudgement && (
              <Card title="최종 판정 완료 · Mock">
                <Field label="작업자 판정" value={inspection.finalJudgement} highlight={inspection.finalJudgement === 'PASS' ? 'success' : 'danger'} />
                <Field label="처리 상태" value="REVIEW_DONE" />
                <Field label="확인 시각" value={inspection.confirmedAt ?? '미제공'} />
                <Text style={styles.smallNote}>AI 원본 예측은 변경되지 않았습니다. 중복 판정은 제한됩니다.</Text>
              </Card>
            )}

            {isReview && role === 'ADMIN' && (
              <View style={styles.infoNote}>
                <Text style={styles.infoNoteText}>
                  관리자 조회 전용 · PASS/FAIL 최종 판정은 WORKER만 제출 가능
                </Text>
                <Text style={styles.infoNoteText}>
                  모델: {inspection.modelVersion ?? '미제공'} / 정책: {inspection.policyVersion ?? '검증된 정책 없음 (Mock)'}
                </Text>
              </View>
            )}

            {inspection.retryOf && (
              <Card title="검사 이력 연결">
                <Text style={styles.note}>이 검사는 {inspection.retryOf}의 재검사로 생성되었습니다.</Text>
                <Pressable onPress={() => navigateTo(inspection.retryOf!)} accessibilityRole="link">
                  <Text style={styles.textLink}>이전 FAILED 검사 {inspection.retryOf} 보기 →</Text>
                </Pressable>
              </Card>
            )}

            <Text style={styles.disclaimer}>시연용 Mock · 실제 서버/API 및 AI 모델과 미연동</Text>
          </>
        )}
      </ScrollView>
      <BottomNav role={role} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.background },
  heading: { paddingHorizontal: 20, paddingTop: 9, paddingBottom: 22 },
  pageTitle: { fontSize: 23, fontWeight: '700', color: C.ink, lineHeight: 34 },
  pageSubtitle: { color: C.muted, fontSize: 11, marginTop: 1, lineHeight: 18 },
  scroller: { flex: 1 },
  body: { paddingHorizontal: 20, paddingBottom: 22, gap: 5 },
  card: { borderWidth: 1, borderColor: C.border, borderRadius: 14, padding: 13, backgroundColor: C.white, gap: 6 },
  cardTitle: { fontSize: 13, fontWeight: '700', color: C.ink, lineHeight: 21 },
  field: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, paddingVertical: 1 },
  fieldLabel: { flex: 0.43, color: C.muted, fontSize: 11, lineHeight: 18 },
  fieldValue: { flex: 0.57, textAlign: 'right', color: C.ink, fontSize: 11, lineHeight: 18, fontWeight: '500' },
  tag: { alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 100 },
  tagText: { fontSize: 10, fontWeight: '600', lineHeight: 15 },
  compareRow: { flexDirection: 'row', gap: 8 },
  imageColumn: { flex: 1, minWidth: 0 },
  imageCaption: { fontSize: 11, lineHeight: 20, color: C.muted, marginBottom: 2, marginLeft: 3 },
  imageFrame: { height: 75, backgroundColor: C.faint, borderRadius: 8, overflow: 'hidden' },
  image: { width: '100%', height: '100%' },
  gradcamEmpty: { height: 75, backgroundColor: '#EAF1FB', borderRadius: 8, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6 },
  gradcamEmptyText: { fontSize: 9, lineHeight: 13, color: '#516889', textAlign: 'center' },
  smallNote: { fontSize: 10, lineHeight: 16, color: C.muted },
  policyNote: { fontSize: 10, fontWeight: '600', lineHeight: 17, color: '#4D6182' },
  choiceRow: { flexDirection: 'row', gap: 9 },
  choice: { flex: 1, alignItems: 'center', justifyContent: 'center', borderRadius: 10, minHeight: 40 },
  choiceText: { fontSize: 13, fontWeight: '700' },
  actionButton: { minHeight: 44, borderRadius: 12, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 12 },
  primaryAction: { backgroundColor: C.blue },
  secondaryAction: { backgroundColor: C.white, borderColor: C.border, borderWidth: 1 },
  disabledAction: { backgroundColor: C.disabled },
  actionLabel: { fontSize: 13, fontWeight: '700', textAlign: 'center' },
  note: { color: C.muted, fontSize: 12, lineHeight: 19 },
  failureHeading: { fontSize: 15, lineHeight: 23, fontWeight: '700', color: C.ink },
  infoNote: { backgroundColor: '#EBF1FF', padding: 9, borderRadius: 10, gap: 4 },
  infoNoteText: { fontSize: 10, lineHeight: 16, color: C.blue },
  textLink: { color: C.blue, fontSize: 12, fontWeight: '700', marginTop: 3 },
  disclaimer: { textAlign: 'center', fontSize: 10, color: C.muted, paddingVertical: 5 },
  bottomNav: { height: 58, backgroundColor: C.white, borderWidth: 1, borderColor: C.border, borderRadius: 15, marginHorizontal: 20, marginBottom: 6, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-evenly' },
  navItem: { flex: 1, height: 46, alignItems: 'center', justifyContent: 'center', gap: 1 },
  navIcon: { fontSize: 16, fontWeight: '700', color: C.muted, lineHeight: 24 },
  navText: { fontSize: 11, fontWeight: '500', color: C.muted, lineHeight: 17 },
});
