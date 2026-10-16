"""
Booking state changes live here so the PayHero callback, the status checks, the dashboard and the
JSON API all behave the same, and every change lands in the booking's timeline.
"""
import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from payments import payhero
from payments.models import Payment

from .models import Booking, BookingEvent, log_event
from .notifications import notify_booking_paid, send_customer_confirmation
from .pricing import QuoteError, count_days, daily_rate_for, kes, parse_time

logger = logging.getLogger(__name__)

NO_RESPONSE_SECONDS = 180
MPESA_CODE_RE = re.compile(r'^[A-Z0-9]{8,12}$')
Kind = BookingEvent.Kind


class ActionError(Exception):
    """A staff action that isn't allowed; the message says why."""


def callback_url():
    return settings.SITE_URL + reverse('payments:callback')


# ---------- M-Pesa ----------

def start_payment(booking):
    """
    Sends the M-Pesa STK prompt and records the attempt as a Payment.
    Raises payhero.PayHeroError if PayHero refuses.
    """
    attempt = Payment.objects.create(booking=booking, reference=booking.ref, amount=booking.due_now,
                                     phone=booking.phone)
    try:
        data = payhero.stk_push(
            amount=booking.due_now,
            phone=booking.phone,
            reference=booking.ref,
            customer_name=booking.customer_name,
            callback_url=callback_url(),
        )
    except payhero.PayHeroError as exc:
        record_result(attempt, Payment.Status.FAILED, desc=f'Prompt not sent: {exc}')
        log_event(booking, Kind.FAILED, f'The M-Pesa prompt could not be sent: {exc}')
        raise
    attempt.checkout_request_id = data.get('CheckoutRequestID', '') or ''
    attempt.payhero_reference = data.get('reference', '') or ''
    attempt.save(update_fields=['checkout_request_id', 'payhero_reference', 'updated_at'])
    booking.checkout_request_id = data.get('CheckoutRequestID', '') or ''
    booking.payhero_reference = data.get('reference', '') or ''
    booking.status = Booking.Status.PENDING
    booking.result_desc = ''
    booking.payment_requested_at = timezone.now()
    booking.save(update_fields=[
        'checkout_request_id', 'payhero_reference', 'status', 'result_desc', 'payment_requested_at', 'updated_at',
    ])
    log_event(booking, Kind.PROMPT, f'Prompt for {kes(booking.due_now)} sent to {booking.masked_phone}')
    return booking


def record_result(payment, status, code='', desc='', receipt='', raw=None):
    """Stores what PayHero told us about one prompt."""
    if payment is None:
        return
    payment.status = status
    payment.result_code = str(code or payment.result_code)[:20]
    payment.result_desc = (desc or payment.result_desc)[:255]
    payment.mpesa_receipt = (receipt or payment.mpesa_receipt)[:40]
    fields = ['status', 'result_code', 'result_desc', 'mpesa_receipt', 'updated_at']
    if raw is not None:
        payment.raw_callback = raw
        fields.append('raw_callback')
    payment.save(update_fields=fields)


def latest_attempt(booking):
    return booking.payments.order_by('-created_at').first()


def mark_paid(booking_id, receipt='', desc='', amount_paid=None, user=None):
    """Marks a booking paid once. Returns (booking, changed)."""
    with transaction.atomic():
        booking = Booking.objects.select_for_update().with_details().get(pk=booking_id)
        if booking.status in Booking.PAID_STATES:
            return booking, False
        booking.status = Booking.Status.PAID
        booking.mpesa_receipt = (receipt or '')[:40]
        booking.result_desc = (desc or '')[:255]
        booking.paid_at = timezone.now()
        booking.amount_paid = booking.due_now if amount_paid is None else amount_paid
        booking.save()
        log_event(booking, Kind.PAID, f'{kes(booking.amount_paid)} paid, M-Pesa receipt {booking.mpesa_receipt or "-"}'
                  + (f'. {desc}' if user is not None and desc else ''), user)
    notify_booking_paid(booking)
    return booking, True


def mark_failed(booking_id, desc):
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking_id)
        if booking.status != Booking.Status.PENDING:
            return booking
        booking.status = Booking.Status.FAILED
        booking.result_desc = (desc or 'Payment was not completed.')[:255]
        booking.save(update_fields=['status', 'result_desc', 'updated_at'])
        log_event(booking, Kind.FAILED, booking.result_desc)
    return booking


