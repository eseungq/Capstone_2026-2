import { requestApiV4, ApiV4RequestError } from './httpCore';
import type { ApiFetch, BodyMode } from './httpCore';

/** 로그인 요청의 loginId 필드만 계약 v4에서 확정됨. */
export function makeLoginBody(loginId: string, password: string) {
  if (!loginId.trim() || !password) throw new Error('로그인 ID와 비밀번호가 필요합니다.');
  return { loginId: loginId.trim(), password };
}

export type BackendRole = 'WORKER' | 'ADMIN' | 'DEVICE';
export interface AuthSessionV4 {
  accessToken: string;
  refreshToken: string;
  role: BackendRole | null; // 실제 응답 위치 미확정: 추측해서 ADMIN/WORKER로 설정하지 않음
  loginId: string | null;
}
export interface AuthVault {
  read(): Promise<AuthSessionV4 | null>;
  write(session: AuthSessionV4): Promise<void>;
  clear(): Promise<void>;
}
export interface AuthPublicState {
  signedIn: boolean;
  role: BackendRole | null;
  loginId: string | null;
}


type TokenReply = {
  accessToken?: unknown;
  refreshToken?: unknown;
  role?: unknown;
  loginId?: unknown;
  user?: unknown;
};


export class AuthContractPendingError extends Error {
  constructor(message: string) { super(message); this.name = 'AuthContractPendingError'; }
}

