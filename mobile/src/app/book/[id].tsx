/**
 * Booking: dates -> details -> pay -> waiting -> confirmed (or failed). Prices always come from the server, which
 * prices the booking again when it's created; nothing here decides what the customer pays.
 */
import { useQuery } from '@tanstack/react-query';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useEffect, useMemo, useRef, useState, type ComponentRef } from 'react';
import { Alert, KeyboardAvoidingView, Linking, Platform, Pressable, ScrollView, Switch, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { DateRange, blockedBetween } from '@/components/date-range';
import {
  Button, Card, Chip, Divider, ErrorText, Fact, Field, Icon, IconButton, Loading, Plate, Row, Text,
} from '@/components/ui';
import { useConfig } from '@/hooks/use-config';
import { ApiError, get, post } from '@/lib/api';
import { addDays, fmtDay, formatPhone, kes, plural, RULES, today } from '@/lib/format';
import { saveBooking, saveCustomer, savedCustomer } from '@/lib/storage';
import type { Booking, CarDetail, Quote } from '@/lib/types';
import { useSearch } from '@/state/search';
import { radius, space, useColors } from '@/theme';

type Step = 'dates' | 'details' | 'pay' | 'waiting' | 'failed' | 'paid';
const STEPS: { key: Step; label: string; icon: 'calendar-outline' | 'person-outline' | 'phone-portrait-outline' | 'checkmark-circle-outline' }[] = [
  { key: 'dates', label: 'Dates', icon: 'calendar-outline' },
  { key: 'details', label: 'Details', icon: 'person-outline' },
  { key: 'pay', label: 'Pay', icon: 'phone-portrait-outline' },
  { key: 'paid', label: 'Confirmed', icon: 'checkmark-circle-outline' },
];
const DETAIL_FIELDS = ['name', 'phone', 'email', 'id_number', 'licence_number'] as const;
const DATE_FIELDS = new Set(['pickup_date', 'return_date', 'pickup_time', 'return_time', 'pickup_point', 'return_location', 'extras']);
const RESEND_AFTER = 45;

export default function BookScreen() {
  const c = useColors();
  const { id } = useLocalSearchParams<{ id: string }>();
  const search = useSearch();
  const { data: config } = useConfig();
  const car = useQuery({
    queryKey: ['car', id, search.from, search.to],
    queryFn: () => get<CarDetail>(`cars/${id}/`, { params: { from: search.from, to: search.to } }),
  });

  const [step, setStep] = useState<Step>('dates');
  const [start, setStart] = useState<string | null>(null);
  const [end, setEnd] = useState<string | null>(null);
  const [dateMessage, setDateMessage] = useState('');
  const [pickupTime, setPickupTime] = useState('');
  const [returnTime, setReturnTime] = useState('');
  const [pointId, setPointId] = useState<number | null>(null);
  const [returnTo, setReturnTo] = useState('');
  const [extras, setExtras] = useState<number[]>([]);
  const [form, setForm] = useState({ name: '', phone: '', email: '', id_number: '', licence_number: '', notes: '' });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [payNow, setPayNow] = useState('');
  const [payError, setPayError] = useState('');
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  const [booking, setBooking] = useState<Booking | null>(null);
  const [failReason, setFailReason] = useState('');
  const unavailable = useMemo(() => new Set(car.data?.unavailable ?? []), [car.data]);
  const scroller = useRef<ComponentRef<typeof ScrollView>>(null);

  // Defaults once the car and settings load: the search dates if this car is free then, the branch's first point.
  useEffect(() => {
    if (!car.data || !config || start) return;
    /* eslint-disable react-hooks/set-state-in-effect -- one-off defaults once the server data arrives */
    setPickupTime(config.booking.default_time);
    setReturnTime(config.booking.default_time);
    setPointId(car.data.branch.pickup_points?.[0]?.id ?? null);
    if (search.from >= today() && !unavailable.has(search.from) && !blockedBetween(unavailable, search.from, search.to)) {
      setStart(search.from);
      setEnd(search.to);
    }
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [car.data, config]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { savedCustomer().then((s) => setForm((f) => ({ ...f, name: f.name || s.name, phone: f.phone || formatPhone(s.phone), email: f.email || s.email }))); }, []);
  useEffect(() => { scroller.current?.scrollTo({ y: 0, animated: false }); }, [step]);

  const quoteParams = start && end ? {
    car_id: id, from: start, to: end, pickup_time: pickupTime, return_time: returnTime,
    pickup_point: pointId ?? '', return_location: returnTo, extras,
  } : null;
  const quote = useQuery({
    queryKey: ['quote', quoteParams],
    enabled: !!quoteParams && !!pickupTime,
    retry: false,
    queryFn: () => get<{ quote: Quote }>('quote/', { params: quoteParams! }).then((r) => r.quote),
  });
  const q = quote.data;

  // ---------- Waiting for M-Pesa ----------
  const status = useQuery({
    queryKey: ['booking-status', booking?.ref],
    enabled: step === 'waiting' && !!booking,
    refetchInterval: 3000,
    queryFn: () => get<{ booking: Booking }>(`bookings/${booking!.ref}/`, { bookingToken: booking!.token }).then((r) => r.booking),
  });
  useEffect(() => {
    const b = status.data;
    if (!b || step !== 'waiting') return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reacting to the polled payment status
    if (['paid', 'picked_up', 'completed'].includes(b.status)) { setBooking(b); saveBooking(b); setStep('paid'); }
    else if (b.status === 'failed' || b.status === 'cancelled') { setBooking(b); saveBooking(b); setFailReason(b.message); setStep('failed'); }
  }, [status.data, step]);

  const [secondsLeft, setSecondsLeft] = useState(0);
  const [waited, setWaited] = useState(0);
  useEffect(() => {
    if (step !== 'waiting') return;
    const total = config?.booking.prompt_seconds ?? 180;
    const began = Date.now();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- restart the countdown for each new prompt
    setSecondsLeft(total); setWaited(0);
    const timer = setInterval(() => {
      const gone = Math.round((Date.now() - began) / 1000);
      setWaited(gone);
      setSecondsLeft(Math.max(0, total - gone));
    }, 1000);
    return () => clearInterval(timer);
  }, [step, booking?.ref, config]);

  if (car.isLoading || !config) return <Loading />;
  if (car.error || !car.data) return <SafeAreaView style={{ padding: space.lg }}><ErrorText>{(car.error as Error)?.message ?? 'Car not found.'}</ErrorText></SafeAreaView>;
  const detail = car.data;

  // ---------- Actions ----------
  function quickPick(days: number) {
    let s = start ?? addDays(today(), 1);
    for (let i = 0; i < 366 && unavailable.has(s); i += 1) s = addDays(s, 1);
    const e = addDays(s, days);
    setReturnTime(pickupTime);
    if (blockedBetween(unavailable, s, e)) { setStart(s); setEnd(null); setDateMessage('The car is booked within those days. Choose a shorter hire or other dates.'); return; }
    setStart(s); setEnd(e); setDateMessage('');
  }

  function validate() {
    const next: Record<string, string> = {};
    DETAIL_FIELDS.forEach((f) => { const m = RULES[f](form[f]); if (m) next[f] = m; });
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  const minPay = q?.min_pay ?? 0;
  const half = q ? Math.max(minPay, Math.round(q.total / 2 / 100) * 100) : 0;
  const payAmount = q && minPay < q.total ? Number(payNow.replace(/\D/g, '')) : q?.total ?? 0;
  function payProblem() {
    if (!q) return 'Choose your dates first.';
    if (!payAmount) return `Enter an amount from ${kes(minPay)} to ${kes(q.total)}.`;
    if (payAmount < minPay) return `The smallest amount that books this car is ${kes(minPay)}.`;
    if (payAmount > q.total) return `That is more than the total of ${kes(q.total)}.`;
    return '';
  }

  function routeServerError(err: ApiError) {
    const field = err.field ?? '';
    if (DATE_FIELDS.has(field) || err.status === 409) { setStep('dates'); setDateMessage(err.message); car.refetch(); return; }
    if ((DETAIL_FIELDS as readonly string[]).includes(field)) { setStep('details'); setErrors({ [field]: err.message }); return; }
    if (field === 'pay_now') { setPayError(err.message); return; }
    setFormError(err.message);
  }

  async function pay() {
    const problem = payProblem();
    setPayError(problem);
    if (problem || !start || !end) return;
    setBusy(true); setFormError('');
    try {
      const res = await post<{ booking: Booking }>('bookings/', {
        ...form, car_id: Number(id), pickup_location: detail.branch.slug, pickup_date: start, return_date: end,
        pickup_time: pickupTime, return_time: returnTime, pickup_point: pointId ?? '', return_location: returnTo,
        extras, pay_now: payAmount,
      });
      await saveBooking(res.booking);
      setBooking(res.booking);
      setStep('waiting');
    } catch (err) {
      if (err instanceof ApiError && err.data.booking) {
        const b = err.data.booking as Booking;
        await saveBooking(b); setBooking(b); setFailReason(err.message); setStep('failed');
      } else if (err instanceof ApiError) routeServerError(err);
      else setFormError('Something went wrong. Try again.');
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    if (!booking) return;
    setBusy(true);
    try {
      const res = await post<{ booking: Booking }>(`bookings/${booking.ref}/retry/`, {}, { bookingToken: booking.token });
      setBooking(res.booking);
      setStep(['paid', 'picked_up', 'completed'].includes(res.booking.status) ? 'paid' : 'waiting');
    } catch (err) {
      setFailReason((err as Error).message);
      setStep('failed');
    } finally {
      setBusy(false);
    }
  }

  function close() {
    if (step === 'waiting') {
      Alert.alert('Leave while paying?', 'Your booking is saved under My bookings. If you pay, it will show as confirmed there.', [
        { text: 'Stay', style: 'cancel' }, { text: 'Leave', onPress: () => router.back() },
      ]);
    } else router.back();
  }

  // ---------- Screen ----------
  const at = STEPS.findIndex((s) => s.key === (step === 'waiting' || step === 'failed' ? 'pay' : step));
  const footer = step === 'dates' ? (
    <Button title="Continue" icon="arrow-forward" disabled={!q || quote.isFetching} onPress={() => setStep('details')} />
  ) : step === 'details' ? (
    <Row gap={space.sm}>
      <Button title="" icon="arrow-back" kind="ghost" accessibilityLabel="Back to dates" onPress={() => setStep('dates')} />
      <Button title="Continue" style={{ flex: 1 }} onPress={() => {
        if (!validate()) return;
        saveCustomer({ name: form.name.trim(), phone: form.phone.trim(), email: form.email.trim() });
        if (q && minPay < q.total && (Number(payNow) < minPay || Number(payNow) > q.total)) setPayNow(String(minPay));
        setStep('pay');
      }} />
    </Row>
  ) : step === 'pay' ? (
    <Row gap={space.sm}>
      <Button title="" icon="arrow-back" kind="ghost" accessibilityLabel="Back to your details" onPress={() => setStep('details')} />
      <Button title={`Pay ${kes(payAmount)}`} accessibilityLabel={`Pay ${kes(payAmount)} with M-Pesa`} kind="mpesa" style={{ flex: 1 }} loading={busy} onPress={pay} />
    </Row>
  ) : step === 'failed' ? (
    <Row gap={space.sm}>
      <Button title="Change details" kind="ghost" onPress={() => setStep('details')} />
      <Button title="Try again" icon="refresh" kind="mpesa" style={{ flex: 1 }} loading={busy} onPress={resend} />
    </Row>
  ) : step === 'paid' ? (
    <Button title="Done" kind="ghost" onPress={() => router.back()} />
  ) : null;

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <Stack.Screen options={{
        title: `Book ${detail.car.name}`,
        headerLeft: () => null,
        headerRight: () => <IconButton icon="close" label="Close booking" color={c.onBrand} onPress={close} />,
        gestureEnabled: step !== 'waiting' && step !== 'pay',
      }} />
      {/* Stepper */}
      <Row style={{ backgroundColor: c.surface, paddingHorizontal: space.lg, paddingVertical: space.md, borderBottomWidth: 1, borderBottomColor: c.border }} gap={6}>
        {STEPS.map((s, i) => (
          <View key={s.key} style={{ flex: i === at ? 2.2 : 1, gap: 6 }}>
            <View style={{ height: 3, borderRadius: 2, backgroundColor: i < at ? c.muted : i === at ? c.plate : c.border }} />
            <Row gap={5}>
              <View style={{ width: 26, height: 26, borderRadius: 13, alignItems: 'center', justifyContent: 'center',
                backgroundColor: i === at ? c.plate : 'transparent', borderWidth: 1.5, borderColor: i === at ? c.plateInk : i < at ? c.text : c.muted }}>
                <Icon name={s.icon} size={14} color={i === at ? c.plateInk : i <= at ? c.text : c.muted} />
              </View>
              {i === at ? <Text variant="label">{s.label}</Text> : null}
            </Row>
          </View>
        ))}
      </Row>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView ref={scroller} contentContainerStyle={{ padding: space.lg, gap: space.lg, paddingBottom: space.xxl }} keyboardShouldPersistTaps="handled">
          {step === 'dates' ? (
            <>
              <Text variant="heading">When do you need the car?</Text>
              <ScrollView horizontal style={{ flexGrow: 0 }} showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
                {[[1, '1 day'], [3, '3 days'], [7, '1 week'], [14, '2 weeks'], [30, '1 month']].map(([n, label]) => (
                  <Chip key={label} label={String(label)} onPress={() => quickPick(Number(n))} />
                ))}
              </ScrollView>
              <Card style={{ paddingHorizontal: space.sm }}>
                <DateRange start={start} end={end} min={today()} maxDays={config.booking.max_days} unavailable={unavailable}
                  onChange={(s, e) => { setStart(s); setEnd(e); }} onMessage={setDateMessage} />
              </Card>
              <Text variant="label">
                {!start ? 'Tap your pick-up date, then your return date.' : !end ? `Pick-up ${fmtDay(start)}. Now tap your return date.`
                  : q ? `Pick-up ${q.pickup} → Return ${q.return}, ${plural(q.days, 'day')}` : `${fmtDay(start)} to ${fmtDay(end)}`}
              </Text>
              <ErrorText>{dateMessage || (quote.error ? (quote.error as Error).message : '')}</ErrorText>

              <Choice title="Pick-up time" values={config.booking.times} value={pickupTime} onChange={setPickupTime} />
              <Choice title="Return time" values={config.booking.times} value={returnTime} onChange={setReturnTime} />

              {detail.branch.pickup_points?.length ? (
                <View style={{ gap: space.sm }}>
                  <Text variant="label">Pick-up point</Text>
                  {detail.branch.pickup_points.map((p) => (
                    <Option key={p.id} selected={pointId === p.id} onPress={() => setPointId(p.id)}
                      title={p.name} note={p.fee ? `+${kes(p.fee)}` : 'Free'} />
                  ))}
                </View>
              ) : null}

              <View style={{ gap: space.sm }}>
                <Text variant="label">Return the car to</Text>
                <Option selected={!returnTo} onPress={() => setReturnTo('')} title={`${detail.branch.name} (same city)`} note="Free" />
                {(detail.branch.routes ?? []).map((r) => (
                  <Option key={r.to} selected={returnTo === r.to} onPress={() => setReturnTo(r.to)} title={`${r.name} (one-way)`} note={`+${kes(r.fee)}`} />
                ))}
              </View>

              {config.extras.length ? (
                <View style={{ gap: space.sm }}>
                  <Text variant="label">Extras (optional)</Text>
                  {config.extras.map((x) => (
                    <Row key={x.id} style={{ justifyContent: 'space-between', backgroundColor: c.surface, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, padding: space.md }}>
                      <View style={{ flex: 1 }}>
                        <Text variant="label">{x.name}</Text>
                        <Text variant="muted">{kes(x.price)}{x.per_day ? ' per day' : ''}{x.description ? ` · ${x.description}` : ''}</Text>
                      </View>
                      <Switch value={extras.includes(x.id)} accessibilityLabel={x.name}
                        onValueChange={(on) => setExtras(on ? [...extras, x.id] : extras.filter((e) => e !== x.id))} />
                    </Row>
                  ))}
                </View>
              ) : null}

              <Breakdown quote={q} loading={quote.isFetching} />
              <Text variant="muted">Every started 24 hours counts as a day, so returning later than your pick-up time adds a day.</Text>
            </>
          ) : null}

          {step === 'details' ? (
            <>
              <Text variant="heading">Your details</Text>
              <Field label="Full name" value={form.name} onChangeText={(v) => setForm({ ...form, name: v })} error={errors.name}
                autoComplete="name" textContentType="name" />
              <Field label="Phone number to pay from" value={form.phone} keyboardType="phone-pad" autoComplete="tel"
                onChangeText={(v) => setForm({ ...form, phone: formatPhone(v) })} error={errors.phone}
                hint="We’ll send the payment prompt to this phone. 07…, 01… or +254… all work." placeholder="0712 345 678" />
              <Field label="Email (optional)" value={form.email} keyboardType="email-address" autoCapitalize="none" autoComplete="email"
                onChangeText={(v) => setForm({ ...form, email: v })} error={errors.email} hint="We’ll email your receipt here." />
              <Field label="National ID or passport number" value={form.id_number} autoCapitalize="characters"
                onChangeText={(v) => setForm({ ...form, id_number: v })} error={errors.id_number} />
              <Field label="Driving licence number" value={form.licence_number} autoCapitalize="characters"
                onChangeText={(v) => setForm({ ...form, licence_number: v })} error={errors.licence_number} />
              <Field label="Pick-up notes (optional)" value={form.notes} multiline maxLength={500}
                onChangeText={(v) => setForm({ ...form, notes: v })} hint="Flight number, hotel or delivery address." />
              <Text variant="muted">Bring your ID or passport and driving licence when you collect the car.</Text>
            </>
          ) : null}

          {step === 'pay' && q ? (
            <>
              <Row gap={space.sm}>
                <Text variant="heading">Check and pay with</Text>
                <View style={{ backgroundColor: c.mpesa, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 1 }}>
                  <Text variant="label" color={c.onMpesa}>M-PESA</Text>
                </View>
              </Row>
              <Card style={{ gap: 0 }}>
                <Fact label="Car" value={detail.car.name} />
                <Fact label="Pick-up" value={q.pickup} />
                <Fact label="Return" value={q.return} />
                <Fact label="M-Pesa number" value={form.phone} />
              </Card>
              <Breakdown quote={q} />
              {minPay < q.total ? (
                <View style={{ gap: space.sm }}>
                  <Text variant="subheading">How much do you want to pay now?</Text>
                  <Text variant="muted">Pay at least {kes(minPay)} to book. Pay the rest when you pick up the car.</Text>
                  <Row style={{ flexWrap: 'wrap' }}>
                    <Chip label="Booking fee" selected={payAmount === minPay} onPress={() => setPayNow(String(minPay))} />
                    {half > minPay && half < q.total ? <Chip label="Half" selected={payAmount === half} onPress={() => setPayNow(String(half))} /> : null}
                    <Chip label="Full amount" selected={payAmount === q.total} onPress={() => setPayNow(String(q.total))} />
                  </Row>
                  <Field label="Amount to pay now (KES)" value={payNow} keyboardType="number-pad" error={payError}
                    onChangeText={(v) => setPayNow(v.replace(/\D/g, ''))} />
                  {payAmount && !payProblem() ? (
                    <Text variant="label">{payAmount < q.total ? `${kes(q.total - payAmount)} to pay when you pick up the car.` : 'Nothing left to pay at pick-up.'}</Text>
                  ) : null}
                </View>
              ) : null}
              <ErrorText>{formError}</ErrorText>
              <Row gap={6}><Icon name="shield-checkmark-outline" size={16} color={c.muted} />
                <Text variant="muted" style={{ flex: 1 }}>We’ll send an M-Pesa prompt to your phone. The car is held for you while you pay.</Text></Row>
            </>
          ) : null}

          {step === 'waiting' && booking ? (
            <View style={{ alignItems: 'center', gap: space.md, paddingTop: space.xl }}>
              <View style={{ width: 96, height: 96, borderRadius: 48, backgroundColor: `${c.mpesa}22`, alignItems: 'center', justifyContent: 'center' }}>
                <Icon name="phone-portrait-outline" size={44} color={c.mpesa} />
              </View>
              <Text variant="title" style={{ textAlign: 'center' }}>Check your phone and enter your M-Pesa PIN</Text>
              <Text style={{ textAlign: 'center' }}>We sent a prompt for {kes(booking.pay_now)} to {booking.phone}
                {config.business.till_name ? `. It will show ${config.business.till_name}.` : '.'}</Text>
              <Text variant="muted">The prompt expires in {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, '0')}</Text>
              <Text variant="muted" accessibilityLiveRegion="polite" style={{ textAlign: 'center' }}>
                {secondsLeft === 0 ? "The prompt has expired. If you didn’t pay, send a new one."
                  : waited >= RESEND_AFTER ? "Didn't get the prompt? Check your phone is on and unlocked, then send it again." : 'Waiting for your payment…'}
              </Text>
              {waited >= RESEND_AFTER || secondsLeft === 0 ? <Button title="Send the prompt again" icon="refresh" kind="ghost" loading={busy} onPress={resend} /> : null}
            </View>
          ) : null}

          {step === 'failed' ? (
            <View style={{ alignItems: 'center', gap: space.md, paddingTop: space.xl }}>
              <Icon name="close-circle" size={72} color={c.danger} />
              <Text variant="title">Payment didn’t go through</Text>
              <Text style={{ textAlign: 'center' }} accessibilityRole="alert">{failReason || 'The M-Pesa payment was cancelled or timed out.'}</Text>
              <Text variant="muted" style={{ textAlign: 'center' }}>If you got an M-Pesa message saying you paid, don’t pay again: chat with us and quote it. Otherwise, send a new prompt.</Text>
            </View>
          ) : null}

          {step === 'paid' && booking ? (
            <View style={{ alignItems: 'center', gap: space.md, paddingTop: space.lg }}>
              <Icon name="checkmark-circle" size={80} color={c.mpesa} />
              <Text variant="title">You’re booked</Text>
              <Text variant="muted">Booking number</Text>
              <Plate size="xl">{booking.ref}</Plate>
              {booking.receipt ? <Text>M-Pesa receipt <Text variant="label">{booking.receipt}</Text></Text> : null}
              <View style={{ alignSelf: 'stretch', gap: space.sm }}>
                {booking.receipt_url ? <Button title="Download receipt" icon="download-outline" size="lg"
                  onPress={() => WebBrowser.openBrowserAsync(booking.receipt_url!)} /> : null}
                <Row gap={space.sm}>
                  {booking.ics_url ? <Button title="Add to calendar" icon="calendar-outline" kind="ghost" size="sm" style={{ flex: 1 }}
                    onPress={() => Linking.openURL(booking.ics_url!)} /> : null}
                  <Button title="Chat with us" icon="chatbubbles-outline" kind="ghost" size="sm" style={{ flex: 1 }}
                    onPress={() => { router.back(); router.navigate('/chat'); }} />
                </Row>
              </View>
              <Card style={{ alignSelf: 'stretch', gap: 0 }}>
                <Fact label="Car" value={booking.car} />
                <Fact label="Pick-up" value={`${fmtDay(booking.pickup_date)} ${booking.pickup_time}${booking.pickup_point ? `, ${booking.pickup_point}` : ''}`} />
                <Fact label="Return" value={`${fmtDay(booking.return_date)} ${booking.return_time}`} />
                <Fact label="Paid" value={kes(booking.amount_paid || booking.pay_now)} />
                {booking.balance > 0 ? <Fact label="Balance at pick-up" value={kes(booking.balance)} /> : null}
              </Card>
              <Text variant="muted" style={{ textAlign: 'center' }}>Keep your booking number. We’ll call you to confirm pick-up. Bring your ID and driving licence.</Text>
            </View>
          ) : null}
        </ScrollView>

        {footer ? (
          <SafeAreaView edges={['bottom']} style={{ backgroundColor: c.surface, borderTopWidth: 1, borderTopColor: c.border }}>
            <Row style={{ padding: space.md, paddingHorizontal: space.lg }} gap={space.md}>
              {['dates', 'details', 'pay'].includes(step) ? (
                <View>
                  <Text variant="muted" style={{ fontSize: 12 }}>Total</Text>
                  <Text variant="subheading">{q ? kes(q.total) : '–'}</Text>
                </View>
              ) : null}
              <View style={{ flex: 1 }}>{footer}</View>
            </Row>
          </SafeAreaView>
        ) : null}
      </KeyboardAvoidingView>
    </View>
  );
}

function Choice({ title, values, value, onChange }: { title: string; values: string[]; value: string; onChange: (v: string) => void }) {
  return (
    <View style={{ gap: space.sm }}>
      <Text variant="label">{title}</Text>
      <ScrollView horizontal style={{ flexGrow: 0 }} showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
        {values.map((t) => <Chip key={t} label={t} selected={value === t} onPress={() => onChange(t)} />)}
      </ScrollView>
    </View>
  );
}

function Option({ title, note, selected, onPress }: { title: string; note: string; selected: boolean; onPress: () => void }) {
  const c = useColors();
  return (
    <Pressable onPress={onPress} accessibilityRole="radio" accessibilityState={{ selected }}
      style={{ flexDirection: 'row', alignItems: 'center', gap: space.md, minHeight: 52, paddingHorizontal: space.md,
        backgroundColor: c.surface, borderRadius: radius.md, borderWidth: selected ? 2 : 1, borderColor: selected ? c.primary : c.border }}>
      <Icon name={selected ? 'radio-button-on' : 'radio-button-off'} size={20} />
      <Text style={{ flex: 1 }}>{title}</Text>
      <Text variant="label">{note}</Text>
    </Pressable>
  );
}

function Breakdown({ quote, loading }: { quote?: Quote; loading?: boolean }) {
  if (!quote) return <Card><Text variant="muted">{loading ? 'Working out the price…' : 'Choose your dates to see the price.'}</Text></Card>;
  return (
    <Card style={{ gap: 0, opacity: loading ? 0.5 : 1 }}>
      {quote.breakdown.map((line, i) => (
        <View key={`${line.label}${i}`}>
          {line.total ? <Divider /> : null}
          <Fact label={line.total ? 'Total' : line.label} value={kes(line.amount)} strong={line.total} />
        </View>
      ))}
    </Card>
  );
}
