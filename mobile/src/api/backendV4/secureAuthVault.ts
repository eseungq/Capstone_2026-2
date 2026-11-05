/**
 * Expo SecureStore 기반 실제 기기용 토큰 저장소.
 * 사용 전 VS Code 터미널: npx expo install expo-secure-store
 * 웹 지원은 이 단계 범위 밖이며, AsyncStorage에 JWT를 저장하지 않습니다.
 */
import * as SecureStore from 'expo-secure-store';
import type { AuthSessionV4, AuthVault } from './authCore';

const SESSION_KEY = 'capstone.v4.auth.session';

function validSession(value: unknown): value is AuthSessionV4 {
  if (!value || typeof value !== 'object') return false;
  const v = value as Partial<AuthSessionV4>;
  return typeof v.accessToken === 'string' && v.accessToken.length > 0 &&
    typeof v.refreshToken === 'string' && v.refreshToken.length > 0 &&
    (v.role === null || v.role === 'WORKER' || v.role === 'ADMIN' || v.role === 'DEVICE') &&
    (v.loginId === null || typeof v.loginId === 'string');
}

export function makeSecureAuthVault(): AuthVault {
  return {
    async read() {
      const stored = await SecureStore.getItemAsync(SESSION_KEY);
      if (!stored) return null;
      try {
        const parsed: unknown = JSON.parse(stored);
        return validSession(parsed) ? parsed : null;
      } catch { return null; }
    },
    async write(value) {
      await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(value), {
        keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
      });
    },
    async clear() { await SecureStore.deleteItemAsync(SESSION_KEY); },
  };
}
