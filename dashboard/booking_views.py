"""Dashboard pages for managing bookings: overview, list (search, filters, CSV), detail with actions, calendar."""
import csv
import re
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from bookings import services
from bookings.models import Booking, BookingEvent
from bookings.pricing import QuoteError, time_choices
from bookings.receipts import build_pdf
from fleet.models import Location
from fleet.utils import parse_date

from .models import staff_location
from .views import _ctx, _stats, out_now, scoped_bookings, scoped_cars, staff_page, view_location

PER_PAGE = 25
CALENDAR_LENGTHS = (7, 14, 30)
SORTS = {
    'newest': ('-created_at', 'Newest first'),
    'pickup': ('pickup_date', 'Pick-up date, soonest first'),
    'pickup_desc': ('-pickup_date', 'Pick-up date, latest first'),
    'amount_desc': ('-amount', 'Amount, highest first'),
    'amount': ('amount', 'Amount, lowest first'),
}
Status = Booking.Status


def _in_city(qs, location):
    return qs.filter(Q(pickup_location=location) | Q(return_location=location)) if location else qs


def _render(request, template, partial, context):
    """Pages that update live: dashboard.js asks for ?partial=1 and swaps in just the changing part."""
    return render(request, partial if request.GET.get('partial') else template, context)


# ---------- Overview ----------

@staff_page
def overview(request):
    today = timezone.localdate()
    viewing = view_location(request)
    qs = _in_city(scoped_bookings(request.user), viewing)
    active = qs.filter(status__in=(Status.PAID, Status.PICKED_UP))
    context = _ctx(
        request, nav='overview', today=today,
        stats=_stats(viewing, request.user),
        pickups=active.filter(pickup_date=today).order_by('pickup_time'),
        returns=active.filter(return_date=today).order_by('return_time'),
        out=out_now(qs, today).order_by('return_date', 'return_time'),
        awaiting=qs.blocking().filter(status=Status.PENDING).order_by('-created_at'),
        latest=qs.order_by('-created_at')[:8],
    )
    return _render(request, 'dashboard/home.html', 'dashboard/_overview.html', context)


# ---------- Bookings list ----------

def filtered_bookings(request):
    """The bookings list's search, filters and sort, shared by the page and the CSV export."""
    g = request.GET
    qs = scoped_bookings(request.user)
    own = staff_location(request.user)
    city = None
    if own is None and 'city' in g:
        city = Location.objects.filter(slug=g.get('city')).first()
    elif own is None:
        city = view_location(request)
    qs = _in_city(qs, city)

    q = g.get('q', '').strip()
    if q:
        match = (Q(ref__icontains=q) | Q(customer_name__icontains=q) | Q(email__icontains=q)
                 | Q(mpesa_receipt__icontains=q) | Q(payments__mpesa_receipt__icontains=q))
        digits = re.sub(r'\D', '', q)
        if len(digits) >= 4:
            match |= Q(phone__contains=digits[1:] if digits.startswith('0') else digits)
        qs = qs.filter(match).distinct()
    if g.get('status') in Status.values:
        qs = qs.filter(status=g['status'])
    if str(g.get('car', '')).isdigit():
        qs = qs.filter(car_id=int(g['car']))
    start, end = parse_date(g.get('from')), parse_date(g.get('to'))
    if start:
        qs = qs.filter(return_date__gte=start)   # hires that overlap the chosen dates
    if end:
        qs = qs.filter(pickup_date__lte=end)
    sort = g.get('sort') if g.get('sort') in SORTS else 'newest'
    return qs.order_by(SORTS[sort][0], '-id'), city, sort


def _csv_cell(value):
    """Stops spreadsheet programs from running cell contents as formulas."""
    text = '' if value is None else str(value)
    return "'" + text if text[:1] in ('=', '+', '-', '@') else text


