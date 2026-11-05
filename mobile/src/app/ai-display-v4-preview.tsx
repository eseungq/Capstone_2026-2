import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { formatCalibratedProbabilityV4, makeAiDisplayPresentationV4 } from '../api/backendV4/aiDisplayCore';
import { aiDisplayExampleV4 as ex, camShowcaseCasesV4 } from '../api/backendV4/aiDisplayExamples';

function checks() {
  const good = makeAiDisplayPresentationV4(ex.goodReview);
  const cam = makeAiDisplayPresentationV4(ex.defectWithCam);
  const camFail = makeAiDisplayPresentationV4(ex.defectCamFailed);
  const noResponse = makeAiDisplayPresentationV4(ex.defectConstantCamDemo);
  const zero = makeAiDisplayPresentationV4(ex.goodReviewWithZeroCalibratedDemo);
  const workerFail = makeAiDisplayPresentationV4(ex.goodReviewWorkerFail);
  const error = makeAiDisplayPresentationV4(ex.failedAnalysis);
  const pending = makeAiDisplayPresentationV4(ex.pending);
  const unknown = makeAiDisplayPresentationV4(ex.defectUnknownCam);
  const invalid = makeAiDisplayPresentationV4(ex.invalidGoodCam);
  return [
    {label:'GOOD + REVIEW는 CAM 미생성이 정상',ok:good.cam.state==='NOT_REQUIRED' && good.policyActionText.includes('REVIEW')},
    {label:'GOOD 예측을 최종 PASS로 간주하지 않음',ok:good.aiPrediction==='GOOD' && good.finalJudgementText==='미확정'},
    {label:'DEFECT CAM 성공은 참고 이미지로만 표시',ok:cam.cam.state==='AVAILABLE' && cam.cam.showInterpretationDisclaimer && cam.cam.imageUrl!==null},
    {label:'DEFECT CAM 실패 시 AI 분류 결과 유지',ok:camFail.cam.state==='GENERATION_FAILED' && camFail.aiPrediction==='DEFECT' && camFail.policyActionText.includes('REVIEW')},
    {label:'0/상수맵은 계산 실패가 아닌 별도 안내',ok:noResponse.cam.state==='NO_SPATIAL_RESPONSE' && noResponse.cam.description==='AI 예측은 완료됐지만, 위치별 강조 반응이 없어 판단 근거 이미지를 제공하기 어렵습니다.'},
    {label:'보정 확률 null을 0%로 표시하지 않음',ok:good.calibratedProbabilityText.includes('미제공') && !good.calibratedProbabilityText.startsWith('0')},
    {label:'보정 확률 0은 null과 구분 (가상값)',ok:zero.calibratedProbabilityText.startsWith('0.0%') && formatCalibratedProbabilityV4(null)!==formatCalibratedProbabilityV4(0)},
    {label:'보정기 버전 null은 미제공 처리',ok:good.calibratorVersionText==='미제공'},
    {label:'AI GOOD와 작업자 FAIL을 별도 표시',ok:workerFail.aiPrediction==='GOOD' && workerFail.finalJudgementText==='작업자 최종 FAIL'},
    {label:'분석 실패·분석 중은 AI 판정으로 오인하지 않음',ok:error.aiPrediction===null && pending.aiPrediction===null && error.cam.state==='AI_FAILED' && pending.cam.state==='PENDING'},
    {label:'CAM 상태 누락은 성공·실패로 임의 추정하지 않음',ok:unknown.cam.state==='UNKNOWN' && invalid.cam.state==='CONTRACT_MISMATCH'},
    {label:'실제 AI 지원 확인 부품은 DOOR뿐',ok:good.partSupportText.includes('지원 확인') && makeAiDisplayPresentationV4(ex.anotherPartDemo).partSupportText.includes('미확인')},
  ];
}