def check_pending_payment(booking):
    """
    Called while the customer's page polls for status. Backs up the PayHero callback:
    if no callback has arrived after ~25 seconds, it asks PayHero directly.
    """
    if booking.status != Booking.Status.PENDING or not booking.payment_requested_at:
        return booking

    elapsed = (timezone.now() - booking.payment_requested_at).total_seconds()

    if settings.FAKE_PAYMENTS:
        if elapsed > 8:
            receipt = 'TEST' + secrets.token_hex(3).upper()
            record_result(latest_attempt(booking), Payment.Status.SUCCESS, '0', 'Simulated payment (FAKE_PAYMENTS)',
                          receipt)
            booking, _ = mark_paid(booking.pk, receipt=receipt, desc='Simulated payment (FAKE_PAYMENTS)')
        return booking

    if elapsed >= 25 and booking.payhero_reference:
        throttle_key = f'phcheck:{booking.pk}'
        if not cache.get(throttle_key):
            cache.set(throttle_key, 1, 15)
            try:
                data = payhero.transaction_status(booking.payhero_reference)
                status = str(data.get('status', '')).upper()
                logger.info('Status check for %s: %s', booking.ref, status or 'no status')
                attempt = booking.payments.filter(payhero_reference=booking.payhero_reference).first()
                if status == 'SUCCESS':
                    receipt = data.get('provider_reference') or data.get('third_party_reference') or ''
                    record_result(attempt, Payment.Status.SUCCESS, '0', 'Confirmed by status check', receipt)
                    booking, _ = mark_paid(booking.pk, receipt=receipt, desc='Confirmed by status check')
                    return booking
                if status in ('FAILED', 'CANCELLED'):
                    reason = payhero.status_message(data)
                    message = 'The M-Pesa payment was not completed. Send a new prompt to try again.'
                    record_result(attempt, Payment.Status.CANCELLED if status == 'CANCELLED' else Payment.Status.FAILED,
                                  desc=f'Status check: {status}' + (f' ({reason})' if reason else ''),
                                  raw={'status_check': data})
                    return mark_failed(booking.pk, message)
                if attempt is not None and data:
                    # Keep PayHero's latest answer on the attempt, so staff can see why a prompt is stuck.
                    record_result(attempt, attempt.status, desc=f'Status check: {status or "no status yet"}'
                                  + (f' ({payhero.status_message(data)})' if payhero.status_message(data) else ''),
                                  raw={'status_check': data})
            except Exception:
                logger.exception('PayHero status check failed for %s', booking.ref)

    if elapsed > NO_RESPONSE_SECONDS:
        attempt = latest_attempt(booking)
        last = attempt.result_desc if attempt is not None and attempt.result_desc.startswith('Status check') else ''
        record_result(attempt, Payment.Status.FAILED,
                      desc='No answer within 3 minutes' + (f'. Last PayHero answer: {last}' if last else ''))
        return mark_failed(booking.pk, "The M-Pesa prompt wasn't answered in time. Send a new prompt to try again.")

    booking.refresh_from_db()
    return booking


# ---------- Staff actions ----------

def _locked(booking):
    return Booking.objects.select_for_update().with_details().get(pk=booking.pk)


def mark_picked_up(booking, user):
    with transaction.atomic():
        booking = _locked(booking)
        if booking.status != Booking.Status.PAID:
            raise ActionError('Only a paid booking can be marked as picked up.')
        booking.status = Booking.Status.PICKED_UP
        booking.save(update_fields=['status', 'updated_at'])
        log_event(booking, Kind.PICKED_UP, f'{booking.car.name} collected by the customer', user)
    return booking


def mark_returned(booking, user):
    with transaction.atomic():
        booking = _locked(booking)
        if booking.status not in (Booking.Status.PAID, Booking.Status.PICKED_UP):
            raise ActionError('Only a paid or picked-up booking can be marked as returned.')
        booking.status = Booking.Status.COMPLETED
        booking.save(update_fields=['status', 'updated_at'])
        log_event(booking, Kind.RETURNED, f'{booking.car.name} returned', user)
    return booking


