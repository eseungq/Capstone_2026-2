
import { authV4 } from '../api/backendV4/authRuntime';

import { useState } from 'react';
import { Stack, useRouter } from 'expo-router';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function LoginScreen() {
  const router = useRouter();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

// 실제 백엔드 로그인: 인증 성공 후 모니터링 화면으로 이동
const handleLogin = async () => {
  if (!username.trim() || !password) {
    Alert.alert('입력 확인', '아이디와 비밀번호를 입력하세요.');
    return;
  }

  try {
    // 실제 백엔드 인증 요청
    const session = await authV4.login(username, password);

    // 실제 서버가 전달한 권한만 사용
    if (session.role !== 'WORKER' && session.role !== 'ADMIN') {
      Alert.alert(
        '서버 권한 확인 필요',
        '로그인 요청은 성공했지만 사용자 권한을 확인할 수 없습니다. 백엔드 응답 형식을 확인해 주세요.',
      );
      return;
    }

    // 인증 성공 후 모니터링 화면으로 이동
    router.replace({
  pathname: '/monitoring',
  params: {
    role: session.role,
    mode: 'live',
  },
});
  } catch (error) {
    Alert.alert(
      '로그인 실패',
      error instanceof Error
        ? error.message
        : '서버와 연결할 수 없습니다.',
    );
  }
};


  // 서버 로그인 없이 화면 권한 표시만 확인하기 위한 독립 Mock WORKER 진입.
  // 실제 인증 세션이나 백엔드의 권한을 변경하지 않습니다.
  const handleWorkerPreview = () => {
    router.replace({
      pathname: '/monitoring',
      params: { role: 'WORKER', mode: 'mock' },
    });
  };

  // 관리자 화면 시연용 이동
  const handleAdminPreview = () => {
    router.replace({
  pathname: '/monitoring',
  params: {
    role: 'ADMIN',
    mode: 'mock',
  },
});
  };

  return (
    <SafeAreaView style={styles.screen}>
      <Stack.Screen options={{ headerShown: false }} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={
          Platform.OS === 'ios' ? 'padding' : undefined
        }
      >
        <ScrollView
          contentContainerStyle={styles.container}
          keyboardShouldPersistTaps="handled"
        >
          {/* 화면 제목 */}
          <Text style={styles.title}>
            AI 공정 모니터링
          </Text>

          <Text style={styles.subtitle}>
            자동차 부품 검사 · 모바일 프로토타입
          </Text>

          {/* 서비스 소개 */}
          <View style={styles.intro}>
            <Text style={styles.cardTitle}>
              현장 공정 모니터링
            </Text>

            <Text style={styles.description}>
              부품별 검사 결과와 확인 필요 알림을
              한 화면에서 확인합니다.
            </Text>
          </View>

          {/* 로그인 입력 */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>
              계정 로그인
            </Text>

            <Text style={styles.label}>
              아이디
            </Text>

            <TextInput
              style={styles.input}
              placeholder="아이디를 입력하세요"
              placeholderTextColor="#64748B"
              value={username}
              onChangeText={setUsername}
              autoCapitalize="none"
              autoCorrect={false}
            />

            <Text style={styles.label}>
              비밀번호
            </Text>

            <TextInput
              style={styles.input}
              placeholder="비밀번호를 입력하세요"
              placeholderTextColor="#64748B"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />
          </View>

          {/* 로그인 버튼 */}
          <Pressable
            style={styles.loginButton}
            onPress={handleLogin}
          >
            <Text style={styles.buttonText}>
              로그인
            </Text>
          </Pressable>

          {/* 계정 권한별 설명 */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>
              계정 권한별 진입
            </Text>

            <View style={styles.roleRow}>
              <Text style={styles.description}>
                현장 작업자
              </Text>

              <Text style={styles.roleValue}>
                모니터링 · 판정 · 이력
              </Text>
            </View>

            <View style={styles.roleRow}>
              <Text style={styles.description}>
                시스템 관리자
              </Text>

              <Text style={styles.roleValue}>
                전체 조회 · 정책 관리
              </Text>
            </View>
          </View>

          {/* 시연 상태 */}
          <View style={styles.notice}>
            <Text style={styles.noticeText}>
              화면 설계 · 계정 인증 및 API 연결은
              별도 검증 대상
            </Text>
          </View>

          {/* Mock WORKER와 ADMIN 역할별 진입: 실서버 인증이 아닙니다. */}
          <Pressable
            accessibilityRole="button"
            style={styles.previewButton}
            onPress={handleWorkerPreview}
          >
            <Text style={styles.previewText}>
              현장 작업자 시연으로 이동 · Mock
            </Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            style={styles.previewButton}
            onPress={handleAdminPreview}
          >
            <Text style={styles.previewText}>
              시스템 관리자 시연으로 이동 · Mock
            </Text>
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#F5F7FB',
  },

  container: {
    flexGrow: 1,
    paddingHorizontal: 20,
    paddingTop: 28,
    paddingBottom: 40,
    gap: 10,
  },

  title: {
    fontSize: 23,
    fontWeight: '700',
    color: '#111827',
  },

  subtitle: {
    fontSize: 11,
    color: '#64748B',
    marginBottom: 62,
  },

  intro: {
    backgroundColor: '#EBF1FF',
    borderWidth: 1,
    borderColor: '#E4E7EC',
    borderRadius: 14,
    padding: 13,
    gap: 8,
  },

  card: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E4E7EC',
    borderRadius: 14,
    padding: 13,
    gap: 7,
  },

  cardTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#111827',
  },

  description: {
    fontSize: 11,
    color: '#64748B',
    lineHeight: 18,
    flexShrink: 1,
  },

  label: {
    fontSize: 12,
    fontWeight: '500',
    color: '#64748B',
    marginTop: 12,
    marginBottom: 2,
    paddingTop: 3,
    lineHeight: 19,
  },

  input: {
    height: 50,
    borderWidth: 1,
    borderColor: '#E4E7EC',
    backgroundColor: '#EEF2F8',
    borderRadius: 9,
    paddingHorizontal: 14,
    paddingVertical: 0,
    fontSize: 13,
    color: '#111827',
  },

  loginButton: {
    height: 44,
    backgroundColor: '#2054D8',
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },

  buttonText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '700',
  },

  roleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 4,
    gap: 8,
  },

  roleValue: {
    fontSize: 11,
    color: '#111827',
    fontWeight: '500',
    textAlign: 'right',
    flexShrink: 1,
  },

  notice: {
    backgroundColor: '#EBF1FF',
    borderRadius: 10,
    padding: 10,
  },

  noticeText: {
    fontSize: 10,
    color: '#2054D8',
  },

  previewButton: {
    height: 40,
    backgroundColor: '#FFFFFF',
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },

  previewText: {
    color: '#2054D8',
    fontSize: 12,
  },
});
