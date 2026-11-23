
import { Stack } from 'expo-router';
import { View } from 'react-native';
import { AutoFailInAppAlertHostV4 } from '../components/AutoFailInAppAlertV4';

export default function RootLayout() {
  return (
    <View style={{ flex: 1 }}>
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="monitoring" />
      <Stack.Screen name="explore" />
    </Stack>
    <AutoFailInAppAlertHostV4 />
    </View>
  );
}
