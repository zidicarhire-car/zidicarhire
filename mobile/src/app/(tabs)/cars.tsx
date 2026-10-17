import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { FlatList, Pressable, RefreshControl, ScrollView, View } from 'react-native';

import { CarCard } from '@/components/car-card';
import { DatesSheet } from '@/components/dates-sheet';
import { Button, Chip, EmptyState, ErrorText, Icon, Loading, Row, Text } from '@/components/ui';
import { useConfig } from '@/hooks/use-config';
import { daysBetween, fmtDay, plural } from '@/lib/format';
import { carsQuery } from '@/lib/queries';
import { useSearch } from '@/state/search';
import { radius, space, useColors } from '@/theme';

export default function Cars() {
  const c = useColors();
  const search = useSearch();
  const { data: config } = useConfig();
  const [picking, setPicking] = useState(false);
  const [category, setCategory] = useState('');
  const [transmission, setTransmission] = useState('');
  const [sort, setSort] = useState('recommended');

  const { data, isLoading, error, refetch, isRefetching } = useQuery(
    carsQuery({ city: search.city, from: search.from, to: search.to, category, transmission, sort }),
  );
  const branch = config?.branches.find((b) => b.slug === search.city);

  const header = (
    <View style={{ gap: space.md, paddingBottom: space.sm }}>
      <ScrollView horizontal style={{ flexGrow: 0 }} showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
        {(config?.branches ?? []).map((b) => (
          <Chip key={b.slug} label={b.name} icon="location-outline" selected={search.city === b.slug} onPress={() => search.setCity(b.slug)} />
        ))}
      </ScrollView>
      <Pressable onPress={() => setPicking(true)} accessibilityRole="button" accessibilityLabel="Change dates"
        style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm, minHeight: 48, backgroundColor: c.surface,
          borderWidth: 1.5, borderColor: c.controlBorder, borderRadius: radius.md, paddingHorizontal: space.md }}>
        <Icon name="calendar-outline" />
        <Text style={{ flex: 1 }}>{fmtDay(search.from)} → {fmtDay(search.to)}</Text>
        <Text variant="muted">{plural(daysBetween(search.from, search.to), 'day')}</Text>
        <Icon name="chevron-forward" size={16} color={c.muted} />
      </Pressable>
      <ScrollView horizontal style={{ flexGrow: 0 }} showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
        <Chip label="Any type" selected={!category} onPress={() => setCategory('')} />
        {(config?.categories ?? []).map((cat) => (
          <Chip key={cat.value} label={cat.label} selected={category === cat.value} onPress={() => setCategory(category === cat.value ? '' : cat.value)} />
        ))}
      </ScrollView>
      <Row style={{ flexWrap: 'wrap' }}>
        {(config?.transmissions ?? []).map((t) => (
          <Chip key={t.value} label={t.label} icon="cog-outline" selected={transmission === t.value}
            onPress={() => setTransmission(transmission === t.value ? '' : t.value)} />
        ))}
        <Chip label={sort === 'price_asc' ? 'Lowest price first' : sort === 'price_desc' ? 'Highest price first' : 'Available first'}
          icon="swap-vertical" accessibilityLabel="Change the sort order"
          onPress={() => setSort(sort === 'recommended' ? 'price_asc' : sort === 'price_asc' ? 'price_desc' : 'recommended')} />
      </Row>
      {data ? <Text variant="muted">{plural(data.cars.length, 'car')} in {data.location?.name ?? branch?.name}</Text> : null}
    </View>
  );

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <FlatList
        data={data?.cars ?? []}
        keyExtractor={(car) => String(car.id)}
        contentContainerStyle={{ padding: space.lg, gap: space.lg }}
        ListHeaderComponent={header}
        renderItem={({ item }) => <CarCard car={item} from={data?.from} to={data?.to} />}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => { refetch(); }} />}
        ListEmptyComponent={isLoading ? <Loading label="Finding cars" /> : error ? <ErrorText>{(error as Error).message}</ErrorText> : (
          <EmptyState icon="car-outline"
            title={category || transmission ? 'No cars match these filters' : `No cars free in ${branch?.name ?? 'this city'}`}
            text={data?.suggestions.length ? 'These nearby branches have cars free for your dates:' : 'Try other dates, or chat with us and we will find you a car.'}
            action={
              <View style={{ gap: space.sm, alignSelf: 'stretch', marginTop: space.sm }}>
                {data?.suggestions.map((s) => (
                  <Button key={s.slug} kind="ghost" icon="location-outline" onPress={() => search.setCity(s.slug)}
                    title={`${s.name}: ${plural(s.free_cars, 'car')} free${s.distance_km ? `, ${s.distance_km} km` : ''}`} />
                ))}
                {category || transmission ? <Button title="Clear filters" onPress={() => { setCategory(''); setTransmission(''); }} /> : null}
              </View>
            } />
        )}
      />
      <DatesSheet visible={picking} from={search.from} to={search.to} maxDays={config?.booking.max_days}
        onClose={() => setPicking(false)} onDone={search.setDates} />
    </View>
  );
}