function isObject(value: unknown): value is TokenReply {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function asRole(value: unknown): BackendRole | null {
  return value === 'WORKER' || value === 'ADMIN' || value === 'DEVICE' ? value : null;
}

/**
 * 현재 확인 가능한 accessToken; refreshToken/role 위치는 승규님 실제 응답 확인 전 가정하지 않음.
 * 첫 로그인은 refreshToken이 없으면 안전하게 실패시켜 인증 상태를 잘못 유지하지 않음.
 * Refresh 응답에서 새 refreshToken이 없으면 이전 refreshToken을 유지 (회전 지원).
 */
export function parseTokenReply(
  data: unknown,
  previous: AuthSessionV4 | null,
  submittedLoginId: string | null = null,
): AuthSessionV4 {
  if (!isObject(data) || typeof data.accessToken !== 'string' || !data.accessToken) {
    throw new AuthContractPendingError('로그인/갱신 응답의 data.accessToken 형식을 확인해야 합니다.');
  }
  const refreshToken =
    typeof data.refreshToken === 'string' && data.refreshToken
      ? data.refreshToken
      : previous?.refreshToken;
  if (!refreshToken) {
    throw new AuthContractPendingError('data.refreshToken 위치를 백엔드와 확인해야 합니다. 임의 토큰으로 로그인하지 않습니다.');
  }
  
  const user = isObject(data.user) ? data.user : null;

  return {
    accessToken: data.accessToken,
    refreshToken,
    role: (user ? asRole(user.role) : null)
      ?? asRole(data.role)
      ?? previous?.role
      ?? null,
    loginId:
      user && typeof user.loginId === 'string'
        ? user.loginId
        : typeof data.loginId === 'string'
          ? data.loginId
          : previous?.loginId ?? submittedLoginId,
  };

}

export interface AuthV4Config {
  baseUrl: string; // 서버 연결 시 외부 설정. 소스 코드에 IP/비밀정보 입력 금지
  vault: AuthVault; // iOS/Android 운영 테스트에서는 makeSecureAuthVault() 사용
  fetchImpl?: ApiFetch;
  /** 실제 /auth/refresh 요청 본문 확인 후에만 지정. 예: (token) => ({ refreshToken: token }) — 미확정 예시 */
  refreshBody?: (refreshToken: string) => unknown;
  /** 실제 /auth/logout 요청 본문 확인 후에만 지정. 없으면 서버 로그아웃을 시도하지 않음. */
  logoutBody?: (refreshToken: string) => unknown;
}

function publicState(s: AuthSessionV4 | null): AuthPublicState {
  return { signedIn: s !== null, role: s?.role ?? null, loginId: s?.loginId ?? null };
}

export function createAuthV4(config: AuthV4Config) {
  let refreshInFlight: Promise<AuthSessionV4> | null = null;
  let epoch = 0; // 로그아웃 중 기존 비동기 갱신이 토큰을 되살리지 못하도록 차단

  const api = <T>(path: string, method: 'GET' | 'POST', body: unknown, token: string | null, mode: BodyMode = 'data') =>
    requestApiV4<T>(config.baseUrl, { path, method, body, token, mode, fetchImpl: config.fetchImpl });

  async function login(loginId: string, password: string): Promise<AuthPublicState> {
    const startedEpoch = ++epoch;
    const data = await api<unknown>('/auth/login', 'POST', makeLoginBody(loginId, password), null);
    const parsed = parseTokenReply(data, null, loginId.trim());
    if (startedEpoch !== epoch) throw new Error('다른 인증 작업이 진행되어 이전 로그인 응답을 폐기했습니다.');
    await config.vault.write(parsed);
    return publicState(parsed);
  }

  async function restore(): Promise<AuthPublicState> {
    return publicState(await config.vault.read());
  }

  async function refreshAccessToken(): Promise<AuthSessionV4> {
    if (refreshInFlight) return refreshInFlight;
    const startedEpoch = epoch;
    const work = (async () => {
      const before = await config.vault.read();
      if (!before) throw new ApiV4RequestError(401, 'NOT_LOGGED_IN', '로그인이 필요합니다.', null);
      if (!config.refreshBody) {
        throw new AuthContractPendingError('백엔드 /auth/refresh 요청 본문을 확인한 후 refreshBody를 지정해 주세요.');
      }
      try {
        const data = await api<unknown>('/auth/refresh', 'POST', config.refreshBody(before.refreshToken), null);
        const next = parseTokenReply(data, before);
        if (startedEpoch !== epoch) throw new Error('로그아웃 이후 도착한 토큰 갱신 결과를 폐기했습니다.');
        await config.vault.write(next);
        return next;
      } catch (err) {
        if (err instanceof ApiV4RequestError && err.httpStatus === 401 && startedEpoch === epoch) {
          await config.vault.clear();
        }
        throw err;
      }
    })();
    refreshInFlight = work;
    try { return await work; }
    finally { if (refreshInFlight === work) refreshInFlight = null; }
  }

  async function authorizedRequest<T>(
    path: string,
    opts: { method?: 'GET' | 'POST'; body?: unknown; mode?: BodyMode } = {},
  ): Promise<T> {
    const current = await config.vault.read();
    if (!current) throw new ApiV4RequestError(401, 'NOT_LOGGED_IN', '로그인이 필요합니다.', null);
    const method = opts.method ?? 'GET';
    const mode = opts.mode ?? 'data';
    try {
      return await api<T>(path, method, opts.body, current.accessToken, mode);
    } catch (err) {
      if (!(err instanceof ApiV4RequestError) || err.httpStatus !== 401) throw err;
      // 동일한 세션의 동시 요청에 401이 발생하면 이미 갱신된 토큰을 재사용
      const stored = await config.vault.read();
      if (!stored) throw err;
      const after = stored.accessToken !== current.accessToken ? stored : await refreshAccessToken();
      // 1회만 재시도하며 401 재귀 갱신은 금지
      return api<T>(path, method, opts.body, after.accessToken, mode);
    }
  }

  async function logout(): Promise<{ remoteRevoked: boolean }> {
    ++epoch;
    const active = await config.vault.read();
    let remoteRevoked = false;
    try {
      if (active && config.logoutBody) {
        await api<void>('/auth/logout', 'POST', config.logoutBody(active.refreshToken), active.accessToken, 'empty');
        remoteRevoked = true;
      }
    } catch {
      // 네트워크 실패여도 기기 토큰은 즉시 삭제. 서버 토큰 폐기를 성공했다고 표시하지 않음.
    } finally {
      await config.vault.clear();
    }
    return { remoteRevoked };
  }

  return { login, restore, refreshAccessToken, authorizedRequest, logout };
}

/** 테스트에서만 사용: 실제 JWT 보관에는 사용하지 마세요. */
export function makeMemoryAuthVault(): AuthVault {
  let session: AuthSessionV4 | null = null;
  return {
    async read() { return session ? { ...session } : null; },
    async write(s) { session = { ...s }; },
    async clear() { session = null; },
  };
}
