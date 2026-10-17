import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { Button, ErrorText, Field, Icon, Screen, Text } from '@/components/ui';
import { post } from '@/lib/api';
import { formatPhone } from '@/lib/format';
import { saveBooking } from '@/lib/storage';
import type { Booking } from '@/lib/types';
import { useColors } from '@/theme';

export default function FindBooking() {
  const c = useColors();
  const [ref, setRef] = useState('');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function find() {
    setError('');
    setBusy(true);
    try {
      const res = await post<{ booking: Booking }>('bookings/find/', { ref, phone });
      await saveBooking(res.booking);
      router.replace({ pathname: '/booking/[ref]', params: { ref: res.booking.ref } });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: c.tint, alignItems: 'center', justifyContent: 'center' }}>
        <Icon name="search" size={26} />
      </View>
      <Text variant="title">Find my booking</Text>
      <Text variant="muted">Enter your booking number and the phone number you paid with. We’ll keep the booking on this phone.</Text>
      <Field label="Booking number" value={ref} onChangeText={(v) => setRef(v.toUpperCase())} autoCapitalize="characters"
        autoCorrect={false} placeholder="ZCH1A2B3C4D" hint="It starts with ZCH and is in your confirmation email and SMS." />
      <Field label="Phone number you paid with" value={phone} onChangeText={(v) => setPhone(formatPhone(v))}
        keyboardType="phone-pad" placeholder="0712 345 678" />
      <ErrorText>{error}</ErrorText>
      <Button title="Find my booking" icon="search" size="lg" loading={busy} disabled={!ref || !phone} onPress={find} />
    </Screen>
  );
}
