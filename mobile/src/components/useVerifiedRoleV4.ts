import { useCallback, useState } from 'react';
import { useFocusEffect } from 'expo-router';
import { authV4 } from '../api/backendV4/authRuntime';

/** URL의 role은 표시 권한으로 사용하지 않습니다. */
export function useVerifiedRoleV4(enabled = true) {
  const [state, setState] = useState<{checking: boolean; role: 'WORKER' | 'ADMIN' | null; epoch: number | null}>({checking: true, role: null, epoch: null});
  useFocusEffect(useCallback(() => {
    let current = true;
    if (!enabled) return;
    const epoch = authV4.sessionEpoch();
    setState({checking: true, role: null, epoch});
    void authV4.restore().then(session => {
      if (!current || epoch !== authV4.sessionEpoch()) return;
      const role = session.signedIn && (session.role === 'ADMIN' || session.role === 'WORKER') ? session.role : null;
      setState({checking: false, role, epoch});
    }).catch(() => {
      if (current && epoch === authV4.sessionEpoch()) setState({checking: false, role: null, epoch});
    });
    return () => { current = false; };
  }, [enabled]));
  if (!enabled || state.epoch !== authV4.sessionEpoch()) return {checking: true, role: null};
  return state;
}
