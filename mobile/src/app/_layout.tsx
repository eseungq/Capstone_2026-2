import React, { Fragment, useCallback, useEffect, useState } from 'react';
import { Stack, useFocusEffect } from 'expo-router';
import { ActivityIndicator, View } from 'react-native';

import { authV4 } from '../api/backendV4/authRuntime';
import { AutoFailInAppAlertHostV4 } from '../components/AutoFailInAppAlertV4';
import {
  type NavigationSession, observeNavigationSession, requiresLiveSession, resetLiveStackToLogin,
} from '../components/sessionNavigationV4';

function LiveScreen({ session, resetToLogin, children }: {
  session: NavigationSession;
  resetToLogin: () => void;
  children: React.ReactElement;
}) {
  useFocusEffect(useCallback(() => {
    if (session === null) resetToLogin();
  }, [resetToLogin, session]));

  if (!session) return <View style={{ flex: 1, justifyContent: 'center' }}>
    <ActivityIndicator accessibilityLabel="로그인 상태 확인 중" />
  </View>;
  return <Fragment key={JSON.stringify([session.loginId, session.role])}>{children}</Fragment>;
}

export default function RootLayout() {
  const [session, setSession] = useState<NavigationSession>(undefined);
  useEffect(() => observeNavigationSession(authV4, setSession), []);

  return (
    <View style={{ flex: 1 }}>
      <Stack screenOptions={{ headerShown: false }}
        screenLayout={({ route, navigation, children }) => requiresLiveSession(route.name, route.params)
          ? <LiveScreen session={session}
              resetToLogin={() => resetLiveStackToLogin(navigation)}>
              {children}
            </LiveScreen>
          : children}>
        <Stack.Screen name="index" />
        <Stack.Screen name="monitoring" />
        <Stack.Screen name="explore" />
      </Stack>
      {session?.role === 'WORKER' && <AutoFailInAppAlertHostV4 key={authV4.sessionEpoch()} />}
    </View>
  );
}
