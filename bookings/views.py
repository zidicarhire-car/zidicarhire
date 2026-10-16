import json
import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from fleet.models import Car
from fleet.utils import parse_date
from payments.payhero import PayHeroError

from . import tokens
from .models import Booking, BookingEvent, BookingExtra, log_event
from .pricing import QuoteError, kes, quote
from .receipts import build_pdf, receipt_address
from .services import check_pending_payment, start_payment
from .utils import normalize_phone, rate_limited
from .validation import clean_customer

logger = logging.getLogger(__name__)

PROMPT_FAILED = "We couldn't send the M-Pesa prompt. Check the phone number and try again."
MAX_DAYS_AHEAD = 365


def _error(message, status=400, **extra):
    return JsonResponse({'error': message, **extra}, status=status)


def _bookable_car(car_id):
    return (Car.objects.select_related('location')
            .filter(pk=car_id, is_active=True, location__is_active=True).first())


def _dates(start, end):
    """Validates the date pair itself; quote() handles times, length and prices."""
    if not start or not end:
        raise QuoteError('Choose your pick-up and return dates.', field='pickup_date')
    today = timezone.localdate()
    if start < today:
        raise QuoteError("The pick-up date has passed. Choose today or a later date.", field='pickup_date')
    if start > today + timedelta(days=MAX_DAYS_AHEAD):
        raise QuoteError('Bookings open up to one year ahead. Choose an earlier pick-up date.', field='pickup_date')


def _booking_json(request, booking):
    data = booking.public_dict()
    if tokens.can_access(request, booking):
        data.update(tokens.links(booking))
    return data


@require_GET
def quote_view(request):
    """Price breakdown for the booking popup. create_booking works it out again, so this is display only."""
    try:
        car = _bookable_car(int(request.GET.get('car_id')))
    except (TypeError, ValueError):
        car = None
    if not car:
        return _error('That car is no longer available. Refresh the page and pick another.', 404)
    start = parse_date(request.GET.get('from'))
    end = parse_date(request.GET.get('to'))
    try:
        _dates(start, end)
        result = quote(car, start, end, request.GET.get('pickup_point'), request.GET.get('return_location'),
                       extras=request.GET.getlist('extras') or request.GET.get('extras'),
                       pickup_time=request.GET.get('pickup_time'), return_time=request.GET.get('return_time'))
    except QuoteError as exc:
        return _error(exc.message, field=exc.field)
    available = car.is_available(start, end)
    data = result.as_dict()
    data['available'] = available
    if not available:
        return _error('This car is booked on some of those days. Choose other dates.', 409, field='return_date',
                      quote=data)
    return JsonResponse({'quote': data})


@require_POST
def create_booking(request):
    if rate_limited(request, 'book', limit=6, window_seconds=300):
        return _error('Too many booking attempts. Wait a few minutes and try again.', 429)

    try:
        data = json.loads(request.body or b'{}')
        car_id = int(data.get('car_id'))
    except (ValueError, TypeError):
        return _error('Choose a car to book.')

    car = _bookable_car(car_id)
    if not car:
        return _error('That car is no longer available. Refresh the page and pick another.', 404)

    # A car is only hired out from its own branch.
    city = str(data.get('pickup_location') or '').strip()
    if city and city not in (str(car.location_id), car.location.slug):
        return _error(f'This car is at our {car.location.name} branch. Search {car.location.name} to book it, '
                      'or pick a car in your city.', field='pickup_location')

    start = parse_date(data.get('pickup_date'))
    end = parse_date(data.get('return_date'))
    try:
        customer = clean_customer(data)
        _dates(start, end)
    except QuoteError as exc:
        return _error(exc.message, field=exc.field)

    with transaction.atomic():
        car = Car.objects.select_for_update().select_related('location').get(pk=car.pk)
        # Priced inside the lock from the database only: any amount or day count the browser sends is ignored.
        try:
            price = quote(car, start, end, data.get('pickup_point'), data.get('return_location'),
                          extras=data.get('extras'), pickup_time=data.get('pickup_time'),
                          return_time=data.get('return_time'))
            pay_now = price.pay_now(data.get('pay_now'))
        except QuoteError as exc:
            return _error(exc.message, field=exc.field)
        if not car.is_available(start, end):
            return _error('This car was just booked for those dates. Try other dates or another car.', 409)
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
        log_event(booking, BookingEvent.Kind.CREATED,
                  f'Booked on the website: {price.days} days, {kes(price.total)}'
                  + (f'; paying {kes(pay_now)} now, {kes(price.total - pay_now)} at pick-up' if pay_now < price.total else ''))
    tokens.remember(request, booking)

    try:
        start_payment(booking)
    except PayHeroError as exc:
        logger.warning('STK push failed for %s: %s', booking.ref, exc)
        booking.status = Booking.Status.FAILED
        booking.result_desc = str(exc)[:255]
        booking.save(update_fields=['status', 'result_desc', 'updated_at'])
        return _error(PROMPT_FAILED, 502, booking=_booking_json(request, booking))

    return JsonResponse({'booking': _booking_json(request, booking)}, status=201)


