import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';

import { fonts, useColors } from '@/theme';

export default function CustomerTabs() {
  const c = useColors();
  return (
    <Tabs screenOptions={{
      headerStyle: { backgroundColor: c.brand }, headerTintColor: c.onBrand, headerTitleStyle: { fontFamily: fonts.semibold },
      tabBarActiveTintColor: c.text, tabBarInactiveTintColor: c.muted,
      tabBarStyle: { backgroundColor: c.surface, borderTopColor: c.border },
      tabBarLabelStyle: { fontFamily: fonts.semibold, fontSize: 11 },
    }}>
      <Tabs.Screen name="index" options={{
        title: 'Home', headerShown: false,
        tabBarIcon: ({ color, focused }) => <Ionicons name={focused ? 'home' : 'home-outline'} size={23} color={color as string} />,
      }} />
      <Tabs.Screen name="cars" options={{
        title: 'Cars',
        tabBarIcon: ({ color, focused }) => <Ionicons name={focused ? 'car' : 'car-outline'} size={25} color={color as string} />,
      }} />
      <Tabs.Screen name="bookings" options={{
        title: 'My bookings',
        tabBarIcon: ({ color, focused }) => <Ionicons name={focused ? 'receipt' : 'receipt-outline'} size={22} color={color as string} />,
      }} />
      <Tabs.Screen name="chat" options={{
        title: 'Chat',
        tabBarIcon: ({ color, focused }) => <Ionicons name={focused ? 'chatbubbles' : 'chatbubbles-outline'} size={23} color={color as string} />,
      }} />
      <Tabs.Screen name="more" options={{
        title: 'More',
        tabBarIcon: ({ color, focused }) => <Ionicons name={focused ? 'grid' : 'grid-outline'} size={22} color={color as string} />,
      }} />
    </Tabs>
  );
}
