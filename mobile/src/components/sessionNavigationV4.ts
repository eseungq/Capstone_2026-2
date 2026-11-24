import type { AuthPublicState } from '../api/backendV4/authCore';

type ObservableSession = {
  restore(): Promise<AuthPublicState>;
  subscribeSessionChange(listener: () => void): () => void;
};

// undefined is checking the vault, null is a signed-out or unsupported account.
export type NavigationSession = AuthPublicState | null | undefined;

export function requiresLiveSession(name: string, params?: Readonly<{ mode?: unknown }>): boolean {
  return name.endsWith('-live') || params?.mode === 'live';
}

// Expo Router 58 requires the existing navigator key, route names and key counter
// on RESET. Passing just { index, routes } is ignored by its native stack router.
export function resetToLoginAction(current: {
  key: string; routeNames: readonly string[]; routeKeySeq: number; stale: false;
}) {
  return { type: 'RESET', payload: { ...current, index: 0, routes: [{ name: 'index' }] } };
}

export function observeNavigationSession(
  auth: ObservableSession,
  onChange: (session: NavigationSession) => void,
): () => void {
  let version = 0;
  const refresh = () => {
    const request = ++version;
    onChange(undefined);
    void auth.restore().then((session) => {
      if (request !== version) return;
      const allowed = session.signedIn && (session.role === 'ADMIN' || session.role === 'WORKER');
      onChange(allowed ? session : null);
    }).catch(() => {
      if (request === version) onChange(null);
    });
  };
  const unsubscribe = auth.subscribeSessionChange(refresh);
  refresh();
  return () => {
    ++version;
    unsubscribe();
  };
}
