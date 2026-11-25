import React, { useEffect, useMemo, useState } from 'react';
import { router, useGlobalSearchParams, usePathname } from 'expo-router';
import { AppState } from 'react-native';

import { authV4 } from '../api/backendV4/authRuntime';
import InspectionAlertBannerV4 from './InspectionAlertBannerV4';
import {reviewAlertQueueV4} from './reviewAlertQueueV4';
import { createInspectionReadServiceV4 } from '../api/backendV4/inspectionReadService';
import {
  createAutoFailInAppControllerV4,
  type AutoFailInAppAlertV4,
} from '../api/backendV4/autoFailInAppCoreV4';

const reader = createInspectionReadServiceV4({ mode: 'api', transport: authV4 });

/** Mock/로그인/프리뷰에서는 서버 알림 폴링을 절대 시작하지 않습니다. */
export function AutoFailInAppAlertHostV4() {
  const pathname = usePathname();
  const { mode } = useGlobalSearchParams<{ mode?: string }>();
  const epoch=authV4.sessionEpoch();
  const [monitorPending,setMonitorPending]=useState(()=>reviewAlertQueueV4.snapshot(epoch).length>0);
  useEffect(()=>{
    setMonitorPending(reviewAlertQueueV4.snapshot(epoch).length>0);
    return reviewAlertQueueV4.subscribe(()=>setMonitorPending(reviewAlertQueueV4.snapshot(epoch).length>0));
  },[epoch]);
  const isLive = (
    (['/monitoring', '/history', '/settings', '/statistics', '/policy-adjust'].includes(pathname) && mode === 'live')
    || pathname.endsWith('-live')
  );
  const [sessionKey, setSessionKey] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    if (!isLive) { setSessionKey(null); return; }
    void authV4.restore().then((session) => {
      if (!active) return;
      setSessionKey(
        session.signedIn && session.role === 'WORKER'
          ? `${session.loginId ?? ''}:${session.role}`
          : null,
      );
    }).catch(() => { if (active) setSessionKey(null); });
    return () => { active = false; };
  }, [isLive, pathname]);

  return isLive && sessionKey !== null
    ? <AutoFailInAppBannerV4 key={sessionKey} hidden={(pathname==='/monitoring'&&monitorPending)||pathname==='/inspection-live'||pathname==='/inspection-image-live'} />
    : null;
}

function AutoFailInAppBannerV4({ hidden }: { hidden: boolean }) {
  const [pending, setPending] = useState<AutoFailInAppAlertV4[]>([]);
  const controller = useMemo(() => createAutoFailInAppControllerV4({
    reader,
    onAlert: (alerts) => {
      setPending((old) => [...old, ...alerts].sort(
        (a, b) => Date.parse(b.receivedAt) - Date.parse(a.receivedAt),
      ));
    },
  }), []);

  useEffect(() => {
    const syncAppState = (state: string) => controller.setForeground(state === 'active');
    controller.setForeground(AppState.currentState == null || AppState.currentState === 'active');
    controller.start();
    const subscription = AppState.addEventListener('change', syncAppState);
    return () => { subscription.remove(); controller.stop(); };
  }, [controller]);

  const alert = pending[0];
  if (!alert || hidden) return null;
  const close = () => setPending((old) => old.slice(1));
  const open = () => {
    const inspectionId = alert.inspectionId;
    close();
    router.push({ pathname: '/inspection-live', params: { inspectionId } });
  };
  return <InspectionAlertBannerV4 kind="autoFail" inspectionNo={alert.inspectionNo} partCode={alert.partCode}
    count={pending.length} bottom={83} onClose={close} onOpen={open}/>;
}
