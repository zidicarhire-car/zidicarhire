import Constants from 'expo-constants';
import { router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { Linking, Pressable, View } from 'react-native';

import { Card, Divider, Icon, Row, Screen, SectionTitle, Text, type IconName } from '@/components/ui';
import { useConfig } from '@/hooks/use-config';
import { useStaff } from '@/state/staff';
import { space, useColors } from '@/theme';

export default function More() {
  const { data: config } = useConfig();
  const staff = useStaff();
  const biz = config?.business;

  return (
    <Screen>
      <SectionTitle>Contact us</SectionTitle>
      <Card style={{ gap: 0, paddingVertical: space.xs }}>
        {biz?.phone ? <Item icon="call-outline" label="Call us" detail={biz.phone} onPress={() => Linking.openURL(`tel:${biz.phone}`)} /> : null}
        {biz?.whatsapp ? <><Divider /><Item icon="logo-whatsapp" label="WhatsApp" detail="Message us"
          onPress={() => Linking.openURL(`https://wa.me/${biz.whatsapp}?text=${encodeURIComponent('Hi, I would like to hire a car.')}`)} /></> : null}
        {biz?.email ? <><Divider /><Item icon="mail-outline" label="Email" detail={biz.email} onPress={() => Linking.openURL(`mailto:${biz.email}`)} /></> : null}
        <Divider />
        <Item icon="chatbubbles-outline" label="Live chat" detail="Instant answers, or a person" onPress={() => router.navigate('/chat')} />
      </Card>

      <SectionTitle>Branches</SectionTitle>
      <Card style={{ gap: 0, paddingVertical: space.xs }}>
        {(config?.branches ?? []).map((b, i) => (
          <View key={b.slug}>
            {i ? <Divider /> : null}
            <Item icon="business-outline" label={b.name} detail={b.address || b.opening_hours || b.city}
              onPress={() => b.maps_url ? Linking.openURL(b.maps_url) : Linking.openURL(`tel:${b.phone}`)} />
          </View>
        ))}
      </Card>

      <SectionTitle>Help</SectionTitle>
      <Card style={{ gap: 0, paddingVertical: space.xs }}>
        <Item icon="search-outline" label="Find my booking" onPress={() => router.push('/find')} />
        {config ? <>
          <Divider /><Item icon="help-circle-outline" label="Questions" onPress={() => WebBrowser.openBrowserAsync(config.links.faq)} />
          <Divider /><Item icon="document-text-outline" label="Terms of hire" onPress={() => WebBrowser.openBrowserAsync(config.links.terms)} />
          <Divider /><Item icon="lock-closed-outline" label="Privacy policy" onPress={() => WebBrowser.openBrowserAsync(config.links.privacy)} />
        </> : null}
      </Card>

      <SectionTitle>Staff</SectionTitle>
      <Card style={{ gap: 0, paddingVertical: space.xs }}>
        <Item icon="briefcase-outline" label={staff.user ? 'Open the staff dashboard' : 'Staff sign in'}
          detail={staff.user ? `Signed in as ${staff.user.name}` : 'Bookings, pick-ups, returns and chats'}
          onPress={() => router.push(staff.token ? '/staff' : '/staff/login')} />
      </Card>

      <Text variant="muted" style={{ textAlign: 'center' }}>
        {biz?.name ?? 'ZIDICARHIRE'} · version {Constants.expoConfig?.version ?? '1.0.0'}
      </Text>
    </Screen>
  );
}

function Item({ icon, label, detail, onPress }: { icon: IconName; label: string; detail?: string; onPress: () => void }) {
  const c = useColors();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })}>
      <Row gap={space.md} style={{ minHeight: 56, paddingVertical: space.sm }}>
        <Icon name={icon} size={22} color={c.muted} />
        <View style={{ flex: 1 }}>
          <Text variant="label">{label}</Text>
          {detail ? <Text variant="muted" numberOfLines={1}>{detail}</Text> : null}
        </View>
        <Icon name="chevron-forward" size={18} color={c.muted} />
      </Row>
    </Pressable>
  );
}
