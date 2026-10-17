import { useQuery } from '@tanstack/react-query';
import { router } from 'expo-router';
import { FlatList, Pressable, RefreshControl, View } from 'react-native';

import { EmptyState, ErrorText, Loading, Row, StatusBadge, Text } from '@/components/ui';
import { get } from '@/lib/api';
import type { StaffChat } from '@/lib/types';
import { useStaff } from '@/state/staff';
import { radius, space, useColors } from '@/theme';

export default function StaffChats() {
  const c = useColors();
  const staff = useStaff();
  const { data, isLoading, error, refetch, isRefetching } = useQuery({
    queryKey: ['staff', 'chats'],
    refetchInterval: 5000,
    queryFn: () => staff.call((token) => get<{ chats: StaffChat[] }>('staff/chats/', { token }).then((r) => r.chats)),
  });

  if (isLoading) return <Loading />;
  return (
    <FlatList
      style={{ backgroundColor: c.bg }}
      data={data ?? []}
      keyExtractor={(chat) => chat.id}
      refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => { refetch(); }} />}
      ListHeaderComponent={error ? <View style={{ padding: space.lg }}><ErrorText>{(error as Error).message}</ErrorText></View> : (
        <Row style={{ padding: space.lg, paddingBottom: space.sm }}>
          <View style={{ width: 9, height: 9, borderRadius: 5, backgroundColor: c.plate, borderWidth: 1.5, borderColor: c.plateInk }} />
          <Text variant="muted" style={{ flex: 1 }}>Visitors see you as online while the staff app is open.</Text>
        </Row>
      )}
      ListEmptyComponent={<EmptyState icon="file-tray-outline" title="No chats yet" text="When a visitor writes on the website or in the app, it shows here." />}
      renderItem={({ item }) => (
        <Pressable onPress={() => router.push({ pathname: '/staff/chat/[id]', params: { id: item.id, name: item.name } })}
          accessibilityRole="button" accessibilityLabel={`Chat with ${item.name}${item.unread ? `, ${item.unread} unread` : ''}`}
          style={({ pressed }) => ({ backgroundColor: pressed ? c.surface2 : c.surface, borderBottomWidth: 1, borderBottomColor: c.border,
            padding: space.lg, gap: 4, borderLeftWidth: 3, borderLeftColor: item.unread ? c.plate : 'transparent' })}>
          <Row style={{ justifyContent: 'space-between' }}>
            <Text variant="subheading" style={{ flex: 1 }}>{item.name}</Text>
            <Text variant="muted" style={{ fontSize: 12 }}>{item.time}</Text>
          </Row>
          <Row style={{ flexWrap: 'wrap' }}>
            {item.city ? <View style={{ backgroundColor: c.neutralBg, borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 1 }}>
              <Text variant="small" style={{ fontSize: 12 }}>{item.city}</Text></View> : null}
            {item.wants_agent ? <StatusBadge status="pending" label="Wants a person" /> : null}
          </Row>
          <Row>
            <Text variant="muted" numberOfLines={1} style={{ flex: 1 }}>{item.preview}</Text>
            {item.unread ? <View style={{ minWidth: 22, paddingHorizontal: 6, borderRadius: 11, backgroundColor: c.plate }}>
              <Text variant="small" color={c.plateInk} style={{ textAlign: 'center', fontSize: 12 }}>{item.unread}</Text></View> : null}
          </Row>
        </Pressable>
      )}
    />
  );
}
