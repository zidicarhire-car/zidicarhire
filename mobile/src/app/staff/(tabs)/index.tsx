import { useQuery } from '@tanstack/react-query';
import { Tabs } from 'expo-router';
import { useState } from 'react';
import { Alert, Pressable, RefreshControl, ScrollView, View } from 'react-native';

import { StaffBookingRow } from '@/components/staff-booking-row';
import { Card, Chip, EmptyState, ErrorText, Icon, IconButton, Loading, Row, Text, type IconName } from '@/components/ui';
import { get } from '@/lib/api';
import { kes } from '@/lib/format';
import type { Overview } from '@/lib/types';
import { useStaff } from '@/state/staff';
import { radius, space, useColors } from '@/theme';

type TabKey = 'pickups' | 'returns' | 'out' | 'awaiting';
const TABS: { key: TabKey; label: string; empty: string; icon: IconName }[] = [
  { key: 'pickups', label: 'Pick-ups', empty: 'No pick-ups today.', icon: 'cafe-outline' },
  { key: 'returns', label: 'Returns', empty: 'No returns today.', icon: 'cafe-outline' },
  { key: 'out', label: 'Out now', empty: 'No cars are out right now.', icon: 'car-outline' },
  { key: 'awaiting', label: 'Waiting', empty: 'Nobody is paying right now.', icon: 'checkmark-circle-outline' },
];

export default function Today() {
  const c = useColors();
  const staff = useStaff();
  const [city, setCity] = useState('');
  const [tab, setTab] = useState<TabKey | null>(null);
  const { data, isLoading, error, refetch, isRefetching } = useQuery({
    queryKey: ['staff', 'overview', city],
    refetchInterval: 30000,
    queryFn: () => staff.call((token) => get<Overview>('staff/overview/', { token, params: { city } })),
  });

  // Open on the first list with something in it, until the staff member picks one.
  const active = tab ?? (data ? TABS.find((t) => data[t.key].length)?.key : undefined) ?? 'pickups';
  const list = data ? data[active] : [];

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <Tabs.Screen options={{
        headerRight: () => <IconButton icon="log-out-outline" label="Sign out" color={c.onBrand} onPress={() => Alert.alert('Sign out of the staff app?', undefined, [
          { text: 'Stay signed in', style: 'cancel' }, { text: 'Sign out', style: 'destructive', onPress: staff.signOut },
        ])} />,
      }} />
      <ScrollView contentContainerStyle={{ paddingBottom: space.xxl }} refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => { refetch(); }} />}>
        <View style={{ padding: space.lg, gap: space.md }}>
          <Text variant="muted">
            {staff.user ? `Signed in as ${staff.user.name} · ` : ''}
            {staff.user?.branch ? `${staff.user.branch.name} branch` : city ? staff.user?.branches.find((b) => b.slug === city)?.name : 'All of Kenya'}
          </Text>
          {staff.user?.is_owner && staff.user.branches.length ? (
            <ScrollView horizontal style={{ flexGrow: 0 }} showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
              <Chip label="All of Kenya" selected={!city} onPress={() => setCity('')} />
              {staff.user.branches.map((b) => <Chip key={b.slug} label={b.name} selected={city === b.slug} onPress={() => setCity(b.slug)} />)}
            </ScrollView>
          ) : null}
          {isLoading ? <Loading /> : error ? <ErrorText>{(error as Error).message}</ErrorText> : data ? (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
              <Stat icon="cash-outline" value={kes(data.stats.revenue_today)} label={`Paid today · ${data.stats.paid_today}`} />
              <Stat icon="trending-up-outline" value={kes(data.stats.revenue_month)} label="Paid this month" />
              <Stat icon="car-outline" value={String(data.stats.on_the_road)} label="Cars out now" />
              <Stat icon="hourglass-outline" value={String(data.stats.awaiting_payment)} label="Waiting for payment" warn={data.stats.awaiting_payment > 0} />
            </View>
          ) : null}
          {data?.stats.returning ? (
            <Card style={{ backgroundColor: c.warnBg, borderColor: c.warnBg }}>
              <Row gap={space.sm}><Icon name="git-branch-outline" color={c.warnText} />
                <Text variant="label" color={c.warnText} style={{ flex: 1 }}>{data.stats.returning} one-way car{data.stats.returning === 1 ? '' : 's'} to move. Open each booking and mark the car as arrived.</Text></Row>
            </Card>
          ) : null}
        </View>

        {data ? (
          <View style={{ marginHorizontal: space.lg, borderRadius: radius.lg, overflow: 'hidden', borderWidth: 1, borderColor: c.border, backgroundColor: c.surface }}>
            <Row gap={0} style={{ borderBottomWidth: 1, borderBottomColor: c.border }}>
              {TABS.map((t) => {
                const on = t.key === active;
                const n = data[t.key].length;
                return (
                  <Pressable key={t.key} onPress={() => setTab(t.key)} accessibilityRole="tab" accessibilityState={{ selected: on }}
                    style={{ flex: 1, alignItems: 'center', gap: 3, paddingVertical: space.sm, minHeight: 52, borderBottomWidth: 3, borderBottomColor: on ? c.plate : 'transparent' }}>
                    <Text variant="small" color={on ? c.text : c.muted} style={{ fontSize: 13 }}>{t.label}</Text>
                    <View style={{ minWidth: 22, paddingHorizontal: 6, borderRadius: 11, backgroundColor: n ? c.primary : c.neutralBg }}>
                      <Text variant="small" color={n ? c.onPrimary : c.neutralText} style={{ fontSize: 12, textAlign: 'center' }}>{n}</Text>
                    </View>
                  </Pressable>
                );
              })}
            </Row>
            {list.length ? list.map((b) => (
              <StaffBookingRow key={b.ref} b={b} when={active === 'pickups' ? 'pickup' : active === 'returns' ? 'return' : undefined} />
            )) : <EmptyState icon={TABS.find((t) => t.key === active)!.icon} title={TABS.find((t) => t.key === active)!.empty} />}
          </View>
        ) : null}

        {data?.latest.length ? (
          <View style={{ marginTop: space.lg }}>
            <Text variant="heading" style={{ paddingHorizontal: space.lg, marginBottom: space.sm }}>Latest bookings</Text>
            <View style={{ marginHorizontal: space.lg, borderRadius: radius.lg, overflow: 'hidden', borderWidth: 1, borderColor: c.border }}>
              {data.latest.map((b) => <StaffBookingRow key={b.ref} b={b} />)}
            </View>
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

function Stat({ icon, value, label, warn }: { icon: IconName; value: string; label: string; warn?: boolean }) {
  const c = useColors();
  return (
    <Card style={{ width: '48.5%', gap: 6, padding: space.md }}>
      <View style={{ width: 34, height: 34, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', backgroundColor: warn ? c.warnBg : c.tint }}>
        <Icon name={icon} size={18} color={warn ? c.warnText : c.text} />
      </View>
      <Text variant="heading" numberOfLines={1} adjustsFontSizeToFit>{value}</Text>
      <Text variant="muted" numberOfLines={2}>{label}</Text>
    </Card>
  );
}