def cancel_booking(booking, user, reason):
    reason = (reason or '').strip()
    if len(reason) < 3:
        raise ActionError('Write why the booking is cancelled, so the team knows later.')
    with transaction.atomic():
        booking = _locked(booking)
        if booking.status not in (Booking.Status.PENDING, Booking.Status.PAID, Booking.Status.FAILED):
            raise ActionError(f'A booking that is "{booking.get_status_display()}" can no longer be cancelled.')
        was_paid = booking.status == Booking.Status.PAID
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=['status', 'updated_at'])
        refund = f' Refund {kes(booking.amount_paid)} by M-Pesa manually if it is owed.' if was_paid else ''
        log_event(booking, Kind.CANCELLED, f'Reason: {reason}.{refund}', user)
    return booking


def mark_paid_manually(booking, user, code):
    code = (code or '').strip().upper().replace(' ', '')
    if not MPESA_CODE_RE.match(code):
        raise ActionError('Enter the M-Pesa code from the till statement, like SJK1ABC2DE (letters and numbers).')
    if booking.status not in (Booking.Status.PENDING, Booking.Status.FAILED):
        raise ActionError(f'A booking that is "{booking.get_status_display()}" cannot be marked paid.')
    booking, _ = mark_paid(booking.pk, receipt=code, desc=f'Marked paid by {user.get_username()}', user=user)
    return booking


def record_balance_payment(booking, user, amount, code=''):
    """Staff record money received after booking (usually the balance at pick-up): cash, or M-Pesa with its code."""
    if not booking.is_paid:
        raise ActionError('Only a paid booking has a balance. Use "Mark as paid" for an unpaid one.')
    if booking.balance <= 0:
        raise ActionError('Nothing is owed on this booking.')
    try:
        amount = int(str(amount or '').replace(',', '').strip())
    except ValueError:
        raise ActionError('Enter the amount received in whole shillings, like 5000.')
    if amount <= 0:
        raise ActionError('Enter the amount received in whole shillings, like 5000.')
    if amount > booking.balance:
        raise ActionError(f'The customer only owes {kes(booking.balance)}. Enter that amount or less.')
    code = (code or '').strip().upper().replace(' ', '')
    if code and not MPESA_CODE_RE.match(code):
        raise ActionError('Enter the M-Pesa code from the till statement, like SJK1ABC2DE, or leave it blank for cash.')
    with transaction.atomic():
        booking = _locked(booking)
        if amount > booking.balance:
            raise ActionError(f'The customer only owes {kes(booking.balance)}. Enter that amount or less.')
        booking.amount_paid += amount
        booking.save(update_fields=['amount_paid', 'updated_at'])
        method = f'M-Pesa {code}' if code else 'cash'
        left = booking.balance
        log_event(booking, Kind.BALANCE, f'{kes(amount)} received ({method}). '
                  + (f'{kes(left)} still owed.' if left > 0 else 'Fully paid.'), user)
    return booking


def date_change_quote(booking, start, start_time, end, end_time):
    """
    New length and total for different dates. Fees and extras chosen at booking stay as they were;
    the daily rate stays the same unless the new length reaches a weekly or monthly rate.
    Raises QuoteError if the dates don't work or the car is booked.
    """
    start_t = parse_time(start_time, 'pick-up')
    end_t = parse_time(end_time, 'return')
    if not start or not end or end <= start:
        raise QuoteError('Choose a return date after the pick-up date.')
    days = count_days(start, start_t, end, end_t)
    if days < settings.MIN_RENTAL_DAYS or days > settings.MAX_RENTAL_DAYS:
        raise QuoteError(f'Hires must be {settings.MIN_RENTAL_DAYS} to {settings.MAX_RENTAL_DAYS} days.')
    rate, rate_type = daily_rate_for(booking.car, days)
    if rate_type == booking.rate_type and booking.daily_rate:
        rate = booking.daily_rate
    extras = sum(e.price * days if e.per_day else e.price for e in booking.extras.all())
    total = days * rate + extras + booking.pickup_fee + booking.one_way_fee
    if not booking.car.is_available(start, end, exclude=booking):
        raise QuoteError(f'{booking.car.name} is booked by someone else on some of those days.')
    paid = booking.amount_paid if booking.is_paid else 0
    return {
        'start': start, 'start_time': start_t, 'end': end, 'end_time': end_t, 'days': days, 'daily_rate': rate,
        'rate_type': rate_type, 'extras': extras, 'total': total, 'old_total': booking.amount,
        'difference': total - paid, 'difference_abs': abs(total - paid), 'paid': paid,
    }


