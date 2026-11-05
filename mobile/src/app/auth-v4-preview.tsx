import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { makeLoginBody, parseTokenReply } from '../api/backendV4/authCore';
import { parseApiV4Error, unwrapApiV4Data } from '../api/backendV4/httpCore';

/** API 서버·실제 계정·토큰을 전혀 사용하지 않는 계약 점검 화면 */
const checks = [
  {
    label: '로그인 요청 필드 loginId / password',
    ok: (() => { const b = makeLoginBody('sample-worker', 'EXAMPLE_ONLY'); return b.loginId === 'sample-worker' && !('username' in b); })(),
  },
  {
    label: '성공 응답 { data } 해제',
    ok: unwrapApiV4Data<{ value: number }>({ data: { value: 8 } }).value === 8,
  },
  {
    label: '오류 응답 code / traceId 구분',
    ok: (() => { const e = parseApiV4Error(403, { error: { code: 'ACCESS_DENIED', message: '권한 없음', traceId: 'trace-example' } }); return e.httpStatus === 403 && e.code === 'ACCESS_DENIED' && e.traceId === 'trace-example'; })(),
  },
  {
    label: '역할 필드 없으면 추측하지 않음',
    ok: parseTokenReply({ accessToken: 'EXAMPLE_ACCESS', refreshToken: 'EXAMPLE_REFRESH' }, null).role === null,
  },
  {
    label: 'Access Token/Refresh Token 분리',
    ok: (() => { const s = parseTokenReply({ accessToken: 'EXAMPLE_A', refreshToken: 'EXAMPLE_R' }, null); return s.accessToken === 'EXAMPLE_A' && s.refreshToken === 'EXAMPLE_R'; })(),
  },
];

export default function AuthV4PreviewScreen() {
  const passed = checks.filter((c) => c.ok).length;
  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.heading}>인증 API v4 사전 점검</Text>
        <Text style={styles.subheading}>서버 연결 전 · 가상 응답만 사용</Text>
        <View style={styles.highlight}>
          <Text style={styles.highlightTitle}>테스트 결과: {passed}/{checks.length}개 통과</Text>
          <Text style={styles.note}>로그인·JWT 저장·토큰 갱신·실제 서버 요청은 아직 실행하지 않았습니다.</Text>
        </View>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>인증 계약 확인</Text>
          {checks.map((c) => (
            <View style={styles.checkRow} key={c.label}>
              <Text style={[styles.checkMark, { color: c.ok ? '#0D8555' : '#B42318' }]}>{c.ok ? '✓' : '✕'}</Text>
              <Text style={styles.checkText}>{c.label}</Text>
            </View>
          ))}
        </View>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>백엔드 확인 전까지 보류</Text>
          <Text style={styles.note}>1. /auth/login의 role·loginId 응답 구조</Text>
          <Text style={styles.note}>2. /auth/refresh의 요청 본문 및 토큰 회전</Text>
          <Text style={styles.note}>3. /auth/logout의 요청 본문</Text>
          <Text style={styles.note}>4. 실제 로그인·401 재발급·로그아웃 서버 테스트 (9~10주차)</Text>
        </View>
        <Text style={styles.footer}>기존 Mock 로그인·검사·품질 통계는 변경되지 않습니다.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F4F6FB' },
  content: { paddingHorizontal: 22, paddingTop: 24, paddingBottom: 48, gap: 16 },
  heading: { color: '#121B2C', fontSize: 27, fontWeight: '800' },
  subheading: { color: '#667895', fontSize: 14 },
  highlight: { backgroundColor: '#EAF0FF', borderRadius: 17, padding: 19, gap: 10 },
  highlightTitle: { color: '#2054CB', fontSize: 20, fontWeight: '700' },
  card: { backgroundColor: '#FFF', borderColor: '#DBE2ED', borderWidth: 1, borderRadius: 17, padding: 18, gap: 13 },
  cardTitle: { color: '#152032', fontSize: 18, fontWeight: '700' },
  checkRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 9 },
  checkMark: { fontSize: 18, fontWeight: '700', width: 24 },
  checkText: { color: '#253145', fontSize: 14, flex: 1, lineHeight: 22 },
  note: { color: '#596D89', fontSize: 14, lineHeight: 22 },
  footer: { color: '#667895', fontSize: 12, lineHeight: 20 },
});
