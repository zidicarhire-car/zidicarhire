import { useQuery } from '@tanstack/react-query';
import { Image } from 'expo-image';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { FlatList, Linking, ScrollView, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button, Card, Divider, ErrorText, Fact, Icon, Loading, Plate, Row, SectionTitle, Text, type IconName } from '@/components/ui';
import { useConfig } from '@/hooks/use-config';
import { get } from '@/lib/api';
import { kes, plural } from '@/lib/format';
import type { CarDetail, Quote } from '@/lib/types';
import { useSearch } from '@/state/search';
import { radius, space, useColors } from '@/theme';

export default function CarScreen() {
  const c = useColors();
  const { width } = useWindowDimensions();
  const { id } = useLocalSearchParams<{ id: string }>();
  const search = useSearch();
  const { data: config } = useConfig();
  const [photo, setPhoto] = useState(0);

  const { data, isLoading, error } = useQuery({
    queryKey: ['car', id, search.from, search.to],
    queryFn: () => get<CarDetail>(`cars/${id}/`, { params: { from: search.from, to: search.to } }),
  });
  const point = data?.branch.pickup_points?.[0];
  const time = config?.booking.default_time ?? '10:00';
  const quote = useQuery({
    queryKey: ['quote', id, search.from, search.to, point?.id],
    enabled: !!data,
    retry: false,
    queryFn: () => get<{ quote: Quote }>('quote/', { params: {
      car_id: id, from: search.from, to: search.to, pickup_time: time, return_time: time, pickup_point: point?.id ?? '',
    } }),
  });

  if (isLoading) return <Loading />;
  if (error || !data) return <SafeAreaView style={{ padding: space.lg }}><ErrorText>{(error as Error)?.message ?? 'Car not found.'}</ErrorText></SafeAreaView>;
  const car = data.car;
  const photos = car.photos.length ? car.photos : [];

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <Stack.Screen options={{ title: car.name }} />
      <ScrollView contentContainerStyle={{ paddingBottom: 120 }}>
        <View style={{ height: width * 0.625, backgroundColor: c.surface2 }}>
          {photos.length ? (
            <FlatList data={photos} horizontal pagingEnabled showsHorizontalScrollIndicator={false}
              keyExtractor={(p) => p.url}
              onMomentumScrollEnd={(e) => setPhoto(Math.round(e.nativeEvent.contentOffset.x / width))}
              renderItem={({ item, index }) => (
                <Image source={{ uri: item.url }} placeholder={{ uri: item.thumb }} style={{ width, height: width * 0.625 }}
                  contentFit="cover" transition={150} accessibilityLabel={`${car.name}, photo ${index + 1} of ${photos.length}`} />
              )} />
          ) : (
            <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}><Icon name="car-outline" size={64} color={c.muted} /></View>
          )}
          {photos.length > 1 ? (
            <Row gap={6} style={{ position: 'absolute', bottom: space.md, alignSelf: 'center' }}>
              {photos.map((p, i) => (
                <View key={p.url} style={{ width: i === photo ? 18 : 7, height: 7, borderRadius: 4, backgroundColor: i === photo ? '#FFFFFF' : '#FFFFFF88' }} />
              ))}
            </Row>
          ) : null}
        </View>

        <View style={{ padding: space.lg, gap: space.lg }}>
          <View style={{ gap: space.sm }}>
            <Row gap={space.sm}>
              <View style={{ backgroundColor: c.brand, borderRadius: radius.pill, paddingHorizontal: 9, paddingVertical: 3 }}>
                <Text variant="small" color={c.onBrand} style={{ fontSize: 12 }}>{car.category_label}</Text>
              </View>
              <Icon name="location-outline" size={15} color={c.muted} />
              <Text variant="muted">{car.location.name}</Text>
            </Row>
            <Text variant="title">{car.name}</Text>
            <Row gap={6}><Plate size="lg">{kes(car.price_per_day)}</Plate><Text variant="muted">/ day</Text></Row>
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
            <Spec icon="people-outline" text={`${car.seats} seats`} />
            <Spec icon="cog-outline" text={car.transmission_label} />
            <Spec icon="water-outline" text={car.fuel_label} />
            <Spec icon="briefcase-outline" text={plural(car.luggage, 'large bag')} />
            <Spec icon="car-outline" text={`${car.doors} doors`} />
            <Spec icon="snow-outline" text={car.air_con ? 'Air con' : 'No air con'} />
            {car.engine_size ? <Spec icon="speedometer-outline" text={car.engine_size} /> : null}
          </View>

          {car.description ? <><SectionTitle>About this car</SectionTitle><Text>{car.description}</Text></> : null}

          {car.features.length ? (
            <>
              <SectionTitle>Features</SectionTitle>
              <View style={{ gap: space.sm }}>
                {car.features.map((f) => <Row key={f} gap={space.sm}><Icon name="checkmark" size={18} /><Text>{f}</Text></Row>)}
              </View>
            </>
          ) : null}

          <SectionTitle>Prices</SectionTitle>
          <Card style={{ gap: 0 }}>
            {car.prices.map((p, i) => (
              <View key={p.label}>
                {i ? <Divider /> : null}
                <Fact label={p.label} value={`${kes(p.per_day)} ${p.note}`} />
              </View>
            ))}
          </Card>
          <Text variant="muted">Every started 24 hours counts as a day. Airport and delivery pick-ups and one-way returns are added when you book.</Text>

          <SectionTitle>The branch</SectionTitle>
          <Card>
            <Row gap={space.sm}><Icon name="business-outline" /><Text variant="heading">{data.branch.name}</Text></Row>
            <Text variant="muted">{data.branch.address || data.branch.city}</Text>
            {data.branch.opening_hours ? <Text variant="muted">{data.branch.opening_hours}</Text> : null}
            <Row style={{ flexWrap: 'wrap', marginTop: space.xs }}>
              <Button title="Call" icon="call-outline" kind="ghost" size="sm" onPress={() => Linking.openURL(`tel:${data.branch.phone}`)} />
              {data.branch.whatsapp ? <Button title="WhatsApp" icon="logo-whatsapp" kind="ghost" size="sm" onPress={() => Linking.openURL(data.branch.whatsapp)} /> : null}
              {data.branch.maps_url ? <Button title="Directions" icon="map-outline" kind="ghost" size="sm" onPress={() => Linking.openURL(data.branch.maps_url)} /> : null}
            </Row>
          </Card>
        </View>
      </ScrollView>

      <SafeAreaView edges={['bottom']} style={{ position: 'absolute', left: 0, right: 0, bottom: 0, backgroundColor: c.surface, borderTopWidth: 1, borderTopColor: c.border }}>
        <Row style={{ padding: space.md, paddingHorizontal: space.lg, justifyContent: 'space-between' }} gap={space.md}>
          <View style={{ flexShrink: 1 }}>
            <Text variant="subheading">{quote.data ? kes(quote.data.quote.total) : kes(car.price_per_day) + ' / day'}</Text>
            <Text variant="muted" numberOfLines={2}>
              {quote.data ? `${plural(quote.data.quote.days, 'day')}, ${quote.data.quote.pickup.split(' ').slice(0, 3).join(' ')} to ${quote.data.quote.return.split(' ').slice(0, 3).join(' ')}`
                : quote.error ? (quote.error as Error).message : 'Pick dates to see the total'}
            </Text>
          </View>
          <Button title="Book now" size="lg" onPress={() => router.push({ pathname: '/book/[id]', params: { id: String(car.id) } })} />
        </Row>
      </SafeAreaView>
    </View>
  );
}

function Spec({ icon, text }: { icon: IconName; text: string }) {
  const c = useColors();
  return (
    <Row gap={6} style={{ backgroundColor: c.surface, borderColor: c.border, borderWidth: 1, borderRadius: radius.md, paddingHorizontal: space.md, paddingVertical: space.sm, minWidth: '47%' }}>
      <Icon name={icon} size={18} />
      <Text variant="label">{text}</Text>
    </Row>
  );
}
