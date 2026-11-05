import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Stack, router, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { validateThresholdEditV4 } from '../api/backendV4/policyThresholdV4';

/**
 * v4 합의: 목표 미검출률 입력 → 후보 계산 방식은 사용하지 않습니다.
 * AI 실측 검증 범위가 없는 현재는 운영 정책을 저장/적용할 수 없습니다.
 * 조건 가정 화면은 별도 Mock이며 서버/AsyncStorage/검사 결과를 변경하지 않습니다.
 */

type Role = 'ADMIN' | 'WORKER';
const C = {
  bg:'#F5F7FB', surface:'#FFFFFF', border:'#E4E7EC', text:'#111827',
  muted:'#64748B', blue:'#2054D8', bluePale:'#EBF1FF',
  red:'#B42318', redPale:'#FFF0ED', inactive:'#DEE5F0'
};

function Row({name,value}: {name:string;value:string}) {
  return <View style={s.row}><Text style={s.label}>{name}</Text><Text style={s.value}>{value}</Text></View>;
}
function Card({title,children}: {title:string;children:React.ReactNode}) {
  return <View style={s.card}><Text style={s.cardTitle}>{title}</Text>{children}</View>;
}
function DisabledAction({label}: {label:string}) {
  return <Pressable disabled accessibilityRole="button" accessibilityState={{disabled:true}} style={s.disabledButton}>
    <Text style={s.disabledText}>{label}</Text>
  </Pressable>;
}
function Nav({role}: {role:Role}) {
  const items: Array<{name:string;symbol:string;to:'/monitoring'|'/history'|'/settings'}> = [
    {name:'모니터링',symbol:'▣',to:'/monitoring'},
    {name:'이력',symbol:'▤',to:'/history'},
    {name:'설정',symbol:'⚙',to:'/settings'},
  ];
  return <View style={s.nav}>{items.map(item=><Pressable key={item.name} accessibilityRole="button"
    onPress={()=>router.replace({pathname:item.to,params:{role}})} style={s.navItem}>
    <Text style={[s.navSymbol,item.name==='설정'&&s.navSelected]}>{item.symbol}</Text>
    <Text style={[s.navLabel,item.name==='설정'&&s.navSelected]}>{item.name}</Text>
  </Pressable>)}</View>;
}

