/**
 * Pick-up and return dates, with the website's rules: a booked day can't be a pick-up day or sit inside the
 * hire, but it can be the return day (the car is free again that day). Booked days are struck through, not
 * only coloured.
 */
import { Pressable, Text as RNText, View } from 'react-native';
import { Calendar, type DateData } from 'react-native-calendars';

import { Row, Text } from '@/components/ui';
import { addDays, daysBetween } from '@/lib/format';
import { fonts, radius, useColors } from '@/theme';

type Props = {
  start: string | null;
  end: string | null;
  min: string;
  maxDays: number;
  unavailable: Set<string>;
  onChange: (start: string | null, end: string | null) => void;
  onMessage: (message: string) => void;
};

export function blockedBetween(unavailable: Set<string>, from: string, to: string) {
  for (let d = from; d < to; d = addDays(d, 1)) if (unavailable.has(d)) return d;
  return null;
}

export function DateRange({ start, end, min, maxDays, unavailable, onChange, onMessage }: Props) {
  const c = useColors();
  const canStart = (d: string) => d >= min && !unavailable.has(d);
  const canEnd = (d: string) =>
    !!start && d > start && daysBetween(start, d) <= maxDays && !blockedBetween(unavailable, start, d);

  function pick(day: string) {
    if (day < min) return;
    if (start && !end && day > start) {
      if (canEnd(day)) { onMessage(''); onChange(start, day); return; }
      if (daysBetween(start, day) > maxDays) { onMessage(`Hires can be up to ${maxDays} days. Chat with us for longer.`); return; }
      const blocked = blockedBetween(unavailable, start, day);
      if (blocked && canStart(day)) { onMessage('The car is booked in between. Starting again from this day.'); onChange(day, null); return; }
      onMessage('The car is booked on some of those days. Choose an earlier return day.');
      return;
    }
    if (canStart(day)) { onMessage(''); onChange(day, null); }
    else onMessage('The car is booked that day. Choose another pick-up day.');
  }

  return (
    <View>
      <Calendar
        minDate={min}
        firstDay={1}
        enableSwipeMonths
        current={start ?? min}
        theme={{
          calendarBackground: 'transparent', monthTextColor: c.text, textMonthFontFamily: fonts.semibold,
          textSectionTitleColor: c.muted, textDayHeaderFontFamily: fonts.semibold, arrowColor: c.text,
        }}
        dayComponent={({ date, state }: { date?: DateData; state?: string }) => {
          if (!date) return <View />;
          const d = date.dateString;
          const isEdge = d === start || d === end;
          const inside = !!start && !!end && d > start && d < end;
          const booked = unavailable.has(d);
          const past = d < min;
          const outside = state === 'disabled' && !past;
          return (
            <Pressable onPress={() => pick(d)} disabled={past}
              accessibilityRole="button"
              accessibilityLabel={`${d}${booked ? ', booked' : ''}${d === start ? ', pick-up day' : ''}${d === end ? ', return day' : ''}`}
              style={{
                width: 44, height: 44, alignItems: 'center', justifyContent: 'center', borderRadius: radius.md,
                backgroundColor: isEdge ? c.plate : inside ? `${c.plate}55` : 'transparent',
                borderWidth: isEdge ? 2 : 0, borderColor: c.plateInk, opacity: outside ? 0.35 : 1,
              }}>
              <RNText style={{
                fontFamily: isEdge || state === 'today' ? fonts.bold : fonts.regular, fontSize: 15,
                color: isEdge ? c.plateInk : past || booked ? c.muted : c.text,
                textDecorationLine: booked ? 'line-through' : state === 'today' ? 'underline' : 'none',
              }}>{date.day}</RNText>
            </Pressable>
          );
        }}
      />
      <Row gap={16} style={{ marginTop: 4 }}>
        <Row gap={6}>
          <RNText style={{ textDecorationLine: 'line-through', color: c.muted, fontFamily: fonts.semibold }}>8</RNText>
          <Text variant="muted">Booked</Text>
        </Row>
        <Row gap={6}>
          <View style={{ width: 18, height: 18, borderRadius: 4, backgroundColor: c.plate, borderWidth: 2, borderColor: c.plateInk }} />
          <Text variant="muted">Your dates</Text>
        </Row>
      </Row>
    </View>
  );
}
