import React, { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { createMonitoringDemoReaderV4, monitoringPollQuickChecksV4 } from '../api/backendV4/monitoringPollExamples';
import { useMonitoringPollV4 } from '../api/backendV4/useMonitoringPollV4';
import type { MonitorAlertV4 } from '../api/backendV4/monitoringPollCore';

export default function MonitoringPollV4PreviewScreen() {
  const reader = useMemo(() => createMonitoringDemoReaderV4(), []);
  const { snapshot, controller } = useMonitoringPollV4(reader);
  const [events, setEvents] = useState<MonitorAlertV4[]>([]);
  const [queued, setQueued] = useState(0);
  useEffect(() => controller.subscribeAlerts((items) => setEvents(old => [...items, ...old].slice(0, 20))), [controller]);
  const checks = monitoringPollQuickChecksV4();
  const passes = checks.filter(x=>x.ok).length;
  const isExample = snapshot.source==='CONTRACT_EXAMPLE';
  return (
    <SafeAreaView style={styles.screen} edges={['top','bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.heading}>공정 모니터링 5초 갱신 점검</Text>
        <Text style={styles.sub}>69단계 · 가상 데이터만 사용 · 서버·푸시 미연결</Text>
        <View style={styles.highlight}>
          <Text style={styles.highlightTitle}>규칙 점검: {passes}/{checks.length}개 통과</Text>
          <Text style={styles.note}>아래 실시간 시연은 화면이 보이고 앱이 활성일 때만 5초 간격으로 조회합니다. 실제 서버 요청은 없습니다.</Text>
        </View>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>5초 주기 가상 폴링 · 직접 확인</Text>
          <Text style={styles.line}>출처: {isExample?'CONTRACT_EXAMPLE (가상)':'SERVER'}</Text>
          <Text style={styles.line}>상태: {snapshot.status} · 성공 조회: {snapshot.successfulPolls}회</Text>
          <Text style={styles.line}>DOOR 카드: {snapshot.parts.length}개 · 확인 필요: {snapshot.queue.length}건</Text>
          <Text style={styles.line}>실패 횟수: {snapshot.failureStreak}회 · 다음 간격: {snapshot.nextDelayMs === null?'없음':`${snapshot.nextDelayMs/1000}초`}</Text>
          <Text style={styles.note}>최근 정상 조회: {snapshot.lastSuccessAtMs ? new Date(snapshot.lastSuccessAtMs).toLocaleTimeString('ko-KR') : '없음'}</Text>
          {snapshot.error && <Text style={styles.error}>가상 오류: {snapshot.error} · 마지막 정상 데이터 유지</Text>}
          <Text style={styles.note}>시작할 때 이미 존재한 REVIEW/FAILED 항목은 신규 알림으로 표시하지 않습니다.</Text>
          <View style={styles.buttonRow}>
            <Pressable accessibilityRole="button" style={styles.button} onPress={() => {reader.addReview();setQueued(v=>v+1);}}>
              <Text style={styles.buttonText}>가상 REVIEW 추가</Text>
            </Pressable>
            <Pressable accessibilityRole="button" style={styles.button} onPress={() => {reader.addFailed();setQueued(v=>v+1);}}>
              <Text style={styles.buttonText}>가상 FAILED 추가</Text>
            </Pressable>
          </View>
          <Pressable accessibilityRole="button" style={styles.outline} onPress={() => reader.failOnce()}>
            <Text style={styles.outlineText}>다음 조회에 가상 네트워크 오류 1회</Text>
          </Pressable>
          <Text style={styles.note}>추가한 가상 검사: {queued}건 · 다음 조회 때 반영. 버튼을 누를 때마다 새 이벤트만 1회 기록해요.</Text>
          <Text style={styles.line}>새 알림 이벤트: {events.length}건 (시연 화면 내부만)</Text>
          {events.slice(0,5).map((event, index)=>(
            <Text style={styles.event} key={`${event.inspectionId}-${event.kind}-${index}`}>
              {event.kind} · {event.inspectionNo ?? '검사번호 미제공'}
            </Text>
          ))}
        </View>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>폴링 규칙 · 사전 점검</Text>
          {checks.map(x=><View key={x.name} style={styles.checkLine}>
            <Text style={[styles.tick,{color:x.ok?'#087D50':'#B42318'}]}>{x.ok?'✓':'✕'}</Text>
            <Text style={styles.checkText}>{x.name}</Text>
          </View>)}
        </View>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>실제 연결 전 확인할 항목</Text>
          <Text style={styles.note}>1. 응답 페이지 커서 안정성 및 400건 이상 대기열 처리</Text>
          <Text style={styles.note}>2. 백엔드의 REVIEW/FAILED 발생 시간과 알림 중복 정책</Text>
          <Text style={styles.note}>3. 화면 이탈·앱 백그라운드 전환 후 네트워크 중단·복귀 동작</Text>
          <Text style={styles.note}>4. 9~10주차 인증된 API 실연동 및 푸시는 별도 범위</Text>
        </View>
        <Text style={styles.footer}>기존 Mock 검사 기록·PASS/FAIL·AsyncStorage·품질 통계는 수정하지 않습니다. 실패 시 마지막 성공 데이터를 보존하며 오래된 정보일 수 있음을 표시해야 합니다.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}
const styles = StyleSheet.create({
  screen:{flex:1,backgroundColor:'#F4F6FB'},
  content:{paddingHorizontal:20,paddingTop:28,paddingBottom:56,gap:17},
  heading:{paddingRight:66,color:'#172033',fontSize:25,fontWeight:'800',lineHeight:36},
  sub:{color:'#667895',fontSize:14},
  highlight:{backgroundColor:'#EAF0FF',padding:20,borderRadius:18,gap:12},
  highlightTitle:{color:'#2054CB',fontWeight:'800',fontSize:22},
  note:{color:'#667895',fontSize:14,lineHeight:23},
  card:{padding:18,borderRadius:18,borderWidth:1,borderColor:'#DBE2ED',backgroundColor:'#FFF',gap:14},
  cardTitle:{fontSize:18,fontWeight:'700',color:'#172033'},
  line:{fontSize:14,color:'#253145',lineHeight:23},
  error:{color:'#B42318',fontSize:14,lineHeight:22},
  buttonRow:{flexDirection:'row',gap:8},
  button:{backgroundColor:'#2456E4',paddingHorizontal:9,paddingVertical:13,borderRadius:10,flex:1,alignItems:'center'},
  buttonText:{color:'white',fontWeight:'700',fontSize:12},
  outline:{borderWidth:1,borderColor:'#B7C5E2',padding:14,borderRadius:10,alignItems:'center'},
  outlineText:{color:'#2054CB',fontWeight:'700',fontSize:13},
  event:{backgroundColor:'#F4F6FB',color:'#253145',fontSize:13,padding:9,borderRadius:7},
  checkLine:{flexDirection:'row',gap:10,alignItems:'flex-start'},
  tick:{fontWeight:'800',fontSize:19,width:25},
  checkText:{flex:1,color:'#253145',fontSize:14,lineHeight:23},
  footer:{color:'#657891',fontSize:12,lineHeight:20},
});
