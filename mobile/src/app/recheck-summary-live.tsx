import React, { useCallback, useRef, useState } from 'react';
import { router, Stack, useFocusEffect } from 'expo-router';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { authV4 } from '../api/backendV4/authRuntime';
import { ApiV4RequestError } from '../api/backendV4/httpCore';
import { createRecheckSummaryServiceV4 } from '../api/backendV4/recheckSummaryServiceV4';
import {
  formatRecheckCompareTitleV4, formatRecheckCompletionV4, formatRecheckRateV4,
} from '../api/backendV4/recheckSummaryCoreV4';
import type {
  RecheckRuleSummaryV4, RecheckSummaryDwellV4, RecheckSummaryV4, RecheckSummaryWaitV4,
} from '../api/backendV4/recheckSummaryCoreV4';

type Part = 'ALL' | 'DOOR' | 'FRAME' | 'COWL_COVER';
type Period = 7 | 30;
const summaryService = createRecheckSummaryServiceV4(authV4);

function safeError(cause: unknown): string {
  if (cause instanceof ApiV4RequestError) {
    if (cause.httpStatus === 404) {
      return '표본 재확인 요약을 불러올 수 없습니다. 잠시 후 다시 조회해 주세요.';
    }
    return cause.message;
  }
  return cause instanceof Error ? cause.message : '재확인 시험 요약을 불러오지 못했습니다.';
}
function countText(x: number): string { return x.toLocaleString('ko-KR') + '건'; }
function timeText(x: number | null): string {
  return x === null ? '기록 없음' : (x / 1000).toFixed(1) + '초';
}
function textOrNone(x: string | null): string { return x ?? '미제공'; }

