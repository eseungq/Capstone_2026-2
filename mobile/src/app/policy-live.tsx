import Pressable from '../components/TouchPressable';
import React, { useCallback, useRef, useState } from 'react';
import { Stack, router, useFocusEffect } from 'expo-router';
import {
  ActivityIndicator, Alert, Keyboard, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { authV4 } from '../api/backendV4/authRuntime';
import { ApiV4RequestError } from '../api/backendV4/httpCore';
import {
  createAdminPolicyServiceV4, createPolicyVisitV4, PolicyAdminContractErrorV4, findEquivalentPolicyVersionV4,
  parsePolicyPercentInputV4, percentageTextV4, rootPolicyForV4,
} from '../api/backendV4/adminPolicyServiceV4';
import type { AdminPolicyV4 } from '../api/backendV4/adminPolicyServiceV4';
import {createAutoFailPolicyServiceV4} from '../api/backendV4/autoFailPolicyServiceV4';
import {ensureAutoFailToggleV4,makeAutoFailThresholdEditV4,autoFailRangeLabelV4} from '../api/backendV4/autoFailPolicyCoreV4';

function openPolicyVisit() {
  const visit = createPolicyVisitV4(authV4);
  return {
    ...visit,
    service: createAdminPolicyServiceV4(visit.transport),
    autoFailService: createAutoFailPolicyServiceV4(visit.transport),
  };
}
type PolicyVisit = ReturnType<typeof openPolicyVisit>;
type WriteAction = 'save' | 'activate' | 'fail-threshold' | 'auto-fail';
type PolicySection = 'pass' | 'fail' | 'versions';
const POLICY_SECTIONS: {value: PolicySection; label: string}[] = [
  {value: 'pass', label: '자동 통과'},
  {value: 'fail', label: '자동 불량'},
  {value: 'versions', label: '버전 관리'},
];

const C = {
  bg: '#F5F7FB', white: '#FFFFFF', ink: '#111827', muted: '#475569',
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
      ACCESS_DENIED: '관리자 계정으로 로그인해 주세요.',
      POLICY_THRESHOLD_OUT_OF_RANGE: '서버 검증 범위를 벗어났습니다. 정책 목록을 다시 확인해 주세요.',
      POLICY_NOT_READY: '이 정책은 아직 적용할 수 없습니다. 모델과 보정기 준비 상태를 확인해 주세요.',
      POLICY_NOT_FOUND: '정책이 변경되거나 삭제됐습니다. 목록을 다시 조회해 주세요.',
      POLICY_VERSION_DUPLICATE: '동시에 다른 버전이 생성됐을 수 있습니다. 목록을 확인해 주세요.',
      NETWORK_ERROR: '연결 불확실: 새 요청 전에 정책 목록에서 생성·적용 여부를 확인해 주세요.',
      REQUEST_TIMEOUT: '서버 응답이 지연됩니다. 새 요청 전에 정책 목록에서 생성·적용 여부를 확인해 주세요.',
    };
    if (error.httpStatus === 401) return '로그인이 만료됐습니다. 다시 로그인해 주세요.';
    if (error.httpStatus === 403) return '정책을 관리할 권한이 없습니다.';
    return hint[error.code] ?? '정책 요청을 처리하지 못했습니다. 현재 정책을 다시 확인해 주세요.';
  }
  if (error instanceof PolicyAdminContractErrorV4) return '정책 정보를 확인할 수 없습니다. 목록을 새로고침해 주세요.';
  return error instanceof Error ? error.message : '정책 요청에 실패했습니다.';
}

function activationDetails(policy: AdminPolicyV4): string {
  const autoFail = policy.autoFailEnabled == null ? '정보 없음' : policy.autoFailEnabled ? '켜짐' : '꺼짐';
  return [
    policy.policyVersion,
    `통과 기준 ${percentageTextV4(policy.passThreshold, 4)} · 허용 범위 ${percentageTextV4(policy.validatedMin, 4)} ~ ${percentageTextV4(policy.validatedMax, 4)}`,
    `자동 불량 ${autoFail} · 불량 기준 ${percentageTextV4(policy.failThreshold, 4)}`,
    `불량 기준 범위 ${autoFailRangeLabelV4(policy.failValidatedMin, policy.failValidatedMax)}`,
  ].join('\n');
}

