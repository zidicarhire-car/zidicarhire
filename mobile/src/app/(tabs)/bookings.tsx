import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Image } from 'expo-image';
import { router, useFocusEffect } from 'expo-router';
import { useCallback } from 'react';
import { FlatList, RefreshControl, View } from 'react-native';

import { Button, Card, EmptyState, Icon, Plate, Row, StatusBadge, Text } from '@/components/ui';
import { get } from '@/lib/api';
import { fmtDay } from '@/lib/format';
import { saveBooking, savedBookings, type SavedBooking } from '@/lib/storage';
import type { Booking } from '@/lib/types';
import { radius, space, useColors } from '@/theme';

/** Bookings made (or found) on this phone. Statuses refresh from the server each time the tab opens. */
async function loadAndRefresh(): Promise<SavedBooking[]> {
  const list = await savedBookings();
  await Promise.all(list.map(async (b) => {
    try {
      const res = await get<{ booking: Booking }>(`bookings/${b.ref}/`, { bookingToken: b.token });
      await saveBooking(res.booking);
    } catch {
      /* offline: show what we have */
    }
  }));
  return savedBookings();
}

export default function MyBookings() {
  const c = useColors();
  const qc = useQueryClient();
  const { data, isLoading, isRefetching, refetch } = useQuery({ queryKey: ['my-bookings'], queryFn: loadAndRefresh });
  useFocusEffect(useCallback(() => { qc.invalidateQueries({ queryKey: ['my-bookings'] }); }, [qc]));

  return (
    <FlatList
      style={{ backgroundColor: c.bg }}
      data={data ?? []}
      keyExtractor={(b) => b.ref}
      contentContainerStyle={{ padding: space.lg, gap: space.md, flexGrow: 1 }}
      refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => { refetch(); }} />}
      ListHeaderComponent={data?.length ? (
        <Button title="Find another booking" icon="search" kind="ghost" onPress={() => router.push('/find')} style={{ marginBottom: space.sm }} />
      ) : undefined}
      ListEmptyComponent={isLoading ? undefined : (
        <EmptyState icon="receipt-outline" title="No bookings on this phone yet"
          text="Bookings you make in the app show here. Booked on the website or another phone? Find it with its number and your phone number."
          action={<View style={{ gap: space.sm, alignSelf: 'stretch', marginTop: space.md }}>
            <Button title="Find my booking" icon="search" onPress={() => router.push('/find')} />
            <Button title="Browse cars" kind="ghost" icon="car-outline" onPress={() => router.navigate('/cars')} />
          </View>} />
      )}
      renderItem={({ item }) => (
        <Card onPress={() => router.push({ pathname: '/booking/[ref]', params: { ref: item.ref } })}>
          <Row gap={space.md} style={{ alignItems: 'flex-start' }}>
            <View style={{ width: 72, height: 48, borderRadius: radius.sm, backgroundColor: c.surface2, overflow: 'hidden', alignItems: 'center', justifyContent: 'center' }}>
              {item.car_photo ? <Image source={item.car_photo} style={{ width: 72, height: 48 }} contentFit="cover" /> : <Icon name="car-outline" color={c.muted} />}
            </View>
            <View style={{ flex: 1, gap: 4 }}>
              <Row style={{ justifyContent: 'space-between' }}>
                <Plate size="sm">{item.ref}</Plate>
                <StatusBadge status={item.status} label={item.status_label} />
              </Row>
              <Text variant="subheading">{item.car}</Text>
              <Text variant="muted">{fmtDay(item.pickup_date)} → {fmtDay(item.return_date)}{item.city ? ` · ${item.city}` : ''}</Text>
            </View>
          </Row>
        </Card>
      )}
    />
  );
}
