import { ArchivoNarrow_700Bold } from '@expo-google-fonts/archivo-narrow';
import { Inter_400Regular, Inter_500Medium, Inter_600SemiBold, Inter_700Bold, useFonts } from '@expo-google-fonts/inter';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { useColorScheme } from 'react-native';

import { SearchProvider } from '@/state/search';
import { StaffProvider } from '@/state/staff';
import { fonts, useColors } from '@/theme';

SplashScreen.preventAutoHideAsync();

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } });

export default function RootLayout() {
  const [loaded, error] = useFonts({
    Inter_400Regular, Inter_500Medium, Inter_600SemiBold, Inter_700Bold, ArchivoNarrow_700Bold,
  });
  const scheme = useColorScheme();
  const c = useColors();

  useEffect(() => {
    if (loaded || error) SplashScreen.hideAsync();
  }, [loaded, error]);

  if (!loaded && !error) return null;

  const base = scheme === 'dark' ? DarkTheme : DefaultTheme;
  const navTheme = { ...base, colors: { ...base.colors, primary: c.text, background: c.bg, card: c.surface, text: c.text, border: c.border } };

  return (
    <QueryClientProvider client={queryClient}>
      <StaffProvider>
        <SearchProvider>
          <ThemeProvider value={navTheme}>
            <StatusBar style="light" />
            <Stack screenOptions={{
              headerStyle: { backgroundColor: c.brand }, headerTintColor: c.onBrand,
              headerTitleStyle: { fontFamily: fonts.semibold }, contentStyle: { backgroundColor: c.bg },
              headerBackButtonDisplayMode: 'minimal',
            }}>
              <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
              <Stack.Screen name="car/[id]" options={{ title: 'Car' }} />
              <Stack.Screen name="book/[id]" options={{ title: 'Book', presentation: 'fullScreenModal' }} />
              <Stack.Screen name="booking/[ref]" options={{ title: 'Booking' }} />
              <Stack.Screen name="find" options={{ title: 'Find my booking' }} />
              <Stack.Screen name="staff" options={{ headerShown: false }} />
            </Stack>
          </ThemeProvider>
        </SearchProvider>
      </StaffProvider>
    </QueryClientProvider>
  );
}