def change_dates(booking, user, start, start_time, end, end_time):
    with transaction.atomic():
        booking = _locked(booking)
        if booking.status in (Booking.Status.COMPLETED, Booking.Status.CANCELLED):
            raise ActionError('Dates can only be changed on active bookings.')
        try:
            new = date_change_quote(booking, start, start_time, end, end_time)
        except QuoteError as exc:
            raise ActionError(exc.message)
        old = (f'{booking.pickup_date:%d %b} {booking.pickup_time:%H:%M} to '
               f'{booking.return_date:%d %b} {booking.return_time:%H:%M}, {booking.days} days, {kes(booking.amount)}')
        for extra in booking.extras.all():
            if extra.per_day:
                extra.amount = extra.price * new['days']
                extra.save(update_fields=['amount'])
        booking.pickup_date, booking.pickup_time = new['start'], new['start_time']
        booking.return_date, booking.return_time = new['end'], new['end_time']
        booking.days, booking.daily_rate, booking.rate_type = new['days'], new['daily_rate'], new['rate_type']
        booking.extras_amount = new['extras']
        booking.amount = new['total']
        booking.save()
        diff = new['difference']
        settle = ('' if not booking.is_paid or diff == 0 else
                  f' Customer owes {kes(diff)} more.' if diff > 0 else f' Refund {kes(-diff)} to the customer.')
        log_event(booking, Kind.DATES,
                  f'Was {old}. Now {booking.pickup_date:%d %b} {booking.pickup_time:%H:%M} to '
                  f'{booking.return_date:%d %b} {booking.return_time:%H:%M}, {booking.days} days, '
                  f'{kes(booking.amount)}.{settle}', user)
    return booking


def resend_confirmation(booking, user):
    if not booking.is_paid:
        raise ActionError('Confirmation emails are only for paid bookings.')
    if not booking.email:
        raise ActionError('This customer did not give an email address. Call or WhatsApp them instead.')
    if not send_customer_confirmation(booking):
        raise ActionError('The email could not be sent. Check the email settings on the Payment settings check page.')
    log_event(booking, Kind.EMAIL, f'Confirmation with receipt sent to {booking.email}', user)
    return booking


def add_note(booking, user, text):
    text = (text or '').strip()
    if not text:
        raise ActionError('Type the note first.')
    log_event(booking, Kind.NOTE, text, user)
    return booking


def relocate_car(booking, user=None):
    """
    After a one-way hire, the admin confirms the car reached the return branch. Paying never moves
    the car by itself, because it is still on the road until the customer drops it off.
    """
    with transaction.atomic():
        booking = _locked(booking)
        if not booking.awaiting_relocation:
            return booking, False
        car = booking.car
        car.location = booking.return_location
        car.save(update_fields=['location'])
        booking.car_relocated = True
        booking.save(update_fields=['car_relocated', 'updated_at'])
        log_event(booking, Kind.RELOCATED, f'{car.name} is now listed in {booking.return_location.name}', user)
    return booking, True


# ---------- Placing a booking and retrying its payment (website and app share these) ----------

PROMPT_FAILED = "We couldn't send the M-Pesa prompt. Check the phone number and try again."
MAX_DAYS_AHEAD = 365