@require_GET
def booking_status(request, ref):
    booking = get_object_or_404(Booking.objects.with_details(), ref=ref)
    booking = check_pending_payment(booking)
    return JsonResponse({'booking': _booking_json(request, booking)})


@require_POST
def retry_payment(request, ref):
    if rate_limited(request, f'retry:{ref}', limit=4, window_seconds=600):
        return _error('Too many attempts. Wait a few minutes, or chat with us for help.', 429)

    booking = get_object_or_404(Booking.objects.with_details(), ref=ref)
    if booking.status not in (Booking.Status.PENDING, Booking.Status.FAILED):
        return JsonResponse({'booking': _booking_json(request, booking)})
    if booking.created_at < timezone.now() - timedelta(hours=1):
        return _error('This booking has expired. Start a new booking.', 410)
    if booking.pickup_date < timezone.localdate():
        return _error('The pick-up date has passed. Start a new booking.', 410)

    with transaction.atomic():
        car = type(booking.car).objects.select_for_update().get(pk=booking.car_id)
        if not car.is_available(booking.pickup_date, booking.return_date, exclude=booking):
            return _error('Sorry, someone else booked this car for those dates. Try another car.', 409)
        booking.status = Booking.Status.PENDING
        booking.payment_requested_at = timezone.now()
        booking.save(update_fields=['status', 'payment_requested_at', 'updated_at'])

    try:
        start_payment(booking)
    except PayHeroError as exc:
        logger.warning('STK retry failed for %s: %s', booking.ref, exc)
        booking.status = Booking.Status.FAILED
        booking.result_desc = str(exc)[:255]
        booking.save(update_fields=['status', 'result_desc', 'updated_at'])
        return _error(PROMPT_FAILED, 502, booking=_booking_json(request, booking))

    return JsonResponse({'booking': _booking_json(request, booking)})


def booking_detail(request, ref):
    booking = get_object_or_404(Booking.objects.with_details(), ref=ref)
    if tokens.check_token(ref, request.GET.get('t')):
        tokens.remember(request, booking)
    allowed = tokens.can_access(request, booking)
    return render(request, 'bookings/detail.html', {
        'booking': booking, 'links': tokens.links(booking) if allowed else None,
    })


def _receipt_problem(request, booking):
    """A friendly page instead of the receipt, or None if the receipt can be shown."""
    if not tokens.can_access(request, booking):
        return render(request, 'bookings/receipt_unavailable.html', {
            'booking': booking, 'reason': 'link',
        }, status=403)
    if booking.status not in Booking.PAID_STATES:
        return render(request, 'bookings/receipt_unavailable.html', {
            'booking': booking, 'reason': 'unpaid',
        }, status=409)
    return None


