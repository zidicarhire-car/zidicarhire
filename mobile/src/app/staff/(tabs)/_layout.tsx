import Ionicons from '@expo/vector-icons/Ionicons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Redirect, Tabs } from 'expo-router';
import { useEffect, useRef } from 'react';
import { Vibration } from 'react-native';

import { Loading } from '@/components/ui';
import { get } from '@/lib/api';
import type { AdminBooking, Stats } from '@/lib/types';
import { useStaff } from '@/state/staff';
import { fonts, useColors } from '@/theme';

type Feed = { bookings: (AdminBooking & { just_paid: boolean })[]; stats: Stats; unread_chats: number; server_time: string };

export default function StaffTabs() {
  const c = useColors();
  const staff = useStaff();
  const qc = useQueryClient();
  const since = useRef('');

  // Live feed while the staff app is open: marks the team online for chats, and new payments buzz the phone.
  const feed = useQuery({
    queryKey: ['staff', 'feed'],
    enabled: !!staff.token,
    refetchInterval: 15000,
    queryFn: () => staff.call((token) => get<Feed>('staff/feed/', { token, params: { since: since.current } })),
  });
  useEffect(() => {
    const data = feed.data;
    if (!data) return;
    const first = !since.current;
    since.current = data.server_time;
    if (!first && data.bookings.length) {
      if (data.bookings.some((b) => b.just_paid)) Vibration.vibrate([0, 250, 120, 250]);
      qc.invalidateQueries({ queryKey: ['staff', 'overview'] });
      qc.invalidateQueries({ queryKey: ['staff', 'bookings'] });
    }
  }, [feed.data, qc]);

  if (!staff.ready) return <Loading />;
  if (!staff.token) return <Redirect href="/staff/login" />;

  return (
    <Tabs screenOptions={{
      headerStyle: { backgroundColor: c.brand }, headerTintColor: c.onBrand, headerTitleStyle: { fontFamily: fonts.semibold },
      tabBarActiveTintColor: c.text, tabBarInactiveTintColor: c.muted,
      tabBarStyle: { backgroundColor: c.surface, borderTopColor: c.border },
      tabBarLabelStyle: { fontFamily: fonts.semibold, fontSize: 11 },
    }}>
      <Tabs.Screen name="index" options={{
        title: 'Today',
        tabBarIcon: ({ color, focused }) => <Ionicons name={focused ? 'speedometer' : 'speedometer-outline'} size={23} color={color as string} />,
      }} />
      <Tabs.Screen name="bookings" options={{
        title: 'Bookings',
        tabBarIcon: ({ color, focused }) => <Ionicons name={focused ? 'journal' : 'journal-outline'} size={22} color={color as string} />,
      }} />
      <Tabs.Screen name="chats" options={{
        title: 'Chats',
        tabBarBadge: feed.data?.unread_chats || undefined,
        tabBarBadgeStyle: { backgroundColor: c.plate, color: c.plateInk, fontFamily: fonts.bold },
        tabBarIcon: ({ color, focused }) => <Ionicons name={focused ? 'chatbubbles' : 'chatbubbles-outline'} size={23} color={color as string} />,
      }} />
      <Tabs.Screen name="cars" options={{
        title: 'Cars',
        tabBarIcon: ({ color, focused }) => <Ionicons name={focused ? 'car' : 'car-outline'} size={25} color={color as string} />,
      }} />
    </Tabs>
  );
}
