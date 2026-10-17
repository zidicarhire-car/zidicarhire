import { useState } from 'react';
import { Modal, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { DateRange } from '@/components/date-range';
import { Button, IconButton, Row, Text } from '@/components/ui';
import { daysBetween, fmtDay, plural, today } from '@/lib/format';
import { space, useColors } from '@/theme';

/** A full-height sheet to choose trip dates (no booked days: those are checked per car). */
export function DatesSheet({ visible, from, to, maxDays = 60, onClose, onDone }: {
  visible: boolean; from: string; to: string; maxDays?: number; onClose: () => void; onDone: (from: string, to: string) => void;
}) {
  const c = useColors();
  const [start, setStart] = useState<string | null>(from);
  const [end, setEnd] = useState<string | null>(to);
  const [message, setMessage] = useState('');
  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}
      onShow={() => { setStart(from); setEnd(to); setMessage(''); }}>
      <SafeAreaView style={{ flex: 1, backgroundColor: c.bg }}>
        <Row style={{ justifyContent: 'space-between', paddingHorizontal: space.lg, paddingTop: space.sm }}>
          <Text variant="heading">When do you need the car?</Text>
          <IconButton icon="close" label="Close" onPress={onClose} />
        </Row>
        <ScrollView contentContainerStyle={{ padding: space.lg, gap: space.md }}>
          <DateRange start={start} end={end} min={today()} maxDays={maxDays} unavailable={new Set()}
            onChange={(s, e) => { setStart(s); setEnd(e); }} onMessage={setMessage} />
          <Text variant="label">
            {!start ? 'Tap your pick-up date.' : !end ? `Pick-up ${fmtDay(start)}. Now tap your return date.`
              : `${fmtDay(start)} to ${fmtDay(end)}, ${plural(daysBetween(start, end), 'day')}`}
          </Text>
          {message ? <Text variant="small" color={c.danger}>{message}</Text> : null}
        </ScrollView>
        <View style={{ padding: space.lg, borderTopWidth: 1, borderTopColor: c.border, backgroundColor: c.surface }}>
          <Button title="Use these dates" size="lg" disabled={!start || !end}
            onPress={() => { if (start && end) { onDone(start, end); onClose(); } }} />
        </View>
      </SafeAreaView>
    </Modal>
  );
}
