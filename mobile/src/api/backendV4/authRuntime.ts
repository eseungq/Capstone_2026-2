
import { createAuthV4 } from './authCore';
import { makeSecureAuthVault } from './secureAuthVault';

// Expo가 .env.local에서 읽는 백엔드 API 기본 주소
export const API_BASE_URL =
  (process.env.EXPO_PUBLIC_API_URL ?? '')
    .trim()
    .replace(/\/+$/, '');

// 실제 서버 인증 + iPhone 보안 저장소 연결

export const authV4 = createAuthV4({
  baseUrl: API_BASE_URL,
  vault: makeSecureAuthVault(),
  refreshBody: (refreshToken) => ({ refreshToken }),
  logoutBody: (refreshToken) => ({ refreshToken }),
});

