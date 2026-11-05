import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Stack, router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { adaptInspectionDetailResponseV4 } from '../api/backendV4/adapter';
import { sampleV4Responses } from '../api/backendV4/examples';

const colors = { background: '#F5F7FB', card: '#FFFFFF', ink: '#172033', muted: '#64748B',
  border: '#DEE5EF', blue: '#2054D8', light: '#EBF1FF', green: '#067647', red: '#B42318' };

// 실제 API를 호출하지 않는 순수 어댑터 점검 화면. 기존 Mock 검사 기록은 절대 변경하지 않습니다.
const checks = sampleV4Responses.map(({ title, response }) => {
  try {
    return { title, data: adaptInspectionDetailResponseV4(response), error: null as string | null };
  } catch (e) {
    return { title, data: null, error: e instanceof Error ? e.message : String(e) };
  }
});

export default function ApiV4PreviewScreen() {
  const successCount = checks.filter(x => x.data !== null).length;
  return (
    <SafeAreaView style={s.root} edges={['top', 'bottom']}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={s.body}>
        <Text style={s.title}>API v4 어댑터 점검</Text>
        <Text style={s.subtitle}>서버 연동 전 · 계약 예시 데이터만 변환</Text>
        <View style={s.banner}>
          <Text style={s.bannerText}>테스트 결과: {successCount}/{checks.length}개 변환 성공</Text>
          <Text style={s.note}>기존 Mock 기록, PASS/FAIL, 품질 통계는 변경되지 않습니다. 실제 서버에 연결된 화면이 아닙니다.</Text>
        </View>
        {checks.map((entry, index) => (
          <View key={index} style={s.card}>
            <Text style={s.cardTitle}>{entry.title}</Text>
            {entry.data ? (
              <>
                <Text style={s.line}>화면 표시: {entry.data.inspectionNo}</Text>
                <Text style={s.line}>서버 호출 ID: {entry.data.inspectionId}</Text>
                <Text style={s.line}>상태: {entry.data.displayState} ({entry.data.displayStateLabel})</Text>
                <Text style={s.line}>예측: {entry.data.prediction ?? '없음'}</Text>
                <Text style={s.line}>최종 판정: {entry.data.finalJudgement ?? '미확정'}</Text>
                <Text style={s.line}>Grad-CAM: {entry.data.gradcamStatus ?? '미제공'}</Text>
                {entry.data.reviewReasonText && <Text style={s.note}>REVIEW 사유: {entry.data.reviewReasonText}</Text>}
                {entry.data.errorMessage && <Text style={[s.note, { color: colors.red }]}>오류: {entry.data.errorMessage}</Text>}
                <Text style={s.note}>판정 후보 버튼: {entry.data.canOfferConfirm ? '표시 가능' : '표시 안 함'} / 재검사 후보: {entry.data.canOfferRetry ? '표시 가능' : '표시 안 함'}</Text>
              </>
            ) : <Text style={[s.line, { color: colors.red }]}>{entry.error}</Text>}
          </View>
        ))}
        <Text style={s.footer}>실제 로그인을 연결하기 전이므로 이 화면에서는 API 호출·정책 적용·서버 판정을 하지 않습니다.</Text>
        <Pressable style={s.button} accessibilityRole="button" onPress={() => router.back()}>
          <Text style={s.buttonText}>이전 화면으로 돌아가기</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background },
  body: { padding: 20, gap: 12, paddingBottom: 32 },
  title: { fontSize: 26, fontWeight: '700', color: colors.ink, paddingTop: 8 },
  subtitle: { fontSize: 13, color: colors.muted },
  banner: { backgroundColor: colors.light, borderRadius: 14, padding: 16, gap: 10 },
  bannerText: { color: colors.blue, fontWeight: '700', fontSize: 18 },
  card: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 14, padding: 16, gap: 7 },
  cardTitle: { fontSize: 17, fontWeight: '700', color: colors.ink },
  line: { color: colors.ink, fontSize: 12, lineHeight: 19 },
  note: { color: colors.muted, fontSize: 12, lineHeight: 19 },
  footer: { color: colors.muted, fontSize: 12, lineHeight: 19 },
  button: { padding: 16, backgroundColor: colors.blue, alignItems: 'center', borderRadius: 12 },
  buttonText: { color: '#FFFFFF', fontWeight: '700', fontSize: 15 },
});
