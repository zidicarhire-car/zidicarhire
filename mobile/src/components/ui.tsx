/** The app's building blocks, in the website's brand: indigo, plate yellow, Inter, 44px touch targets. */
import Ionicons from '@expo/vector-icons/Ionicons';
import type { ComponentProps, ReactNode } from 'react';
import {
  ActivityIndicator, Pressable, ScrollView, StyleSheet, Text as RNText, TextInput, View,
  type PressableProps, type StyleProp, type TextInputProps, type TextProps, type TextStyle, type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { fonts, radius, space, useColors, type Palette } from '@/theme';

export type IconName = ComponentProps<typeof Ionicons>['name'];

// ---------- Text ----------

type Variant = 'display' | 'title' | 'heading' | 'subheading' | 'body' | 'label' | 'small' | 'muted';

const variants: Record<Variant, TextStyle> = {
  display: { fontFamily: fonts.bold, fontSize: 32, lineHeight: 36, letterSpacing: -0.6 },
  title: { fontFamily: fonts.bold, fontSize: 24, lineHeight: 30, letterSpacing: -0.4 },
  heading: { fontFamily: fonts.semibold, fontSize: 18, lineHeight: 24, letterSpacing: -0.2 },
  subheading: { fontFamily: fonts.semibold, fontSize: 16, lineHeight: 22 },
  body: { fontFamily: fonts.regular, fontSize: 16, lineHeight: 23 },
  label: { fontFamily: fonts.semibold, fontSize: 14, lineHeight: 19 },
  small: { fontFamily: fonts.regular, fontSize: 14, lineHeight: 20 },
  muted: { fontFamily: fonts.regular, fontSize: 14, lineHeight: 20 },
};

export function Text({ variant = 'body', color, style, ...rest }: TextProps & { variant?: Variant; color?: string }) {
  const c = useColors();
  return <RNText {...rest} style={[variants[variant], { color: color ?? (variant === 'muted' ? c.muted : c.text) }, style]} />;
}

export function Icon({ name, size = 20, color }: { name: IconName; size?: number; color?: string }) {
  const c = useColors();
  return <Ionicons name={name} size={size} color={color ?? c.text} />;
}

// ---------- Layout ----------

export function Screen({ children, scroll = true, padded = true, edges = ['bottom'], refresh, style }: {
  children: ReactNode;
  scroll?: boolean;
  padded?: boolean;
  edges?: ('top' | 'bottom' | 'left' | 'right')[];
  refresh?: ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  const c = useColors();
  const inner = { padding: padded ? space.lg : 0, gap: space.lg };
  return (
    <SafeAreaView edges={edges} style={{ flex: 1, backgroundColor: c.bg }}>
      {scroll ? (
        <ScrollView contentContainerStyle={[inner, { paddingBottom: space.xxl }, style]} keyboardShouldPersistTaps="handled"
          refreshControl={refresh as never}>
          {children}
        </ScrollView>
      ) : (
        <View style={[{ flex: 1 }, inner, style]}>{children}</View>
      )}
    </SafeAreaView>
  );
}

export function Card({ children, style, onPress }: { children: ReactNode; style?: StyleProp<ViewStyle>; onPress?: () => void }) {
  const c = useColors();
  const base: ViewStyle = {
    backgroundColor: c.surface, borderColor: c.border, borderWidth: StyleSheet.hairlineWidth * 2,
    borderRadius: radius.lg, padding: space.lg, gap: space.sm,
  };
  if (!onPress) return <View style={[base, style]}>{children}</View>;
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [base, pressed && { opacity: 0.85 }, style]} accessibilityRole="button">
      {children}
    </Pressable>
  );
}

export function Row({ children, gap = space.sm, style }: { children: ReactNode; gap?: number; style?: StyleProp<ViewStyle> }) {
  return <View style={[{ flexDirection: 'row', alignItems: 'center', gap }, style]}>{children}</View>;
}

export function Divider() {
  const c = useColors();
  return <View style={{ height: StyleSheet.hairlineWidth * 2, backgroundColor: c.border }} />;
}

// ---------- Buttons ----------

type Kind = 'primary' | 'plate' | 'ghost' | 'mpesa' | 'danger';