export default function PolicyLiveScreen() {
  const [section, setSection] = useState<PolicySection>('pass');
  const [showPolicyDetails, setShowPolicyDetails] = useState(false);
  const scrollRef = useRef<React.ComponentRef<typeof ScrollView>>(null);
  const selectSection = (next: PolicySection) => {
    Keyboard.dismiss();
    setSection(next);
    scrollRef.current?.scrollTo({y: 0, animated: false});
  };
  const [policies, setPolicies] = useState<AdminPolicyV4[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [access, setAccess] = useState<'checking' | 'admin' | 'denied'>('checking');
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [percentInput, setPercentInput] = useState('');
  const [savedPolicy, setSavedPolicy] = useState<AdminPolicyV4 | null>(null);
  const [failPercent, setFailPercent] = useState('');
  const [failMinPercent, setFailMinPercent] = useState('');
  const [failMaxPercent, setFailMaxPercent] = useState('');
  const editedFailInput = useRef(false);
  const [writing, setWriting] = useState<WriteAction | null>(null);
  const refreshSerial = useRef(0);
  const focusedVisit = useRef<PolicyVisit | null>(null);
  const writeLock = useRef<PolicyVisit | null>(null);
  const editedInput = useRef(false);

  const load = useCallback(async (initial = false): Promise<void> => {
    const visit = focusedVisit.current;
    if (!visit?.isCurrent()) return;
    const serial = ++refreshSerial.current;
    const currentRead = () => refreshSerial.current === serial && visit.isCurrent();
    if (initial) setLoading(true);
    else setRefreshing(true);
    setError(null);
    try {
      const session = await visit.transport.restore();
      if (!currentRead()) return;
      if (!session.signedIn || session.role !== 'ADMIN') {
        setAccess('denied');
        setPolicies([]);
        throw new Error('정책을 조회하거나 변경하려면 관리자 계정으로 로그인해 주세요.');
      }
      setAccess('admin');
      const result = await visit.service.list();
      if (!currentRead()) return;
      setPolicies(result);
      const serverActive = result.find((p) => p.active);
      if (!editedFailInput.current && serverActive) {
        setFailPercent(serverActive.failThreshold == null ? '' : (serverActive.failThreshold * 100).toFixed(4));
        setFailMinPercent(serverActive.failValidatedMin == null ? '' : (serverActive.failValidatedMin * 100).toFixed(4));
        setFailMaxPercent(serverActive.failValidatedMax == null ? '' : (serverActive.failValidatedMax * 100).toFixed(4));
      }
      if (!editedInput.current && serverActive?.passThreshold != null) {
        setPercentInput(String(Number((serverActive.passThreshold * 100).toFixed(4))));
      }
    } catch (cause) {
      if (currentRead()) setError(errorText(cause));
    } finally {
      if (currentRead()) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useFocusEffect(useCallback(() => {
    const visit = openPolicyVisit();
    focusedVisit.current = visit;
    setWriting(null);
    setActionError(null);
    setActionNotice(null);
    void load(true);
    return () => {
      visit.close();
      focusedVisit.current = null;
    };
  }, [load]));

  const active = policies.find((item) => item.active) ?? null;
  const root = active ? rootPolicyForV4(active, policies) : null;
  const currentSaved = savedPolicy ? (policies.find((p) => p.policyId === savedPolicy.policyId) ?? savedPolicy) : null;
  const activeHasBounds = active?.ready === true &&
    active.validatedMin != null && active.validatedMax != null;
  let validInput = false;
  let invalidPassInput = false;
  let validationText = '활성 정책과 서버 검증 범위를 확인한 후 조정할 수 있습니다.';
  if (active && activeHasBounds) {
    try {
      const candidate = parsePolicyPercentInputV4(percentInput, active);
      const existing = findEquivalentPolicyVersionV4(policies, active, candidate);
      if (existing) {
        validationText = existing.active
          ? '현재 적용 중인 기준치입니다. 다른 값을 입력해 주세요.'
          : `같은 설정의 ${existing.policyVersion} 정책이 이미 저장돼 있습니다. 버전 관리에서 기존 버전을 적용해 주세요.`;
      } else {
        validInput = true;
        validationText = '검증 범위 안의 값입니다. 저장 시 새 비활성 정책 버전이 생성됩니다.';
      }
    } catch (cause) {
      validationText = errorText(cause);
      invalidPassInput = true;
    }
  }
  // 목록 재조회가 실패했다면 오래된 정책 정보로 POST하지 않습니다.
  const canWrite = access === 'admin' && !loading && !refreshing && writing === null && error === null;

  let failEditValid = false;
  let invalidFailInput = false;
  let failEditHint = '현재 정책의 불량 기준과 허용 범위를 확인해 주세요.';
  if (active && active.autoFailEnabled !== null) {
    try {
      const value=makeAutoFailThresholdEditV4(active,failPercent,failMinPercent,failMaxPercent);
      if (active.failThreshold===value.failThreshold &&
        active.failValidatedMin===value.failValidatedMin &&
        active.failValidatedMax===value.failValidatedMax) {
        failEditHint='현재 불량 기준과 동일합니다. 불필요한 버전을 생성하지 않습니다.';
      } else {
        failEditValid=true;
        failEditHint=value.failValidatedMin===value.failValidatedMax
          ? '검증 범위 없음(고정값) · 시험값 고정용입니다. 저장 시 비활성 버전이 생성됩니다.'
          : '불량 기준이 입력한 허용 범위 안에 있습니다. 저장 시 비활성 버전이 생성됩니다.';
      }
    } catch(cause) {failEditHint=errorText(cause);invalidFailInput=true;}
  }
  const evidencePresent = !!active?.metrics && !!active.metrics.autoFail &&
    typeof active.metrics.autoFail === 'object';
  const canToggleOn = active?.ready===true && active.autoFailEnabled===false && active.failThreshold!=null;
  const canToggleOff = active?.autoFailEnabled===true;

  /** 다른 관리자의 동시 변경을 확인해 이전 화면 상태로 POST하지 않습니다. */
  const assertLatest = async (visit: PolicyVisit, expectedActive: AdminPolicyV4 | null): Promise<AdminPolicyV4[]> => {
    const latest = await visit.service.list();
    visit.assertCurrent();
    const current = latest.find((p) => p.active) ?? null;
    if ((expectedActive?.policyId ?? null) !== (current?.policyId ?? null)) {
      setPolicies(latest);
      throw new Error('다른 관리자가 활성 정책을 변경했습니다. 최신 목록을 확인한 뒤 다시 선택해 주세요.');
    }
    return latest;
  };

  // Capture the visit when opening the native dialog. A delayed tap belongs to that visit.
  const confirmedWrite = (action: WriteAction, operation: (visit: PolicyVisit) => Promise<void>) => {
    const visit = focusedVisit.current;
    return async () => {
      if (!visit?.isCurrent() || writeLock.current === visit) return;
      writeLock.current = visit;
      setWriting(action);
      setActionError(null);
      setActionNotice(null);
      try {
        await operation(visit);
        // 성공 응답 후에는 저장된 버전을 보여주기만 합니다. 적용은 별도 확인을 거칩니다.
        if (visit.isCurrent()) selectSection('versions');
      } catch (cause) {
        if (visit.isCurrent()) {
          setActionError(errorText(cause) + '\n다시 시도하기 전에 목록을 새로고침해 변경 사항을 확인해 주세요.');
          scrollRef.current?.scrollTo({y: 0, animated: false});
        }
      } finally {
        if (writeLock.current === visit) writeLock.current = null;
        if (visit.isCurrent()) setWriting(null);
      }
    };
  };

  const confirmSave = () => {
    if (!active || !canWrite || !validInput) return;
    const base = active;
    const input = percentInput;
    const value = parsePolicyPercentInputV4(input, base);
    Alert.alert('새 정책 버전 저장',
      `${base.policyVersion}의 기준치를 ${percentageTextV4(value, 4)}로 조정해 새 비활성 버전을 생성할까요?\n\n원래 적용 중인 정책은 그대로 유지됩니다.`,
      [
        { text: '취소', style: 'cancel' },
        { text: '저장', onPress: confirmedWrite('save', async (visit) => {
          const latest = await assertLatest(visit, base);
          visit.assertCurrent();
          const current = latest.find((p) => p.policyId === base.policyId);
          if (!current?.active) throw new Error('원래 정책이 더 이상 활성 상태가 아닙니다.');
          const matching = findEquivalentPolicyVersionV4(latest, current, value);
          if (matching) {
            setPolicies(latest);
            throw new Error(`같은 설정의 ${matching.policyVersion} 정책이 이미 있습니다. 기존 버전을 사용해 주세요.`);
          }
          const result = await visit.service.saveNewVersion(current, input);
          visit.assertCurrent();
          setSavedPolicy(result);
          setActionNotice(`새 정책 ${result.policyVersion} 저장 완료. 아직 적용되지 않았습니다.\n다음 단계에서 새 버전 적용을 눌러야 합니다.`);
          await load(false);
        }) },
      ],
    );
  };

  const confirmActivate = (target: AdminPolicyV4) => {
    if (!canWrite || target.active || !target.ready) return;
    const expectedActive = active;
    Alert.alert(
      target.policyId === root?.policyId ? '원래 정책으로 복귀' : '정책 적용',
      `현재 적용 중\n${expectedActive ? activationDetails(expectedActive) : '활성 정책 없음'}\n\n적용할 정책\n${activationDetails(target)}\n\n적용 이후 접수하는 검사부터 새 정책을 사용합니다.${target.autoFailEnabled && !target.metrics?.autoFail ? '\n자동 불량 검증 자료가 없습니다. 승인된 시험 범위를 확인해 주세요.' : ''}`,
      [
        { text: '취소', style: 'cancel' },
        { text: '적용', onPress: confirmedWrite('activate', async (visit) => {
          const latest = await assertLatest(visit, expectedActive);
          visit.assertCurrent();
          const current = latest.find((p) => p.policyId === target.policyId);
          if (!current || !current.ready || current.partCode !== 'COWL_COVER') {
            throw new Error('대상 정책의 준비 상태가 달라졌습니다. 목록을 확인해 주세요.');
          }
          if (expectedActive && current.modelVersion !== expectedActive.modelVersion) {
            throw new Error('현재 활성 정책과 모델이 다른 버전은 이 화면에서 적용할 수 없습니다.');
          }
          const result = await visit.service.activate(current);
          visit.assertCurrent();
          setActionNotice(`${result.policyVersion} 정책 적용 응답을 받았습니다. 버전 관리의 서버 목록에서 활성 상태를 확인해 주세요.`);
          await load(false);
        }) },
      ],
    );
  };

  const confirmSaveFail = () => {
    if (!active || !canWrite || !failEditValid) return;
    const base=active;
    const args=[failPercent,failMinPercent,failMaxPercent] as const;
    const expected=makeAutoFailThresholdEditV4(base,...args);
    Alert.alert('자동 불량 기준 새 버전 저장',
      `${base.policyVersion}\n불량 기준 ${percentageTextV4(expected.failThreshold,4)}\n불량 기준 범위: ${autoFailRangeLabelV4(expected.failValidatedMin,expected.failValidatedMax)}\n\n저장해도 자동 불량은 즉시 적용되지 않습니다.`,
      [{text:'취소',style:'cancel'},{text:'새 비활성 버전 저장',onPress:confirmedWrite('fail-threshold', async (visit) => {
        const latest = await assertLatest(visit, base);
        visit.assertCurrent();
        const current = latest.find(p => p.policyId === base.policyId);
        if(!current?.active || current.autoFailEnabled===null)
          throw new Error('적용 중인 정책 또는 자동 불량 기능의 사용 가능 여부가 변경됐습니다.');
        const latestEdit=makeAutoFailThresholdEditV4(current,...args);
        if(latestEdit.failThreshold!==expected.failThreshold ||
          latestEdit.failValidatedMin!==expected.failValidatedMin ||
          latestEdit.failValidatedMax!==expected.failValidatedMax)
          throw new Error('정책 검증 범위가 변경됐습니다. 최신 값을 확인해 주세요.');
        const saved=await visit.autoFailService.saveThreshold(current,...args);
        visit.assertCurrent();
        setSavedPolicy(saved);
        setActionNotice(`${saved.policyVersion} 불량 기준 새 비활성 버전을 저장했습니다. 별도 적용 전까지 현재 정책은 그대로입니다.`);
        await load(false);
      })}]);
  };

  const confirmAutoFailToggle = (enabled:boolean, target?:AdminPolicyV4) => {
    const base=target??active;
    if (!base || !canWrite || !active || base.modelVersion!==active.modelVersion) return;
    const expectedActive=active;
    try {ensureAutoFailToggleV4(base,enabled);}catch(cause){setActionError(errorText(cause));return;}
    const hasEvidence=!!base.metrics?.autoFail && typeof base.metrics.autoFail==='object';
    const warning=enabled&&!hasEvidence?'\n\n검증 자료 없음: 품질 정확도나 미검출률이 검증되었다는 뜻이 아닙니다. 팀 승인 시험 범위에서만 사용하세요.':'';
    Alert.alert(enabled?'자동 불량 켜기 · 새 버전':'자동 불량 끄기 · 새 버전',
      `${base.policyVersion}에서 자동 불량을 ${enabled?'켜는':'끄는'} 새 비활성 버전을 만들까요?\n\n실제 적용은 생성된 버전을 관리자가 별도로 활성화할 때만 변경됩니다.${warning}`,
      [{text:'취소',style:'cancel'},{text:'새 비활성 버전 저장',onPress:confirmedWrite('auto-fail', async (visit) => {
        const latest = await assertLatest(visit, expectedActive);
        visit.assertCurrent();
        const current = latest.find(p => p.policyId === base.policyId);
        if(!current || current.modelVersion!==expectedActive.modelVersion ||
          current.autoFailEnabled!==base.autoFailEnabled || current.failThreshold!==base.failThreshold ||
          current.failValidatedMin!==base.failValidatedMin || current.failValidatedMax!==base.failValidatedMax)
          throw new Error('대상 정책의 자동 불량 상태가 변경됐습니다. 다시 확인해 주세요.');
        ensureAutoFailToggleV4(current,enabled);
        const saved=await visit.autoFailService.saveToggle(current,enabled);
        visit.assertCurrent();
        setSavedPolicy(saved);
        setActionNotice(`${saved.policyVersion} 자동 불량 ${enabled?'켜기':'끄기'} 버전을 비활성 상태로 저장했습니다. 기존 활성 정책은 변경되지 않았습니다.`);
        await load(false);
      })}]);
  };

  return (
    <SafeAreaView style={s.screen} edges={['top', 'bottom']}>
      <Stack.Screen options={{headerShown: false}} />
      <View style={s.header}>
        <Pressable accessibilityRole="button" onPress={() => router.back()} style={s.backTouch}>
          <Text style={s.back}>‹ 뒤로</Text>
        </Pressable>
        <Text style={s.title}>카울커버 자동 판정 정책</Text>
        <Text style={s.subtitle}>관리자 · COWL_COVER</Text>
      </View>
      <KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView ref={scrollRef} style={s.scroll} contentContainerStyle={s.body} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
        <View style={s.notice}>
          <Text style={s.noticeText}>
            저장은 새 비활성 버전 생성입니다. 버전 관리에서 별도로 적용해야 새 검사에 반영됩니다.
          </Text>
        </View>
        {(loading || refreshing) && (
          <View style={s.status}>
            <ActivityIndicator />
            <Text style={s.muted}>{loading ? '정책과 접근 권한 확인 중…' : '최신 정책 다시 조회 중…'}</Text>
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
            <Text style={s.muted}>정책을 관리하려면 관리자 계정으로 로그인해 주세요.</Text>
          </Card>
        )}
        {access === 'admin' && !loading && (
          <>
            <Card title="현재 적용 중인 정책">
              {!active ? (
                <Text style={s.errorText}>현재 적용 중인 카울커버 정책이 없습니다. 서버에서 적용 상태를 확인해 주세요.</Text>
              ) : (
                <>
                  <Row label="정책 버전" value={active.policyVersion} />
                  <View style={s.metrics}>
                    <View style={s.metric}>
                      <Text style={s.metricLabel}>자동 통과 기준</Text>
                      <Text style={s.metricValue}>{percentageTextV4(active.passThreshold, 4)}</Text>
                    </View>
                    <View style={s.metric}>
                      <Text style={s.metricLabel}>자동 불량</Text>
                      <Text style={[s.metricValue, active.autoFailEnabled === true && s.failEnabled]}>
                        {active.autoFailEnabled===null?'미지원':active.autoFailEnabled?'켜짐':'꺼짐'}
                      </Text>
                      {active.autoFailEnabled===true && <Text style={s.muted}>{percentageTextV4(active.failThreshold,4)}</Text>}
                    </View>
                  </View>
                  <Row label="통과 검증 범위" value={`${percentageTextV4(active.validatedMin, 4)} ~ ${percentageTextV4(active.validatedMax, 4)}`} />
                  <Row label="정책 상태" value={`${active.ready ? '준비됨' : '미준비'} / 적용 중`} />
                  <Pressable style={s.detailsToggle} accessibilityRole="button"
                    accessibilityState={{expanded:showPolicyDetails}} onPress={()=>setShowPolicyDetails(v=>!v)}>
                    <Text style={s.secondaryText}>{showPolicyDetails?'모델·보정기 정보 접기':'모델·보정기 정보 보기'}</Text>
                    <Text style={s.secondaryText}>{showPolicyDetails?'−':'+'}</Text>
                  </Pressable>
                  {showPolicyDetails && <>
                    <Row label="AI 모델" value={active.modelVersion} />
                    <Row label="보정기" value={active.calibratorVersion ?? '미제공'} />
                  </>}
                </>
              )}
              <Button title="정책 새로고침" secondary onPress={() => { void load(false); }}
                disabled={!canWrite} />
            </Card>

            <View style={s.sectionTabs}>
              {POLICY_SECTIONS.map(item=>(
                <Pressable key={item.value} testID={'policy-section-' + item.value} style={[s.sectionTab,section===item.value&&s.sectionTabActive,writing!==null&&s.disabled]}
                  accessibilityRole="button" accessibilityState={{selected:section===item.value,disabled:writing!==null}}
                  disabled={writing!==null} onPress={()=>selectSection(item.value)}>
                  <Text style={[s.sectionTabText,section===item.value&&s.sectionTabTextActive]}>{item.label}</Text>
                </Pressable>
              ))}
            </View>

            {writing && (
              <View style={s.status}>
                <ActivityIndicator />
                <Text style={s.muted}>실제 서버에 정책 요청 중입니다. 두 번 제출하지 마세요.</Text>
              </View>
            )}
            {actionNotice && <View style={s.successCard}><Text style={s.successText}>{actionNotice}</Text></View>}
            {actionError && <View style={s.errorCard}><Text style={s.errorText}>{actionError}</Text></View>}

            {section === 'pass' && (
            <Card title="자동 통과 기준 조정">
              <Text style={s.muted}>
                현재 정책의 허용 범위 안에서 백분율(%)을 입력하세요.
              </Text>
              <Text style={s.formLabel}>새 기준치 입력 (%)</Text>
              <TextInput style={s.input} value={percentInput}
                onChangeText={(v) => { editedInput.current = true; setPercentInput(v); }}
                placeholder="예: 1.00" keyboardType="decimal-pad" maxLength={9}
                editable={canWrite && activeHasBounds} selectTextOnFocus
                accessibilityLabel="새 자동 통과 기준 백분율" />
              <Text style={validInput?s.hint:invalidPassInput?s.errorText:s.muted}>{validationText}</Text>
              <Button title={writing === 'save' ? '새 버전 저장 중…' : '새 정책 버전 저장'}
                onPress={confirmSave} disabled={!canWrite || !validInput} />
              <Text style={s.muted}>저장 직후 새 정책은 비활성이며, 이전 활성 정책은 그대로 유지됩니다.</Text>
            </Card>
            )}

            {section === 'fail' && (
            <Card title="자동 불량 정책 · 별도 검증·적용">
              <Text style={s.muted}>
                자동 불량 기본값은 꺼짐입니다. 기준 등록/켜기/끄기는 각각 새 비활성 정책 버전을 만듭니다.
                활성화는 버전 관리에서 별도로 선택해야 하며, 시험 승인 전에는 적용하지 마세요.
              </Text>
              {!active ? <Text style={s.errorText}>활성 정책을 확인한 뒤 사용할 수 있습니다.</Text> : <>
                <Row label="현재 자동 불량" value={active.autoFailEnabled===null?'정보 없음':active.autoFailEnabled?'켜짐':'꺼짐'} />
                <Row label="불량 기준" value={percentageTextV4(active.failThreshold,4)} />
                <Row label="불량 검증 범위" value={autoFailRangeLabelV4(active.failValidatedMin,active.failValidatedMax)} />
                <Row label="AI 검증 근거" value={evidencePresent?'정책 자료 등록됨 (독립 검증 여부 별도)':'검증 자료 없음'} />
                {active.autoFailEnabled===null && (
                  <Text style={s.errorText}>현재 정책에서는 자동 불량 설정을 사용할 수 없습니다.</Text>
                )}
                {active.autoFailEnabled!==null && <>
                  <Text style={s.formLabel}>불량 기준 입력 (%)</Text>
                  <TextInput style={s.input} value={failPercent} placeholder="불량 기준 (%)"
                    onChangeText={x=>{editedFailInput.current=true;setFailPercent(x);}}
                    keyboardType="decimal-pad" maxLength={9} editable={canWrite}
                    accessibilityLabel="자동 불량 기준 백분율" />
                  <Text style={s.muted}>최솟값과 최댓값이 같으면 시험용 고정 기준입니다.</Text>
                  <Text style={s.formLabel}>불량 기준 최솟값 (%)</Text>
                  <TextInput style={s.input} value={failMinPercent} placeholder="최솟값 (%)"
                    onChangeText={x=>{editedFailInput.current=true;setFailMinPercent(x);}}
                    keyboardType="decimal-pad" maxLength={9} editable={canWrite}
                    accessibilityLabel="불량 기준 최솟값" />
                  <Text style={s.formLabel}>불량 기준 최댓값 (%)</Text>
                  <TextInput style={s.input} value={failMaxPercent} placeholder="최댓값 (%)"
                    onChangeText={x=>{editedFailInput.current=true;setFailMaxPercent(x);}}
                    keyboardType="decimal-pad" maxLength={9} editable={canWrite}
                    accessibilityLabel="불량 기준 최댓값" />
                  <Text style={failEditValid?s.hint:invalidFailInput?s.errorText:s.muted}>{failEditHint}</Text>
                  <Button title="불량 기준 새 비활성 버전 저장" onPress={confirmSaveFail}
                    disabled={!canWrite||!failEditValid}/>
                  {!evidencePresent && <Text style={s.errorText}>검증 자료 없음: 팀 승인 시험 범위에서만 사용하세요. 품질 정확도를 보장하지 않습니다.</Text>}
                  <Button title="자동 불량 켜기 버전 저장 · 적용 아님"
                    onPress={()=>confirmAutoFailToggle(true)}
                    disabled={!canWrite||!canToggleOn}/>
                  <Button title="자동 불량 끄기 버전 저장 · 적용 아님" secondary
                    onPress={()=>confirmAutoFailToggle(false)}
                    disabled={!canWrite||!canToggleOff}/>
                  <Text style={s.muted}>
                    불량 기준이 등록된 정책에서 켜기 버전을 저장할 수 있습니다. 새 비활성 기준 버전은 버전 관리에서 바로 켜기 버전을 만들 수 있으며, 적용은 별도입니다.
                  </Text>
                </>}
              </>}
            </Card>
            )}

            {section === 'versions' && (<>
            {currentSaved && (
              <Card title="마지막으로 저장한 새 버전">
                <Row label="정책 버전" value={currentSaved.policyVersion} />
                <Row label="자동 통과 기준" value={percentageTextV4(currentSaved.passThreshold, 4)} />
                <Row label="불량 기준" value={percentageTextV4(currentSaved.failThreshold,4)} />
                <Row label="불량 검증 범위" value={autoFailRangeLabelV4(currentSaved.failValidatedMin,currentSaved.failValidatedMax)} />
                <Row label="현재 상태" value={currentSaved.active ? '적용 중' : '비활성 (별도 적용 필요)'} />
                {!currentSaved.active && (
                  <Button title="새 버전 적용"
                    onPress={() => confirmActivate(currentSaved)}
                    disabled={!canWrite || !currentSaved.ready} />
                )}
              </Card>
            )}

            <Card title="정책 버전 목록 · 복귀">
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
                    <Row label="기준치" value={percentageTextV4(policy.passThreshold, 4)} />
                    <Row label="상태" value={`${policy.ready ? '준비됨' : '미준비'} · ${policy.active ? '적용 중' : '비활성'}`} />
                    <Row label="자동 불량" value={policy.autoFailEnabled===null?'미지원':policy.autoFailEnabled?'켜짐':'꺼짐'} />
                    <Row label="불량 기준" value={percentageTextV4(policy.failThreshold,4)} />
                    <Row label="불량 검증 범위" value={autoFailRangeLabelV4(policy.failValidatedMin,policy.failValidatedMax)} />
                    {policy.failThreshold!=null && <Row label="AI 검증 근거" value={policy.metrics?.autoFail && typeof policy.metrics.autoFail==='object'?'자료 등록됨 (독립 검증 여부 별도)':'검증 자료 없음'}/>}
                    {canActivate && policy.autoFailEnabled!==null && policy.failThreshold!=null && (
                      <Button secondary title={policy.autoFailEnabled?'이 버전에서 자동 불량 끄기 버전 저장':'이 버전에서 자동 불량 켜기 버전 저장'}
                        onPress={()=>confirmAutoFailToggle(!policy.autoFailEnabled,policy)} disabled={!canWrite}/>
                    )}
                    {isOriginal && <Text style={s.muted}>원본 정책 버전</Text>}
                    {canActivate && (
                      <Button secondary
                        title={isOriginal ? '원래 정책으로 복귀' : '이 정책 적용'}
                        onPress={() => confirmActivate(policy)} disabled={!canWrite} />
                    )}
                  </View>
                );
              })}
            </Card>
            </>)}
            <Text style={s.footer}>
              각 검사의 이력에는 접수 당시 적용한 정책이 표시됩니다.
            </Text>
          </>
        )}
      </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  backTouch: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' },
  metrics: { flexDirection: 'row', gap: 8 },
  metric: { flex: 1, minWidth: 0, backgroundColor: C.bg, borderRadius: 10, padding: 10, gap: 4 },
  metricLabel: { color: C.muted, fontSize: 13, lineHeight: 18 },
  metricValue: { color: C.ink, fontSize: 20, fontWeight: '700' },
  failEnabled: { color: C.red },
  detailsToggle: { minHeight: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 6, paddingHorizontal: 4 },
  sectionTabs: { flexDirection: 'row', gap: 6 },
  sectionTab: { flex: 1, minWidth: 0, minHeight: 44, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 4, paddingVertical: 9, borderRadius: 10, borderWidth: 1, borderColor: '#64748B', backgroundColor: C.white },
  sectionTabActive: { backgroundColor: '#1E293B', borderColor: '#1E293B' },
  sectionTabText: { color: C.ink, fontSize: 13, fontWeight: '700', textAlign: 'center' },
  sectionTabTextActive: { color: C.white },
  formLabel: { color: C.ink, fontSize: 13, lineHeight: 18, fontWeight: '600' },
  screen: { flex: 1, backgroundColor: C.bg },
  header: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 14, gap: 6 },
  back: { color: C.blue, fontSize: 14, fontWeight: '600' },
  title: { color: C.ink, fontSize: 23, lineHeight: 32, fontWeight: '700' },
  subtitle: { color: C.muted, fontSize: 13, lineHeight: 18},
  scroll: { flex: 1 },
  body: { paddingHorizontal: 20, paddingBottom: 35, gap: 12 },
  card: { padding: 15, backgroundColor: C.white, borderRadius: 14, borderWidth: 1, borderColor: C.border, gap: 10 },
  cardTitle: { color: C.ink, fontWeight: '700', fontSize: 16 },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  label: { color: C.muted, fontSize: 13, lineHeight: 18, flex: 0.46 },
  value: { color: C.ink, fontSize: 13, lineHeight: 18, textAlign: 'right', flex: 0.54, fontWeight: '600' },
  muted: { color: C.muted, fontSize: 13, lineHeight: 19 },
  evidenceCheck: { borderWidth: 1, borderColor: '#CBD5E1', borderRadius: 10, padding: 12 },
  input: { borderWidth: 1, borderColor: '#64748B', borderRadius: 10, minHeight: 46,
    backgroundColor: '#F8FAFC', color: C.ink, paddingHorizontal: 14, fontSize: 16 },
  hint: { fontSize: 13, lineHeight: 19, color: C.green },
  button: { borderRadius: 10, minHeight: 44, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 10 },
  primary: { backgroundColor: C.blue },
  secondary: { backgroundColor: C.white, borderWidth: 1, borderColor: C.blue },
  buttonText: { fontWeight: '700', fontSize: 14, textAlign: 'center' },
  primaryText: { color: C.white },
  secondaryText: { color: C.blue },
  disabled: { opacity: 0.45 },
  notice: { backgroundColor: C.pale, padding: 13, borderRadius: 12 },
  noticeText: { color: C.blue, fontSize: 13, lineHeight: 19 },
  status: { flexDirection: 'row', alignItems: 'center', gap: 9, padding: 11 },
  policyItem: { borderRadius: 10, backgroundColor: '#F8FAFC', padding: 12, borderWidth: 1,
    borderColor: C.border, gap: 7 },
  policyName: { color: C.ink, fontSize: 13, fontWeight: '700' },
  errorCard: { borderRadius: 12, padding: 12, backgroundColor: C.redPale, gap: 9 },
  errorText: { color: C.red, fontSize: 13, lineHeight: 19 },
  successCard: { borderRadius: 12, padding: 12, backgroundColor: C.greenPale },
  successText: { color: C.green, fontSize: 13, lineHeight: 20 },
  footer: { color: C.muted, fontSize: 12, lineHeight: 18, paddingHorizontal: 3 },
});
