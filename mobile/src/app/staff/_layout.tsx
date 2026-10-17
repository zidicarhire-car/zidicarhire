import { Stack } from 'expo-router';

import { fonts, useColors } from '@/theme';

export default function StaffLayout() {
  const c = useColors();
  return (
    <Stack screenOptions={{
      headerStyle: { backgroundColor: c.brand }, headerTintColor: c.onBrand, headerTitleStyle: { fontFamily: fonts.semibold },
      contentStyle: { backgroundColor: c.bg }, headerBackButtonDisplayMode: 'minimal',
    }}>
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="login" options={{ title: 'Staff sign in' }} />
      <Stack.Screen name="booking/[ref]" options={{ title: 'Booking' }} />
      <Stack.Screen name="chat/[id]" options={{ title: 'Chat' }} />
    </Stack>
  );
}
