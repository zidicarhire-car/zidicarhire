import { router } from 'expo-router';
import { Linking, Pressable, View } from 'react-native';

import { IconButton, Icon, Plate, Row, StatusBadge, Text } from '@/components/ui';
import { fmtDay, kes } from '@/lib/format';
import type { AdminBooking } from '@/lib/types';
import { space, useColors } from '@/theme';

/** One booking in a staff list: number plate, status, customer, car, dates, money, and a call button. */
export function StaffBookingRow({ b, when }: { b: AdminBooking; when?: 'pickup' | 'return' }) {
  const c = useColors();
  return (
    <Row gap={0} style={{ backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.border }}>
      <Pressable style={({ pressed }) => ({ flex: 1, padding: space.lg, gap: 4, opacity: pressed ? 0.7 : 1 })}
        accessibilityRole="button" accessibilityLabel={`Booking ${b.ref}, ${b.customer_name}, ${b.status_label}`}
        onPress={() => router.push({ pathname: '/staff/booking/[ref]', params: { ref: b.ref } })}>
        <Row style={{ flexWrap: 'wrap' }}>
          <Plate size="sm">{b.ref}</Plate>
          <StatusBadge status={b.status} label={b.status_label} />
        </Row>
        <Text variant="subheading">{b.customer_name}</Text>
        <Row gap={6}><Icon name="car-outline" size={15} color={c.muted} /><Text variant="muted">{b.car}{b.city ? `, ${b.city}` : ''}</Text></Row>
        <Row gap={6}>
          <Icon name={when ? 'time-outline' : 'calendar-outline'} size={15} color={c.muted} />
          <Text variant="muted">
            {when === 'pickup' ? `Pick-up at ${b.pickup_time}${b.pickup_point ? `, ${b.pickup_point}` : ''}`
              : when === 'return' ? `Return at ${b.return_time}${b.return_city ? `, in ${b.return_city}` : ''}`
                : `${fmtDay(b.pickup_date)} to ${fmtDay(b.return_date)}`}
          </Text>
        </Row>
        <Text variant="label">{kes(b.amount)}{b.balance > 0 && b.status !== 'pending' ? <Text variant="label" color={c.warnText}>  owes {kes(b.balance)}</Text> : null}</Text>
      </Pressable>
      <View style={{ borderLeftWidth: 1, borderLeftColor: c.border, alignSelf: 'stretch', justifyContent: 'center', paddingHorizontal: space.xs }}>
        <IconButton icon="call-outline" label={`Call ${b.customer_name}`} onPress={() => Linking.openURL(`tel:${b.phone}`)} />
      </View>
    </Row>
  );
}
