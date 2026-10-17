import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Stack, useLocalSearchParams } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useState } from 'react';
import { Alert, Linking, RefreshControl, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { DatesSheet } from '@/components/dates-sheet';
import { FormSheet } from '@/components/form-sheet';
import { Button, Card, Chip, Divider, ErrorText, Fact, Field, Loading, Plate, Row, StatusBadge, Text } from '@/components/ui';
import { useConfig } from '@/hooks/use-config';
import { get, post } from '@/lib/api';
import { fmtDay, kes, plural } from '@/lib/format';
import type { AdminBookingDetail } from '@/lib/types';
import { useStaff } from '@/state/staff';
import { space, useColors } from '@/theme';

type Sheet = null | 'cancel' | 'mark_paid' | 'balance' | 'dates';
type Preview = { days: number; daily_rate: number; old_total: number; total: number; difference: number; difference_abs: number };

export default function StaffBooking() {
  const c = useColors();
  const { ref } = useLocalSearchParams<{ ref: string }>();
  const staff = useStaff();
  const qc = useQueryClient();
  const { data: config } = useConfig();
  const [sheet, setSheet] = useState<Sheet>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reason, setReason] = useState('');
  const [code, setCode] = useState('');
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [pickingDates, setPickingDates] = useState(false);
  const [dates, setDates] = useState({ pickup_date: '', return_date: '', pickup_time: '', return_time: '' });
  const [preview, setPreview] = useState<Preview | null>(null);

  const { data: b, isLoading, error: loadError, refetch, isRefetching } = useQuery({
    queryKey: ['staff', 'booking', ref],
    queryFn: () => staff.call((token) => get<{ booking: AdminBookingDetail }>(`staff/bookings/${ref}/`, { token }).then((r) => r.booking)),
  });

  async function act(action: string, extra: Record<string, unknown> = {}) {
    setBusy(true); setError('');
    try {
      const res = await staff.call((token) => post<{ booking?: AdminBookingDetail; preview?: Preview }>(`staff/bookings/${ref}/action/`, { action, ...extra }, { token }));
      if (res.preview) { setPreview(res.preview); return; }
      if (res.booking) qc.setQueryData(['staff', 'booking', ref], res.booking);
      qc.invalidateQueries({ queryKey: ['staff', 'overview'] });
      qc.invalidateQueries({ queryKey: ['staff', 'bookings'] });
      setSheet(null); setReason(''); setCode(''); setNote(''); setPreview(null);
    } catch (err) {
      const message = (err as Error).message;
      if (sheet) setError(message); else Alert.alert("That didn't work", message);
    } finally {
      setBusy(false);
    }
  }

  const confirm = (title: string, action: string, yes: string) => Alert.alert(title, undefined, [
    { text: 'Go back', style: 'cancel' }, { text: yes, onPress: () => act(action) },
  ]);

  if (isLoading) return <Loading />;
  if (loadError || !b) return <SafeAreaView style={{ padding: space.lg }}><ErrorText>{(loadError as Error)?.message ?? 'Booking not found.'}</ErrorText></SafeAreaView>;
  const a = b.allowed;

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <Stack.Screen options={{ title: b.ref }} />
      <ScrollView contentContainerStyle={{ padding: space.lg, gap: space.lg, paddingBottom: space.xxl }}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => { refetch(); }} />}>
        <View style={{ gap: space.sm }}>
          <Row style={{ flexWrap: 'wrap' }}><Plate size="lg">{b.ref}</Plate><StatusBadge status={b.status} label={b.status_label} /></Row>
          <Text variant="muted">Booked {b.created}{b.paid_at ? ` · paid ${b.paid_at}` : ''}</Text>
        </View>

        <Card>
          <Text variant="heading">Actions</Text>
          {a.pickup ? <Button title="Mark picked up" icon="exit-outline" onPress={() => confirm(`Mark ${b.car} as picked up by ${b.customer_name}?`, 'pickup', 'Yes, picked up')} /> : null}
          {a.return ? <Button title="Mark returned" icon="enter-outline" onPress={() => confirm(`Mark ${b.car} as returned? It becomes free to book again from today.`, 'return', 'Yes, returned')} /> : null}
          {a.relocate ? <Button title={`Car arrived in ${b.return_city}`} icon="git-branch-outline" kind="ghost"
            onPress={() => confirm(`Has ${b.car} arrived in ${b.return_city}? It will be listed there from now on.`, 'relocate', 'Yes, move the car')} /> : null}
          {a.balance ? <Button title={`Record balance payment (${kes(b.balance)} owed)`} icon="cash-outline" kind="mpesa"
            onPress={() => { setAmount(String(b.balance)); setError(''); setSheet('balance'); }} /> : null}
          {a.mark_paid ? <Button title="Mark paid manually" icon="checkmark-circle-outline" kind="ghost" onPress={() => { setError(''); setSheet('mark_paid'); }} /> : null}
          {a.dates ? <Button title="Change dates" icon="calendar-outline" kind="ghost" onPress={() => {
            setDates({ pickup_date: b.pickup_date, return_date: b.return_date, pickup_time: b.pickup_time, return_time: b.return_time });
            setPreview(null); setError(''); setSheet('dates');
          }} /> : null}
          {a.resend ? <Button title="Resend confirmation email" icon="mail-outline" kind="ghost"
            onPress={() => confirm(`Send the confirmation and receipt again to ${b.email}?`, 'resend', 'Yes, send it')} /> : null}
          {a.receipt && b.receipt_url ? <Button title="Open receipt" icon="document-text-outline" kind="ghost" onPress={() => WebBrowser.openBrowserAsync(b.receipt_url!)} /> : null}
          <Row>
            <Button title="Call" icon="call-outline" kind="ghost" style={{ flex: 1 }} onPress={() => Linking.openURL(`tel:${b.phone}`)} />
            {b.whatsapp_link ? <Button title="WhatsApp" icon="logo-whatsapp" kind="ghost" style={{ flex: 1 }} onPress={() => Linking.openURL(b.whatsapp_link)} /> : null}
          </Row>
          {a.cancel ? <Button title="Cancel booking" icon="close-circle-outline" kind="danger" onPress={() => { setError(''); setSheet('cancel'); }} /> : null}
        </Card>

        <Card style={{ gap: 0 }}>
          <Text variant="heading" style={{ marginBottom: space.sm }}>Customer</Text>
          <Fact label="Name" value={b.customer_name} />
          <Fact label="Phone" value={b.phone} />
          <Fact label="Email" value={b.email || 'Not given'} />
          <Fact label="ID or passport" value={b.id_number || 'Not given'} />
          <Fact label="Driving licence" value={b.licence_number || 'Not given'} />
        </Card>

        <Card style={{ gap: 0 }}>
          <Text variant="heading" style={{ marginBottom: space.sm }}>Car and dates</Text>
          <Fact label="Car" value={b.car} />
          <Fact label="Pick-up" value={`${fmtDay(b.pickup_date)}, ${b.pickup_time}${b.pickup_point ? `\n${b.pickup_point}, ${b.city}` : ''}`} />
          <Fact label="Return" value={`${fmtDay(b.return_date)}, ${b.return_time}${b.return_city ? `\n${b.return_city} (one-way)` : ''}`} />
          <Fact label="Length" value={plural(b.days, 'day')} />
          {b.notes ? <Fact label="Customer notes" value={b.notes} /> : null}
        </Card>

        <Card style={{ gap: 0 }}>
          <Text variant="heading" style={{ marginBottom: space.sm }}>Price</Text>
          {b.breakdown.map((line, i) => (
            <View key={`${line.label}${i}`}>{line.total ? <Divider /> : null}<Fact label={line.label} value={kes(line.amount)} strong={line.total} /></View>
          ))}
          <Fact label="Paid" value={`${kes(b.amount_paid)}${b.receipt ? ` (${b.receipt})` : ''}`} />
          {b.balance > 0 && b.status !== 'pending' ? <Fact label="Customer still owes" value={kes(b.balance)} strong /> : null}
        </Card>

        <Card>
          <Text variant="heading">M-Pesa payment attempts</Text>
          {b.payments.length ? b.payments.map((p, i) => (
            <View key={i} style={{ gap: 2, paddingVertical: 4 }}>
              <StatusBadge status={p.status === 'success' ? 'paid' : p.status === 'pending' ? 'pending' : 'failed'} label={p.label} />
              <Text variant="small">{kes(p.amount)} to {p.phone} · {p.at}</Text>
              {p.receipt ? <Text variant="muted">M-Pesa receipt {p.receipt}</Text> : null}
              {p.result ? <Text variant="muted">{p.result}</Text> : null}
            </View>
          )) : <Text variant="muted">No M-Pesa prompts were sent for this booking.</Text>}
        </Card>

        <Card>
          <Text variant="heading">Timeline and notes</Text>
          <Field label="Add an internal note (only staff see this)" value={note} onChangeText={setNote} multiline maxLength={2000}
            placeholder="e.g. Customer asked for delivery to Westlands at 9am" />
          <Button title="Add note" icon="add" kind="ghost" size="sm" disabled={!note.trim()} loading={busy && !sheet} onPress={() => act('note', { note })} />
          {b.events.map((e, i) => (
            <View key={i} style={{ borderTopWidth: 1, borderTopColor: c.border, paddingTop: space.sm, gap: 2, backgroundColor: e.kind === 'note' ? c.warnBg : undefined }}>
              <Text variant="muted">{e.at}</Text>
              <Text variant="label">{e.label} · {e.who}</Text>
              {e.message ? <Text variant="small">{e.message}</Text> : null}
            </View>
          ))}
        </Card>
      </ScrollView>

      <FormSheet visible={sheet === 'cancel'} title={`Cancel ${b.ref}?`} confirm="Cancel booking" kind="danger" busy={busy} error={error}
        message={b.amount_paid ? `The customer paid ${kes(b.amount_paid)}. Cancelling does not refund M-Pesa: send any refund from your till by hand.` : undefined}
        onClose={() => setSheet(null)} onConfirm={() => act('cancel', { reason })}>
        <Field label="Why is it cancelled?" value={reason} onChangeText={setReason} multiline placeholder="e.g. Customer changed plans, refund sent by M-Pesa" />
      </FormSheet>

      <FormSheet visible={sheet === 'mark_paid'} title={`Mark ${b.ref} as paid`} confirm="Mark as paid" busy={busy} error={error}
        message={`Only do this after you see the ${kes(b.pay_now)} payment on your till statement.`}
        onClose={() => setSheet(null)} onConfirm={() => act('mark_paid', { code })}>
        <Field label="M-Pesa code" value={code} onChangeText={(v) => setCode(v.toUpperCase())} autoCapitalize="characters" maxLength={12} placeholder="SJK1ABC2DE" />
      </FormSheet>

      <FormSheet visible={sheet === 'balance'} title={`Record a payment for ${b.ref}`} confirm="Record payment" kind="mpesa" busy={busy} error={error}
        message={`${b.customer_name} has paid ${kes(b.amount_paid)} of ${kes(b.amount)} and still owes ${kes(b.balance)}.`}
        onClose={() => setSheet(null)} onConfirm={() => act('balance', { amount, code })}>
        <Field label="Amount received (KES)" value={amount} onChangeText={(v) => setAmount(v.replace(/\D/g, ''))} keyboardType="number-pad" />
        <Field label="M-Pesa code (leave blank for cash)" value={code} onChangeText={(v) => setCode(v.toUpperCase())} autoCapitalize="characters" maxLength={12} />
      </FormSheet>

      <FormSheet visible={sheet === 'dates'} title={`Change dates for ${b.ref}`} busy={busy} error={error}
        confirm={preview ? 'Change to these dates' : 'Check dates and price'}
        onClose={() => setSheet(null)}
        onConfirm={() => act(preview ? 'change_dates' : 'preview_dates', dates)}>
        <Button title={`${fmtDay(dates.pickup_date || b.pickup_date)} → ${fmtDay(dates.return_date || b.return_date)}`} icon="calendar-outline" kind="ghost"
          onPress={() => setPickingDates(true)} />
        <Text variant="label">Pick-up time</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
          {(config?.booking.times ?? []).map((t) => <Chip key={t} label={t} selected={dates.pickup_time === t} onPress={() => { setPreview(null); setDates({ ...dates, pickup_time: t }); }} />)}
        </ScrollView>
        <Text variant="label">Return time</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
          {(config?.booking.times ?? []).map((t) => <Chip key={t} label={t} selected={dates.return_time === t} onPress={() => { setPreview(null); setDates({ ...dates, return_time: t }); }} />)}
        </ScrollView>
        {preview ? (
          <Card style={{ gap: 0, backgroundColor: c.surface2 }}>
            <Text variant="label">{b.car} is free on those dates.</Text>
            <Fact label="New length" value={`${plural(preview.days, 'day')} at ${kes(preview.daily_rate)}`} />
            <Fact label="Old total" value={kes(preview.old_total)} />
            <Fact label="New total" value={kes(preview.total)} strong />
            {b.amount_paid ? <Fact label={preview.difference > 0 ? 'Customer owes' : preview.difference < 0 ? 'Refund to customer' : 'Difference'} value={kes(preview.difference_abs)} /> : null}
          </Card>
        ) : null}
      </FormSheet>
      <DatesSheet visible={pickingDates} from={dates.pickup_date || b.pickup_date} to={dates.return_date || b.return_date}
        onClose={() => setPickingDates(false)} onDone={(f, t) => { setPreview(null); setDates({ ...dates, pickup_date: f, return_date: t }); }} />
    </View>
  );
}
