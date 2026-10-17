import { useQuery } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { Alert, Linking, RefreshControl, View } from 'react-native';

import { Button, Card, Divider, ErrorText, Fact, Icon, Loading, Plate, Row, Screen, StatusBadge, Text } from '@/components/ui';
import { useConfig } from '@/hooks/use-config';
import { get } from '@/lib/api';
import { fmtDay, kes, plural } from '@/lib/format';
import { forgetBooking, saveBooking, savedBookings } from '@/lib/storage';
import type { Booking } from '@/lib/types';
import { space, useColors } from '@/theme';

const STEPS = [
  { key: 'booked', label: 'Booked' },
  { key: 'paid', label: 'Paid' },
  { key: 'picked_up', label: 'Picked up' },
  { key: 'completed', label: 'Returned' },
];

export default function BookingScreen() {
  const c = useColors();
  const { ref } = useLocalSearchParams<{ ref: string }>();
  const { data: config } = useConfig();
  const { data: b, isLoading, error, refetch, isRefetching } = useQuery({
    queryKey: ['booking', ref],
    refetchInterval: (q) => (q.state.data?.status === 'pending' ? 4000 : false),
    queryFn: async () => {
      const saved = (await savedBookings()).find((s) => s.ref === ref);
      const res = await get<{ booking: Booking }>(`bookings/${ref}/`, { bookingToken: saved?.token });
      await saveBooking(res.booking);
      return res.booking;
    },
  });

  if (isLoading) return <Loading />;
  if (error || !b) return <Screen><ErrorText>{(error as Error)?.message ?? 'Booking not found.'}</ErrorText></Screen>;

  const stopped = b.status === 'cancelled' || b.status === 'failed';
  const reached = { pending: 0, paid: 1, picked_up: 2, completed: 3, cancelled: 0, failed: 0 }[b.status];
  const phone = config?.business.phone ?? '';

  return (
    <Screen refresh={<RefreshControl refreshing={isRefetching} onRefresh={() => { refetch(); }} />}>
      <Card style={{ gap: space.md }}>
        <Row style={{ justifyContent: 'space-between' }}>
          <Plate size="lg">{b.ref}</Plate>
          <StatusBadge status={b.status} label={b.status_label} />
        </Row>
        <Text variant="title">
          {['paid', 'picked_up', 'completed'].includes(b.status) ? 'Your booking is confirmed'
            : b.status === 'pending' ? 'Waiting for your payment' : b.status === 'cancelled' ? 'This booking was cancelled' : "This booking wasn't paid"}
        </Text>
        <Row gap={0}>
          {(stopped ? STEPS.slice(0, 1) : STEPS).map((s, i) => (
            <View key={s.key} style={{ flex: 1, alignItems: 'center', gap: 4 }}>
              <Icon name={i <= reached ? 'ellipse' : 'ellipse-outline'} size={16} color={i <= reached ? c.text : c.muted} />
              <Text variant="small" color={i <= reached ? c.text : c.muted}>{s.label}</Text>
            </View>
          ))}
          {stopped ? (
            <View style={{ flex: 1, alignItems: 'center', gap: 4 }}>
              <Icon name="close-circle" size={16} color={c.danger} />
              <Text variant="small" color={c.danger}>{b.status_label}</Text>
            </View>
          ) : null}
        </Row>
        {b.receipt_url && ['paid', 'picked_up', 'completed'].includes(b.status) ? (
          <View style={{ gap: space.sm }}>
            <Button title="Download receipt" icon="download-outline" onPress={() => WebBrowser.openBrowserAsync(b.receipt_url!)} />
            {b.ics_url ? <Button title="Add to calendar" icon="calendar-outline" kind="ghost" onPress={() => Linking.openURL(b.ics_url!)} /> : null}
          </View>
        ) : null}
        {stopped && b.car_id ? <Button title="Book this car again" onPress={() => router.push({ pathname: '/car/[id]', params: { id: String(b.car_id) } })} /> : null}
      </Card>

      <Text variant="heading">Your hire</Text>
      <Card style={{ gap: 0 }}>
        <Fact label="Car" value={b.car} />
        {b.city ? <Fact label="City" value={b.city} /> : null}
        {b.pickup_point ? <Fact label="Pick-up point" value={b.pickup_point} /> : null}
        <Fact label="Pick-up" value={`${fmtDay(b.pickup_date)}, ${b.pickup_time}`} />
        <Fact label="Return" value={`${fmtDay(b.return_date)}, ${b.return_time}${b.return_city ? `, in ${b.return_city}` : ''}`} />
        <Fact label="Length" value={plural(b.days, 'day')} />
      </Card>

      <Text variant="heading">Price</Text>
      <Card style={{ gap: 0 }}>
        {b.breakdown.map((line, i) => (
          <View key={`${line.label}${i}`}>
            {line.total ? <Divider /> : null}
            <Fact label={line.label} value={kes(line.amount)} strong={line.total} />
          </View>
        ))}
        {b.amount_paid ? <Fact label="Paid" value={kes(b.amount_paid)} /> : null}
        {b.balance > 0 ? <Fact label="Balance due at pick-up" value={kes(b.balance)} strong /> : null}
        {b.receipt ? <Fact label="M-Pesa receipt" value={b.receipt} /> : null}
      </Card>

      <Card style={{ backgroundColor: c.tint, borderColor: c.tint }}>
        <Row gap={space.sm} style={{ alignItems: 'flex-start' }}>
          <Icon name="headset-outline" />
          <Text style={{ flex: 1 }}>Need to change something? Call us or chat with us, and quote your booking number.</Text>
        </Row>
        <Row>
          {phone ? <Button title="Call" icon="call-outline" kind="ghost" size="sm" onPress={() => Linking.openURL(`tel:${phone}`)} /> : null}
          <Button title="Chat" icon="chatbubbles-outline" kind="ghost" size="sm" onPress={() => router.navigate('/chat')} />
        </Row>
      </Card>

      <Button title="Remove from this phone" kind="danger" size="sm" icon="trash-outline"
        onPress={() => Alert.alert('Remove this booking from the phone?', 'The booking itself is not cancelled. You can find it again with its number.', [
          { text: 'Keep', style: 'cancel' },
          { text: 'Remove', style: 'destructive', onPress: async () => { await forgetBooking(b.ref); router.back(); } },
        ])} />
    </Screen>
  );
}
