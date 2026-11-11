import React, { useCallback, useRef, useState } from 'react';
import { Stack, router, useFocusEffect } from 'expo-router';
import {
  ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { authV4 } from '../api/backendV4/authRuntime';
import { ApiV4RequestError } from '../api/backendV4/httpCore';
import {
  createAdminPolicyServiceV4, parsePolicyPercentInputV4, percentageTextV4, rootPolicyForV4,
} from '../api/backendV4/adminPolicyServiceV4';
import type { AdminPolicyV4 } from '../api/backendV4/adminPolicyServiceV4';

const service = createAdminPolicyServiceV4(authV4);
type WriteAction = 'save' | 'activate';

const C = {
  bg: '#F5F7FB', white: '#FFFFFF', ink: '#111827', muted: '#64748B',
  blue: '#2054D8', pale: '#EBF1FF', border: '#E4E7EC',
  green: '#067647', greenPale: '#EAFBF2', red: '#B42318', redPale: '#FFF0ED',
};

function Row({ label, value }: {label: string; value: string}) {
  return <View style={s.row}><Text style={s.label}>{label}</Text><Text style={s.value}>{value}</Text></View>;
}
function Card({ title, children }: {title: string; children: React.ReactNode}) {
  return <View style={s.card}><Text style={s.cardTitle}>{title}</Text>{children}</View>;
}
function Button({ title, onPress, disabled, secondary }: {
  title: string; onPress: () => void; disabled?: boolean; secondary?: boolean;
}) {
  return (
    <Pressable accessibilityRole="button" disabled={!!disabled} onPress={onPress}
      style={[s.button, secondary ? s.secondary : s.primary, disabled && s.disabled]}>
      <Text style={[s.buttonText, secondary ? s.secondaryText : s.primaryText]}>{title}</Text>
    </Pressable>
  );
}

function errorText(error: unknown): string {
  if (error instanceof ApiV4RequestError) {
    const hint: Record<string, string> = {
      ACCESS_DENIED: 'ADMIN 계정 권한을 확인해 주세요.',
      POLICY_THRESHOLD_OUT_OF_RANGE: '서버 검증 범위를 벗어났습니다. 정책 목록을 다시 확인해 주세요.',
      POLICY_NOT_READY: '활성 모델 또는 보정기 호환성·ready 상태를 확인해 주세요.',
      POLICY_NOT_FOUND: '정책이 변경되거나 삭제됐습니다. 목록을 다시 조회해 주세요.',
      POLICY_VERSION_DUPLICATE: '동시에 다른 버전이 생성됐을 수 있습니다. 목록을 확인해 주세요.',
      NETWORK_ERROR: '연결 불확실: 새 요청 전에 정책 목록에서 생성·적용 여부를 확인해 주세요.',
    };
    return `${hint[error.code] ?? '서버 정책 요청 실패'}\n${error.message} (HTTP ${error.httpStatus}, ${error.code})${error.traceId ? `\ntraceId: ${error.traceId}` : ''}`;
  }
  return error instanceof Error ? error.message : '정책 요청에 실패했습니다.';
}

export default function PolicyLiveScreen() {
  const [policies, setPolicies] = useState<AdminPolicyV4[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [access, setAccess] = useState<'checking' | 'admin' | 'denied'>('checking');
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [percentInput, setPercentInput] = useState('1.00');
  const [savedPolicy, setSavedPolicy] = useState<AdminPolicyV4 | null>(null);
  const [writing, setWriting] = useState<WriteAction | null>(null);
  const refreshSerial = useRef(0);
  const writeLock = useRef(false);
  const editedInput = useRef(false);

  const load = useCallback(async (initial = false): Promise<void> => {
    const serial = ++refreshSerial.current;
    if (initial) setLoading(true);
    else setRefreshing(true);
    setError(null);
    try {
      const session = await authV4.restore();
      if (refreshSerial.current !== serial) return;
      if (!session.signedIn || session.role !== 'ADMIN') {
        setAccess('denied');
        setPolicies([]);
        throw new Error('실제 서버 ADMIN 계정으로 로그인해야 정책을 조회·변경할 수 있습니다.');
      }
      setAccess('admin');
      const result = await service.list();
      if (refreshSerial.current !== serial) return;
      setPolicies(result);
      if (!editedInput.current) {
        const active = result.find((item) => item.active);
        // 최초 입력값만 서버 기준에 따라 채우며, 사용자가 편집 중이면 덮어쓰지 않습니다.
        if (active?.passThreshold != null) {
          const suggested = active.validatedMin != null &&
            active.validatedMin <= 0.01 && (active.validatedMax ?? 0) >= 0.01
              ? '1.00' : (active.passThreshold * 100).toFixed(2);
          setPercentInput(suggested);
        }
      }
    } catch (cause) {
      if (refreshSerial.current === serial) setError(errorText(cause));
    } finally {
      if (refreshSerial.current === serial) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useFocusEffect(useCallback(() => {
    void load(true);
    return () => { refreshSerial.current += 1; };
  }, [load]));

  const active = policies.find((item) => item.active) ?? null;
  const root = active ? rootPolicyForV4(active, policies) : null;
  const currentSaved = savedPolicy ? (policies.find((p) => p.policyId === savedPolicy.policyId) ?? savedPolicy) : null;
  const activeHasBounds = active?.ready === true &&
    active.validatedMin != null && active.validatedMax != null;
  let validInput = false;
  let validationText = '활성 정책과 서버 검증 범위를 확인한 후 조정할 수 있습니다.';
  if (active && activeHasBounds) {
    try {
      const candidate = parsePolicyPercentInputV4(percentInput, active);
      const existing = policies.find((p) =>
        p.modelVersion === active.modelVersion &&
        p.calibratorVersion === active.calibratorVersion &&
        p.ready && p.passThreshold != null &&
        Math.abs(p.passThreshold - candidate) < 0.0000005
      );
      if (existing) {
        validationText = existing.active
          ? '현재 적용 중인 기준치입니다. 다른 값을 입력해 주세요.'
          : `이미 ${existing.policyVersion} 정책이 같은 기준치로 저장돼 있습니다. 아래 정책 목록에서 기존 버전을 적용해 주세요.`;
      } else {
        validInput = true;
        validationText = '검증 범위 안의 값입니다. 저장 시 새 비활성 정책 버전이 생성됩니다.';
      }
    } catch (cause) {
      validationText = errorText(cause);
    }
  }
  const canWrite = access === 'admin' && !loading && !refreshing && writing === null;

  /** 다른 관리자의 동시 변경을 확인해 이전 화면 상태로 POST하지 않습니다. */
  const assertLatest = async (expectedActive: AdminPolicyV4 | null): Promise<AdminPolicyV4[]> => {
    const latest = await service.list();
    const current = latest.find((p) => p.active) ?? null;
    if ((expectedActive?.policyId ?? null) !== (current?.policyId ?? null)) {
      setPolicies(latest);
      throw new Error('다른 관리자가 활성 정책을 변경했습니다. 최신 목록을 확인한 뒤 다시 선택해 주세요.');
    }
    return latest;
  };

  const runWrite = async (action: WriteAction, operation: () => Promise<void>) => {
    if (writeLock.current) return;
    writeLock.current = true;
    setWriting(action);
    setActionError(null);
    setActionNotice(null);
    try {
      await operation();
    } catch (cause) {
      setActionError(errorText(cause) + '\n서버 상태가 불확실하면 POST를 반복하지 말고 목록을 먼저 새로고침하세요.');
    } finally {
      writeLock.current = false;
      setWriting(null);
    }
  };

  const confirmSave = () => {
    if (!active || !canWrite || !validInput) return;
    const base = active;
    const input = percentInput;
    const value = parsePolicyPercentInputV4(input, base);
    Alert.alert('실서버 새 정책 버전 저장',
      `${base.policyVersion}의 기준치를 ${percentageTextV4(value)}로 조정해 새 비활성 버전을 생성할까요?\n\n원래 적용 중인 정책은 그대로 유지됩니다.`,
      [
        { text: '취소', style: 'cancel' },
        { text: '실제 서버에 저장', onPress: () => {
          void runWrite('save', async () => {
            const latest = await assertLatest(base);
            const current = latest.find((p) => p.policyId === base.policyId);
            if (!current?.active) throw new Error('원래 정책이 더 이상 활성 상태가 아닙니다.');
            const matching = latest.find((p) =>
              p.modelVersion === current.modelVersion &&
              p.calibratorVersion === current.calibratorVersion &&
              p.ready && p.passThreshold != null &&
              Math.abs(p.passThreshold - value) < 0.0000005
            );
            if (matching) {
              setPolicies(latest);
              throw new Error(`동일 기준치의 ${matching.policyVersion} 정책이 이미 존재합니다. 기존 버전을 사용해 주세요.`);
            }
            const result = await service.saveNewVersion(current, input);
            setSavedPolicy(result);
            setActionNotice(`새 정책 ${result.policyVersion} 저장 완료. 아직 적용되지 않았습니다.\n다음 단계에서 새 버전 적용을 눌러야 합니다.`);
            await load(false);
          });
        } },
      ],
    );
  };

  const confirmActivate = (target: AdminPolicyV4) => {
    if (!canWrite || target.active || !target.ready) return;
    const expectedActive = active;
    Alert.alert(
      target.policyId === root?.policyId ? '실서버 원래 정책 복귀' : '실서버 정책 적용',
      `${target.policyVersion} (${percentageTextV4(target.passThreshold)})을(를) 적용할까요?\n\n실제로 서버의 활성 정책이 변경되고 같은 모델의 다른 정책은 중지됩니다. 과거 검사 판정은 바뀌지 않습니다.`,
      [
        { text: '취소', style: 'cancel' },
        { text: '실제 서버에 적용', onPress: () => {
          void runWrite('activate', async () => {
            const latest = await assertLatest(expectedActive);
            const current = latest.find((p) => p.policyId === target.policyId);
            if (!current || !current.ready || current.partCode !== 'COWL_COVER') {
              throw new Error('대상 정책의 준비 상태가 달라졌습니다. 목록을 확인해 주세요.');
            }
            if (expectedActive && current.modelVersion !== expectedActive.modelVersion) {
              throw new Error('현재 활성 정책과 모델이 다른 버전은 이 화면에서 적용할 수 없습니다.');
            }
            const result = await service.activate(current);
            setActionNotice(`${result.policyVersion} 정책 적용 응답을 받았습니다. 아래 서버 목록에서 활성 상태를 확인해 주세요.`);
            await load(false);
          });
        } },
      ],
    );
  };

  return (
    <SafeAreaView style={s.screen} edges={['top', 'bottom']}>
      <Stack.Screen options={{headerShown: false}} />
      <View style={s.header}>
        <Pressable accessibilityRole="button" onPress={() => router.back()}>
          <Text style={s.back}>‹ 설정으로 돌아가기</Text>
        </Pressable>
        <Text style={s.title}>자동 통과 기준 · 실서버</Text>
        <Text style={s.subtitle}>ADMIN 전용 · COWL_COVER · API v4 6.9</Text>
      </View>
      <ScrollView style={s.scroll} contentContainerStyle={s.body} keyboardShouldPersistTaps="handled">
        <View style={s.notice}>
          <Text style={s.noticeText}>
            이 화면은 실제 백엔드 정책을 변경합니다. 시연 목표는 1.63% → 1.00%로 새 버전을 저장·적용한 후 원래 1.63% 정책으로 복귀하는 것입니다. 수치는 서버에서 조회한 값을 우선합니다.
          </Text>
        </View>
        {(loading || refreshing) && (
          <View style={s.status}>
            <ActivityIndicator />
            <Text style={s.muted}>{loading ? '실서버 정책과 로그인 권한 확인 중…' : '최신 정책 다시 조회 중…'}</Text>
          </View>
        )}
        {error && (
          <View style={s.errorCard}>
            <Text style={s.errorText}>{error}</Text>
            <Button title="정책 다시 조회" secondary onPress={() => { void load(false); }} disabled={!!writing} />
          </View>
        )}
        {access === 'denied' && (
          <Card title="접근 권한 없음">
            <Text style={s.muted}>화면의 role 파라미터와 관계없이 실제 로그인 세션의 ADMIN 권한이 필요합니다.</Text>
          </Card>
        )}
        {access === 'admin' && !loading && (
          <>
            <Card title="1. 현재 적용 중인 정책">
              {!active ? (
                <Text style={s.errorText}>현재 활성 COWL_COVER 정책이 없습니다. 서버에서 적용 상태를 확인해 주세요.</Text>
              ) : (
                <>
                  <Row label="정책 버전" value={active.policyVersion} />
                  <Row label="AI 모델" value={active.modelVersion} />
                  <Row label="보정기" value={active.calibratorVersion ?? '미제공'} />
                  <Row label="활성 기준치" value={percentageTextV4(active.passThreshold)} />
                  <Row label="검증 범위" value={`${percentageTextV4(active.validatedMin)} ~ ${percentageTextV4(active.validatedMax)}`} />
                  <Row label="ready / active" value={`${active.ready ? '준비됨' : '미준비'} / 적용 중`} />
                </>
              )}
              <Button title="실서버 정책 새로고침" secondary onPress={() => { void load(false); }}
                disabled={!canWrite} />
            </Card>

            <Card title="2. 기준치 조정 · 새 버전 저장">
              <Text style={s.muted}>
                백분율(%)을 입력하세요. 예: 1.00 = API 요청 passThreshold 0.0100. 검증 범위 밖이면 저장할 수 없습니다.
              </Text>
              <Text style={s.label}>새 기준치 입력 (%)</Text>
              <TextInput style={s.input} value={percentInput}
                onChangeText={(v) => { editedInput.current = true; setPercentInput(v); }}
                placeholder="예: 1.00" keyboardType="decimal-pad" maxLength={9}
                editable={canWrite && activeHasBounds} selectTextOnFocus
                accessibilityLabel="새 자동 통과 기준 백분율" />
              <Text style={[s.hint, !validInput && s.errorText]}>{validationText}</Text>
              <Button title={writing === 'save' ? '새 버전 저장 중…' : '새 정책 버전 저장 · 실서버'}
                onPress={confirmSave} disabled={!canWrite || !validInput} />
              <Text style={s.muted}>저장 직후 새 정책은 비활성이며, 이전 활성 정책은 그대로 유지됩니다.</Text>
            </Card>

            {currentSaved && (
              <Card title="3. 마지막으로 저장한 새 버전">
                <Row label="정책 버전" value={currentSaved.policyVersion} />
                <Row label="새 기준치" value={percentageTextV4(currentSaved.passThreshold)} />
                <Row label="현재 상태" value={currentSaved.active ? '적용 중' : '비활성 (별도 적용 필요)'} />
                {!currentSaved.active && (
                  <Button title="새 버전 적용 · 실서버"
                    onPress={() => confirmActivate(currentSaved)}
                    disabled={!canWrite || !currentSaved.ready} />
                )}
              </Card>
            )}

            <Card title="4. 정책 버전 목록 · 복귀">
              <Text style={s.muted}>
                서버 기준 최신 생성순입니다. 현재 적용 정책 외에 준비된 버전을 선택해 원래 기준으로 복귀할 수 있습니다.
              </Text>
              {policies.length === 0 && <Text style={s.muted}>조회된 COWL_COVER 정책이 없습니다.</Text>}
              {policies.map((policy) => {
                const isOriginal = root?.policyId === policy.policyId ||
                  (root === null && policy.basedOnPolicyId === null);
                const canActivate = policy.ready && !policy.active &&
                  (!active || policy.modelVersion === active.modelVersion);
                return (
                  <View key={policy.policyId} style={s.policyItem}>
                    <Text style={s.policyName}>
                      {policy.policyVersion}{policy.active ? ' · 적용 중' : ''}
                    </Text>
                    <Row label="기준치" value={percentageTextV4(policy.passThreshold)} />
                    <Row label="상태" value={`${policy.ready ? 'ready' : '미준비'} · ${policy.active ? 'active' : '비활성'}`} />
                    {isOriginal && <Text style={s.muted}>원본 정책 버전</Text>}
                    {canActivate && (
                      <Button secondary
                        title={isOriginal ? '원래 정책 복귀 · 실서버' : '이 정책 적용 · 실서버'}
                        onPress={() => confirmActivate(policy)} disabled={!canWrite} />
                    )}
                  </View>
                );
              })}
            </Card>
            {writing && (
              <View style={s.status}>
                <ActivityIndicator />
                <Text style={s.muted}>실제 서버에 정책 요청 중입니다. 두 번 제출하지 마세요.</Text>
              </View>
            )}
            {actionNotice && <View style={s.successCard}><Text style={s.successText}>{actionNotice}</Text></View>}
            {actionError && <View style={s.errorCard}><Text style={s.errorText}>{actionError}</Text></View>}
            <Text style={s.footer}>
              동일한 사진을 다시 접수해야 정책 변경 전후의 AUTO_PASS / REVIEW 차이를 관찰할 수 있습니다. 기존 검사 기록은 소급 변경되지 않습니다.
            </Text>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  header: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 14, gap: 6 },
  back: { color: C.blue, fontSize: 13, fontWeight: '600' },
  title: { color: C.ink, fontSize: 23, lineHeight: 32, fontWeight: '700' },
  subtitle: { color: C.muted, fontSize: 11, lineHeight: 17 },
  scroll: { flex: 1 },
  body: { paddingHorizontal: 20, paddingBottom: 35, gap: 12 },
  card: { padding: 15, backgroundColor: C.white, borderRadius: 14, borderWidth: 1, borderColor: C.border, gap: 10 },
  cardTitle: { color: C.ink, fontWeight: '700', fontSize: 16 },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  label: { color: C.muted, fontSize: 12, lineHeight: 18, flex: 0.46 },
  value: { color: C.ink, fontSize: 12, lineHeight: 18, textAlign: 'right', flex: 0.54, fontWeight: '600' },
  muted: { color: C.muted, fontSize: 12, lineHeight: 19 },
  input: { borderWidth: 1, borderColor: '#D5DCE8', borderRadius: 10, minHeight: 46,
    backgroundColor: '#F8FAFC', color: C.ink, paddingHorizontal: 14, fontSize: 16 },
  hint: { fontSize: 12, lineHeight: 19, color: C.green },
  button: { borderRadius: 10, minHeight: 44, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 10 },
  primary: { backgroundColor: C.blue },
  secondary: { backgroundColor: C.white, borderWidth: 1, borderColor: C.blue },
  buttonText: { fontWeight: '700', fontSize: 13, textAlign: 'center' },
  primaryText: { color: C.white },
  secondaryText: { color: C.blue },
  disabled: { opacity: 0.45 },
  notice: { backgroundColor: C.pale, padding: 13, borderRadius: 12 },
  noticeText: { color: C.blue, fontSize: 12, lineHeight: 19 },
  status: { flexDirection: 'row', alignItems: 'center', gap: 9, padding: 11 },
  policyItem: { borderRadius: 10, backgroundColor: '#F8FAFC', padding: 12, borderWidth: 1,
    borderColor: C.border, gap: 7 },
  policyName: { color: C.ink, fontSize: 13, fontWeight: '700' },
  errorCard: { borderRadius: 12, padding: 12, backgroundColor: C.redPale, gap: 9 },
  errorText: { color: C.red, fontSize: 12, lineHeight: 19 },
  successCard: { borderRadius: 12, padding: 12, backgroundColor: C.greenPale },
  successText: { color: C.green, fontSize: 12, lineHeight: 20 },
  footer: { color: C.muted, fontSize: 11, lineHeight: 18, paddingHorizontal: 3 },
});