def receipt_pdf(request, ref):
    booking = get_object_or_404(Booking.objects.with_details(), ref=ref)
    problem = _receipt_problem(request, booking)
    if problem:
        return problem
    response = HttpResponse(build_pdf(booking), content_type='application/pdf')
    disposition = 'inline' if request.GET.get('view') else 'attachment'
    response['Content-Disposition'] = f'{disposition}; filename="{settings.BUSINESS["name"]}-receipt-{booking.ref}.pdf"'
    return response


def receipt_page(request, ref):
    """Printable HTML copy of the receipt, in case the PDF won't open."""
    booking = get_object_or_404(Booking.objects.with_details(), ref=ref)
    problem = _receipt_problem(request, booking)
    if problem:
        return problem
    return render(request, 'bookings/receipt.html', {'booking': booking, 'links': tokens.links(booking),
                                                     'office_address': receipt_address()})


FIND_LIMIT = 10  # lookups per IP per 10 minutes, so booking numbers can't be guessed


def find_booking(request):
    """Booking number + phone number opens the booking, its status and receipt."""
    error = ''
    ref = phone_raw = ''
    if request.method == 'POST':
        ref = str(request.POST.get('ref') or '').strip().upper().replace(' ', '')
        phone_raw = str(request.POST.get('phone') or '').strip()
        if rate_limited(request, 'find', limit=FIND_LIMIT, window_seconds=600):
            error = 'Too many tries. Wait 10 minutes, or chat with us and we will find your booking.'
        else:
            booking = Booking.objects.filter(ref=ref).first() if ref else None
            phone = normalize_phone(phone_raw)
            if booking and phone and booking.phone == phone:
                tokens.remember(request, booking)
                return redirect(tokens.links(booking)['detail_url'])
            error = ("We couldn't find a booking with that number and phone. Check both: the booking number "
                     'starts with ZCH and is in your confirmation, and the phone is the one you paid with.')
    return render(request, 'bookings/find.html', {'error': error, 'ref': ref, 'phone': phone_raw})


def _ics_text(value):
    return str(value).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


@require_GET
def booking_ics(request, ref):
    """Calendar file with the pick-up and return as two events."""
    booking = get_object_or_404(Booking.objects.with_details(), ref=ref)
    if not tokens.can_access(request, booking) or booking.status not in Booking.PAID_STATES:
        raise Http404('No calendar file for this booking')
    biz = settings.BUSINESS
    tz = timezone.get_current_timezone()
    stamp = timezone.now().strftime('%Y%m%dT%H%M%SZ')
    place = booking.pickup_point.name if booking.pickup_point_id else (
        booking.pickup_location.name if booking.pickup_location_id else biz['location'])
    return_place = booking.return_location.name if booking.return_location_id else place
    phone = booking.pickup_location.contact_phone if booking.pickup_location_id else biz['phone']

    def event(uid, title, day, at, where):
        begin = datetime.combine(day, at, tzinfo=tz).astimezone(dt_timezone.utc)
        end = begin + timedelta(minutes=30)
        return [
            'BEGIN:VEVENT', f'UID:{booking.ref}-{uid}@zidicarhire.com', f'DTSTAMP:{stamp}',
            f'DTSTART:{begin:%Y%m%dT%H%M%SZ}', f'DTEND:{end:%Y%m%dT%H%M%SZ}',
            f'SUMMARY:{_ics_text(title)}', f'LOCATION:{_ics_text(where)}',
            f'DESCRIPTION:{_ics_text(f"Booking {booking.ref}. Questions? Call {phone}.")}', 'END:VEVENT',
        ]

    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', f'PRODID:-//{biz["name"]}//Bookings//EN', 'CALSCALE:GREGORIAN']
    lines += event('pickup', f'Pick up {booking.car.name} ({biz["name"]})', booking.pickup_date,
                   booking.pickup_time, place)
    lines += event('return', f'Return {booking.car.name} ({biz["name"]})', booking.return_date,
                   booking.return_time, return_place)
    lines.append('END:VCALENDAR')
    response = HttpResponse('\r\n'.join(lines) + '\r\n', content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{booking.ref}.ics"'
    return response
