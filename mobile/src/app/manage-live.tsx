import React from 'react';
import { router, Stack } from 'expo-router';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Pressable from '../components/TouchPressable';
import LiveBottomNavV4 from '../components/LiveBottomNavV4';
import { useVerifiedRoleV4 } from '../components/useVerifiedRoleV4';

const entries = [
  {id:'judgements',title:'판정 확인 요청',desc:'시스템 판정 유지·정정 요청 검토',route:'/judgement-requests-admin-live'},
  {id:'policy',title:'자동 판정 정책',desc:'자동 통과·자동 불량 기준 및 버전 관리',route:'/policy-live'},
  {id:'daily',title:'날짜별 자동 판정 이력',desc:'날짜·정책별 집계 및 기준 주변 검사',route:'/admin-daily-live'},
  {id:'rechecks',title:'자동 통과 표본 재확인',desc:'재확인 결과·관리자 확인함 및 공동시험 요약',route:'/rechecks-live'},
] as const;

export default function ManageLiveScreen(){
  const {role,checking}=useVerifiedRoleV4();
  return <SafeAreaView style={s.root} edges={['top','bottom']}>
    <Stack.Screen options={{headerShown:false}}/>
    <View style={s.header}><Text style={s.title}>관리</Text><Text style={s.muted}>관리자 업무</Text></View>
    {checking?<View style={s.guard}><ActivityIndicator/><Text style={s.muted}>권한 확인 중</Text></View>:
      role!=='ADMIN'?<View style={s.guard}><Text style={s.muted}>관리자 계정에서만 사용할 수 있습니다.</Text>
        <Pressable accessibilityRole="button" style={s.entry} onPress={()=>router.replace({pathname:'/monitoring',params:{role:'WORKER',mode:'live'}})}>
          <Text style={s.link}>모니터링으로 돌아가기</Text>
        </Pressable></View>:
      <>
        <ScrollView style={s.scroll} contentContainerStyle={s.body}>
          {entries.map(entry=><Pressable key={entry.id} testID={'manage-'+entry.id} accessibilityRole="button"
            accessibilityLabel={entry.title} style={s.entry} onPress={()=>router.push(entry.route)}>
            <View style={s.copy}><Text style={s.entryTitle}>{entry.title}</Text><Text style={s.muted}>{entry.desc}</Text></View>
            <Text style={s.arrow}>›</Text>
          </Pressable>)}
        </ScrollView>
        <LiveBottomNavV4 role="ADMIN" active="manage"/>
      </>}
  </SafeAreaView>;
}
const s=StyleSheet.create({
  root:{flex:1,backgroundColor:'#F5F7FB'},header:{paddingHorizontal:20,paddingTop:12,paddingBottom:16,gap:5},
  title:{fontSize:23,color:'#111827',fontWeight:'700'},muted:{fontSize:13,lineHeight:19,color:'#475569'},
  scroll:{flex:1},body:{paddingHorizontal:20,paddingBottom:24,gap:12},guard:{flex:1,padding:20,gap:12},
  entry:{minHeight:64,padding:16,borderRadius:14,backgroundColor:'#FFFFFF',borderColor:'#E4E7EC',borderWidth:1,flexDirection:'row',alignItems:'center',gap:8},
  copy:{flex:1,minWidth:0,gap:5},entryTitle:{fontSize:16,color:'#111827',fontWeight:'700'},arrow:{fontSize:22,color:'#475569'},link:{fontSize:14,color:'#2054D8',fontWeight:'700'},
});
