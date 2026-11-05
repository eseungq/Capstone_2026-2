import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { decodeHistoryPageV4, decodeMonitoringPartsV4, decodeQueuePageV4, imageNeedsDetailRefetchV4, makeHistoryQueryV4, makeQueueQueryV4, listItemTitleV4 } from '../api/backendV4/inspectionReadCore';
import { contractDetailExamplesV4, contractHistoryExamplesV4, contractPartsExamplesV4, contractQueueExamplesV4 } from '../api/backendV4/inspectionReadExamples';
import { adaptInspectionDetailResponseV4 } from '../api/backendV4/adapter';

/** 네트워크/로그인/JWT/AsyncStorage 사용 없이 즉시 확인하는 사전 테스트 */
function makeChecks() {
  const detail = contractDetailExamplesV4[0];
  const historyPage = decodeHistoryPageV4({ items: contractHistoryExamplesV4.slice(0, 2), hasNext: true, totalElements: 5 }, 0, 2);
  const queuePage = decodeQueuePageV4({ items: contractQueueExamplesV4, nextCursor: null });
  const parts = decodeMonitoringPartsV4(contractPartsExamplesV4);
  return [
    { name: '검사 이력 페이지(page=0, size=20)', ok: makeHistoryQueryV4({page:0}).includes('page=0&size=20') },
    { name: '검사 이력 응답 items 및 다음 페이지', ok: historyPage.items.length === 2 && historyPage.hasNext === true },
    { name: '확인 필요 목록 cursor/size 분리', ok: makeQueueQueryV4({type:'REVIEW',cursor:'test +/'}).includes('cursor=test%20%2B%2F') },
    { name: 'REVIEW/FAILED 대기 목록 구분', ok: queuePage.items.length === 2 && queuePage.items.every(x=>x.displayState === 'REVIEW_PENDING' || x.displayState === 'FAILED') },
    { name: 'DOOR 공정 카드·최근 이미지 목록', ok: parts.length === 1 && parts[0].recent.length === 5 },
    { name: '서버 UUID와 검사 표시 번호 구분', ok: detail.inspectionId !== detail.inspectionNo && adaptInspectionDetailResponseV4({data:detail}).inspectionNo === detail.inspectionNo },
    { name: '검사번호 미제공 시 임의 생성 안 함', ok: listItemTitleV4(null).includes('미제공') },
    { name: '서명 이미지 만료 30초 전 재조회 판단', ok: imageNeedsDetailRefetchV4('2026-10-28T12:00:00+09:00',false,Date.parse('2026-10-28T11:59:40+09:00')) },
    { name: '검증되지 않은 AUTO_PASS 예시 구분', ok: contractDetailExamplesV4[2].displayState === 'AUTO_PASS' },
  ];
}

export default function InspectionReadV4PreviewScreen() {
  const checks = makeChecks();
  const passed = checks.filter((x) => x.ok).length;
  return (
    <SafeAreaView style={styles.screen} edges={['top','bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.heading}>검사 조회 API v4 사전 점검</Text>
        <Text style={styles.sub}>서버 연결 전 · 계약 예시 데이터만 사용</Text>
        <View style={styles.highlight}>
          <Text style={styles.highlightTitle}>테스트 결과: {passed}/{checks.length}개 통과</Text>
          <Text style={styles.note}>지금은 실제 검사 조회, 이미지 다운로드, 서버 폴링을 실행하지 않습니다.</Text>
        </View>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>검사 목록·상세·모니터링 점검</Text>
          {checks.map((x) => (
            <View key={x.name} style={styles.line}>
              <Text style={[styles.tick, {color:x.ok?'#088557':'#B42318'}]}>{x.ok?'✓':'✕'}</Text>
              <Text style={styles.lineText}>{x.name}</Text>
            </View>
          ))}
        </View>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>백엔드 확인 후 연동할 항목</Text>
          <Text style={styles.note}>1. GET /inspections의 페이지 응답 구조(items 또는 content, hasNext/totalElements)</Text>
          <Text style={styles.note}>2. 목록·모니터링 recent/queue의 inspectionNo 포함 여부</Text>
          <Text style={styles.note}>3. thumbnailUrl 만료 규칙과 이미지 오류 시 상세 재조회 방식</Text>
          <Text style={styles.note}>4. 실제 서버 로그인 후 GET 이력·상세·parts·queue 통합 테스트 (9~10주차)</Text>
        </View>
        <Text style={styles.footer}>기존 Mock 데이터, PASS/FAIL 판정 기록과 품질 통계는 변경되지 않습니다. 예시 AUTO_PASS는 실제 검증된 운영 결과가 아닙니다.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}
const styles = StyleSheet.create({
  screen: {flex:1,backgroundColor:'#F4F6FB'},
  content: {paddingHorizontal:22,paddingTop:24,paddingBottom:48,gap:16},
  heading: {color:'#121B2C',fontSize:25,fontWeight:'800'},
  sub: {color:'#667895',fontSize:14},
  highlight: {backgroundColor:'#EAF0FF',borderRadius:17,padding:19,gap:10},
  highlightTitle: {color:'#2054CB',fontSize:20,fontWeight:'700'},
  note: {color:'#596D89',fontSize:14,lineHeight:22},
  card: {backgroundColor:'#FFF',borderColor:'#DBE2ED',borderWidth:1,borderRadius:17,padding:18,gap:14},
  cardTitle: {color:'#152032',fontSize:18,fontWeight:'700'},
  line: {flexDirection:'row',gap:10,alignItems:'flex-start'},
  tick: {width:24,fontSize:18,fontWeight:'700'},
  lineText: {flex:1,color:'#253145',fontSize:14,lineHeight:22},
  footer: {color:'#667895',fontSize:12,lineHeight:20},
});