function Field({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <Text style={styles.fieldValue}>{value}</Text>
    </View>
  );
}
function Notice({ children }: { children: React.ReactNode }) {
  return <View style={styles.notice}><Text style={styles.noticeText}>{children}</Text></View>;
}
function MetricPair({ title, value }: { title: string; value: string }) {
  return <View style={styles.metric}>
    <Text style={styles.metricTitle}>{title}</Text>
    <Text style={styles.metricValue}>{value}</Text>
  </View>;
}
function WaitCard({ label, value }: {label: string; value: RecheckSummaryWaitV4}) {
  return <View style={styles.metricCard}>
    <Text style={styles.itemTitle}>{label}</Text>
    <Field label="완료·대기" value={countText(value.count) + ' / ' + countText(value.pendingCount)} />
    <Field label="평균 대기" value={timeText(value.averageMs)} />
    <Field label="중앙 대기" value={timeText(value.medianMs)} />
  </View>;
}
function DwellCard({ label, value }: {label: string; value: RecheckSummaryDwellV4}) {
  return <View style={styles.metricCard}>
    <Text style={styles.itemTitle}>{label}</Text>
    <Field label="시간 기록 제출" value={countText(value.count)} />
    <Field label="평균 화면 체류" value={timeText(value.averageMs)} />
    <Field label="중앙 화면 체류" value={timeText(value.medianMs)} />
    <Field label="평균 열기 횟수"
      value={value.averageOpenCount === null ? '기록 없음' : value.averageOpenCount.toFixed(2) + '회'} />
  </View>;
}
function RuleCard({ rule, index }: { rule: RecheckRuleSummaryV4; index: number }) {
  const completedCount = rule.passCount + rule.failCount;
  const compare = rule.compare;
  return <View style={styles.card}>
    <Text style={styles.itemTitle}>조건 {index + 1} · {textOrNone(rule.partCode)}</Text>
    <Field label="추출 규칙" value={rule.ruleVersion} />
    <Field label="시험 이름" value={textOrNone(rule.trialName)} />
    <Field label="정책 버전" value={textOrNone(rule.policyVersion)} />
    <Field label="AI 모델 버전" value={textOrNone(rule.modelVersion)} />
    <Field label="보정기 버전" value={textOrNone(rule.calibratorVersion)} />
    <View style={styles.divider}/>
    <Text style={styles.sectionTitle}>실제 수집 결과</Text>
    <Field label="AUTO_PASS 검사" value={countText(rule.autoPassCount)} />
    <Field label="추출 결정·누락"
      value={countText(rule.decidedCount) + ' / ' + countText(rule.undecidedCount)} />
    <Field label="재확인 PASS·FAIL"
      value={countText(rule.passCount) + ' / ' + countText(rule.failCount)} />
    <Field label="재확인 완료" value={formatRecheckCompletionV4(
      completedCount, rule.sampledCount, rule.completionRate,
    )} />
    <View style={styles.highlight}>
      <Text style={styles.highlightTitle}>AUTO_PASS 추정 불량률</Text>
      <Text style={styles.highlightValue}>{formatRecheckRateV4(rule.estimatedDefectRateInAutoPass)}</Text>
      <Text style={styles.muted}>자동 통과된 검사 내 불량 비율 추정값이며 전체 불량률이 아닙니다.</Text>
    </View>
    {rule.partial && <Notice>일부만 완료되어 결과가 치우칠 수 있습니다</Notice>}
    <Text style={styles.sectionTitle}>구간별 재확인 완료율</Text>
    {rule.strata.map(s => (
      <View key={s.stratum} style={styles.stratumCard}>
        <View style={styles.rowBetween}>
          <Text style={styles.itemTitle}>{s.stratum}</Text>
          <Text style={styles.strong}>{formatRecheckCompletionV4(
            s.completedCount, s.sampledCount, s.completionRate,
          )}</Text>
        </View>
        <Text style={styles.muted}>
          AUTO_PASS {countText(s.autoPassCount)} · 결정 누락 {countText(s.undecidedCount)} · 대기 {countText(s.pendingCount)}
        </Text>
        <Text style={styles.muted}>
          재확인 PASS {countText(s.passCount)} · FAIL {countText(s.failCount)}
          {' · 완료 건 중 FAIL '}
          {s.failRateAmongCompleted === null ? '추정하지 않음' : formatRecheckRateV4(s.failRateAmongCompleted)}
        </Text>
      </View>
    ))}
    <View style={styles.divider}/>
    <View style={styles.virtualCard}>
      <Text style={styles.sectionTitle}>
        {compare ? formatRecheckCompareTitleV4(compare) : '가상 비교 (50·30·10%)'}
      </Text>
      <Text style={styles.muted}>
        같은 검사 기록에 다른 추출 비율을 가정한 값입니다. 실제 재확인 결과와 합산하지 않습니다.
      </Text>
      {!compare ? (
        <Text style={styles.muted}>가상 비교 결과가 제공되지 않았습니다.</Text>
      ) : !compare.computable ? (
        <Text style={styles.warning}>현재 수집 비율보다 높은 가상 비율이거나 규칙 기록이 없어 계산할 수 없습니다.</Text>
      ) : (
        <>
          <Field label="가상 선정" value={countText(compare.sampledCount ?? 0)} />
          <Field label="재확인 미완료" value={countText(compare.unverifiedCount ?? 0)} />
          <Field label="PASS·FAIL" value={countText(compare.passCount ?? 0) + ' / ' + countText(compare.failCount ?? 0)} />
          <Field label="AUTO_PASS 추정 불량률" value={formatRecheckRateV4(
            compare.estimatedDefectRateInAutoPass,
          )} />
          {compare.partial === true && <Notice>일부만 완료되어 결과가 치우칠 수 있습니다</Notice>}
        </>
      )}
    </View>
  </View>;
}