function kindStyle(kind: Kind, c: Palette) {
  switch (kind) {
    case 'plate': return { bg: c.plate, fg: c.plateInk, border: c.plateInk };
    case 'ghost': return { bg: 'transparent', fg: c.text, border: c.controlBorder };
    case 'mpesa': return { bg: c.mpesa, fg: c.onMpesa, border: c.mpesa };
    case 'danger': return { bg: 'transparent', fg: c.danger, border: c.danger };
    default: return { bg: c.primary, fg: c.onPrimary, border: c.primary };
  }
}

export function Button({ title, onPress, kind = 'primary', icon, loading, disabled, size = 'md', style, accessibilityLabel }: {
  title: string;
  onPress?: PressableProps['onPress'];
  kind?: Kind;
  icon?: IconName;
  loading?: boolean;
  disabled?: boolean;
  size?: 'sm' | 'md' | 'lg';
  style?: StyleProp<ViewStyle>;
  accessibilityLabel?: string;
}) {
  const c = useColors();
  const k = kindStyle(kind, c);
  const height = size === 'lg' ? 54 : size === 'sm' ? 40 : 48;
  const off = disabled || loading;
  return (
    <Pressable
      onPress={off ? undefined : onPress}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? title}
      accessibilityState={{ disabled: !!off, busy: !!loading }}
      style={({ pressed }) => [{
        minHeight: height, paddingHorizontal: size === 'sm' ? space.md : space.lg, borderRadius: radius.md,
        backgroundColor: k.bg, borderColor: k.border, borderWidth: 2, flexDirection: 'row', alignItems: 'center',
        justifyContent: 'center', gap: space.sm, opacity: off ? 0.5 : pressed ? 0.85 : 1,
      }, style]}>
      {loading ? <ActivityIndicator color={k.fg} /> : (
        <>
          {icon ? <Ionicons name={icon} size={size === 'sm' ? 16 : 19} color={k.fg} /> : null}
          {title ? <RNText style={{ color: k.fg, fontFamily: fonts.semibold, fontSize: size === 'sm' ? 14 : 16 }}>{title}</RNText> : null}
        </>
      )}
    </Pressable>
  );
}

export function IconButton({ icon, onPress, label, size = 22, color }: { icon: IconName; onPress: () => void; label: string; size?: number; color?: string }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label} hitSlop={8}
      style={({ pressed }) => ({ minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center', opacity: pressed ? 0.6 : 1 })}>
      <Icon name={icon} size={size} color={color} />
    </Pressable>
  );
}

// ---------- Brand pieces ----------

/** The number plate: prices, booking numbers. */
export function Plate({ children, size = 'md' }: { children: ReactNode; size?: 'sm' | 'md' | 'lg' | 'xl' }) {
  const c = useColors();
  const fontSize = { sm: 13, md: 18, lg: 24, xl: 34 }[size];
  return (
    <View style={{ alignSelf: 'flex-start', backgroundColor: c.plate, borderColor: c.plateInk, borderWidth: 2,
      borderRadius: radius.sm, paddingHorizontal: size === 'sm' ? 6 : 10, paddingVertical: size === 'sm' ? 1 : 2 }}>
      <RNText style={{ fontFamily: fonts.plate, fontSize, color: c.plateInk, letterSpacing: 0.6 }}>{children}</RNText>
    </View>
  );
}

export function Chip({ label, selected, onPress, icon, accessibilityLabel }: {
  label: string; selected?: boolean; onPress?: () => void; icon?: IconName; accessibilityLabel?: string;
}) {
  const c = useColors();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityState={{ selected: !!selected }}
      accessibilityLabel={accessibilityLabel ?? label}
      style={({ pressed }) => ({
        minHeight: 40, paddingHorizontal: 14, borderRadius: radius.pill, borderWidth: 1.5,
        borderColor: selected ? c.primary : c.controlBorder, backgroundColor: selected ? c.primary : c.surface,
        flexDirection: 'row', alignItems: 'center', gap: 6, opacity: pressed ? 0.8 : 1,
      })}>
      {icon ? <Ionicons name={icon} size={15} color={selected ? c.onPrimary : c.text} /> : null}
      <RNText style={{ fontFamily: fonts.semibold, fontSize: 14, color: selected ? c.onPrimary : c.text }}>{label}</RNText>
    </Pressable>
  );
}