export default function PolicyAdjustScreen() {
  const params=useLocalSearchParams<{role?:string}>();
  // 화면 시연용 라우트 역할 값. 운영 인가는 로그인된 서버 토큰과 백엔드가 수행합니다.
  const role:Role = params.role === 'ADMIN' ? 'ADMIN' : 'WORKER';
  // 아직 도현님이 검증된 실측 허용 범위를 제공하지 않았습니다.
  const current = {validatedMin:null,validatedMax:null,evidenceVerified:false};
  const threshold = validateThresholdEditV4('',current);
  const allowOperation = threshold.ok; // 항상 false: 검증된 범위/값 미제공

  return <SafeAreaView style={s.screen} edges={['top','bottom']}>
    <Stack.Screen options={{headerShown:false}} />
    <View style={s.header}>
      <Text style={s.title}>자동 통과 기준 조정</Text>
      <Text style={s.subtitle}>AI 검증 범위 내 조정 → 새 버전 저장 → 별도 적용</Text>
    </View>
    {role!=='ADMIN' ? <View style={s.body}>
      <Card title="관리자 전용 기능"><Text style={s.note}>작업자 역할에서는 정책 관리 기능을 사용할 수 없습니다.</Text></Card>
    </View> : <ScrollView style={s.scroller} contentContainerStyle={s.body} showsVerticalScrollIndicator={false}>
      <View style={s.notice}><Text style={s.noticeText}>
        현재 운영 상태: 검증된 보정기·기준치·허용 범위가 제공되지 않았습니다. 자동 통과 정책은 준비 전이며 저장과 적용이 비활성화되어 있습니다.
      </Text></View>
      <Card title="정책 정보 · 실제 상태">
        <Row name="부품" value="DOOR" />
        <Row name="AI 모델 버전" value="실서버 확인 전" />
        <Row name="보정기 버전" value="미제공" />
        <Row name="정책 상태" value="미준비 / 미적용" />
        <Row name="현재 passThreshold" value="미제공" />
      </Card>
      <Card title="1. AI 검증 범위 확인">
        <Row name="검증된 최소값 (validatedMin)" value="미제공" />
        <Row name="검증된 최대값 (validatedMax)" value="미제공" />
        <Row name="실측 검증 근거" value="미제공" />
        <Text style={s.note}>허용 범위와 평가 근거는 AI 팀이 제공하고 백엔드에서 검증합니다. 가상 수치를 운영 허용 범위처럼 사용하지 않습니다.</Text>
      </Card>
      <Card title="2. passThreshold 조정 및 저장">
        <Text style={s.note}>검증된 범위가 확인되면 관리자가 범위 안의 기준치를 입력할 수 있습니다. 저장하면 기존 정책을 덮어쓰지 않고 새 버전을 만듭니다.</Text>
        <View style={s.readOnlyInput} accessibilityLabel="검증 범위 미제공, 기준치 입력 비활성">
          <Text style={s.readOnlyInputText}>검증 범위 미제공 · 기준치 조정 불가</Text>
        </View>
        <DisabledAction label="새 정책 버전 저장 · 검증 전" />
      </Card>
      <Card title="3. 저장된 정책 별도 적용">
        <Text style={s.note}>새 버전은 저장 직후 자동 적용되지 않습니다. 정책 ready, 활성 모델, 보정기 호환성을 확인한 뒤 별도 적용해야 합니다.</Text>
        <Row name="저장된 새 버전" value="없음" />
        <Row name="ready" value="미확인" />
        <Row name="active" value="미적용" />
        <DisabledAction label="새 버전 적용 · 저장/검증 전" />
      </Card>
      <Pressable accessibilityRole="button" style={s.demoButton}
        onPress={()=>router.push({pathname:'/policy-assumed',params:{role:'ADMIN'}})}>
        <Text style={s.demoButtonText}>검증 범위가 있다고 가정한 흐름 시연 · Mock →</Text>
      </Pressable>
      <View style={s.notice}><Text style={s.noticeText}>
        위 화면은 정책 관리 구조를 구현한 프론트엔드 준비 화면입니다. 현재 서버 API 호출, 정책 저장·적용, 검사 판정 변경은 발생하지 않습니다. 별도 Mock 시연 역시 운영 기록에 반영되지 않습니다.
      </Text></View>
    </ScrollView>}
    <Nav role={role}/>
  </SafeAreaView>;
}
const s=StyleSheet.create({
  screen:{flex:1,backgroundColor:C.bg},header:{paddingHorizontal:20,paddingTop:10,paddingBottom:23},
  title:{fontSize:24,fontWeight:'700',color:C.text,lineHeight:34},subtitle:{color:C.muted,fontSize:12,lineHeight:19,marginTop:2},
  scroller:{flex:1},body:{paddingHorizontal:20,paddingBottom:28,gap:12},
  card:{backgroundColor:C.surface,borderWidth:1,borderColor:C.border,borderRadius:16,padding:16,gap:13},
  cardTitle:{fontSize:17,fontWeight:'700',color:C.text},row:{flexDirection:'row',alignItems:'flex-start',gap:8},
  label:{flex:0.52,fontSize:13,color:C.muted,lineHeight:20},value:{flex:0.48,textAlign:'right',fontSize:13,color:C.text,lineHeight:20,fontWeight:'600'},
  note:{fontSize:12,color:C.muted,lineHeight:20},notice:{backgroundColor:C.bluePale,borderRadius:13,padding:14},
  noticeText:{fontSize:12,color:C.blue,lineHeight:20},readOnlyInput:{backgroundColor:'#F3F6FA',borderWidth:1,borderColor:'#D9E0F0',borderRadius:10,padding:14},
  readOnlyInputText:{color:C.muted,fontSize:12},disabledButton:{minHeight:46,alignItems:'center',justifyContent:'center',backgroundColor:C.inactive,borderRadius:12},
  disabledText:{color:'#62748D',fontWeight:'700',fontSize:13},demoButton:{minHeight:48,alignItems:'center',justifyContent:'center',backgroundColor:C.bluePale,borderRadius:12,padding:12},
  demoButtonText:{color:C.blue,fontWeight:'700',fontSize:13,textAlign:'center'},nav:{height:58,flexDirection:'row',alignItems:'center',marginHorizontal:20,marginBottom:7,borderRadius:15,backgroundColor:C.surface,borderWidth:1,borderColor:C.border},
  navItem:{flex:1,alignItems:'center',justifyContent:'center',gap:2,minHeight:46},navSymbol:{fontSize:17,color:C.muted},navLabel:{fontSize:11,color:C.muted,fontWeight:'600'},navSelected:{color:C.blue,fontWeight:'700'}
});
