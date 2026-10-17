import { useInfiniteQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { FlatList, RefreshControl, ScrollView, TextInput, View } from 'react-native';

import { StaffBookingRow } from '@/components/staff-booking-row';
import { Button, Chip, EmptyState, ErrorText, Icon, Loading, Row, Text } from '@/components/ui';
import { get } from '@/lib/api';
import type { AdminBooking } from '@/lib/types';
import { useStaff } from '@/state/staff';
import { fonts, radius, space, useColors } from '@/theme';

type Page = { results: AdminBooking[]; page: number; pages: number; total: number; statuses: { value: string; label: string }[] };

const STATUSES = [
  ['', 'All'], ['pending', 'Waiting'], ['paid', 'Paid'], ['picked_up', 'Picked up'], ['completed', 'Returned'],
  ['cancelled', 'Cancelled'], ['failed', 'Failed'],
];

export default function StaffBookings() {
  const c = useColors();
  const staff = useStaff();
  const [typed, setTyped] = useState('');
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');

  useEffect(() => {   // search a moment after typing stops
    const t = setTimeout(() => setQ(typed.trim()), 400);
    return () => clearTimeout(t);
  }, [typed]);

  const query = useInfiniteQuery({
    queryKey: ['staff', 'bookings', q, status],
    initialPageParam: 1,
    getNextPageParam: (last: Page) => (last.page < last.pages ? last.page + 1 : undefined),
    queryFn: ({ pageParam }) => staff.call((token) => get<Page>('staff/bookings/', { token, params: { q, status, page: pageParam } })),
  });
  const rows = query.data?.pages.flatMap((p) => p.results) ?? [];
  const total = query.data?.pages[0]?.total;

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <View style={{ padding: space.lg, gap: space.sm, backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.border }}>
        <Row gap={space.sm} style={{ borderWidth: 1.5, borderColor: c.controlBorder, borderRadius: radius.md, paddingHorizontal: space.md, backgroundColor: c.bg }}>
          <Icon name="search" size={18} color={c.muted} />
          <TextInput value={typed} onChangeText={setTyped} placeholder="Booking number, name, phone or M-Pesa code"
            placeholderTextColor={c.muted} autoCapitalize="none" autoCorrect={false} accessibilityLabel="Search bookings"
            style={{ flex: 1, minHeight: 46, fontSize: 16, fontFamily: fonts.regular, color: c.text }} />
        </Row>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
          {STATUSES.map(([value, label]) => <Chip key={value} label={label} selected={status === value} onPress={() => setStatus(value)} />)}
        </ScrollView>
        {total !== undefined ? <Text variant="muted">{total} booking{total === 1 ? '' : 's'}</Text> : null}
      </View>
      <FlatList
        data={rows}
        keyExtractor={(b) => b.ref}
        renderItem={({ item }) => <StaffBookingRow b={item} />}
        refreshControl={<RefreshControl refreshing={query.isRefetching && !query.isFetchingNextPage} onRefresh={() => { query.refetch(); }} />}
        ListEmptyComponent={query.isLoading ? <Loading /> : query.error ? <View style={{ padding: space.lg }}><ErrorText>{(query.error as Error).message}</ErrorText></View>
          : <EmptyState icon="journal-outline" title="No bookings match" text="Change the search or the status, or clear them to see everything." />}
        ListFooterComponent={query.hasNextPage ? (
          <View style={{ padding: space.lg }}><Button title="Load more" kind="ghost" loading={query.isFetchingNextPage} onPress={() => query.fetchNextPage()} /></View>
        ) : undefined}
      />
    </View>
  );
}
