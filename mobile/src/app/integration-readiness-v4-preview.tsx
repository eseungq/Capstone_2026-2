import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { pendingIntegrationDecisionsV4, runIntegrationReadinessChecksV4 } from '../api/backendV4/integrationReadinessV4';
import type { ReadinessCategoryV4 } from '../api/backendV4/integrationReadinessV4';

const sections: ReadinessCategoryV4[] = ['검사 이력·상세','모니터링·알림','판정·재검사','AI·Grad-CAM','통계·출처'];

/** 75단계: 다른 화면/기존 저장소를 수정하지 않는 읽기 전용 진단 화면. */
export default function IntegrationReadinessV4Preview() {
  const checks = runIntegrationReadinessChecksV4();
  const passed = checks.filter(c => c.ok).length;
  return (
    <SafeAreaView style={styles.screen} edges={['top','bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.heading}>통합 연결 준비 · 75단계</Text>
        <Text style={styles.subtitle}>서버 연결 전 · 실제 검사·판정·저장소를 변경하지 않는 계약 예시 점검</Text>
        <View style={styles.banner}>
          <Text style={styles.bannerTitle}>오프라인 규칙 검사: {passed}/{checks.length}개 통과</Text>
          <Text style={styles.note}>이 수치는 현재 앱 기능 전체의 통합 성공률이 아닙니다. 실제 서버 호출·화면 간 데이터 동기화·권한 인증은 검사하지 않았습니다.</Text>
        </View>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>데이터 출처 분리</Text>
          <Text style={styles.line}>CONTRACT_EXAMPLE · 계약 응답 예시 (서버 연결 없음)</Text>
          <Text style={styles.line}>LOCAL_INS_MOCK · 기존 INS 로컬 검사·AsyncStorage</Text>
          <Text style={styles.line}>SERVER · 추후 인증된 실제 UUID 검사</Text>
          <Text style={styles.note}>현재 화면은 위 세 출처를 합치지 않습니다. 가상 DOOR 대기열과 기존 INS 검사 이력·품질 통계를 섞지 않습니다.</Text>
        </View>
        {sections.map(section => {
          const rows = checks.filter(c=>c.category===section);
          return (
            <View style={styles.card} key={section}>
              <Text style={styles.cardTitle}>{section}</Text>
              {rows.map(c => <View style={styles.checkRow} key={c.label}>
                <Text style={[styles.tick,{color:c.ok?'#087E51':'#BD2419'}]}>{c.ok?'✓':'✕'}</Text>
                <Text style={styles.checkText}>{c.label}</Text>
              </View>)}
            </View>
          );
        })}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>실제 연동 전에 합의할 사항</Text>
          {pendingIntegrationDecisionsV4.map((line,index) =>
            <Text style={styles.line} key={index}>{index+1}. {line}</Text>
          )}
        </View>
        <View style={styles.footBox}>
          <Text style={styles.footTitle}>아직 운영 기능으로 검증되지 않았습니다</Text>
          <Text style={styles.note}>실제 AI·백엔드·iPhone 간 요청, 운영 AUTO_PASS 정책, 실제 푸시 알림, 서버 데이터를 이용한 품질 통계는 팀의 연동 일정에 맞춰 별도로 검증해야 합니다.</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles=StyleSheet.create({
  screen:{flex:1,backgroundColor:'#F4F6FB'},
  content:{paddingHorizontal:21,paddingTop:24,paddingBottom:48,gap:16},
  heading:{color:'#172033',fontSize:27,fontWeight:'800',lineHeight:38,paddingRight:50},
  subtitle:{color:'#657895',fontSize:14,lineHeight:23},
  banner:{backgroundColor:'#E9EFFF',borderRadius:18,padding:20,gap:12},
  bannerTitle:{color:'#2054CD',fontSize:20,fontWeight:'800',lineHeight:30},
  card:{backgroundColor:'#FFF',borderColor:'#DBE3EE',borderWidth:1,borderRadius:18,padding:18,gap:14},
  cardTitle:{color:'#172033',fontSize:18,fontWeight:'800',lineHeight:27},
  checkRow:{flexDirection:'row',alignItems:'flex-start',gap:12},
  tick:{width:20,fontSize:20,fontWeight:'800'},
  checkText:{flex:1,color:'#27354E',fontSize:14,lineHeight:23},
  line:{color:'#526683',fontSize:14,lineHeight:24},
  note:{color:'#637794',fontSize:13,lineHeight:21},
  footBox:{backgroundColor:'#F0F3F9',borderRadius:16,padding:18,gap:8},
  footTitle:{color:'#172033',fontSize:15,fontWeight:'700'},
});
