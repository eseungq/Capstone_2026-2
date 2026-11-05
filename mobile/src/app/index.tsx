
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

  // Mock 로그인: 실제 서버 인증은 아직 연결하지 않음
  const handleLogin = () => {
    if (!username.trim() || !password) {
      Alert.alert(
        '입력 확인',
        '아이디와 비밀번호를 입력하세요.'
      );
      return;
    }

    // admin 계정은 관리자 화면,
    // 나머지 계정은 작업자 화면으로 이동
    const role =
      username.trim().toLowerCase() === 'admin'
        ? 'ADMIN'
        : 'WORKER';

    router.replace({
      pathname: '/monitoring',
      params: { role },
    });
  };

  // 관리자 화면 시연용 이동
  const handleAdminPreview = () => {
    router.replace({
      pathname: '/monitoring',
      params: { role: 'ADMIN' },
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

          {/* 관리자 시연 버튼 */}
          <Pressable
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