const STATUS_COLORS = (c: Palette): Record<string, [string, string]> => ({
  paid: [c.successBg, c.successText],
  picked_up: [c.infoBg, c.infoText],
  completed: [c.neutralBg, c.neutralText],
  pending: [c.warnBg, c.warnText],
  failed: [c.dangerBg, c.danger],
  cancelled: [c.dangerBg, c.danger],
});

export function StatusBadge({ status, label }: { status: string; label: string }) {
  const c = useColors();
  const [bg, fg] = STATUS_COLORS(c)[status] ?? [c.neutralBg, c.neutralText];
  return (
    <View style={{ alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: bg,
      borderRadius: radius.pill, paddingHorizontal: 9, paddingVertical: 3 }}>
      <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: fg }} />
      <RNText style={{ fontFamily: fonts.semibold, fontSize: 12, color: fg }}>{label}</RNText>
    </View>
  );
}

// ---------- Forms ----------

export function Field({ label, error, hint, style, ...input }: TextInputProps & { label: string; error?: string; hint?: string }) {
  const c = useColors();
  return (
    <View style={{ gap: 6 }}>
      <Text variant="label">{label}</Text>
      <TextInput
        placeholderTextColor={c.placeholder}
        accessibilityLabel={label}
        {...input}
        style={[{
          minHeight: 48, borderWidth: 1.5, borderColor: error ? c.danger : c.controlBorder, borderRadius: radius.md,
          paddingHorizontal: space.md, fontSize: 16, fontFamily: fonts.regular, color: c.text, backgroundColor: c.surface,
        }, input.multiline && { minHeight: 90, paddingTop: space.md, textAlignVertical: 'top' }, style]}
      />
      {error ? <Text variant="small" color={c.danger}>{error}</Text> : hint ? <Text variant="muted">{hint}</Text> : null}
    </View>
  );
}

export function ErrorText({ children }: { children?: string | null }) {
  const c = useColors();
  if (!children) return null;
  return (
    <View accessibilityRole="alert" style={{ flexDirection: 'row', gap: 8, backgroundColor: c.dangerBg, borderRadius: radius.md, padding: space.md }}>
      <Ionicons name="alert-circle" size={18} color={c.danger} />
      <Text variant="small" color={c.danger} style={{ flex: 1 }}>{children}</Text>
    </View>
  );
}

export function EmptyState({ icon, title, text, action }: { icon: IconName; title: string; text?: string; action?: ReactNode }) {
  const c = useColors();
  return (
    <View style={{ alignItems: 'center', gap: space.sm, paddingVertical: space.xxl, paddingHorizontal: space.lg }}>
      <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: c.surface2, alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name={icon} size={28} color={c.muted} />
      </View>
      <Text variant="subheading" style={{ textAlign: 'center' }}>{title}</Text>
      {text ? <Text variant="muted" style={{ textAlign: 'center', maxWidth: 320 }}>{text}</Text> : null}
      {action}
    </View>
  );
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  const c = useColors();
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xxl, gap: space.md }} accessibilityLabel={label}>
      <ActivityIndicator size="large" color={c.text} />
    </View>
  );
}

/** Label on the left, value on the right: booking facts and price lines. */
export function Fact({ label, value, strong }: { label: string; value: ReactNode; strong?: boolean }) {
  return (
    <Row style={{ justifyContent: 'space-between', paddingVertical: 6, alignItems: 'flex-start' }} gap={space.lg}>
      <Text variant={strong ? 'label' : 'muted'} style={{ flexShrink: 0, maxWidth: '62%' }}>{label}</Text>
      {typeof value === 'string' || typeof value === 'number'
        ? <Text variant={strong ? 'subheading' : 'label'} style={{ textAlign: 'right', flex: 1 }}>{value}</Text>
        : value}
    </Row>
  );
}

export function SectionTitle({ children, action }: { children: string; action?: ReactNode }) {
  return (
    <Row style={{ justifyContent: 'space-between', marginTop: space.sm }}>
      <Text variant="heading">{children}</Text>
      {action}
    </Row>
  );
}
