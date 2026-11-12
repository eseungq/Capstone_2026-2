import React, { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Stack, router, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { validateThresholdEditV4 } from '../api/backendV4/policyThresholdV4';
import { DOOR_AUTOPASS_DEMO_V4, evaluateMockDoorAutopassDemoV4 } from '../api/backendV4/demoPolicyScenarioV4';

/**
 * 11/12 도현님 안내(0.84% → 0.92%)를 반영한 독립 Mock 재현입니다.
 * 실제 e02 보정값/보정기 버전은 null이며 실서버는 REVIEW를 유지합니다.
 * 서버, API, AsyncStorage, 운영 검사 기록/통계에는 접근하지 않습니다.
 */
const MOCK = DOOR_AUTOPASS_DEMO_V4;
type DemoReceipt = {
  id: number;
  threshold: number;
  policyVersion: string;
  decision: 'AUTO_PASS' | 'REVIEW';
};

type Phase = 'EDITING' | 'SAVED' | 'ACTIVE';
type Role = 'ADMIN' | 'WORKER';
const C={
  bg:'#F5F7FB',white:'#FFF',text:'#111827',muted:'#64748B',border:'#E4E7EC',
  blue:'#2054D8',bluePale:'#EBF1FF',red:'#B42318',redPale:'#FFF0ED',
  green:'#067647',greenPale:'#EAFBF2',gray:'#E2E8F0'
};
function Card({title,children}:{title:string;children:React.ReactNode}){
  return <View style={s.card}><Text style={s.cardTitle}>{title}</Text>{children}</View>;
}
function Row({name,value}:{name:string;value:string}){
  return <View style={s.row}><Text style={s.muted}>{name}</Text><Text style={s.val}>{value}</Text></View>;
}
function Nav({role}:{role:Role}){
  const items:Array<{label:string;symbol:string;route:'/monitoring'|'/history'|'/settings'}>=[
    {label:'모니터링',symbol:'▣',route:'/monitoring'},
    {label:'이력',symbol:'▤',route:'/history'},
    {label:'설정',symbol:'⚙',route:'/settings'},
  ];
  return <View style={s.nav}>{items.map((item)=><Pressable key={item.label} accessibilityRole="button" style={s.navItem}
    onPress={()=>router.replace({pathname:item.route,params:{role}})}>
    <Text style={[s.navSymbol,item.label==='설정'&&s.selected]}>{item.symbol}</Text>
    <Text style={[s.navLabel,item.label==='설정'&&s.selected]}>{item.label}</Text>
  </Pressable>)}</View>;
}
export default function AssumedPolicyScreen(){
  const params=useLocalSearchParams<{role?:string}>();
  const role:Role=params.role==='ADMIN'?'ADMIN':'WORKER';
  const [phase,setPhase]=useState<Phase>('EDITING');
  const [value,setValue]=useState(String(MOCK.adjustedThreshold));
  const [savedValue,setSavedValue]=useState<number|null>(null);
  const [demoReceipts,setDemoReceipts]=useState<DemoReceipt[]>([]);
  // evidenceVerified는 Mock UI의 입력 검증에만 사용합니다. 운영 승인 여부가 아닙니다.
  const result=validateThresholdEditV4(value,{
    validatedMin:MOCK.validatedMin,
    validatedMax:MOCK.validatedMax,
    evidenceVerified:true,
  });
  const appliedThreshold=phase==='ACTIVE' && savedValue!==null ? savedValue : MOCK.initialThreshold;
  const appliedVersion=phase==='ACTIVE' ? MOCK.adjustedPolicyVersion : MOCK.basePolicyVersion;
  const expectedDecision=evaluateMockDoorAutopassDemoV4(
    MOCK.samplePrediction,MOCK.sampleCalibratedDefectProbability,appliedThreshold,true,
  );
  const save=()=>{
    if(!result.ok || phase!=='EDITING') return;
    const candidate=result.value;
    Alert.alert('시연용 새 버전 저장',
      `기준치 ${candidate}를 ${MOCK.adjustedPolicyVersion}에 저장한 화면만 시연합니다. 실제 서버 요청은 없습니다.`,[
        {text:'취소',style:'cancel'},
        {text:'Mock 저장',onPress:()=>{setSavedValue(candidate);setPhase('SAVED');}},
      ]);
  };
  const activate=()=>{
    if(phase!=='SAVED'||savedValue===null)return;
    Alert.alert('시연용 정책 적용',
      `${MOCK.adjustedPolicyVersion}을(를) 적용한 것으로 시연합니다. 실제 정책·검사 DB는 변경되지 않습니다.`,[
        {text:'취소',style:'cancel'},
        {text:'Mock 적용',onPress:()=>setPhase('ACTIVE')},
      ]);
  };
  const submitMock=()=>{
    // 새 시연 건만 생성하며, 앞서 접수한 REVIEW 기록은 소급 변경하지 않습니다.
    const decision=evaluateMockDoorAutopassDemoV4(
      MOCK.samplePrediction,MOCK.sampleCalibratedDefectProbability,appliedThreshold,true,
    );
    setDemoReceipts(previous=>[...previous,{
      id:previous.length+1,threshold:appliedThreshold,policyVersion:appliedVersion,decision,
    }]);
  };
  return <SafeAreaView style={s.screen} edges={['top','bottom']}>
    <Stack.Screen options={{headerShown:false}} />
    <View style={s.header}>
      <Text style={s.title}>도어 AUTO_PASS · Mock 시연</Text>
      <Text style={s.subtitle}>11/12 시연 0.84% → 0.92% · 실서버/운영 정책 미연동</Text>
    </View>
    {role!=='ADMIN'?<View style={s.body}><Card title="관리자 전용"><Text style={s.note}>WORKER 시연 역할에서는 접근할 수 없습니다.</Text></Card></View>:
      <ScrollView style={s.scroller} contentContainerStyle={s.body} showsVerticalScrollIndicator={false}>
        <View style={s.warningBox}><Text style={s.warning}>
          도현님이 안내한 0.84~0.92% 범위와 정책 기본값 0.92%를 Mock으로 재현합니다. 비교 시작은 0.84% 활성 상태이며, 실제 운영 근거로 사용하거나 서버에 전송하지 않습니다.
        </Text></View>
        <Card title="시연 조건 · Mock 전용">
          <Row name="부품/모델" value={`${MOCK.partCode} / ${MOCK.mockModelVersion}`} />
          <Row name="시연 기본 정책" value={`${MOCK.basePolicyVersion} · Mock`} />
          <Row name="시연 조정 허용 범위" value={`${(MOCK.validatedMin*100).toFixed(2)}~${(MOCK.validatedMax*100).toFixed(2)}%`} />
          <Row name="정책 기본값" value={`${(MOCK.defaultThreshold*100).toFixed(2)}% · Mock`} />
          <Row name="비교 시작 활성 기준치" value={`${(MOCK.initialThreshold*100).toFixed(2)}% · Mock`} />
          <Row name="비교용 새 기준치" value={`${(MOCK.adjustedThreshold*100).toFixed(2)}% · Mock`} />
          <Row name="비교 입력" value={`${MOCK.samplePrediction} / 보정 불량 확률 ${(MOCK.sampleCalibratedDefectProbability*100).toFixed(2)}%`} />
          <Text style={s.note}>실제 e02의 보정값·보정기 버전은 미제공입니다. 아래 결과는 시연 전용이며 실제 AI·DB 결과가 아닙니다.</Text>
        </Card>
        <Card title="1. 검증 범위 내 기준치 조정">
          <Text style={s.note}>목표 미검출률이 아닌 passThreshold를 입력합니다. 도현님이 제공한 범위는 시연 정책에만 사용하며 실제 운영 기준으로 사용할 수 없습니다.</Text>
          <View style={s.inputRow}>
            <Text style={s.inputLabel}>passThreshold (0~1, 0.0092 = 0.92%)</Text>
            <TextInput accessibilityLabel="Mock 기준치" keyboardType="decimal-pad" style={[s.input,phase!=='EDITING'&&s.inputDisabled]}
              value={value} maxLength={12} editable={phase==='EDITING'} onChangeText={setValue}/>
          </View>
          {phase==='EDITING' && !result.ok?<Text style={s.warning}>{result.reason==='OUT_OF_RANGE'?'시연 허용 범위(0.0084~0.0092) 안의 값을 입력해 주세요.':'0~1 사이의 올바른 소수를 입력해 주세요.'}</Text>:null}
          <Pressable accessibilityRole="button" disabled={phase!=='EDITING'||!result.ok}
            accessibilityState={{disabled:phase!=='EDITING'||!result.ok}} onPress={save}
            style={[s.action,(phase!=='EDITING'||!result.ok)&&s.disabled]}>
            <Text style={[s.actionText,(phase!=='EDITING'||!result.ok)&&s.disabledText]}>
              {phase==='EDITING'?'새 정책 버전 저장 · Mock':'새 정책 버전 저장됨 · Mock'}
            </Text>
          </Pressable>
        </Card>
        <Card title="2. 저장 후 별도 적용">
          <Row name="새 버전" value={savedValue===null?'없음':`${MOCK.adjustedPolicyVersion} · Mock`} />
          <Row name="저장된 기준치" value={savedValue===null?'없음':`${(savedValue*100).toFixed(2)}% · Mock`} />
          <Row name="ready" value={savedValue===null?'미준비':'시연 준비됨 · Mock'} />
          <Row name="active" value={phase==='ACTIVE'?'새 시연 정책 적용':'시연 시작 0.84% 정책 유지'} />
          <Text style={s.note}>기준치를 저장해도 자동 적용되지 않습니다. 실제 환경에서는 서버가 ready·활성 모델·보정기 호환성을 검증합니다.</Text>
          <Pressable accessibilityRole="button" disabled={phase!=='SAVED'} accessibilityState={{disabled:phase!=='SAVED'}}
            onPress={activate} style={[s.action,phase!=='SAVED'&&s.disabled]}>
            <Text style={[s.actionText,phase!=='SAVED'&&s.disabledText]}>{phase==='ACTIVE'?'적용 시연 완료':'저장된 새 정책 적용 · Mock'}</Text>
          </Pressable>
        </Card>
        <Card title="3. 같은 Mock 입력으로 검사 접수 비교">
          <Row name="현재 활성 시연 정책" value={`${appliedVersion} · Mock`} />
          <Row name="현재 기준치" value={`${(appliedThreshold*100).toFixed(2)}%`} />
          <Row name={`${MOCK.samplePrediction} / 보정 불량 확률 ${(MOCK.sampleCalibratedDefectProbability*100).toFixed(2)}%`} value={`${expectedDecision}${expectedDecision==='REVIEW' ? ' (ABOVE_THRESHOLD)' : ''} · Mock 예상`} />
          {phase==='SAVED' && <Text style={s.note}>새 기준치는 저장되었지만 아직 적용되지 않아 0.84% 정책으로 판정합니다.</Text>}
          <Pressable accessibilityRole="button" style={s.action} onPress={submitMock}>
            <Text style={s.actionText}>GOOD / 0.88% 새 검사 접수 · Mock</Text>
          </Pressable>
          {demoReceipts.length===0
            ? <Text style={s.note}>먼저 0.84% 적용 상태에서 Mock 검사를 접수한 뒤, 0.92% 버전을 저장·적용하고 같은 GOOD / 0.88% 입력을 새로 접수해 비교하세요.</Text>
            : demoReceipts.map(receipt=><View key={receipt.id} style={s.receipt}>
                <Text style={s.receiptTitle}>시연 검사 #{receipt.id} · 운영 DB 기록 아님</Text>
                <Row name="사용한 정책" value={receipt.policyVersion} />
                <Row name="접수 당시 기준치" value={`${(receipt.threshold*100).toFixed(2)}%`} />
                <Text style={[s.receiptResult,{color:receipt.decision==='AUTO_PASS'?C.green:C.red}]}>
                  {receipt.decision==='AUTO_PASS'
                    ? 'AUTO_PASS · SYSTEM 최종 PASS (시연)'
                    : 'REVIEW (ABOVE_THRESHOLD) · 작업자 확인 필요 (시연)'}
                </Text>
              </View>)}
          <Text style={s.note}>기존 REVIEW 검사는 정책이 바뀌어도 그대로 남습니다. 실제 REVIEW의 작업자 PASS/FAIL은 서버에서 반환한 검사 UUID의 상세 화면에서만 수행합니다.</Text>
        </Card>
        <Card title="시연 상태">
          <Row name="진행 단계" value={phase==='EDITING'
            ? '0.84% 시연 시작 정책'
            : phase==='SAVED'
              ? `${((savedValue??MOCK.adjustedThreshold)*100).toFixed(2)}% 저장·미적용`
              : `${(appliedThreshold*100).toFixed(2)}% 새 정책 적용`} />
          <Row name="서버 API 요청" value="없음" />
          <Row name="운영 정책/검사 기록 변경" value="없음" />
          {phase!=='EDITING'||demoReceipts.length>0?<Pressable accessibilityRole="button" onPress={()=>{
            setPhase('EDITING');setValue(String(MOCK.adjustedThreshold));setSavedValue(null);setDemoReceipts([]);
          }} style={s.secondary}>
            <Text style={s.secondaryText}>시연 초기화 · 0.84% 기준으로 돌아가기</Text>
          </Pressable>:null}
        </Card>
        <Pressable accessibilityRole="button" onPress={()=>router.replace({pathname:'/policy-adjust',params:{role:'ADMIN'}})} style={s.secondary}>
          <Text style={s.secondaryText}>실제 준비 상태 화면으로 돌아가기</Text>
        </Pressable>
      </ScrollView>}
    <Nav role={role}/>
  </SafeAreaView>;
}
const s=StyleSheet.create({
  screen:{flex:1,backgroundColor:C.bg},header:{paddingHorizontal:20,paddingTop:10,paddingBottom:23},
  title:{fontSize:24,fontWeight:'700',color:C.text,lineHeight:34},subtitle:{color:C.muted,fontSize:12,lineHeight:20},
  scroller:{flex:1},body:{paddingHorizontal:20,paddingBottom:28,gap:12},
  card:{backgroundColor:C.white,borderWidth:1,borderColor:C.border,borderRadius:16,padding:16,gap:13},
  cardTitle:{fontSize:17,fontWeight:'700',color:C.text},row:{flexDirection:'row',gap:10},
  muted:{flex:0.5,color:C.muted,fontSize:13,lineHeight:20},val:{flex:0.5,textAlign:'right',color:C.text,fontSize:13,fontWeight:'600',lineHeight:20},
  note:{color:C.muted,fontSize:12,lineHeight:20},warningBox:{backgroundColor:C.redPale,padding:14,borderRadius:12},
  warning:{fontSize:12,color:C.red,lineHeight:20},inputRow:{flexDirection:'row',alignItems:'center',gap:10},
  inputLabel:{color:C.muted,flex:1,fontSize:13},input:{width:108,borderRadius:10,borderColor:'#CAD5E8',borderWidth:1,backgroundColor:C.white,color:C.text,textAlign:'right',paddingHorizontal:13,paddingVertical:10,fontSize:16},
  inputDisabled:{backgroundColor:'#F0F4FA',color:C.muted},action:{minHeight:46,borderRadius:12,backgroundColor:C.blue,alignItems:'center',justifyContent:'center',padding:12},
  actionText:{color:C.white,fontSize:13,fontWeight:'700',textAlign:'center'},disabled:{backgroundColor:C.gray},disabledText:{color:C.muted},
  secondary:{minHeight:46,borderRadius:12,backgroundColor:C.bluePale,alignItems:'center',justifyContent:'center',padding:12},secondaryText:{color:C.blue,fontSize:13,fontWeight:'700',textAlign:'center'},
  receipt:{padding:12,borderWidth:1,borderColor:C.border,borderRadius:10,gap:7,backgroundColor:'#FAFCFF'},
  receiptTitle:{color:C.text,fontSize:12,fontWeight:'700'},receiptResult:{fontSize:13,fontWeight:'700'},
  nav:{height:58,marginHorizontal:20,marginBottom:7,borderWidth:1,borderColor:C.border,borderRadius:15,backgroundColor:C.white,flexDirection:'row',alignItems:'center'},
  navItem:{flex:1,alignItems:'center',justifyContent:'center',gap:2,minHeight:46},navSymbol:{fontSize:17,color:C.muted},navLabel:{fontSize:11,color:C.muted,fontWeight:'600'},selected:{color:C.blue,fontWeight:'700'}
});
