import { Image } from 'expo-image';
import { router } from 'expo-router';
import { View } from 'react-native';

import { Card, Icon, Plate, Row, Text } from '@/components/ui';
import { kes, plural } from '@/lib/format';
import type { Car } from '@/lib/types';
import { radius, space, useColors } from '@/theme';

/** One car in a list: photo, badges, specs, plate price and the total for the chosen dates. */
export function CarCard({ car, from, to }: { car: Car; from?: string; to?: string }) {
  const c = useColors();
  const booked = car.available === false;
  return (
    <Card style={{ padding: 0, overflow: 'hidden', gap: 0 }}
      onPress={() => router.push({ pathname: '/car/[id]', params: { id: String(car.id), from: from ?? '', to: to ?? '' } })}>
      <View style={{ aspectRatio: 16 / 10, backgroundColor: c.surface2 }}>
        {car.photo ? (
          <Image source={car.photo} style={{ flex: 1, opacity: booked ? 0.45 : 1 }} contentFit="cover" transition={150}
            accessibilityLabel={`Photo of the ${car.name}`} />
        ) : (
          <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}><Icon name="car-outline" size={48} color={c.muted} /></View>
        )}
        <Row style={{ position: 'absolute', top: space.md, left: space.md }} gap={6}>
          <View style={{ backgroundColor: c.brand, borderRadius: radius.pill, paddingHorizontal: 9, paddingVertical: 3 }}>
            <Text variant="small" color={c.onBrand} style={{ fontSize: 12 }}>{car.category_label}</Text>
          </View>
          <Row gap={3} style={{ backgroundColor: '#FFFFFFEE', borderRadius: radius.pill, paddingHorizontal: 9, paddingVertical: 3 }}>
            <Icon name="location-outline" size={12} color="#1C2340" />
            <Text variant="small" color="#1C2340" style={{ fontSize: 12 }}>{car.location.name}</Text>
          </Row>
        </Row>
        {booked ? (
          <View style={{ position: 'absolute', left: space.md, bottom: space.md, backgroundColor: '#0A0D1EDD', borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4 }}>
            <Text variant="small" color="#FFFFFF" style={{ fontSize: 12 }}>Booked for these dates</Text>
          </View>
        ) : null}
      </View>
      <View style={{ padding: space.lg, gap: space.sm }}>
        <Text variant="heading">{car.name}</Text>
        <Row gap={space.md} style={{ flexWrap: 'wrap' }}>
          <Spec icon="people-outline" text={`${car.seats} seats`} />
          <Spec icon="cog-outline" text={car.transmission_label} />
          <Spec icon="water-outline" text={car.fuel_label} />
          {car.luggage ? <Spec icon="briefcase-outline" text={plural(car.luggage, 'bag')} /> : null}
        </Row>
        <Row style={{ justifyContent: 'space-between', marginTop: 4 }}>
          <Row gap={6}>
            <Plate>{kes(car.price_per_day)}</Plate>
            <Text variant="muted">/ day</Text>
          </Row>
          {car.total && car.days ? <Text variant="muted">{kes(car.total)} for {plural(car.days, 'day')}</Text> : null}
        </Row>
      </View>
    </Card>
  );
}

function Spec({ icon, text }: { icon: Parameters<typeof Icon>[0]['name']; text: string }) {
  const c = useColors();
  return (
    <Row gap={4}>
      <Icon name={icon} size={15} color={c.muted} />
      <Text variant="muted">{text}</Text>
    </Row>
  );
}
