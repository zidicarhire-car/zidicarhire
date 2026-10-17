import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { DatesSheet } from '@/components/dates-sheet';
import { Button, Card, Chip, Icon, Plate, Row, SectionTitle, Text, type IconName } from '@/components/ui';
import { useConfig } from '@/hooks/use-config';
import { daysBetween, fmtDay, plural } from '@/lib/format';
import { useSearch } from '@/state/search';
import { radius, space, useColors } from '@/theme';

const FEATURES: { icon: IconName; title: string; text: string }[] = [
  { icon: 'flash-outline', title: 'Instant confirmation', text: 'Booked the moment you pay.' },
  { icon: 'location-outline', title: '5 cities', text: 'Nairobi, Mombasa, Kisumu, Nakuru and Eldoret.' },
  { icon: 'phone-portrait-outline', title: 'Pay on your phone', text: 'No cash, no paperwork queues.' },
  { icon: 'headset-outline', title: 'Real people on chat', text: 'Ask us anything before you book.' },
];

const STEPS: { icon: IconName; title: string; text: string }[] = [
  { icon: 'calendar-outline', title: 'Choose city and dates', text: 'You only see the cars that are free for your whole trip.' },
  { icon: 'car-outline', title: 'Pick a car', text: 'Compare prices, seats and gearbox, then add your details.' },
  { icon: 'checkmark-circle-outline', title: "Pay and you're booked", text: 'Pay on your phone. Your booking number and receipt come straight away.' },
];

export default function Home() {
  const c = useColors();
  const insets = useSafeAreaInsets();
  const { data: config } = useConfig();
  const search = useSearch();
  const [picking, setPicking] = useState(false);
  const branches = config?.branches ?? [];
  const days = daysBetween(search.from, search.to);

  return (
    <ScrollView style={{ flex: 1, backgroundColor: c.bg }} contentContainerStyle={{ paddingBottom: space.xxl }}>
      {/* Hero */}
      <View style={{ backgroundColor: c.brand, paddingTop: insets.top + space.md, paddingHorizontal: space.lg, paddingBottom: 72, gap: space.md }}>
        <Image source={require('@/assets/images/logo-white.png')} style={{ width: 150, height: 38 }} contentFit="contain"
          accessibilityLabel="ZidiCarHire" />
        <Text variant="display" color={c.onBrand} style={{ marginTop: space.md }}>Car hire across Kenya.</Text>
        <Text color={c.onBrandMuted}>
          {branches.length ? `Branches in ${branches.map((b) => b.name).join(', ').replace(/, ([^,]*)$/, ' and $1')}. ` : ''}
          Choose your city and dates, pick a car, and pay securely on your phone.
        </Text>
      </View>

      {/* Search card, overlapping the hero */}
      <Card style={{ marginHorizontal: space.lg, marginTop: -52, gap: space.md, shadowColor: '#000', shadowOpacity: 0.15, shadowRadius: 16, elevation: 6 }}>
        <Text variant="label">City</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
          {branches.map((b) => (
            <Chip key={b.slug} label={b.name} icon="location-outline" selected={search.city === b.slug} onPress={() => search.setCity(b.slug)} />
          ))}
        </ScrollView>
        <Text variant="label">Dates</Text>
        <Pressable onPress={() => setPicking(true)} accessibilityRole="button" accessibilityLabel="Change dates"
          style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm, minHeight: 48, borderWidth: 1.5, borderColor: c.controlBorder, borderRadius: radius.md, paddingHorizontal: space.md }}>
          <Icon name="calendar-outline" />
          <Text style={{ flex: 1 }}>{fmtDay(search.from)} → {fmtDay(search.to)}</Text>
          <Text variant="muted">{plural(days, 'day')}</Text>
        </Pressable>
        <Button title="Search cars" kind="plate" icon="search" size="lg" onPress={() => router.navigate('/cars')} />
      </Card>

      <View style={{ padding: space.lg, gap: space.lg }}>
        {/* Features */}
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.md }}>
          {FEATURES.map((f) => (
            <View key={f.title} style={{ width: '47%', gap: 6 }}>
              <View style={{ width: 48, height: 48, borderRadius: radius.md, backgroundColor: c.plate, alignItems: 'center', justifyContent: 'center' }}>
                <Icon name={f.icon} size={24} color={c.plateInk} />
              </View>
              <Text variant="subheading">{f.title}</Text>
              <Text variant="muted">{f.text}</Text>
            </View>
          ))}
        </View>

        {/* Branches */}
        <SectionTitle>Our branches</SectionTitle>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.md }} style={{ marginHorizontal: -space.lg }}>
          <View style={{ width: space.lg - space.md }} />
          {branches.map((b) => (
            <Card key={b.slug} style={{ width: 240 }} onPress={() => { search.setCity(b.slug); router.navigate('/cars'); }}>
              <View style={{ width: 40, height: 40, borderRadius: radius.md, backgroundColor: c.tint, alignItems: 'center', justifyContent: 'center' }}>
                <Icon name="business-outline" />
              </View>
              <Text variant="heading">{b.name}</Text>
              <Row gap={6} style={{ alignItems: 'flex-start' }}>
                <Icon name="location-outline" size={15} color={c.muted} />
                <Text variant="muted" style={{ flex: 1 }}>{b.address || b.city}</Text>
              </Row>
              {b.opening_hours ? (
                <Row gap={6} style={{ alignItems: 'flex-start' }}>
                  <Icon name="time-outline" size={15} color={c.muted} />
                  <Text variant="muted" style={{ flex: 1 }}>{b.opening_hours}</Text>
                </Row>
              ) : null}
              <Row gap={6} style={{ marginTop: 4 }}>
                <Text variant="label">See cars in {b.name}</Text>
                <Icon name="arrow-forward" size={16} />
              </Row>
            </Card>
          ))}
          <View style={{ width: space.lg - space.md }} />
        </ScrollView>

        {/* How it works */}
        <SectionTitle>How it works</SectionTitle>
        <View style={{ gap: space.lg }}>
          {STEPS.map((s, i) => (
            <Row key={s.title} gap={space.md} style={{ alignItems: 'flex-start' }}>
              <Plate>{String(i + 1)}</Plate>
              <View style={{ flex: 1, gap: 2 }}>
                <Row gap={6}><Icon name={s.icon} size={18} color={c.muted} /><Text variant="subheading">{s.title}</Text></Row>
                <Text variant="muted">{s.text}</Text>
              </View>
            </Row>
          ))}
        </View>

        <Card style={{ backgroundColor: c.brand, borderColor: c.brand, gap: space.md }}>
          <Text variant="title" color={c.onBrand}>Ready when you are.</Text>
          <Button title="Find a car" kind="plate" icon="search" onPress={() => router.navigate('/cars')} />
        </Card>
      </View>

      <DatesSheet visible={picking} from={search.from} to={search.to} maxDays={config?.booking.max_days}
        onClose={() => setPicking(false)} onDone={search.setDates} />
    </ScrollView>
  );
}