def bookings_csv(qs):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="bookings-{timezone.localdate():%Y-%m-%d}.csv"'
    response.write('﻿')  # so Excel reads the file as UTF-8
    writer = csv.writer(response)
    writer.writerow(['Booking', 'Made', 'Status', 'Customer', 'Phone', 'Email', 'ID/passport', 'Licence', 'Car',
                     'City', 'Pick-up point', 'Pick-up', 'Return', 'Return to', 'Days', 'Daily rate (KES)',
                     'Extras (KES)', 'Pick-up fee (KES)', 'One-way fee (KES)', 'Total (KES)', 'Paid (KES)',
                     'M-Pesa code'])
    for b in qs:
        writer.writerow([_csv_cell(v) for v in (
            b.ref, timezone.localtime(b.created_at).strftime('%Y-%m-%d %H:%M'), b.get_status_display(),
            b.customer_name, b.local_phone, b.email, b.id_number, b.licence_number, b.car.name,
            b.pickup_location.name if b.pickup_location_id else '', b.pickup_point.name if b.pickup_point_id else '',
            f'{b.pickup_date:%Y-%m-%d} {b.pickup_time:%H:%M}', f'{b.return_date:%Y-%m-%d} {b.return_time:%H:%M}',
            b.return_location.name if b.return_location_id else '', b.days, b.daily_rate, b.extras_amount,
            b.pickup_fee, b.one_way_fee, b.amount, b.amount_paid, b.mpesa_receipt,
        )])
    return response


@staff_page
def bookings_list(request):
    qs, city, sort = filtered_bookings(request)
    if request.GET.get('export') == 'csv':
        return bookings_csv(qs)
    page = Paginator(qs, PER_PAGE).get_page(request.GET.get('page'))
    params = request.GET.copy()
    for key in ('page', 'partial'):
        params.pop(key, None)
    context = _ctx(
        request, nav='bookings', page=page, statuses=Status.choices, sorts=[(k, v[1]) for k, v in SORTS.items()],
        sort=sort, filter_city=city, cars=scoped_cars(request.user).order_by('name'),
        query=params.urlencode(), filters=request.GET, total=page.paginator.count,
    )
    return _render(request, 'dashboard/bookings.html', 'dashboard/_booking_table.html', context)


# ---------- Booking detail and actions ----------

def _allowed(booking):
    s = booking.status
    return {
        'pickup': s == Status.PAID,
        'return': s in (Status.PAID, Status.PICKED_UP),
        'cancel': s in (Status.PENDING, Status.PAID, Status.FAILED),
        'mark_paid': s in (Status.PENDING, Status.FAILED),
        'dates': s not in (Status.COMPLETED, Status.CANCELLED),
        'resend': booking.is_paid and bool(booking.email),
        'receipt': booking.is_paid,
        'relocate': booking.awaiting_relocation,
    }


def _date_values(post, booking):
    return {
        'pickup_date': post.get('pickup_date') or booking.pickup_date.isoformat(),
        'pickup_time': post.get('pickup_time') or booking.pickup_time.strftime('%H:%M'),
        'return_date': post.get('return_date') or booking.return_date.isoformat(),
        'return_time': post.get('return_time') or booking.return_time.strftime('%H:%M'),
    }


ACTION_DONE = {
    'pickup': 'Marked as picked up.',
    'return': 'Marked as returned.',
    'cancel': 'Booking cancelled. Remember to refund any M-Pesa payment by hand.',
    'mark_paid': 'Marked as paid.',
    'change_dates': 'Dates changed. Settle any price difference with the customer.',
    'resend': 'Confirmation email sent with the receipt attached.',
    'note': 'Note added.',
    'relocate': 'Car moved to the return branch.',
}


@staff_page
def booking_detail(request, ref):
    qs = scoped_bookings(request.user).prefetch_related(
        'extras', 'payments', Prefetch('events', queryset=BookingEvent.objects.select_related('user')))
    booking = get_object_or_404(qs, ref=ref)
    dates = _date_values({}, booking)
    preview = date_error = None

    if request.method == 'POST':
        action = request.POST.get('action', '')
        post = request.POST
        user = request.user
        try:
            if action == 'pickup':
                services.mark_picked_up(booking, user)
            elif action == 'return':
                services.mark_returned(booking, user)
            elif action == 'cancel':
                services.cancel_booking(booking, user, post.get('reason'))
            elif action == 'mark_paid':
                services.mark_paid_manually(booking, user, post.get('code'))
            elif action == 'resend':
                services.resend_confirmation(booking, user)
            elif action == 'note':
                services.add_note(booking, user, post.get('note'))
            elif action == 'relocate':
                services.relocate_car(booking, user)
            elif action in ('preview_dates', 'change_dates'):
                dates = _date_values(post, booking)
                start, end = parse_date(dates['pickup_date']), parse_date(dates['return_date'])
                if action == 'preview_dates':
                    try:
                        preview = services.date_change_quote(booking, start, dates['pickup_time'], end,
                                                             dates['return_time'])
                    except QuoteError as exc:
                        date_error = exc.message
                else:
                    services.change_dates(booking, user, start, dates['pickup_time'], end, dates['return_time'])
            else:
                messages.error(request, 'Unknown action.')
                return redirect('dashboard:booking_detail', ref=booking.ref)
        except services.ActionError as exc:
            if action != 'change_dates':
                messages.error(request, str(exc))
                return redirect('dashboard:booking_detail', ref=booking.ref)
            date_error = str(exc)
        else:
            if action != 'preview_dates':
                messages.success(request, ACTION_DONE.get(action, 'Done.'))
                return redirect('dashboard:booking_detail', ref=booking.ref)

    return render(request, 'dashboard/booking_detail.html', _ctx(
        request, nav='bookings', booking=booking, allowed=_allowed(booking), dates=dates, preview=preview,
        date_error=date_error, time_choices=[t.strftime('%H:%M') for t in time_choices()],
        open_dates=bool(preview or date_error),
    ))