class BookingRequestError(Exception):
    """A booking or payment request the customer has to fix. `status` is the HTTP status to answer with;
    `booking` is set when a booking was saved but its M-Pesa prompt failed."""

    def __init__(self, message, status=400, field=None, booking=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.field = field
        self.booking = booking


def check_dates(start, end):
    """Validates the date pair itself; quote() handles times, length and prices."""
    if not start or not end:
        raise QuoteError('Choose your pick-up and return dates.', field='pickup_date')
    today = timezone.localdate()
    if start < today:
        raise QuoteError("The pick-up date has passed. Choose today or a later date.", field='pickup_date')
    if start > today + timedelta(days=MAX_DAYS_AHEAD):
        raise QuoteError('Bookings open up to one year ahead. Choose an earlier pick-up date.', field='pickup_date')


def place_booking(data, channel='website'):
    """
    Checks, prices and saves a booking from the customer's form data, then sends the M-Pesa prompt.
    Prices come from the database only (any amount or day count sent in is ignored). Returns the booking;
    raises BookingRequestError with the message to show.
    """
    from fleet.models import Car
    from fleet.utils import parse_date

    from .models import BookingExtra
    from .pricing import quote
    from .validation import clean_customer

    try:
        car_id = int(data.get('car_id'))
    except (ValueError, TypeError):
        raise BookingRequestError('Choose a car to book.')
    car = (Car.objects.select_related('location')
           .filter(pk=car_id, is_active=True, location__is_active=True).first())
    if not car:
        raise BookingRequestError('That car is no longer available. Refresh the page and pick another.', 404)

    # A car is only hired out from its own branch.
    city = str(data.get('pickup_location') or '').strip()
    if city and city not in (str(car.location_id), car.location.slug):
        raise BookingRequestError(f'This car is at our {car.location.name} branch. Search {car.location.name} to book '
                                  'it, or pick a car in your city.', field='pickup_location')

    start = parse_date(data.get('pickup_date'))
    end = parse_date(data.get('return_date'))
    try:
        customer = clean_customer(data)
        check_dates(start, end)
    except QuoteError as exc:
        raise BookingRequestError(exc.message, field=exc.field)

    with transaction.atomic():
        car = Car.objects.select_for_update().select_related('location').get(pk=car.pk)
        try:
            price = quote(car, start, end, data.get('pickup_point'), data.get('return_location'),
                          extras=data.get('extras'), pickup_time=data.get('pickup_time'),
                          return_time=data.get('return_time'))
            pay_now = price.pay_now(data.get('pay_now'))
        except QuoteError as exc:
            raise BookingRequestError(exc.message, field=exc.field)
        if not car.is_available(start, end):
            raise BookingRequestError('This car was just booked for those dates. Try other dates or another car.', 409)
        booking = Booking.objects.create(
            car=car, **customer,
            pickup_location=car.location, pickup_point=price.pickup_point, return_location=price.return_location,
            pickup_date=start, pickup_time=price.start_time, return_date=end, return_time=price.end_time,
            days=price.days, daily_rate=price.daily_rate, rate_type=price.rate_type,
            pickup_fee=price.pickup_fee, one_way_fee=price.one_way_fee, extras_amount=price.extras,
            amount=price.total, pay_now=pay_now, payment_requested_at=timezone.now(),
        )
        BookingExtra.objects.bulk_create([
            BookingExtra(booking=booking, extra=extra, name=extra.name, price=extra.price, per_day=extra.per_day,
                         amount=amount)
            for extra, amount in price.extra_items
        ])
        where = 'in the app' if channel == 'app' else 'on the website'
        log_event(booking, Kind.CREATED,
                  f'Booked {where}: {price.days} days, {kes(price.total)}'
                  + (f'; paying {kes(pay_now)} now, {kes(price.total - pay_now)} at pick-up' if pay_now < price.total else ''))

    _send_prompt(booking, 'STK push failed')
    return booking


def retry_booking_payment(booking):
    """Sends a new M-Pesa prompt for an unpaid booking. Returns the booking; raises BookingRequestError."""
    if booking.status not in (Booking.Status.PENDING, Booking.Status.FAILED):
        return booking
    if booking.created_at < timezone.now() - timedelta(hours=1):
        raise BookingRequestError('This booking has expired. Start a new booking.', 410)
    if booking.pickup_date < timezone.localdate():
        raise BookingRequestError('The pick-up date has passed. Start a new booking.', 410)

    with transaction.atomic():
        car = type(booking.car).objects.select_for_update().get(pk=booking.car_id)
        if not car.is_available(booking.pickup_date, booking.return_date, exclude=booking):
            raise BookingRequestError('Sorry, someone else booked this car for those dates. Try another car.', 409)
        booking.status = Booking.Status.PENDING
        booking.payment_requested_at = timezone.now()
        booking.save(update_fields=['status', 'payment_requested_at', 'updated_at'])

    _send_prompt(booking, 'STK retry failed')
    return booking


def _send_prompt(booking, what):
    try:
        start_payment(booking)
    except payhero.PayHeroError as exc:
        logger.warning('%s for %s: %s', what, booking.ref, exc)
        booking.status = Booking.Status.FAILED
        booking.result_desc = str(exc)[:255]
        booking.save(update_fields=['status', 'result_desc', 'updated_at'])
        raise BookingRequestError(PROMPT_FAILED, 502, booking=booking)
