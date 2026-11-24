import { requestApiV4, ApiV4RequestError } from './httpCore';
import type { ApiFetch, BodyMode } from './httpCore';

/** 로그인 요청의 loginId 필드만 계약 v4에서 확정됨. */
export function makeLoginBody(loginId: string, password: string) {
  if (!loginId.trim() || !password) throw new Error('로그인 ID와 비밀번호가 필요합니다.');
  return { loginId: loginId.trim(), password };
}

type MobileRole = 'WORKER' | 'ADMIN';
export type BackendRole = MobileRole | 'DEVICE';
export interface AuthSessionV4 {
  accessToken: string;
  refreshToken: string;
  role: BackendRole | null;
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

export class UnsupportedMobileRoleError extends Error {
  constructor() {
    super('모바일 앱은 작업자 또는 관리자 계정으로 이용할 수 있습니다.');
    this.name = 'UnsupportedMobileRoleError';
  }
}

function isMobileRole(role: BackendRole | null): role is MobileRole {
  return role === 'WORKER' || role === 'ADMIN';
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
  const returnedRole = user?.role === undefined ? data.role : user.role;

  return {
    accessToken: data.accessToken,
    refreshToken,
    role: returnedRole === undefined ? previous?.role ?? null : asRole(returnedRole),
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
  let epoch = 0;
  let changingSession = false;
  let vaultTail = Promise.resolve();
  const listeners = new Set<() => void>();

  // Serialize storage operations so a delayed write cannot undo a later clear.
  function withVault<T>(operation: () => Promise<T>): Promise<T> {
    const result = vaultTail.then(operation);
    vaultTail = result.then(() => {}, () => {});
    return result;
  }

  function beginChange() {
    changingSession = true;
    refreshInFlight = null;
    return ++epoch;
  }

  function finishChange(generation: number) {
    if (generation !== epoch) return;
    changingSession = false;
    listeners.forEach(listener => listener());
  }

  function requireCurrent(generation: number) {
    if (generation !== epoch || changingSession) {
      throw new ApiV4RequestError(401, 'SESSION_CHANGED', '로그인 상태가 변경됐습니다. 현재 계정에서 다시 시도해 주세요.', null);
    }
  }

  const api = <T>(path: string, method: 'GET' | 'POST', body: unknown, token: string | null, mode: BodyMode = 'data', signal?: AbortSignal) =>
    requestApiV4<T>(config.baseUrl, { path, method, body, token, mode, signal, fetchImpl: config.fetchImpl });

  // Revoke exactly this token pair, regardless of which account is now on the device.
  async function revokeServerSession(session: AuthSessionV4): Promise<boolean> {
    if (!config.logoutBody) return false;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      await api<void>('/auth/logout', 'POST', config.logoutBody(session.refreshToken), session.accessToken, 'empty', controller.signal);
      return true;
    } catch {
      return false;
    } finally {
      clearTimeout(timeout);
    }
  }

  // Older builds could have persisted a device or unidentified account.
  function readMobileSession(): Promise<AuthSessionV4 | null> {
    return withVault(async () => {
      const session = await config.vault.read();
      if (!session || isMobileRole(session.role)) return session;
      await config.vault.clear();
      return null;
    });
  }

  async function login(loginId: string, password: string): Promise<AuthPublicState & { role: MobileRole }> {
    const generation = beginChange();
    try {
      const data = await api<unknown>('/auth/login', 'POST', makeLoginBody(loginId, password), null);
      const parsed = parseTokenReply(data, null, loginId.trim());
      const role = parsed.role;
      if (!isMobileRole(role)) {
        void revokeServerSession(parsed);
        if (generation !== epoch) throw new Error('이전 로그인 요청이 취소됐습니다.');
        throw new UnsupportedMobileRoleError();
      }
      await withVault(async () => {
        if (generation !== epoch) throw new Error('이전 로그인 요청이 취소됐습니다.');
        await config.vault.write(parsed);
      });
      if (generation !== epoch) throw new Error('이전 로그인 요청이 취소됐습니다.');
      return { signedIn: true, role, loginId: parsed.loginId };
    } finally {
      finishChange(generation);
    }
  }

  async function restore(): Promise<AuthPublicState> {
    const generation = epoch;
    if (changingSession) return publicState(null);
    const session = await readMobileSession();
    return publicState(generation === epoch && !changingSession ? session : null);
  }

  async function refreshAccessToken(): Promise<AuthSessionV4> {
    const generation = epoch;
    requireCurrent(generation);
    if (refreshInFlight) return refreshInFlight;
    const work = (async () => {
      const before = await readMobileSession();
      requireCurrent(generation);
      if (!before) throw new ApiV4RequestError(401, 'NOT_LOGGED_IN', '로그인이 필요합니다.', null);
      if (!config.refreshBody) throw new AuthContractPendingError('인증 갱신 설정이 필요합니다.');
      try {
        const data = await api<unknown>('/auth/refresh', 'POST', config.refreshBody(before.refreshToken), null);
        const next = parseTokenReply(data, before);
        if (!isMobileRole(next.role)) {
          void revokeServerSession(next);
          throw new UnsupportedMobileRoleError();
        }
        await withVault(async () => {
          requireCurrent(generation);
          await config.vault.write(next);
        });
        requireCurrent(generation);
        return next;
      } catch (err) {
        const expiredOrLocked = err instanceof ApiV4RequestError &&
          (err.httpStatus === 401 || (err.httpStatus === 423 && err.code === 'AUTH_ACCOUNT_LOCKED'));
        if ((expiredOrLocked || err instanceof UnsupportedMobileRoleError) && generation === epoch) {
          const expired = beginChange();
          try { await withVault(() => config.vault.clear()); }
          finally { finishChange(expired); }
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
    const generation = epoch;
    requireCurrent(generation);
    const current = await readMobileSession();
    requireCurrent(generation);
    if (!current) throw new ApiV4RequestError(401, 'NOT_LOGGED_IN', '로그인이 필요합니다.', null);
    const send = (token: string) => api<T>(path, opts.method ?? 'GET', opts.body, token, opts.mode ?? 'data');
    let response: T;
    try {
      response = await send(current.accessToken);
    } catch (err) {
      requireCurrent(generation);
      if (!(err instanceof ApiV4RequestError) || err.httpStatus !== 401) throw err;
      const stored = await readMobileSession();
      requireCurrent(generation);
      if (!stored || stored.loginId !== current.loginId || stored.role !== current.role) throw err;
      const after = stored.accessToken !== current.accessToken ? stored : await refreshAccessToken();
      requireCurrent(generation);
      response = await send(after.accessToken);
    }
    requireCurrent(generation);
    return response;
  }

  async function logout(): Promise<{ remoteRevoked: boolean }> {
    const generation = beginChange();
    let active: AuthSessionV4 | null;
    try {
      active = await withVault(async () => {
        // Forget the device session before waiting for the network.
        let session: AuthSessionV4 | null = null;
        try { session = await config.vault.read(); }
        catch { /* A missing or unreadable token still permits local sign-out. */ }
        await config.vault.clear();
        return session;
      });
    } finally {
      finishChange(generation);
    }
    return { remoteRevoked: active ? await revokeServerSession(active) : false };
  }

  function subscribeSessionChange(listener: () => void) {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }

  return { login, restore, refreshAccessToken, authorizedRequest, logout, sessionEpoch: () => epoch, subscribeSessionChange };
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