@staff_page
def booking_receipt(request, ref):
    """Staff can download the receipt of any paid booking in their branch."""
    booking = get_object_or_404(scoped_bookings(request.user), ref=ref)
    if not booking.is_paid:
        messages.error(request, f'{booking.ref} is not paid, so it has no receipt.')
        return redirect('dashboard:booking_detail', ref=booking.ref)
    response = HttpResponse(build_pdf(booking), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="receipt-{booking.ref}.pdf"'
    return response


# ---------- Calendar ----------

def _lanes(bookings):
    """Puts overlapping bookings of the same car (several units) on separate lines."""
    lanes = []
    placed = []
    for b in sorted(bookings, key=lambda x: (x.pickup_date, x.return_date)):
        for i, last_end in enumerate(lanes):
            if b.pickup_date >= last_end:
                lanes[i] = b.return_date
                placed.append((i, b))
                break
        else:
            lanes.append(b.return_date)
            placed.append((len(lanes) - 1, b))
    return max(len(lanes), 1), placed


@staff_page
def calendar(request):
    today = timezone.localdate()
    try:
        length = int(request.GET.get('days', 14))
    except ValueError:
        length = 14
    length = length if length in CALENDAR_LENGTHS else 14
    start = parse_date(request.GET.get('start')) or today
    end = start + timedelta(days=length)
    viewing = view_location(request)

    cars = scoped_cars(request.user)
    if viewing:
        cars = cars.filter(location=viewing)
    held_cutoff = timezone.now() - timedelta(minutes=settings.BOOKING_HOLD_MINUTES)
    bookings = (Booking.objects.select_related('car').filter(car__in=cars, pickup_date__lt=end, return_date__gt=start)
                .filter(Q(status__in=(Status.PAID, Status.PICKED_UP, Status.COMPLETED))
                        | Q(status=Status.PENDING, payment_requested_at__gte=held_cutoff)))
    by_car = {}
    for b in bookings:
        by_car.setdefault(b.car_id, []).append(b)
    cars = [c for c in cars.order_by('location__display_order', 'name') if c.is_active or c.pk in by_car]

    rows, row = [], 2  # grid row 1 is the day header
    for car in cars:
        lane_count, placed = _lanes(by_car.get(car.pk, []))
        blocks = []
        for lane, b in placed:
            first = max((b.pickup_date - start).days, 0)
            last = min((b.return_date - start).days, length)
            blocks.append({
                'booking': b, 'row': row + lane, 'col': first + 2, 'span': max(last - first, 1),
                'starts_before': b.pickup_date < start, 'ends_after': b.return_date > end,
            })
        rows.append({'car': car, 'row': row, 'lanes': lane_count, 'blocks': blocks})
        row += lane_count

    days = [start + timedelta(days=i) for i in range(length)]
    return render(request, 'dashboard/calendar.html', _ctx(
        request, nav='calendar', rows=rows, days=days, length=length, lengths=CALENDAR_LENGTHS, start=start,
        today=today, prev_start=start - timedelta(days=length), next_start=start + timedelta(days=length),
        last_row=row, day_cells=[(r, i + 2, d) for r in range(2, row) for i, d in enumerate(days)],
    ))