export default function AiDisplayV4PreviewScreen() {
  const items = checks();
  const passed = items.filter(x=>x.ok).length;
  return (
    <SafeAreaView style={styles.screen} edges={['top','bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>AI 결과·Grad-CAM 표시 점검</Text>
        <Text style={styles.subtitle}>계약 v4 · NO_ACTIVATION 추가 · 예시만 사용 · 서버 미연결</Text>
        <View style={styles.banner}>
          <Text style={styles.bannerTitle}>테스트 결과: {passed}/{items.length}개 통과</Text>
          <Text style={styles.caption}>기존 Mock 검사, 판정, 품질 통계, 이미지 저장소는 변경하지 않습니다.</Text>
        </View>
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>AI 표시 규칙 · 사전 점검</Text>
          {items.map(c=>(
            <View style={styles.checkRow} key={c.label}>
              <Text style={[styles.tick,{color:c.ok?'#088557':'#B42318'}]}>{c.ok?'✓':'✕'}</Text>
              <Text style={styles.checkLabel}>{c.label}</Text>
            </View>
          ))}
        </View>
        {camShowcaseCasesV4.map((sample,index)=>{
          const p = makeAiDisplayPresentationV4(sample.detail);
          return (
            <View style={styles.card} key={sample.label}>
              <Text style={styles.sectionTitle}>{index+1}. {sample.label}</Text>
              <Text style={styles.details}>AI 예측: {p.aiPredictionLabel}</Text>
              <Text style={styles.details}>백엔드 정책: {p.policyActionText}</Text>
              <Text style={styles.details}>최종 판정: {p.finalJudgementText}</Text>
              <Text style={styles.details}>보정 불량 확률: {p.calibratedProbabilityText}</Text>
              <Text style={styles.details}>보정기 버전: {p.calibratorVersionText}</Text>
              <View style={styles.camPanel}>
                <Text style={styles.camTitle}>Grad-CAM · {p.cam.title}</Text>
                <Text style={styles.details}>{p.cam.description}</Text>
                {p.cam.imageUrl !== null && <Text style={styles.hint}>이미지 주소만 변환됨 · 실제 다운로드하지 않음</Text>}
              </View>
              <Text style={styles.hint}>{sample.explanation}</Text>
            </View>
          );
        })}
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>백엔드 합의 후 반영할 부분</Text>
          <Text style={styles.details}>1. 승규님 서버에 NO_ACTIVATION 구현 후 실제 응답 확인 (images.gradcam = null)</Text>
          <Text style={styles.details}>2. DEFECT CAM 생성 실패의 실제 응답 처리와 이미지 URL 만료</Text>
          <Text style={styles.details}>3. 보정기 버전·보정 확률·정책 ready 근거의 실데이터 제공 여부</Text>
          <Text style={styles.details}>4. 9~10주차 실제 AI·백엔드·iPhone 연동 시험</Text>
        </View>
        <Text style={styles.footer}>주의: 이 점검은 기존 API의 변경이나 AI 추론 실행이 아니라 표시 규칙 테스트입니다. 0/상수맵은 백엔드가 명시적으로 NO_ACTIVATION을 반환할 때만 표시합니다. Grad-CAM은 결함의 정확한 위치·면적·마스크가 아닙니다.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen:{flex:1,backgroundColor:'#F4F6FB'},
  content:{paddingHorizontal:22,paddingTop:24,paddingBottom:50,gap:16},
  title:{color:'#131D30',fontSize:25,fontWeight:'800'},
  subtitle:{color:'#667995',fontSize:14,lineHeight:21},
  banner:{backgroundColor:'#EAF0FF',borderRadius:17,padding:19,gap:10},
  bannerTitle:{color:'#2054CB',fontSize:20,fontWeight:'700'},
  caption:{color:'#596D89',fontSize:14,lineHeight:22},
  card:{backgroundColor:'#FFF',borderColor:'#DBE3ED',borderWidth:1,borderRadius:17,padding:18,gap:14},
  sectionTitle:{color:'#152032',fontSize:18,fontWeight:'700'},
  checkRow:{flexDirection:'row',gap:10,alignItems:'flex-start'},
  tick:{width:24,fontSize:19,fontWeight:'700'},
  checkLabel:{flex:1,color:'#263249',fontSize:14,lineHeight:22},
  details:{color:'#536682',fontSize:14,lineHeight:22},
  hint:{color:'#7889A3',fontSize:12,lineHeight:19},
  camPanel:{backgroundColor:'#F0F4FB',padding:12,borderRadius:12,gap:7},
  camTitle:{color:'#253854',fontSize:15,fontWeight:'700'},
  footer:{color:'#667895',fontSize:12,lineHeight:20},
});