export default function RecheckSummaryLiveScreen() {
  const [part, setPart] = useState<Part>('ALL');
  const [period, setPeriod] = useState<Period>(7);
  const [loading, setLoading] = useState(true);
  const [authorized, setAuthorized] = useState(false);
  const [summary, setSummary] = useState<RecheckSummaryV4 | null>(null);
  const [error, setError] = useState<string | null>(null);
  const serialRef = useRef(0);

  const load = useCallback(async () => {
    const serial = ++serialRef.current;
    setLoading(true);
    setSummary(null);
    setError(null);
    setAuthorized(false);
    try {
      const session = await authV4.restore();
      if (serial !== serialRef.current) return;
      if (!session.signedIn || session.role !== 'ADMIN') {
        throw new Error('이 화면은 실제 서버 ADMIN 계정만 조회할 수 있습니다.');
      }
      setAuthorized(true);
      // 기간 없는 전체 DB 스캔을 피하기 위해 항상 명시적 시험 기간 지정.
      const now = Date.now();
      const from = new Date(now - period * 24 * 60 * 60 * 1000).toISOString();
      const to = new Date(now).toISOString();
      const result = await summaryService.get({
        ...(part === 'ALL' ? {} : { partCode: part }),
        from, to,
        compareNearRate: 0.5, compareMidRate: 0.3, compareLowRate: 0.1,
      });
      if (serial !== serialRef.current) return;
      setSummary(result);
    } catch (cause) {
      if (serial === serialRef.current) setError(safeError(cause));
    } finally {
      if (serial === serialRef.current) setLoading(false);
    }
  }, [part, period]);

  useFocusEffect(useCallback(() => {
    void load();
    return () => { serialRef.current += 1; };
  }, [load]));

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable accessibilityRole="button" onPress={() => router.back()}>
          <Text style={styles.link}>‹ 뒤로</Text>
        </Pressable>
        <Text style={styles.title}>AUTO_PASS 표본 재확인 요약</Text>
        <Text style={styles.muted}>관리자 전용 · 조회만 가능</Text>
      </View>
      <ScrollView contentContainerStyle={styles.body}>
        <Notice>
          AUTO_PASS 추정 불량률은 전체 불량률이 아닙니다. 같은 규칙이어도 부품·정책·모델·보정기 버전이 다르면 별도 결과로 표시합니다.
        </Notice>
        <Text style={styles.sectionTitle}>조회 기간</Text>
        <View style={styles.row}>
          {([7,30] as const).map(v => (
            <Pressable key={v} accessibilityRole="button" accessibilityState={{ selected:period === v }}
              style={[styles.filter,period === v && styles.selected]}
              onPress={() => setPeriod(v)}>
              <Text style={[styles.filterLabel,period === v && styles.selectedText]}>최근 {v}일</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.sectionTitle}>부품 필터</Text>
        <View style={styles.row}>
          {(['ALL','DOOR','FRAME','COWL_COVER'] as const).map(value => (
            <Pressable key={value} accessibilityRole="button" accessibilityState={{ selected:part === value }}
              style={[styles.filter,part === value && styles.selected]}
              onPress={() => setPart(value)}>
              <Text style={[styles.filterLabel,part === value && styles.selectedText]}>{value}</Text>
            </Pressable>
          ))}
        </View>
        {loading && <View style={styles.card}>
          <ActivityIndicator/>
          <Text style={styles.muted}>서버에서 공동시험 요약을 조회하고 있습니다…</Text>
        </View>}
        {error && <View style={styles.card}>
          <Text style={styles.errorText}>{error}</Text>
        </View>}
        {!loading && authorized && (
          <Pressable accessibilityRole="button"
            style={({ pressed }) => [styles.filter,pressed && styles.pressed]}
            onPress={() => void load()}>
            <Text style={styles.link}>요약 다시 조회</Text>
          </Pressable>
        )}
        {!loading && summary && (
          <>
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>전체 기록 건수 (조건별 불량률은 합산하지 않음)</Text>
              <View style={styles.metrics}>
                <MetricPair title="AUTO_PASS" value={countText(summary.autoPassCount)}/>
                <MetricPair title="추출 결정" value={countText(summary.decidedCount)}/>
                <MetricPair title="결정 누락" value={countText(summary.undecidedCount)}/>
                <MetricPair title="규칙 없는 결정 누락" value={countText(summary.undecidedWithoutRuleCount)}/>
              </View>
              <Text style={styles.muted}>불량률은 아래 조건별 항목에서 각각 확인하세요.</Text>
            </View>
            <Text style={styles.sectionTitle}>규칙·정책·모델·보정기별 결과</Text>
            {summary.rules.length === 0 && <View style={styles.card}>
              <Text style={styles.muted}>
                선택한 기간에 표본 추출 규칙에 연결된 AUTO_PASS 기록이 없습니다.
              </Text>
            </View>}
            {summary.rules.map((rule,index) => (
              <RuleCard key={[rule.ruleVersion,rule.trialName,rule.partCode,
                rule.policyVersion,rule.modelVersion,rule.calibratorVersion,index].join('|')}
                rule={rule} index={index}/>
            ))}
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>대기 시간 비교 · 서버 기록</Text>
              <WaitCard label="REVIEW 확인" value={summary.waits.review}/>
              <WaitCard label="AUTO_PASS 재확인" value={summary.waits.recheck}/>
              <Text style={styles.muted}>
                평균·중앙값은 완료된 건만, 대기 중인 건은 따로 집계합니다.
              </Text>
            </View>
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>화면 체류 시간 비교 · 제출된 건만</Text>
              <DwellCard label="REVIEW 확인" value={summary.dwell.review}/>
              <DwellCard label="AUTO_PASS 재확인" value={summary.dwell.recheck}/>
              <Text style={styles.muted}>
                제출하지 않고 나간 건은 기록하지 않았습니다. 화면 체류가 실제 작업 시간과 같지는 않습니다.
              </Text>
            </View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles=StyleSheet.create({
  screen:{flex:1,backgroundColor:'#F5F7FB'},
  header:{paddingHorizontal:20,paddingTop:12,paddingBottom:12,gap:7},
  title:{fontSize:21,fontWeight:'700',color:'#111827'},
  body:{paddingHorizontal:20,paddingBottom:32,gap:12},
  row:{flexDirection:'row',flexWrap:'wrap',gap:7},
  filter:{paddingVertical:11,paddingHorizontal:12,borderWidth:1,
    borderColor:'#CBD5E1',backgroundColor:'#FFF',borderRadius:10,alignItems:'center'},
  selected:{backgroundColor:'#2054D8',borderColor:'#2054D8'},
  filterLabel:{color:'#475569',fontSize:12,fontWeight:'600'},
  selectedText:{color:'#FFF'},
  card:{backgroundColor:'#FFF',borderWidth:1,borderColor:'#E4E7EC',borderRadius:14,padding:15,gap:9},
  itemTitle:{fontSize:14,fontWeight:'700',color:'#111827',flexShrink:1},
  sectionTitle:{fontSize:14,fontWeight:'700',color:'#111827'},
  field:{flexDirection:'row',alignItems:'flex-start',justifyContent:'space-between',gap:12},
  fieldLabel:{fontSize:12,color:'#64748B',flexShrink:1},
  fieldValue:{fontSize:12,color:'#111827',fontWeight:'600',textAlign:'right',flex:1},
  muted:{fontSize:11,color:'#64748B',lineHeight:17},
  link:{fontSize:13,color:'#2054D8',fontWeight:'700'},
  divider:{height:1,backgroundColor:'#E4E7EC',marginVertical:4},
  warning:{fontSize:12,color:'#92400E',lineHeight:19},
  errorText:{fontSize:13,color:'#B42318',lineHeight:19},
  metrics:{flexDirection:'row',flexWrap:'wrap',gap:9},
  metric:{padding:10,minWidth:'46%',flexGrow:1,flexBasis:'46%',backgroundColor:'#F5F7FB',borderRadius:10,gap:4},
  metricTitle:{fontSize:11,color:'#64748B'},
  metricValue:{fontSize:17,fontWeight:'700',color:'#111827'},
  highlight:{borderWidth:1,borderColor:'#BFDBFE',backgroundColor:'#EFF6FF',borderRadius:12,padding:13,gap:5},
  highlightTitle:{fontSize:13,fontWeight:'700',color:'#1D4ED8'},
  highlightValue:{fontSize:19,fontWeight:'800',color:'#1E3A8A'},
  notice:{padding:11,borderRadius:10,borderWidth:1,borderColor:'#E8D7B6',backgroundColor:'#FFF8E8'},
  noticeText:{color:'#92400E',fontSize:12,lineHeight:19},
  stratumCard:{padding:11,borderRadius:10,backgroundColor:'#F7F9FC',gap:5},
  rowBetween:{flexDirection:'row',flexWrap:'wrap',justifyContent:'space-between',alignItems:'center',gap:5},
  strong:{color:'#111827',fontWeight:'700',fontSize:12,flexShrink:1},
  virtualCard:{backgroundColor:'#F8FAFC',borderWidth:1,borderColor:'#CBD5E1',padding:12,borderRadius:12,gap:9},
  metricCard:{borderWidth:1,borderColor:'#E4E7EC',padding:11,borderRadius:10,gap:8},
  pressed:{opacity:0.75},
});
